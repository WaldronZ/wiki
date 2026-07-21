from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..config import AppConfig
from ..db import get_setting

CLAUDE_PROFILES_DIR = Path.home() / ".claude" / "profiles"


class LLMConfigurationError(RuntimeError):
    """Raised when a provider cannot run until the user configures it."""


class LLMGenerationError(RuntimeError):
    """Raised when an LLM provider call fails."""


class LLMProvider(Protocol):
    def generate(self, prompt: str) -> str:
        """Return report markdown for a prepared prompt."""


def summarize_llm_http_error(status_code: int, body: str) -> str:
    message = ""
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            error = parsed.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or "")
            elif isinstance(error, str):
                message = error
    except json.JSONDecodeError:
        message = body.strip()

    normalized = message.lower()
    if status_code == 401:
        return "HTTP 401：API Key 无效或未被当前服务接受，请检查密钥是否粘贴正确。"
    if status_code == 403:
        return "HTTP 403：当前 API Key 没有权限访问该模型或服务。"
    if status_code == 404:
        return "HTTP 404：接口地址或模型路径不存在，请确认 base URL 是否以 /v1 结尾。"
    if "model" in normalized and ("not" in normalized or "不存在" in normalized):
        return f"模型不可用：{message[:180]}"
    if message:
        return f"HTTP {status_code}：{message[:220]}"
    return f"HTTP {status_code}：上游没有返回可读错误正文。"


@dataclass(frozen=True)
class OpenAICompatibleProvider:
    api_key: str
    base_url: str
    model: str
    timeout: int = 900

    def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise LLMConfigurationError("OPENAI_API_KEY is not configured.")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You write rigorous Chinese paper-reading reports from TeX source.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "AutoPaperReader/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                data = json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LLMGenerationError(summarize_llm_http_error(exc.code, body)) from exc
        except urllib.error.URLError as exc:
            raise LLMGenerationError(f"LLM provider request failed: {exc}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise LLMGenerationError(
                f"LLM provider request timed out after {self.timeout} seconds. "
                "深度论文分析会生成较长内容，可以稍后重试，或换一个响应更稳定的模型/网关。"
            ) from exc
        except json.JSONDecodeError as exc:
            preview = body.strip()[:200] if "body" in locals() else ""
            detail = f" Response preview: {preview}" if preview else ""
            raise LLMGenerationError(
                "LLM provider response was not JSON. Check the API base URL, model name, and OpenAI-compatible endpoint."
                + detail
            ) from exc

        try:
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMGenerationError("LLM provider response did not contain message content.") from exc


@dataclass(frozen=True)
class MockProvider:
    markdown: str

    def generate(self, prompt: str) -> str:
        return self.markdown


def list_claude_profiles() -> list[dict[str, str]]:
    """Read available Claude Code profiles from ~/.claude/profiles/*.env."""
    profiles: list[dict[str, str]] = []
    if not CLAUDE_PROFILES_DIR.is_dir():
        return profiles
    for env_file in sorted(CLAUDE_PROFILES_DIR.glob("*.env")):
        name = env_file.stem
        env_vars = _parse_env_file(env_file)
        model = env_vars.get("ANTHROPIC_MODEL", "")
        base_url = env_vars.get("ANTHROPIC_BASE_URL", "")
        profiles.append({
            "id": name,
            "name": name,
            "model": model,
            "base_url": base_url,
        })
    return profiles


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict, ignoring comments and blank lines."""
    result: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return result
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
        if match:
            key = match.group(1)
            value = match.group(2).strip().strip('"').strip("'")
            # Expand $VAR references
            value = re.sub(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?',
                          lambda m: result.get(m.group(1), m.group(0)), value)
            result[key] = value
    return result


@dataclass(frozen=True)
class ClaudeCodeProvider:
    """Call local Claude Code CLI with a selected profile."""
    profile_name: str = ""
    allowed_tools: str = "Bash,Read,Write,WebSearch,WebFetch"

    def generate(self, prompt: str) -> str:
        profiles = list_claude_profiles()
        if not profiles:
            raise LLMConfigurationError(
                "没有找到 Claude Code profiles。请先在 ~/.claude/profiles/ 下创建 .env 文件。"
            )

        # Find the selected profile
        profile = None
        if self.profile_name:
            profile = next((p for p in profiles if p["id"] == self.profile_name), None)
        if not profile:
            profile = profiles[0]  # Default to first profile

        # Build environment with profile vars
        env = os.environ.copy()
        env_file = CLAUDE_PROFILES_DIR / f"{profile['id']}.env"
        if env_file.exists():
            profile_env = _parse_env_file(env_file)
            env.update(profile_env)

        try:
            result = subprocess.run(
                [
                    "claude", "-p", prompt,
                    "--output-format", "text",
                    "--allowedTools", self.allowed_tools,
                    "--max-turns", "30",
                ],
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMGenerationError(
                "Claude Code 执行超时（1小时）。论文分析可能需要更长时间，请重试或换用更简单的任务。"
            ) from exc
        except FileNotFoundError as exc:
            raise LLMConfigurationError(
                "找不到 claude 命令。请确保 Claude Code CLI 已安装并在 PATH 中。"
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip()[:500] if result.stderr else ""
            raise LLMGenerationError(f"Claude Code 执行失败（返回码 {result.returncode}）：{stderr}")

        return result.stdout.strip()


def test_claude_code_connection(profile_name: str = "") -> str:
    """Test Claude Code connection with a simple prompt."""
    provider = ClaudeCodeProvider(profile_name=profile_name)
    try:
        result = provider.generate("回复'连接成功'即可，不要多说。")
        return result or "连接成功，但 Claude Code 返回为空。"
    except (LLMConfigurationError, LLMGenerationError) as exc:
        raise


def build_provider(config: AppConfig, provider_name: str, model: str, *, mock_markdown: str) -> LLMProvider:
    provider = (provider_name or "openai").lower()
    if provider == "mock":
        return MockProvider(mock_markdown)
    if provider == "claude-code":
        return ClaudeCodeProvider(profile_name=model)
    if provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleProvider(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
            model=model or "gpt-4.1",
        )
    raise LLMConfigurationError(f"Unsupported LLM provider: {provider_name}")


def effective_llm_settings(conn, config: AppConfig, *, provider_name: str = "", model: str = "") -> dict[str, str]:
    provider = provider_name or get_setting(conn, "llm_provider", "openai")
    effective_model = model or get_setting(conn, "llm_model", "gpt-4.1")
    api_key = get_setting(conn, "openai_api_key", config.openai_api_key)
    base_url = get_setting(conn, "openai_base_url", config.openai_base_url)
    return {
        "provider": provider,
        "model": effective_model,
        "openai_api_key": api_key,
        "openai_base_url": base_url,
    }


def build_effective_provider(
    settings: dict[str, str],
    *,
    mock_markdown: str,
) -> LLMProvider:
    provider = settings.get("provider", "openai")
    if provider.lower() == "mock":
        return MockProvider(mock_markdown)
    if provider.lower() == "claude-code":
        return ClaudeCodeProvider(profile_name=settings.get("model", ""))
    if provider.lower() in {"openai", "openai-compatible"}:
        return OpenAICompatibleProvider(
            api_key=settings.get("openai_api_key", ""),
            base_url=settings.get("openai_base_url", "https://api.openai.com/v1"),
            model=settings.get("model", "gpt-4.1"),
        )
    raise LLMConfigurationError(f"Unsupported LLM provider: {provider}")


def test_llm_connection(settings: dict[str, str]) -> str:
    provider = settings.get("provider", "openai").lower()
    if provider == "mock":
        return "Mock provider is available."
    if provider == "claude-code":
        return test_claude_code_connection(profile_name=settings.get("model", ""))
    if provider not in {"openai", "openai-compatible"}:
        raise LLMConfigurationError(f"Unsupported LLM provider: {settings.get('provider', provider)}")

    api_key = settings.get("openai_api_key", "").strip()
    base_url = settings.get("openai_base_url", "https://api.openai.com/v1").strip()
    model = settings.get("model", "gpt-4.1").strip()
    if not api_key:
        raise LLMConfigurationError("API Key 为空，请先填写或保存 API Key。")
    if not base_url:
        raise LLMConfigurationError("接口地址为空，请填写 OpenAI 兼容 base URL。")
    if not model:
        raise LLMConfigurationError("报告模型为空，请填写模型名。")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a connection test endpoint."},
            {"role": "user", "content": "Reply with exactly: success"},
        ],
        "temperature": 0,
        "max_tokens": 8,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AutoPaperReader/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            data = json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        summary = summarize_llm_http_error(exc.code, body)
        detail = body[:2000] if body else "上游没有返回错误正文"
        raise LLMGenerationError(f"{summary}\n\n原始响应：\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMGenerationError(f"网络请求失败：{exc}") from exc
    except json.JSONDecodeError as exc:
        preview = body.strip()[:300] if "body" in locals() else ""
        raise LLMGenerationError(f"上游返回的不是 JSON。请检查接口地址是否应以 /v1 结尾。返回预览：{preview or '空响应'}") from exc

    try:
        content = str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMGenerationError("连接成功但响应格式不是 chat/completions 兼容格式。") from exc
    return content or "连接成功，但模型返回为空。"
