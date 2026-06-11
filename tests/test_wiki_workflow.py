from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


REPORT_A = """---
slug: 2601.00001-alpha-paper
title: Alpha Paper
title_zh: Alpha 论文
title_en: Alpha Paper
arxiv_id: "2601.00001"
year: 2026
authors:
  - Ada Lovelace
domains:
  - LLM Systems
tracks:
  - Inference Acceleration
problems:
  - Batch Scheduling
topics:
  - LLM Serving
methods:
  - speculative decoding
research_line: LLM Serving
line_role: foundation
status: read
reading_stage: deep_read
importance: 5
confidence: 4
reproducibility: 3
has_code: true
---

# Alpha 论文

## 1. 基本情况

Alpha report body.
"""


REPORT_B = """---
slug: 2501.00002-beta-paper
title: Beta Paper
title_zh: Beta 论文
title_en: Beta Paper
arxiv_id: "2501.00002"
year: 2025
authors:
  - Grace Hopper
domains:
  - LLM Systems
tracks:
  - Attention Kernels
problems:
  - Efficient Exact Attention
topics:
  - Attention Kernels
methods:
  - tiling
research_line: Attention Kernels
line_role: system
status: read
reading_stage: skimmed
review_stage: fresh
next_review: 2026-06-30
importance: 4
confidence: 5
reproducibility: 4
has_code: false
---

# Beta 论文

## 1. 基本情况

Beta report body.
"""


class WikiWorkflowTest(unittest.TestCase):
    def run_cmd(self, *args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args],
            cwd=cwd,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def make_report_dir(self, tmp: Path) -> Path:
        report_dir = tmp / "docs"
        report_dir.mkdir()
        for slug, text in {
            "2601.00001-alpha-paper": REPORT_A,
            "2501.00002-beta-paper": REPORT_B,
        }.items():
            (report_dir / f"{slug}.md").write_text(text, encoding="utf-8")
            (report_dir / f"{slug}.html").write_text(
                f"<!doctype html><title>{slug}</title><h1>{slug}</h1>",
                encoding="utf-8",
            )
        return report_dir

    def test_build_validate_and_apply_review_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            report_dir = self.make_report_dir(Path(tmp_name))

            self.run_cmd("scripts/build_wiki.py", str(report_dir))
            self.run_cmd("scripts/build_wiki.py", str(report_dir), "--check")
            self.run_cmd("scripts/validate_wiki.py", str(report_dir))

            generated = {
                "index.html",
                "library.html",
                "review.html",
                "dashboard.html",
                "tags.html",
                "papers.json",
                "search_index.json",
                "quality.json",
                "review.json",
                "lines/index.html",
            }
            for relative in generated:
                self.assertTrue((report_dir / relative).exists(), relative)

            papers = json.loads((report_dir / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(papers["count"], 2)
            self.assertIn("LLM Serving", papers["taxonomy"]["research_lines"])

            review = json.loads((report_dir / "review.json").read_text(encoding="utf-8"))
            self.assertEqual(review["count"], 2)
            self.assertEqual(review["queues"]["needs_plan"], ["2601.00001-alpha-paper"])
            self.assertEqual(review["queues"]["scheduled"], ["2501.00002-beta-paper"])

            dry = self.run_cmd("scripts/apply_review_plan.py", str(report_dir))
            self.assertIn("DRY  2601.00001-alpha-paper", dry.stdout)
            self.assertIn("OK   2501.00002-beta-paper", dry.stdout)
            self.assertNotIn("next_review:", (report_dir / "2601.00001-alpha-paper.md").read_text(encoding="utf-8"))

            self.run_cmd("scripts/apply_review_plan.py", str(report_dir), "--write")
            updated = (report_dir / "2601.00001-alpha-paper.md").read_text(encoding="utf-8")
            self.assertIn("review_stage: fresh", updated)
            self.assertIn("next_review:", updated)

            self.run_cmd("scripts/build_wiki.py", str(report_dir))
            self.run_cmd("scripts/validate_wiki.py", str(report_dir))
            review_after = json.loads((report_dir / "review.json").read_text(encoding="utf-8"))
            self.assertEqual(review_after["queues"]["needs_plan"], [])


if __name__ == "__main__":
    unittest.main()
