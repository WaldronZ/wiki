from __future__ import annotations

import gzip
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path


def download_eprint(arxiv_id: str, target_path: Path, *, timeout: int = 60) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    request = urllib.request.Request(url, headers={"User-Agent": "AutoPaperReader/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        with target_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    return target_path


def download_pdf(pdf_url: str, target_path: Path, *, timeout: int = 60) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(pdf_url, headers={"User-Agent": "AutoPaperReader/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        with target_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    header = target_path.read_bytes()[:8]
    if not header.startswith(b"%PDF"):
        try:
            target_path.unlink()
        except OSError:
            pass
        raise ValueError(f"Downloaded file is not a PDF: {pdf_url}")
    return target_path


def _safe_child(base: Path, name: str) -> Path:
    target = (base / name).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise ValueError(f"Archive member escapes target directory: {name}")
    return target


def _extract_tar(package_path: Path, extract_dir: Path) -> None:
    with tarfile.open(package_path) as archive:
        for member in archive.getmembers():
            _safe_child(extract_dir, member.name)
        archive.extractall(extract_dir, filter="data")


def _extract_zip(package_path: Path, extract_dir: Path) -> None:
    with zipfile.ZipFile(package_path) as archive:
        for name in archive.namelist():
            _safe_child(extract_dir, name)
        archive.extractall(extract_dir)


def extract_source_package(package_path: Path, extract_dir: Path) -> str:
    extract_dir.mkdir(parents=True, exist_ok=True)
    if tarfile.is_tarfile(package_path):
        _extract_tar(package_path, extract_dir)
        return "tar"
    if zipfile.is_zipfile(package_path):
        _extract_zip(package_path, extract_dir)
        return "zip"

    header = package_path.read_bytes()[:8]
    if header.startswith(b"%PDF"):
        shutil.copy2(package_path, extract_dir / "paper.pdf")
        return "pdf"
    if header.startswith(b"\x1f\x8b"):
        output_path = extract_dir / "main.tex"
        with gzip.open(package_path, "rb") as source, output_path.open("wb") as target:
            shutil.copyfileobj(source, target)
        return "gzip"

    raise ValueError(f"Unsupported arXiv source package format: {package_path}")


def find_main_tex(source_dir: Path) -> Path | None:
    candidates = sorted(source_dir.rglob("*.tex"))
    scored: list[tuple[int, Path]] = []
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        score = 0
        if "\\documentclass" in text:
            score += 3
        if "\\begin{document}" in text:
            score += 3
        if "\\input" in text or "\\include" in text:
            score += 1
        if path.name.lower() in {"main.tex", "paper.tex", "article.tex"}:
            score += 1
        if score:
            scored.append((score, path))
    if scored:
        scored.sort(key=lambda item: (-item[0], len(str(item[1]))))
        return scored[0][1]
    if len(candidates) == 1:
        return candidates[0]
    return None
