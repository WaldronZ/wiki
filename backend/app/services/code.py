from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path


REPO_RE = re.compile(
    r"https?://(?:www\.)?(github\.com|gitlab\.com)/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CodeDiscovery:
    url: str = ""
    cloned: bool = False
    path: str = ""
    error: str = ""


@dataclass(frozen=True)
class CodeSummary:
    url: str
    cloned: bool
    path: str
    error: str
    files: list[str]
    languages: dict[str, int]
    has_readme: bool
    license_files: list[str]
    entrypoints: list[str]


def normalize_repo_url(url: str) -> str:
    clean = url.strip().rstrip(".,);]}>'\"")
    clean = re.sub(r"/(?:tree|blob|issues|pull|releases|commit)/.*$", "", clean)
    clean = re.sub(r"\.git$", "", clean)
    return clean


def find_code_url(*texts: str) -> str:
    for text in texts:
        if not text:
            continue
        match = REPO_RE.search(text)
        if match:
            return normalize_repo_url(match.group(0))
    return ""


def read_tex_for_code_scan(source_dir: Path, *, max_files: int = 24, max_chars: int = 120000) -> str:
    pieces: list[str] = []
    total = 0
    for path in sorted(source_dir.rglob("*.tex"))[:max_files]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        pieces.append(text[:remaining])
        total += min(len(text), remaining)
    return "\n".join(pieces)


def clone_code_repo(repo_url: str, target_dir: Path) -> CodeDiscovery:
    if not repo_url:
        return CodeDiscovery()
    if target_dir.exists():
        if any(target_dir.iterdir()):
            return CodeDiscovery(url=repo_url, cloned=True, path=str(target_dir))
        shutil.rmtree(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(target_dir)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return CodeDiscovery(
            url=repo_url,
            cloned=False,
            path=str(target_dir),
            error=(result.stderr or result.stdout).strip(),
        )
    return CodeDiscovery(url=repo_url, cloned=True, path=str(target_dir))


def discover_and_clone_code(
    *,
    abstract: str,
    source_dir: Path,
    target_dir: Path,
    extra_text: str = "",
) -> CodeDiscovery:
    tex_text = read_tex_for_code_scan(source_dir)
    repo_url = find_code_url(abstract, extra_text, tex_text)
    if not repo_url:
        return CodeDiscovery()
    return clone_code_repo(repo_url, target_dir)


def summarize_code_repo(discovery: CodeDiscovery, *, max_files: int = 80) -> CodeSummary:
    repo_path = Path(discovery.path) if discovery.path else Path()
    if not discovery.cloned or not repo_path.exists():
        return CodeSummary(
            url=discovery.url,
            cloned=discovery.cloned,
            path=discovery.path,
            error=discovery.error,
            files=[],
            languages={},
            has_readme=False,
            license_files=[],
            entrypoints=[],
        )

    ignored_dirs = {".git", "__pycache__", ".venv", "node_modules", "dist", "build"}
    files: list[str] = []
    languages: dict[str, int] = {}
    license_files: list[str] = []
    entrypoints: list[str] = []
    has_readme = False
    entry_names = {
        "train.py",
        "eval.py",
        "inference.py",
        "generate.py",
        "main.py",
        "run.py",
        "requirements.txt",
        "pyproject.toml",
        "environment.yml",
        "package.json",
    }
    for path in sorted(repo_path.rglob("*")):
        if len(files) >= max_files:
            break
        if not path.is_file():
            continue
        rel_path = path.relative_to(repo_path)
        if any(part in ignored_dirs for part in rel_path.parts):
            continue
        rel = rel_path.as_posix()
        files.append(rel)
        suffix = path.suffix.lower() or "[no extension]"
        languages[suffix] = languages.get(suffix, 0) + 1
        lower_name = path.name.lower()
        if lower_name.startswith("readme"):
            has_readme = True
        if lower_name.startswith("license") or lower_name in {"copying", "notice"}:
            license_files.append(rel)
        if lower_name in entry_names or rel.startswith(("scripts/", "examples/")):
            entrypoints.append(rel)

    return CodeSummary(
        url=discovery.url,
        cloned=discovery.cloned,
        path=discovery.path,
        error=discovery.error,
        files=files,
        languages=languages,
        has_readme=has_readme,
        license_files=license_files[:12],
        entrypoints=entrypoints[:16],
    )


def build_code_observation(summary: CodeSummary) -> str:
    if not summary.url:
        return ""
    lines: list[str] = [
        "## 10. 代码实现观察",
        "",
        "### 10.1 仓库基本情况",
        "",
        f"- 代码仓库：{summary.url}",
        f"- 本地路径：{summary.path or '未克隆'}",
    ]
    if not summary.cloned:
        lines.extend(
            [
                "- 克隆状态：未成功克隆，论文主体报告仍可使用。",
                f"- 失败原因：{summary.error or '未提供'}",
                "",
                "### 10.2 方法实现核对",
                "",
                "- 实现与论文是否一致：未能检查源码。",
                "- 论文未提到的工程 trick：未能检查源码。",
                "",
                "### 10.3 真实算力规模",
                "",
                "- 未能从代码中确认训练或推理资源。",
                "",
                "### 10.4 可复现性评价",
                "",
                "- 未能检查 README、依赖、license 与运行脚本。",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    language_bits = ", ".join(
        f"{suffix}: {count}" for suffix, count in sorted(summary.languages.items(), key=lambda item: (-item[1], item[0]))[:8]
    )
    lines.extend(
        [
            "- 克隆状态：已浅克隆。",
            f"- README：{'存在' if summary.has_readme else '未发现'}",
            f"- License：{', '.join(summary.license_files) if summary.license_files else '未发现明确 license 文件'}",
            f"- 文件类型分布：{language_bits or '未统计到源码文件'}",
            f"- 可能的训练/推理入口：{', '.join(summary.entrypoints) if summary.entrypoints else '未从常见文件名中识别'}",
            f"- 代表性文件：{', '.join(summary.files[:20]) if summary.files else '未发现'}",
            "",
            "### 10.2 方法实现核对",
            "",
            "- 实现与论文是否一致：需要后续 code observation 深读确认。",
            "- 论文未提到的工程 trick：需要后续 code observation 深读确认。",
            "",
            "### 10.3 真实算力规模",
            "",
            "- 真实算力规模：需要从配置、脚本和 README 进一步确认。",
            "",
            "### 10.4 可复现性评价",
            "",
            "- License 与可复现性：以上 license/README 信号可作为初筛，仍需人工或 LLM 复核。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def read_code_analyst_contract() -> str:
    path = project_root() / ".Codex" / "agents" / "code-analyst.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    return str(data.get("developer_instructions") or "").strip()


def _is_text_like(path: Path) -> bool:
    if path.name.lower().startswith(("readme", "license", "notice", "copying")):
        return True
    return path.suffix.lower() in {
        ".py",
        ".md",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".txt",
        ".sh",
        ".cfg",
        ".ini",
        ".cu",
        ".cpp",
        ".cc",
        ".cuh",
        ".h",
        ".hpp",
        ".rs",
        ".js",
        ".ts",
    }


def build_code_context(
    code_dir: Path,
    *,
    max_files: int = 36,
    max_chars: int = 120000,
    max_chars_per_file: int = 14000,
) -> str:
    if not code_dir.exists():
        return ""
    ignored_dirs = {".git", "__pycache__", ".venv", "node_modules", "dist", "build", ".mypy_cache"}
    priority_names = {
        "readme.md": 0,
        "readme": 0,
        "license": 0,
        "license.md": 0,
        "pyproject.toml": 1,
        "requirements.txt": 1,
        "environment.yml": 1,
        "setup.py": 1,
        "dockerfile": 1,
        "train.py": 2,
        "eval.py": 2,
        "inference.py": 2,
        "generate.py": 2,
        "main.py": 2,
        "run.py": 2,
    }

    candidates: list[tuple[int, str, Path]] = []
    for path in code_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(code_dir)
        if any(part in ignored_dirs for part in rel.parts):
            continue
        if not _is_text_like(path):
            continue
        rel_text = rel.as_posix()
        lower = path.name.lower()
        priority = priority_names.get(lower, 4)
        if rel_text.startswith(("scripts/", "configs/", "config/", "examples/", "src/")):
            priority = min(priority, 3)
        candidates.append((priority, rel_text, path))

    chunks: list[str] = []
    remaining = max_chars
    for _, rel, path in sorted(candidates)[:max_files]:
        if remaining <= 0:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text.strip():
            continue
        take = min(len(text), max_chars_per_file, remaining)
        chunks.append(f"# ===== FILE: {rel} =====\n{text[:take]}")
        remaining -= take
    return "\n\n".join(chunks)


def validate_code_observation(observation: str) -> list[str]:
    errors: list[str] = []
    if "## 10. 代码实现观察" not in observation:
        errors.append("missing section: ## 10. 代码实现观察")
    for heading in (
        "### 10.1 仓库基本情况",
        "### 10.2 方法实现核对",
        "### 10.3 真实算力规模",
        "### 10.4 可复现性评价",
    ):
        if heading not in observation:
            errors.append(f"missing subsection: {heading}")
    return errors


def build_code_analyst_prompt(
    *,
    slug: str,
    report_markdown: str,
    summary: CodeSummary,
    code_context: str,
) -> str:
    contract = read_code_analyst_contract()
    summary_text = "\n".join(
        [
            f"- repository: {summary.url or 'none'}",
            f"- cloned: {summary.cloned}",
            f"- local_path: {summary.path or ''}",
            f"- clone_error: {summary.error or ''}",
            f"- has_readme: {summary.has_readme}",
            f"- license_files: {', '.join(summary.license_files) if summary.license_files else 'none'}",
            f"- entrypoints: {', '.join(summary.entrypoints) if summary.entrypoints else 'none'}",
            f"- representative_files: {', '.join(summary.files[:60]) if summary.files else 'none'}",
        ]
    )
    return f"""
你现在严格扮演 AutoPaperReader 的 `code-analyst` 子 agent。你的任务不是重写报告，而是在已有报告基础上补充或修订代码实现观察。

【code-analyst 契约】
```text
{contract}
```

【输出要求】
- 只输出完整的 `## 10. 代码实现观察` 小节。
- 必须包含 `### 10.1` 到 `### 10.4` 四个子小节。
- 中文为主，关键术语保留英文。
- 找不到证据时写“未在代码中确认”，不要编造。
- 如果发现原报告事实错误，在 `## 10. 代码实现观察` 中明确写出“需要回修的方法/实验描述”，后续 editor 会据此处理。

slug:
{slug}

代码仓库摘要：
```text
{summary_text}
```

已有阅读报告：
```markdown
{report_markdown}
```

代码上下文（按 README/config/入口/源码优先级截断）：
```text
{code_context or "代码上下文不可用。"}
```
""".strip()


def build_code_revision_prompt(
    *,
    slug: str,
    report_markdown: str,
    observation: str,
    summary: CodeSummary,
    code_context: str,
) -> str:
    contract = read_code_analyst_contract()
    return f"""
你现在继续扮演 AutoPaperReader 的 `code-analyst` 子 agent。你已经形成了代码观察小节，现在要按原契约“回写报告”。

【code-analyst 原契约】
```text
{contract}
```

【任务】
- 返回一份完整 Markdown 报告，不要输出解释。
- 保留原报告 1-9 章的事实和写作风格。
- 如果代码观察指出「需要回修的方法/实验描述」或发现明显事实差异，请直接修订对应的 `## 8. 方法细节` / `## 9. 实验` 文字，并加上 `（已据代码核对修订）`。
- 在报告末尾包含完整 `## 10. 代码实现观察`，且必须包含 `### 10.1` 到 `### 10.4`。
- 不要删除 YAML frontmatter、图片、公式、图解或已有章节。
- 找不到代码证据时保留原文，只在第 10 节说明“未在代码中确认”。

slug:
{slug}

代码仓库：
- url: {summary.url or "none"}
- local_path: {summary.path or "none"}

代码观察小节：
```markdown
{observation}
```

已有阅读报告：
```markdown
{report_markdown}
```

代码上下文：
```text
{code_context or "代码上下文不可用。"}
```
""".strip()
