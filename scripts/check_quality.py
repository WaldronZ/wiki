#!/usr/bin/env python3
"""Run the local quality gate used by CI.

This intentionally stays standard-library only so contributors can validate a
fresh clone without installing project dependencies.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_SCRIPTS = [
    "scripts/build_wiki.py",
    "scripts/render_report_html.py",
    "scripts/validate_wiki.py",
    "scripts/apply_review_plan.py",
    "scripts/apply_library_metadata.py",
    "scripts/export_library_csv.py",
    "scripts/check_quality.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AutoPaperReader wiki quality checks.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default="docs",
        help="Directory containing generated wiki files and paper reports.",
    )
    return parser.parse_args()


def run_step(label: str, command: list[str]) -> None:
    print(f"\n==> {label}", flush=True)
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    args = parse_args()
    report_dir = args.report_dir
    node = shutil.which("node")
    if not node:
        print("ERROR: node is required for scripts/check_wiki_js.js", file=sys.stderr, flush=True)
        return 127

    steps = [
        ("Compile Python scripts", [sys.executable, "-m", "py_compile", *PYTHON_SCRIPTS]),
        ("Check generated wiki artifacts", [sys.executable, "scripts/build_wiki.py", report_dir, "--check"]),
        (
            "Validate wiki metadata and links",
            [sys.executable, "scripts/validate_wiki.py", report_dir, "--strict-taxonomy"],
        ),
        ("Check inline wiki scripts", [node, "scripts/check_wiki_js.js", report_dir]),
        ("Run workflow tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
    ]

    for label, command in steps:
        run_step(label, command)

    print("\nQuality gate passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
