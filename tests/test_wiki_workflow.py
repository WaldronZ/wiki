from __future__ import annotations

import json
import csv
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
    def run_cmd(
        self,
        *args: str,
        cwd: Path = ROOT,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args],
            cwd=cwd,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def make_report_dir(self, tmp: Path) -> Path:
        report_dir = tmp / "docs"
        report_dir.mkdir()
        guides_dir = report_dir / "guides"
        guides_dir.mkdir()
        (guides_dir / "taxonomy.json").write_text(
            json.dumps(
                {
                    "label_aliases": {
                        "batch scheduling": "Request Scheduling",
                        "llm serving": "LLM Serving",
                    },
                    "role_order": ["foundation", "system", "followup"],
                    "status_values": ["unread", "triaged", "reading", "read", "archived"],
                    "reading_stage_values": ["skimmed", "deep_read", "code_checked"],
                    "review_stage_values": ["fresh", "due", "reviewed"],
                }
            ),
            encoding="utf-8",
        )
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
                "taxonomy.html",
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
            self.assertIn("Request Scheduling", papers["taxonomy"]["problems"])
            self.assertIn("triaged", papers["taxonomy"]["statuses"])
            self.assertEqual(papers["taxonomy"]["statuses"]["triaged"], 0)
            index_html = (report_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn('<option value="triaged">triaged (0)</option>', index_html)

            review = json.loads((report_dir / "review.json").read_text(encoding="utf-8"))
            self.assertEqual(review["count"], 2)
            self.assertEqual(review["queues"]["needs_plan"], ["2601.00001-alpha-paper"])
            self.assertEqual(review["queues"]["scheduled"], ["2501.00002-beta-paper"])

            csv_path = report_dir / "library.csv"
            self.run_cmd("scripts/export_library_csv.py", str(report_dir), "--output", str(csv_path))
            rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))
            self.assertEqual(len(rows), 2)
            row_by_slug = {row["slug"]: row for row in rows}
            self.assertEqual(row_by_slug["2601.00001-alpha-paper"]["review_state"], "needs_plan")
            self.assertEqual(row_by_slug["2501.00002-beta-paper"]["review_state"], "scheduled")
            self.assertTrue(row_by_slug["2601.00001-alpha-paper"]["suggested_next_review"])
            self.assertTrue(row_by_slug["2601.00001-alpha-paper"]["quality_score"])

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

    def test_invalid_taxonomy_config_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            report_dir = self.make_report_dir(Path(tmp_name))
            self.run_cmd("scripts/build_wiki.py", str(report_dir))

            (report_dir / "guides" / "taxonomy.json").write_text(
                json.dumps(
                    {
                        "label_aliases": {"": "Broken", "ok": ""},
                        "role_order": ["foundation", "foundation", ""],
                        "status_values": "read",
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_cmd("scripts/validate_wiki.py", str(report_dir), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("guides/taxonomy.json", result.stderr)
            self.assertIn("duplicate value", result.stderr)
            self.assertIn("status_values must be a list", result.stderr)


if __name__ == "__main__":
    unittest.main()
