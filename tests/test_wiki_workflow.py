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
  - KV-cache
  - KV cache
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
                    "status_values": ["unread", "read"],
                    "active_status_workflow": "research",
                    "status_workflows": {
                        "simple": {
                            "status_values": ["unread", "read", "archived"],
                            "reading_stage_values": ["skimmed", "deep_read"],
                            "review_stage_values": ["fresh", "reviewed"],
                        },
                        "research": {
                            "status_values": ["unread", "triaged", "reading", "read", "archived"],
                            "reading_stage_values": ["skimmed", "deep_read", "code_checked"],
                            "review_stage_values": ["fresh", "due", "reviewed"],
                        },
                    },
                    "shared_views": [
                        {
                            "name": "重点队列",
                            "page": "all",
                            "state": {"importance": "5", "sort": "importance"},
                        },
                        {
                            "name": "Kernel 方向",
                            "page": "library",
                            "state": {"track": "Attention Kernels", "sort": "year"},
                        },
                    ],
                    "research_line_owners": {
                        "LLM Serving": {
                            "owner": "serving-owner",
                            "team": "systems",
                            "cadence": "weekly",
                            "note": "Review serving and scheduling reports.",
                        },
                        "Attention Kernels": {
                            "owner": "kernel-owner",
                            "team": "kernels",
                            "cadence": "monthly",
                        },
                    },
                    "label_definitions": {
                        "domains": {
                            "LLM Systems": {
                                "description": "System papers about inference, serving, and kernels.",
                                "owner": "systems-owner",
                                "status": "active",
                            }
                        },
                        "topics": {
                            "KV Cache": {
                                "description": "Key/value cache layout, reuse, and serving behavior.",
                                "owner": "cache-owner",
                                "status": "watch",
                            }
                        },
                        "status": {
                            "read": {
                                "description": "Report is stable enough for reuse.",
                                "owner": "workflow-owner",
                                "status": "active",
                            }
                        },
                        "reading_stage": {
                            "deep_read": {
                                "description": "Detailed analysis pass.",
                                "owner": "workflow-owner",
                                "status": "active",
                            }
                        },
                    },
                    "governance_policy": {
                        "taxonomy_load": {
                            "min_structure_labels": 3,
                            "min_tags": 5,
                            "max_tags": 10,
                            "max_methods": 8,
                        },
                        "taxonomy_actions": {
                            "singleton_max_count": 1,
                            "watch_share": 0.4,
                            "watch_min_count": 4,
                            "split_share": 0.6,
                            "split_min_count": 5,
                        },
                        "taxonomy_balance": {
                            "high_score_below": 45,
                            "medium_score_below": 70,
                            "singleton_medium_count": 3,
                            "unused_medium_count": 3,
                        },
                        "coverage": {
                            "high_score_below": 70,
                            "medium_score_below": 90,
                            "missing_high_min": 2,
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        (guides_dir / "metadata.schema.json").write_text(
            (ROOT / "docs" / "guides" / "metadata.schema.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (guides_dir / "inbox.schema.json").write_text(
            (ROOT / "docs" / "guides" / "inbox.schema.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (guides_dir / "report.template.md").write_text(
            (ROOT / "docs" / "guides" / "report.template.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (guides_dir / "taxonomy.schema.json").write_text(
            (ROOT / "docs" / "guides" / "taxonomy.schema.json").read_text(encoding="utf-8"),
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
        (report_dir / "inbox.csv").write_text(
            "title,link,status,priority,tags,note\n"
            "Gamma Paper,https://arxiv.org/abs/2602.00003,queued,high,LLM Serving;Batching,候选论文\n"
            "Alpha Duplicate,https://arxiv.org/abs/2601.00001,queued,normal,Duplicate,已读论文\n",
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
                "board.html",
                "workflow.html",
                "status.html",
                "views.html",
                "batch.html",
                "pivot.html",
                "compare.html",
                "taxonomy_map.html",
                "clusters.html",
                "roadmap.html",
                "scale.html",
                "ownership.html",
                "routing.html",
                "onboarding.html",
                "catalog.html",
                "intake.html",
                "inbox.html",
                "dedupe.html",
                "registry.html",
                "quality.html",
                "review.html",
                "freshness.html",
                "dashboard.html",
                "release.html",
                "command.html",
                "snapshot.html",
                "actions.html",
                "collections.html",
                "balance.html",
                "coverage.html",
                "facets.html",
                "related.html",
                "taxonomy.html",
                "timeline.html",
                "matrix.html",
                "gaps.html",
                "tags.html",
                "papers.json",
                "search_index.json",
                "stats.json",
                "inbox.json",
                "quality.json",
                "review.json",
                "freshness.json",
                "taxonomy_actions.json",
                "actions.json",
                "command.json",
                "workflow.json",
                "status.json",
                "views.json",
                "batch.json",
                "collections.json",
                "coverage.json",
                "gaps.json",
                "pivot.json",
                "compare.json",
                "taxonomy_map.json",
                "clusters.json",
                "roadmap.json",
                "scale.json",
                "ownership.json",
                "routing.json",
                "onboarding.json",
                "catalog.json",
                "intake.json",
                "dedupe.json",
                "registry.json",
                "snapshot.json",
                "manifest.json",
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
            self.assertEqual(
                papers["controls"]["status"],
                ["unread", "triaged", "reading", "read", "archived"],
            )
            self.assertEqual(papers["controls"]["active_status_workflow"], "research")
            self.assertIn("simple", papers["controls"]["status_workflows"])
            self.assertEqual(
                papers["controls"]["status_workflows"]["research"]["status_values"],
                ["unread", "triaged", "reading", "read", "archived"],
            )
            self.assertEqual(papers["controls"]["reading_stage"], ["skimmed", "deep_read", "code_checked"])
            index_html = (report_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn('<option value="triaged">triaged (0)</option>', index_html)
            self.assertIn('"shared_views": [{"name": "重点队列"', index_html)
            self.assertIn('id="copySharedView"', index_html)
            self.assertIn('id="copyCurrentLink"', index_html)
            self.assertIn("currentViewUrl", index_html)
            self.assertIn('id="exportSavedViews"', index_html)
            self.assertIn('id="importSavedViews"', index_html)
            self.assertIn("index_saved_views.json", index_html)
            self.assertIn("normalizeSavedViews", index_html)
            self.assertIn('sharedViewPayload("index")', index_html)
            self.assertIn('id="statusWorkflow"', index_html)
            self.assertIn("const statusWorkflows =", index_html)
            self.assertIn("applyStatusWorkflow", index_html)
            self.assertIn("workflowValuesFor", index_html)
            self.assertIn('["workflow", statusWorkflow]', index_html)
            self.assertIn("打开命令中心", index_html)
            self.assertIn("按场景进入", index_html)
            self.assertIn("Daily Reading", index_html)
            self.assertIn("Paper Intake", index_html)
            self.assertIn("Taxonomy Governance", index_html)
            self.assertIn("推荐下一步", index_html)
            self.assertIn("Command JSON", index_html)
            self.assertIn('id="quickOpen"', index_html)
            self.assertIn("快速跳转", index_html)
            self.assertIn("const quickEntries =", index_html)
            self.assertIn('"kind": "paper"', index_html)
            self.assertIn("View: 重点队列", index_html)
            self.assertIn("View: Kernel 方向", index_html)
            self.assertIn("Playbook: Release readiness", index_html)
            self.assertIn('"href": "actions.html"', index_html)
            self.assertIn('"href": "workflow.html"', index_html)
            self.assertIn('"href": "status.html"', index_html)
            self.assertIn('"href": "batch.html"', index_html)
            self.assertIn('"href": "pivot.html"', index_html)
            self.assertIn('"href": "compare.html"', index_html)
            self.assertIn('"href": "taxonomy_map.html"', index_html)
            self.assertIn('"href": "clusters.html"', index_html)
            self.assertIn('"href": "roadmap.html"', index_html)
            self.assertIn('"href": "scale.html"', index_html)
            self.assertIn('"href": "ownership.html"', index_html)
            self.assertIn('"href": "routing.html"', index_html)
            self.assertIn('"href": "onboarding.html"', index_html)
            self.assertIn('"href": "catalog.html"', index_html)
            self.assertIn('"href": "intake.html"', index_html)
            self.assertIn('"href": "dedupe.html"', index_html)
            self.assertIn('"href": "registry.html"', index_html)
            self.assertIn('"href": "balance.html"', index_html)
            self.assertIn('"href": "coverage.html"', index_html)
            self.assertIn("Data: manifest.json", index_html)
            self.assertIn("Data: workflow.json", index_html)
            self.assertIn("Data: status.json", index_html)
            self.assertIn("Data: batch.json", index_html)
            self.assertIn("Data: pivot.json", index_html)
            self.assertIn("Data: compare.json", index_html)
            self.assertIn("Data: taxonomy_map.json", index_html)
            self.assertIn("Data: clusters.json", index_html)
            self.assertIn("Data: roadmap.json", index_html)
            self.assertIn("Data: scale.json", index_html)
            self.assertIn("Data: ownership.json", index_html)
            self.assertIn("Data: routing.json", index_html)
            self.assertIn("Data: onboarding.json", index_html)
            self.assertIn("Data: catalog.json", index_html)
            self.assertIn("Data: intake.json", index_html)
            self.assertIn("Data: dedupe.json", index_html)
            self.assertIn("Data: registry.json", index_html)
            self.assertIn("Data: snapshot.json", index_html)
            self.assertIn('"href": "snapshot.html"', index_html)
            self.assertIn("Command: Export taxonomy balance project tasks", index_html)
            self.assertIn("export_taxonomy_balance.py", index_html)
            library_html = (report_dir / "library.html").read_text(encoding="utf-8")
            self.assertIn('"shared_views": [{"name": "重点队列"', library_html)
            self.assertIn("Kernel 方向", library_html)
            self.assertIn('id="copySharedView"', library_html)
            self.assertIn('id="copyCurrentLink"', library_html)
            self.assertIn("currentViewUrl", library_html)
            self.assertIn('id="exportSavedViews"', library_html)
            self.assertIn('id="importSavedViews"', library_html)
            self.assertIn("library_saved_views.json", library_html)
            self.assertIn("normalizeSavedViews", library_html)
            self.assertIn('sharedViewPayload("library")', library_html)
            self.assertIn('id="statusWorkflow"', library_html)
            self.assertIn('id="review"', library_html)
            self.assertIn('["review", review]', library_html)
            self.assertIn("matchesReviewQueue", library_html)
            self.assertIn("const statusWorkflows =", library_html)
            self.assertIn("applyStatusWorkflow", library_html)
            self.assertIn("workflowValuesFor", library_html)
            self.assertIn("reading_stage_values", library_html)
            self.assertIn("review_stage_values", library_html)
            self.assertIn('["workflow", statusWorkflow]', library_html)
            self.assertIn('id="bulkStatus"', library_html)
            self.assertIn('id="bulkStage"', library_html)
            self.assertIn('id="bulkReviewStage"', library_html)
            self.assertIn('id="bulkImportance"', library_html)
            self.assertIn('id="bulkListMode"', library_html)
            self.assertIn("_list_mode", library_html)
            self.assertIn("listPatchFields", library_html)
            self.assertIn('id="activeFilters"', library_html)
            self.assertIn("renderActiveFilters", library_html)
            self.assertIn("clearActiveFilter", library_html)
            self.assertIn('id="libraryInsights"', library_html)
            self.assertIn('id="insightReviewGap"', library_html)
            self.assertIn('id="insightTopics"', library_html)
            self.assertIn('id="insightMethods"', library_html)
            self.assertIn("countTokens", library_html)
            self.assertIn("updateLibraryInsights", library_html)
            self.assertIn("data-next-review=", library_html)
            self.assertIn('id="topic"', library_html)
            self.assertIn('id="method"', library_html)
            self.assertIn("data-topics=", library_html)
            self.assertIn("data-methods=", library_html)
            self.assertIn('id="bulkResearchLine"', library_html)
            self.assertIn('id="bulkDomains"', library_html)
            self.assertIn('id="bulkMethods"', library_html)
            self.assertIn('id="selectFiltered"', library_html)
            self.assertIn("currentRankedRows.forEach", library_html)
            self.assertIn("批量分类字段", library_html)
            self.assertIn('id="bulkPreview"', library_html)
            self.assertIn('id="previewPatch"', library_html)
            self.assertIn('id="copyPatchDryRun"', library_html)
            self.assertIn('id="copyPatchWrite"', library_html)
            self.assertIn('id="copySelectedMarkdown"', library_html)
            self.assertIn('id="copySelectedSlugs"', library_html)
            self.assertIn("selectedMarkdown", library_html)
            self.assertIn("patchCommand(false)", library_html)
            self.assertIn("updateBulkPreview", library_html)
            self.assertIn("metadata_patch.csv", library_html)
            self.assertIn('id="exportMarkdown"', library_html)
            self.assertIn('id="exportCsv"', library_html)
            self.assertIn('id="exportBibtex"', library_html)
            self.assertIn("reading_list.md", library_html)
            self.assertIn("library_filtered.csv", library_html)
            self.assertIn('"topics",', library_html)
            self.assertIn('"methods",', library_html)
            self.assertIn("library.bib", library_html)
            self.assertIn('id="columnMenu"', library_html)
            self.assertIn('data-column-toggle="structure"', library_html)
            self.assertIn('id="densityMode"', library_html)
            self.assertIn("autopaperreader:library:prefs", library_html)
            self.assertIn('data-slug="2601.00001-alpha-paper"', library_html)
            board_html = (report_dir / "board.html").read_text(encoding="utf-8")
            self.assertIn("状态看板", board_html)
            self.assertIn('data-status="triaged"', board_html)
            self.assertIn("status_board_patch.csv", board_html)
            self.assertIn('draggable="true"', board_html)
            self.assertIn('id="boardWorkflow"', board_html)
            self.assertIn("const boardWorkflows =", board_html)
            self.assertIn("applyWorkflow(boardWorkflow.value)", board_html)
            self.assertIn("readBoardState", board_html)
            self.assertIn("syncBoardUrl", board_html)
            self.assertIn("url.searchParams.set(key, value)", board_html)
            self.assertIn('id="newStatusName"', board_html)
            self.assertIn("新增状态列", board_html)
            workflow = json.loads((report_dir / "workflow.json").read_text(encoding="utf-8"))
            self.assertEqual(workflow["count"], 2)
            self.assertEqual(workflow["active_status_workflow"], "research")
            self.assertEqual(workflow["workflow_count"], 2)
            self.assertEqual({item["name"] for item in workflow["workflows"]}, {"simple", "research"})
            active_workflow = next(item for item in workflow["workflows"] if item["active"])
            self.assertEqual(active_workflow["name"], "research")
            self.assertEqual(len(active_workflow["status_values"]), 5)
            self.assertEqual(active_workflow["fields"]["status"]["values"][3]["value"], "read")
            self.assertEqual(active_workflow["fields"]["status"]["values"][3]["count"], 2)
            self.assertEqual(active_workflow["fields"]["status"]["values"][3]["definition_status"], "active")
            self.assertEqual(active_workflow["fields"]["status"]["values"][3]["owner_name"], "workflow-owner")
            self.assertIn("stable enough", active_workflow["fields"]["status"]["values"][3]["description"])
            self.assertGreater(active_workflow["definition_total"], 0)
            self.assertEqual(active_workflow["fields"]["review_stage"]["empty_count"], 1)
            self.assertEqual(workflow["active_unconfigured"], [])
            self.assertTrue(workflow["recommendations"])
            workflow_html = (report_dir / "workflow.html").read_text(encoding="utf-8")
            self.assertIn("工作流中心", workflow_html)
            self.assertIn("Workflow JSON", workflow_html)
            self.assertIn("当前 Status 分布", workflow_html)
            self.assertIn("Workflow 对比", workflow_html)
            self.assertIn("当前 Drift", workflow_html)
            self.assertIn("Report is stable enough for reuse.", workflow_html)
            self.assertIn("状态工作流配置、分布和漂移审计", workflow_html)
            status = json.loads((report_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["count"], 2)
            self.assertEqual(status["active_status_workflow"], "research")
            self.assertEqual(status["workflow_count"], 2)
            self.assertEqual({item["name"] for item in status["workflows"]}, {"simple", "research"})
            active_status_workflow = next(item for item in status["workflows"] if item["active"])
            self.assertIn("stable enough", active_status_workflow["fields"]["status"]["values"][3]["description"])
            self.assertEqual({item["slug"] for item in status["papers"]}, {"2601.00001-alpha-paper", "2501.00002-beta-paper"})
            self.assertEqual(status["defaults"]["workflow"], "research")
            self.assertEqual(status["links"]["library"], "library.html")
            self.assertTrue(any("apply_status_workflow.py" in command for command in status["commands"]))
            self.assertTrue(any("apply_shared_views.py" in command for command in status["commands"]))
            self.assertIn("python3 scripts/apply_library_metadata.py docs --input <status_patch.csv> --write", status["commands"])
            status_html = (report_dir / "status.html").read_text(encoding="utf-8")
            self.assertIn("状态选择器", status_html)
            self.assertIn("Status JSON", status_html)
            self.assertIn('id="statusWorkflow"', status_html)
            self.assertIn('id="statusValue"', status_html)
            self.assertIn('id="statusStage"', status_html)
            self.assertIn('id="statusReview"', status_html)
            self.assertIn('id="copyStatusView"', status_html)
            self.assertIn('id="copyStatusUrl"', status_html)
            self.assertIn('id="downloadStatusView"', status_html)
            self.assertIn('id="statusSharedViewPreview"', status_html)
            self.assertIn('id="statusShareUrl"', status_html)
            self.assertIn('id="statusViewName"', status_html)
            self.assertIn('id="statusViewPage"', status_html)
            self.assertIn('id="copyStatusConfig"', status_html)
            self.assertIn('id="statusPatchField"', status_html)
            self.assertIn('id="statusPatchValue"', status_html)
            self.assertIn('id="copyStatusPatch"', status_html)
            self.assertIn('id="downloadStatusPatch"', status_html)
            self.assertIn('id="copyStatusPatchDryRun"', status_html)
            self.assertIn('id="copyStatusPatchWrite"', status_html)
            self.assertIn("function sharedViewPayload", status_html)
            self.assertIn("function statusPatchCsv", status_html)
            self.assertIn("status_shared_view.json", status_html)
            self.assertIn("status_patch.csv", status_html)
            self.assertIn("apply_shared_views.py", status_html)
            self.assertIn("apply_library_metadata.py", status_html)
            self.assertIn("function renderStatus", status_html)
            self.assertIn("active_status_workflow", status_html)
            self.assertIn("Report is stable enough for reuse.", status_html)
            views = json.loads((report_dir / "views.json").read_text(encoding="utf-8"))
            self.assertEqual(views["count"], 2)
            self.assertGreaterEqual(views["view_count"], views["configured_count"])
            self.assertEqual(views["configured_count"], 2)
            self.assertIn("configured", views["source_counts"])
            self.assertIn("workflow_status", views["kind_counts"])
            self.assertTrue(any(item["name"] == "Kernel 方向" and item["count"] == 1 for item in views["views"]))
            self.assertTrue(any(item["kind"] == "research_line" and item["state"].get("line") == "LLM Serving" for item in views["views"]))
            self.assertTrue(all("shared_view" in item for item in views["views"]))
            views_html = (report_dir / "views.html").read_text(encoding="utf-8")
            self.assertIn("视图目录", views_html)
            self.assertIn("Views JSON", views_html)
            self.assertIn('id="viewSearch"', views_html)
            self.assertIn('class="button copy-view-json"', views_html)
            self.assertIn("Kernel 方向", views_html)
            self.assertIn("apply_shared_views.py", views_html)
            batch = json.loads((report_dir / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(batch["count"], 2)
            self.assertGreater(batch["batch_count"], 0)
            self.assertIn("research_line", {item["key"] for item in batch["dimensions"]})
            self.assertIn("status", {item["key"] for item in batch["dimensions"]})
            self.assertTrue(batch["top_batches"])
            serving_batch = next(item for item in batch["batches"] if item["dimension"] == "research_line" and item["value"] == "LLM Serving")
            self.assertEqual(serving_batch["count"], 1)
            self.assertIn(serving_batch["severity"], {"high", "medium", "low"})
            self.assertIn("library.html?line=LLM+Serving", serving_batch["href"])
            self.assertIn("export_reading_list.py", serving_batch["export_command"])
            self.assertIn("2601.00001-alpha-paper", serving_batch["slugs"])
            self.assertIn("2601.00001-alpha-paper", serving_batch["sample_slugs"])
            batch_html = (report_dir / "batch.html").read_text(encoding="utf-8")
            self.assertIn("批次规划", batch_html)
            self.assertIn("Batch JSON", batch_html)
            self.assertIn('id="batchSearch"', batch_html)
            self.assertIn('id="batchDimension"', batch_html)
            self.assertIn('id="batchSeverity"', batch_html)
            self.assertIn('id="downloadBatchCsv"', batch_html)
            self.assertIn('id="copyBatchMarkdown"', batch_html)
            self.assertIn('id="batchDetail"', batch_html)
            self.assertIn('id="copyBatchLink"', batch_html)
            self.assertIn('id="copyBatchTask"', batch_html)
            self.assertIn('id="copyBatchCommand"', batch_html)
            self.assertIn('id="batchPatchField"', batch_html)
            self.assertIn('id="batchPatchValue"', batch_html)
            self.assertIn('id="downloadBatchPatch"', batch_html)
            self.assertIn('id="copyBatchDryRun"', batch_html)
            self.assertIn('id="copyBatchWrite"', batch_html)
            self.assertIn("paper_batches.csv", batch_html)
            self.assertIn("metadata-patch.csv", batch_html)
            self.assertIn("function batchPatchCsv", batch_html)
            self.assertIn("function batchPatchCommand", batch_html)
            self.assertIn("function renderBatchDetail", batch_html)
            self.assertIn("function batchTask", batch_html)
            self.assertIn("function renderBatchRows", batch_html)
            pivot = json.loads((report_dir / "pivot.json").read_text(encoding="utf-8"))
            self.assertEqual(pivot["count"], 2)
            self.assertIn("research_line", {item["key"] for item in pivot["dimensions"]})
            self.assertIn("method", {item["key"] for item in pivot["dimensions"]})
            self.assertEqual({item["slug"] for item in pivot["papers"]}, {"2601.00001-alpha-paper", "2501.00002-beta-paper"})
            first_pivot_paper = next(item for item in pivot["papers"] if item["slug"] == "2601.00001-alpha-paper")
            self.assertIn("LLM Serving", first_pivot_paper["dimensions"]["research_line"])
            preset_names = {(item["row_dimension"], item["column_dimension"]) for item in pivot["presets"]}
            self.assertIn(("research_line", "method"), preset_names)
            self.assertTrue(any(cell["count"] >= 1 for preset in pivot["presets"] for cell in preset["cells"]))
            pivot_html = (report_dir / "pivot.html").read_text(encoding="utf-8")
            self.assertIn("分类透视表", pivot_html)
            self.assertIn("Pivot JSON", pivot_html)
            self.assertIn('id="pivotRowDim"', pivot_html)
            self.assertIn('id="pivotColDim"', pivot_html)
            self.assertIn("Classification Pivot", pivot_html)
            compare = json.loads((report_dir / "compare.json").read_text(encoding="utf-8"))
            self.assertEqual(compare["count"], 2)
            self.assertIn("research_line", {item["key"] for item in compare["fields"]})
            self.assertIn("has_code", {item["key"] for item in compare["fields"]})
            self.assertEqual({item["slug"] for item in compare["papers"]}, {"2601.00001-alpha-paper", "2501.00002-beta-paper"})
            self.assertTrue(any(item["name"] == "高优先级论文" for item in compare["suggested_sets"]))
            self.assertTrue(any(item["kind"] == "workflow" for item in compare["suggested_sets"]))
            compare_html = (report_dir / "compare.html").read_text(encoding="utf-8")
            self.assertIn("论文对比", compare_html)
            self.assertIn("Compare JSON", compare_html)
            self.assertIn('id="comparePreset"', compare_html)
            self.assertIn('id="compareCopyLink"', compare_html)
            self.assertIn("Paper Compare", compare_html)
            taxonomy_map = json.loads((report_dir / "taxonomy_map.json").read_text(encoding="utf-8"))
            self.assertEqual(taxonomy_map["count"], 2)
            self.assertIn("nodes", taxonomy_map)
            self.assertIn("edges", taxonomy_map)
            self.assertIn("clusters", taxonomy_map)
            self.assertTrue(any(node["field"] == "track" and node["value"] == "Attention Kernels" for node in taxonomy_map["nodes"]))
            self.assertTrue(any(edge["source_field"] == "track" and edge["target_field"] == "problem" for edge in taxonomy_map["edges"]))
            self.assertTrue(taxonomy_map["recommendations"])
            taxonomy_map_html = (report_dir / "taxonomy_map.html").read_text(encoding="utf-8")
            self.assertIn("分类图谱", taxonomy_map_html)
            self.assertIn("Map JSON", taxonomy_map_html)
            self.assertIn('id="mapSearch"', taxonomy_map_html)
            self.assertIn("taxonomy_map_edges.csv", taxonomy_map_html)
            clusters = json.loads((report_dir / "clusters.json").read_text(encoding="utf-8"))
            self.assertEqual(clusters["count"], 2)
            self.assertEqual(clusters["cluster_count"], 2)
            self.assertTrue(clusters["clusters"])
            self.assertIn("LLM Serving", {item["name"] for item in clusters["clusters"]})
            serving_cluster = next(item for item in clusters["clusters"] if item["name"] == "LLM Serving")
            self.assertIn("representative_slugs", serving_cluster)
            self.assertIn(serving_cluster["risk"], {"high", "medium", "low"})
            clusters_html = (report_dir / "clusters.html").read_text(encoding="utf-8")
            self.assertIn("研究簇驾驶舱", clusters_html)
            self.assertIn("Clusters JSON", clusters_html)
            self.assertIn('id="clusterSearch"', clusters_html)
            self.assertIn("research_clusters.csv", clusters_html)
            roadmap = json.loads((report_dir / "roadmap.json").read_text(encoding="utf-8"))
            self.assertEqual(roadmap["count"], 2)
            self.assertEqual(roadmap["line_count"], 2)
            self.assertIn("foundation", roadmap["recommended_roles"])
            self.assertIn("LLM Serving", {item["line"] for item in roadmap["roadmaps"]})
            serving_roadmap = next(item for item in roadmap["roadmaps"] if item["line"] == "LLM Serving")
            self.assertEqual(serving_roadmap["owner"], "serving-owner")
            self.assertIn(serving_roadmap["risk"], {"high", "medium", "low"})
            self.assertIn("role_counts", serving_roadmap)
            self.assertIn("actions", serving_roadmap)
            self.assertTrue(serving_roadmap["representative_papers"])
            self.assertTrue(roadmap["actions"])
            roadmap_html = (report_dir / "roadmap.html").read_text(encoding="utf-8")
            self.assertIn("研究路线图", roadmap_html)
            self.assertIn("Roadmap JSON", roadmap_html)
            self.assertIn('id="roadmapSearch"', roadmap_html)
            self.assertIn('id="copyRoadmapMarkdown"', roadmap_html)
            self.assertIn("research_roadmap.csv", roadmap_html)
            self.assertIn("function renderRoadmapCards", roadmap_html)
            scale = json.loads((report_dir / "scale.json").read_text(encoding="utf-8"))
            self.assertEqual(scale["count"], 2)
            self.assertIn(scale["readiness_label"], {"ready", "watch", "needs_governance"})
            self.assertGreaterEqual(scale["readiness_score"], 0)
            self.assertLessEqual(scale["readiness_score"], 100)
            self.assertEqual(scale["status_workflow"]["active"], "research")
            self.assertEqual(scale["status_workflow"]["workflow_count"], 2)
            self.assertGreaterEqual(scale["status_workflow"]["status_count"], 5)
            self.assertIn("search_index.json", {item["href"] for item in scale["resource_sizes"]})
            self.assertTrue(scale["capacity_projection"])
            self.assertTrue(scale["bottlenecks"])
            scale_html = (report_dir / "scale.html").read_text(encoding="utf-8")
            self.assertIn("规模就绪", scale_html)
            self.assertIn("Scale JSON", scale_html)
            self.assertIn("动态状态体系", scale_html)
            self.assertIn("Active workflow", scale_html)
            self.assertIn('id="scaleSearch"', scale_html)
            self.assertIn("scale_bottlenecks.csv", scale_html)
            ownership = json.loads((report_dir / "ownership.json").read_text(encoding="utf-8"))
            self.assertEqual(ownership["count"], 2)
            self.assertEqual(ownership["owner_count"], 2)
            self.assertIn("serving-owner", {item["owner"] for item in ownership["owners"]})
            self.assertIn("kernel-owner", {item["owner"] for item in ownership["owners"]})
            serving_owner = next(item for item in ownership["owners"] if item["owner"] == "serving-owner")
            self.assertEqual(serving_owner["paper_count"], 1)
            self.assertIn("queues", serving_owner)
            self.assertTrue(serving_owner["lines"])
            ownership_html = (report_dir / "ownership.html").read_text(encoding="utf-8")
            self.assertIn("Owner 工作台", ownership_html)
            self.assertIn("Ownership JSON", ownership_html)
            self.assertIn('id="ownershipSearch"', ownership_html)
            self.assertIn('id="ownershipRisk"', ownership_html)
            self.assertIn("ownership_workload.csv", ownership_html)
            routing = json.loads((report_dir / "routing.json").read_text(encoding="utf-8"))
            self.assertEqual(routing["count"], 2)
            self.assertEqual(routing["paper_count"], 2)
            self.assertTrue(routing["line_profiles"])
            self.assertTrue(routing["label_profiles"])
            self.assertEqual({item["slug"] for item in routing["paper_signatures"]}, {"2601.00001-alpha-paper", "2501.00002-beta-paper"})
            self.assertIn("LLM Serving", {item["line"] for item in routing["line_profiles"]})
            self.assertTrue(any(item["field"] == "tracks" and item["value"] == "Attention Kernels" for item in routing["label_profiles"]))
            routing_html = (report_dir / "routing.html").read_text(encoding="utf-8")
            self.assertIn("新论文分类路由器", routing_html)
            self.assertIn("Routing JSON", routing_html)
            self.assertIn('id="routingTitle"', routing_html)
            self.assertIn('id="routingAbstract"', routing_html)
            self.assertIn("function renderRouting", routing_html)
            onboarding = json.loads((report_dir / "onboarding.json").read_text(encoding="utf-8"))
            self.assertEqual(onboarding["count"], 2)
            self.assertTrue(onboarding["readiness_checks"])
            self.assertTrue(onboarding["contribution_paths"])
            self.assertIn("onboarding.json", onboarding["bootstrap_files"])
            self.assertIn("intake.json", onboarding["bootstrap_files"])
            paper_intake = next(item for item in onboarding["contribution_paths"] if item["id"] == "paper-intake")
            self.assertEqual(paper_intake["entry"], "intake.html")
            self.assertIn("intake.html", paper_intake["recommended_pages"])
            self.assertTrue(any(item["id"] == "taxonomy-governance" for item in onboarding["contribution_paths"]))
            onboarding_html = (report_dir / "onboarding.html").read_text(encoding="utf-8")
            self.assertIn("开源上手控制台", onboarding_html)
            self.assertIn("Onboarding JSON", onboarding_html)
            self.assertIn('id="onboardingSearch"', onboarding_html)
            self.assertIn("python3 scripts/check_quality.py docs", onboarding_html)
            intake = json.loads((report_dir / "intake.json").read_text(encoding="utf-8"))
            self.assertEqual(intake["count"], 2)
            self.assertEqual(intake["inbox_count"], 2)
            self.assertEqual({item["slug"] for item in intake["existing_papers"]}, {"2601.00001-alpha-paper", "2501.00002-beta-paper"})
            self.assertIn("2601.00001", {item["arxiv_key"] for item in intake["existing_papers"]})
            self.assertIn("title", intake["csv_columns"])
            self.assertIn("link", intake["csv_columns"])
            self.assertEqual(intake["defaults"]["status"], "queued")
            self.assertIn("new_candidate", intake["statuses"])
            self.assertTrue(any("apply_inbox_items.py" in command for command in intake["commands"]))
            intake_html = (report_dir / "intake.html").read_text(encoding="utf-8")
            self.assertIn("批量导入", intake_html)
            self.assertIn("Intake JSON", intake_html)
            self.assertIn('id="intakePaste"', intake_html)
            self.assertIn('id="parseIntake"', intake_html)
            self.assertIn("candidate_inbox.csv", intake_html)
            self.assertIn("function parseIntakeLines", intake_html)
            self.assertIn("library_duplicate", intake_html)
            catalog = json.loads((report_dir / "catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(catalog["count"], 2)
            self.assertIn("papers.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("catalog.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("taxonomy_map.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("clusters.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("roadmap.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("scale.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("ownership.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("routing.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("onboarding.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("command.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("status.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("views.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("collections.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("intake.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("dedupe.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("registry.json", {item["href"] for item in catalog["data_resources"]})
            self.assertIn("status.html", {item["href"] for item in catalog["pages"]})
            self.assertIn("views.html", {item["href"] for item in catalog["pages"]})
            self.assertIn("intake.html", {item["href"] for item in catalog["pages"]})
            self.assertIn("dedupe.html", {item["href"] for item in catalog["pages"]})
            self.assertIn("registry.html", {item["href"] for item in catalog["pages"]})
            self.assertIn("command.html", {item["href"] for item in catalog["pages"]})
            self.assertIn("roadmap.html", {item["href"] for item in catalog["pages"]})
            self.assertIn("index.html", {item["href"] for item in catalog["pages"]})
            self.assertIn("guides/taxonomy.json", {item["href"] for item in catalog["contracts"]})
            self.assertTrue(catalog["integration_recipes"])
            self.assertIn("catalog.json", catalog["recommended_bootstrap_files"])
            self.assertIn("views.json", catalog["recommended_bootstrap_files"])
            catalog_html = (report_dir / "catalog.html").read_text(encoding="utf-8")
            self.assertIn("数据目录", catalog_html)
            self.assertIn("Catalog JSON", catalog_html)
            self.assertIn("机器数据", catalog_html)
            self.assertIn("集成 Recipes", catalog_html)
            inbox = json.loads((report_dir / "inbox.json").read_text(encoding="utf-8"))
            self.assertEqual(inbox["count"], 2)
            self.assertEqual(inbox["statuses"]["queued"], 2)
            self.assertEqual(inbox["priorities"]["high"], 1)
            self.assertEqual(inbox["duplicates"], ["inbox-2"])
            inbox_html = (report_dir / "inbox.html").read_text(encoding="utf-8")
            self.assertIn("Gamma Paper", inbox_html)
            self.assertIn("复制任务", inbox_html)
            self.assertIn('id="copyVisiblePrompts"', inbox_html)
            self.assertIn('id="downloadInboxCsv"', inbox_html)
            self.assertIn('id="copyInboxTemplate"', inbox_html)
            self.assertIn("inbox_filtered.csv", inbox_html)
            self.assertIn("inboxCsvHeader", inbox_html)
            self.assertIn('data-title="Gamma Paper"', inbox_html)
            self.assertIn("visibleInboxRows", inbox_html)
            dedupe = json.loads((report_dir / "dedupe.json").read_text(encoding="utf-8"))
            self.assertEqual(dedupe["count"], 2)
            self.assertEqual(dedupe["inbox_count"], 2)
            self.assertEqual(dedupe["duplicate_report_count"], 0)
            self.assertEqual(dedupe["inbox_duplicate_count"], 1)
            self.assertEqual(dedupe["group_count"], 1)
            self.assertEqual(dedupe["inbox_groups"][0]["item_ids"], ["inbox-2"])
            self.assertEqual(dedupe["inbox_groups"][0]["matched_slugs"], ["2601.00001-alpha-paper"])
            self.assertIn("scope", dedupe["csv_columns"])
            self.assertIn("severity", dedupe["csv_columns"])
            self.assertTrue(any("check_quality.py" in command for command in dedupe["commands"]))
            dedupe_html = (report_dir / "dedupe.html").read_text(encoding="utf-8")
            self.assertIn("去重工作台", dedupe_html)
            self.assertIn("Dedupe JSON", dedupe_html)
            self.assertIn('id="dedupeSearch"', dedupe_html)
            self.assertIn('id="downloadDedupeCsv"', dedupe_html)
            self.assertIn('id="copyDedupeMarkdown"', dedupe_html)
            self.assertIn("dedupe_review.csv", dedupe_html)
            self.assertIn("function renderDedupe", dedupe_html)
            registry = json.loads((report_dir / "registry.json").read_text(encoding="utf-8"))
            self.assertEqual(registry["count"], 2)
            self.assertGreater(registry["label_count"], 0)
            self.assertIn("labels", registry)
            self.assertIn("domains", registry["field_counts"])
            self.assertIn("label", registry["csv_columns"])
            self.assertIn("recommended_action", registry["csv_columns"])
            self.assertTrue(any("KV Cache" == item["label"] and item["aliases"] for item in registry["labels"]))
            self.assertTrue(any("singleton" in item["signals"] for item in registry["labels"]))
            self.assertTrue(any("export_taxonomy_registry.py" in command for command in registry["commands"]))
            llm_systems = next(item for item in registry["labels"] if item["label"] == "LLM Systems")
            self.assertEqual(llm_systems["definition_status"], "active")
            self.assertEqual(llm_systems["owner_name"], "systems-owner")
            self.assertIn("System papers", llm_systems["description"])
            registry_html = (report_dir / "registry.html").read_text(encoding="utf-8")
            self.assertIn("标签注册表", registry_html)
            self.assertIn("Registry JSON", registry_html)
            self.assertIn("System papers about inference", registry_html)
            self.assertIn('id="registrySearch"', registry_html)
            self.assertIn('id="downloadRegistryCsv"', registry_html)
            self.assertIn("taxonomy_registry.csv", registry_html)
            self.assertIn("function renderRegistry", registry_html)
            quality = json.loads((report_dir / "quality.json").read_text(encoding="utf-8"))
            self.assertIn("taxonomy_drift", quality)
            self.assertEqual(quality["taxonomy_drift"], [])
            self.assertEqual(quality["queues"]["taxonomy_drift"], [])
            self.assertEqual(quality["governance_policy"]["taxonomy_load"]["min_tags"], 5)
            self.assertEqual(quality["queues"]["taxonomy_sparse"], ["2501.00002-beta-paper", "2601.00001-alpha-paper"])
            self.assertEqual(quality["queues"]["taxonomy_dense"], [])
            self.assertEqual(quality["taxonomy_load"][0]["signals"], ["sparse_tags"])
            self.assertEqual(quality["taxonomy_load"][0]["policy"]["min_tags"], 5)
            self.assertEqual(quality["duplicate_reports"], [])
            self.assertEqual(quality["label_alias_suggestions"][0]["canonical"], "KV Cache")
            self.assertEqual(quality["label_alias_suggestions"][0]["aliases"], {"KV-cache": "KV Cache"})
            quality_html = (report_dir / "quality.html").read_text(encoding="utf-8")
            self.assertIn("质量治理", quality_html)
            self.assertIn("Taxonomy Drift", quality_html)
            self.assertIn("分类粒度审计", quality_html)
            self.assertIn("sparse_tags", quality_html)
            self.assertIn('id="downloadTaxonomyLoad"', quality_html)
            self.assertIn("taxonomy_load_audit.csv", quality_html)
            self.assertIn("标签归一化建议", quality_html)
            self.assertIn("治理命令", quality_html)
            self.assertIn("copy-quality-command", quality_html)
            self.assertIn("python3 scripts/check_quality.py docs", quality_html)
            self.assertIn("python3 scripts/apply_inbox_items.py docs --input &lt;candidate_csv&gt; --write", quality_html)
            self.assertIn("python3 scripts/apply_shared_views.py docs --input &lt;shared_views.json&gt; --write", quality_html)
            self.assertIn("python3 scripts/apply_status_workflow.py docs --input &lt;taxonomy_status_workflow.json&gt; --write", quality_html)
            self.assertIn("python3 scripts/export_actions.py docs --format project --output docs/exports/actions-project.csv", quality_html)
            self.assertIn("python3 scripts/export_taxonomy_actions.py docs --format project --output docs/exports/taxonomy-project.csv", quality_html)
            self.assertIn("python3 scripts/export_taxonomy_balance.py docs --format project --max-score 50 --output docs/exports/taxonomy-balance-project.csv", quality_html)
            self.assertIn("python3 scripts/export_taxonomy_load.py docs --format patch --output docs/exports/taxonomy-load-patch.csv", quality_html)
            self.assertIn("python3 scripts/export_batches.py docs --format patch --gap review --field review_stage --set-value due --output docs/exports/batches-review-patch.csv", quality_html)
            self.assertIn("python3 scripts/export_coverage.py docs --format project --risk high --risk medium --output docs/exports/coverage-project.csv", quality_html)
            self.assertIn("python3 scripts/export_gaps.py docs --format project --min-priority 20 --output docs/exports/gaps-project.csv", quality_html)
            self.assertIn("python3 scripts/export_views.py docs --format sidebar --min-count 1 --output docs/exports/views-sidebar.json", quality_html)
            self.assertIn("python3 scripts/export_views.py docs --format patch --view &lt;view_id_or_name&gt; --field status --set-value reading --output docs/exports/views-status-patch.csv", quality_html)
            self.assertIn("python3 scripts/export_collections.py docs --format project --output docs/exports/collections-project.csv", quality_html)
            self.assertIn("python3 scripts/export_ownership.py docs --format project --only-open-queues --output docs/exports/ownership-project.csv", quality_html)
            self.assertIn("python3 scripts/export_roadmap.py docs --format project --output docs/exports/roadmap-project.csv", quality_html)

            review = json.loads((report_dir / "review.json").read_text(encoding="utf-8"))
            self.assertEqual(review["count"], 2)
            self.assertEqual(review["queues"]["needs_plan"], ["2601.00001-alpha-paper"])
            self.assertEqual(review["queues"]["scheduled"], ["2501.00002-beta-paper"])
            review_html = (report_dir / "review.html").read_text(encoding="utf-8")
            self.assertIn('id="downloadReviewPatch"', review_html)
            self.assertIn("review_plan_patch.csv", review_html)
            freshness = json.loads((report_dir / "freshness.json").read_text(encoding="utf-8"))
            self.assertEqual(freshness["count"], 2)
            self.assertIn("needs_plan", freshness["queues"])
            self.assertIn("2601.00001-alpha-paper", freshness["queues"]["needs_plan"])
            self.assertTrue(freshness["line_health"])
            freshness_html = (report_dir / "freshness.html").read_text(encoding="utf-8")
            self.assertIn("时效治理", freshness_html)
            self.assertIn('id="freshnessRows"', freshness_html)
            self.assertIn("freshness_queue.csv", freshness_html)
            self.assertIn("copyFreshnessQueue", freshness_html)
            taxonomy_actions = json.loads((report_dir / "taxonomy_actions.json").read_text(encoding="utf-8"))
            self.assertEqual(taxonomy_actions["paper_count"], 2)
            self.assertEqual(taxonomy_actions["governance_policy"]["split_share"], 0.6)
            self.assertGreater(taxonomy_actions["summary"]["unused_config"], 0)
            triaged_action = next(item for item in taxonomy_actions["actions"] if item["field"] == "status" and item["value"] == "triaged")
            self.assertEqual(triaged_action["action"], "unused_config")
            self.assertEqual(triaged_action["href"], "library.html?status=triaged")
            actions = json.loads((report_dir / "actions.json").read_text(encoding="utf-8"))
            self.assertGreater(actions["count"], 0)
            self.assertIn("review", actions["summary"]["groups"])
            self.assertIn("taxonomy", actions["summary"]["groups"])
            self.assertTrue(any(item["source"] == "taxonomy_actions.json" for item in actions["actions"]))
            self.assertTrue(any(item["source"] == "review.json" for item in actions["actions"]))
            command = json.loads((report_dir / "command.json").read_text(encoding="utf-8"))
            self.assertEqual(command["count"], 2)
            self.assertEqual(command["lane_count"], 6)
            self.assertIn("daily_reading", {item["id"] for item in command["lanes"]})
            self.assertIn("taxonomy_governance", {item["id"] for item in command["lanes"]})
            release_lane = next(item for item in command["lanes"] if item["id"] == "release_open_source")
            self.assertIn("command.json", {item["href"] for item in release_lane["data_files"]})
            self.assertTrue(command["recommended_next"])

            snapshot = json.loads((report_dir / "snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["count"], 2)
            self.assertRegex(snapshot["snapshot_id"], r"^[0-9a-f]{16}$")
            self.assertIn("publish_checks", snapshot)
            self.assertIn("queue_sizes", snapshot)
            self.assertIn("risk_queue_sizes", snapshot)
            self.assertIn("action_groups", snapshot)
            self.assertIn("research_lines", snapshot)
            self.assertEqual(snapshot["risk_queue_sizes"]["needs_review_plan"], 1)
            self.assertEqual(snapshot["risk_queue_sizes"]["inbox_duplicates"], 1)
            self.assertEqual(snapshot["governance_policy"]["taxonomy_load"]["min_tags"], 5)
            self.assertEqual(snapshot["active_status_workflow"], "research")
            self.assertEqual(snapshot["artifact_summary"]["missing"], [])
            self.assertTrue(snapshot["artifact_summary"]["hashes"])
            snapshot_html = (report_dir / "snapshot.html").read_text(encoding="utf-8")
            self.assertIn("治理快照", snapshot_html)
            self.assertIn("Snapshot JSON", snapshot_html)
            self.assertIn("风险队列", snapshot_html)
            self.assertIn("治理策略", snapshot_html)
            self.assertIn("Artifact Hashes", snapshot_html)

            actions_export_path = report_dir / "exports" / "actions.md"
            self.run_cmd(
                "scripts/export_actions.py",
                str(report_dir),
                "--group",
                "review",
                "--output",
                str(actions_export_path),
            )
            actions_export = actions_export_path.read_text(encoding="utf-8")
            self.assertIn("# AutoPaperReader Action Queue", actions_export)
            self.assertIn("review.json", actions_export)

            actions_project_path = report_dir / "exports" / "actions-project.csv"
            self.run_cmd(
                "scripts/export_actions.py",
                str(report_dir),
                "--format",
                "project",
                "--source",
                "taxonomy_actions.json",
                "--assignee",
                "wiki-owner",
                "--task-status",
                "ready",
                "--due-date",
                "2026-07-01",
                "--output",
                str(actions_project_path),
            )
            action_project_rows = list(csv.DictReader(actions_project_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(action_project_rows)
            self.assertEqual(action_project_rows[0]["status"], "ready")
            self.assertEqual(action_project_rows[0]["assignee"], "wiki-owner")
            self.assertEqual(action_project_rows[0]["due_date"], "2026-07-01")
            self.assertIn("action_center", action_project_rows[0]["labels"])
            self.assertEqual(action_project_rows[0]["source"], "taxonomy_actions.json")

            unsafe_actions_export = self.run_cmd(
                "scripts/export_actions.py",
                str(report_dir),
                "--output",
                str(report_dir / "actions.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_actions_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_actions_export.stderr)

            batches_export_path = report_dir / "exports" / "batches.md"
            self.run_cmd(
                "scripts/export_batches.py",
                str(report_dir),
                "--dimension",
                "research_line",
                "--min-count",
                "1",
                "--output",
                str(batches_export_path),
            )
            batches_export = batches_export_path.read_text(encoding="utf-8")
            self.assertIn("# AutoPaperReader Paper Batches", batches_export)
            self.assertIn("LLM Serving", batches_export)

            batches_project_path = report_dir / "exports" / "batches-project.csv"
            self.run_cmd(
                "scripts/export_batches.py",
                str(report_dir),
                "--format",
                "project",
                "--severity",
                "high",
                "--assignee",
                "batch-owner",
                "--task-status",
                "ready",
                "--output",
                str(batches_project_path),
            )
            batch_project_rows = list(csv.DictReader(batches_project_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(batch_project_rows)
            self.assertEqual(batch_project_rows[0]["status"], "ready")
            self.assertEqual(batch_project_rows[0]["assignee"], "batch-owner")
            self.assertIn("batch", batch_project_rows[0]["labels"])
            self.assertTrue(batch_project_rows[0]["batch_id"])

            batch_patch_path = report_dir / "exports" / "batches-review-patch.csv"
            self.run_cmd(
                "scripts/export_batches.py",
                str(report_dir),
                "--format",
                "patch",
                "--gap",
                "review",
                "--field",
                "review_stage",
                "--set-value",
                "due",
                "--output",
                str(batch_patch_path),
            )
            batch_patch_rows = list(csv.DictReader(batch_patch_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(batch_patch_rows)
            self.assertIn("review_stage", batch_patch_rows[0])
            self.assertTrue(all(row["review_stage"] == "due" for row in batch_patch_rows))

            unsafe_batches_export = self.run_cmd(
                "scripts/export_batches.py",
                str(report_dir),
                "--output",
                str(report_dir / "batches.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_batches_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_batches_export.stderr)

            coverage_export_path = report_dir / "exports" / "coverage.md"
            self.run_cmd(
                "scripts/export_coverage.py",
                str(report_dir),
                "--min-missing",
                "0",
                "--max-score",
                "100",
                "--output",
                str(coverage_export_path),
            )
            coverage_export = coverage_export_path.read_text(encoding="utf-8")
            self.assertIn("# AutoPaperReader Coverage Gaps", coverage_export)
            self.assertIn("LLM Serving", coverage_export)

            coverage_project_path = report_dir / "exports" / "coverage-project.csv"
            self.run_cmd(
                "scripts/export_coverage.py",
                str(report_dir),
                "--format",
                "project",
                "--field",
                "topics",
                "--min-missing",
                "0",
                "--task-status",
                "ready",
                "--output",
                str(coverage_project_path),
            )
            coverage_project_rows = list(csv.DictReader(coverage_project_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(coverage_project_rows)
            self.assertEqual(coverage_project_rows[0]["status"], "ready")
            self.assertEqual(coverage_project_rows[0]["field"], "topics")
            self.assertIn("coverage", coverage_project_rows[0]["labels"])

            coverage_patch_path = report_dir / "exports" / "coverage-topic-patch.csv"
            self.run_cmd(
                "scripts/export_coverage.py",
                str(report_dir),
                "--format",
                "patch",
                "--field",
                "topics",
                "--min-missing",
                "0",
                "--set-value",
                "LLM Serving",
                "--output",
                str(coverage_patch_path),
            )
            coverage_patch_text = coverage_patch_path.read_text(encoding="utf-8")
            self.assertTrue(coverage_patch_text.startswith("slug,topics,_list_mode"))

            unsafe_coverage_export = self.run_cmd(
                "scripts/export_coverage.py",
                str(report_dir),
                "--output",
                str(report_dir / "coverage.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_coverage_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_coverage_export.stderr)

            gaps_export_path = report_dir / "exports" / "gaps.md"
            self.run_cmd(
                "scripts/export_gaps.py",
                str(report_dir),
                "--output",
                str(gaps_export_path),
            )
            gaps_export = gaps_export_path.read_text(encoding="utf-8")
            self.assertIn("# AutoPaperReader Research Gaps", gaps_export)
            self.assertIn("LLM Serving", gaps_export)
            self.assertIn("补复习计划", gaps_export)

            gaps_project_path = report_dir / "exports" / "gaps-project.csv"
            self.run_cmd(
                "scripts/export_gaps.py",
                str(report_dir),
                "--format",
                "project",
                "--min-priority",
                "1",
                "--task-status",
                "ready",
                "--assignee",
                "research-owner",
                "--output",
                str(gaps_project_path),
            )
            gaps_project_rows = list(csv.DictReader(gaps_project_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(gaps_project_rows)
            self.assertTrue(any(row["line"] == "LLM Serving" for row in gaps_project_rows))
            self.assertEqual(gaps_project_rows[0]["status"], "ready")
            self.assertEqual(gaps_project_rows[0]["assignee"], "research-owner")
            self.assertIn("gap", gaps_project_rows[0]["labels"])

            unsafe_gaps_export = self.run_cmd(
                "scripts/export_gaps.py",
                str(report_dir),
                "--output",
                str(report_dir / "gaps.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_gaps_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_gaps_export.stderr)

            views_export_path = report_dir / "exports" / "views.md"
            self.run_cmd(
                "scripts/export_views.py",
                str(report_dir),
                "--min-count",
                "1",
                "--output",
                str(views_export_path),
            )
            views_export = views_export_path.read_text(encoding="utf-8")
            self.assertIn("# AutoPaperReader View Directory", views_export)
            self.assertIn("Kernel 方向", views_export)
            self.assertIn("LLM Serving", views_export)

            views_csv_path = report_dir / "exports" / "views.csv"
            self.run_cmd(
                "scripts/export_views.py",
                str(report_dir),
                "--format",
                "csv",
                "--source",
                "configured",
                "--output",
                str(views_csv_path),
            )
            view_rows = list(csv.DictReader(views_csv_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(view_rows)
            self.assertTrue(all(row["source"] == "configured" for row in view_rows))
            self.assertIn("state", view_rows[0])

            views_sidebar_path = report_dir / "exports" / "views-sidebar.json"
            self.run_cmd(
                "scripts/export_views.py",
                str(report_dir),
                "--format",
                "sidebar",
                "--min-count",
                "1",
                "--output",
                str(views_sidebar_path),
            )
            sidebar = json.loads(views_sidebar_path.read_text(encoding="utf-8"))
            self.assertEqual(sidebar["generated_from"], "views.json")
            self.assertTrue(sidebar["groups"])
            self.assertTrue(any(item["label"] == "Kernel 方向" for group in sidebar["groups"] for item in group["items"]))

            views_patch_path = report_dir / "exports" / "views-status-patch.csv"
            self.run_cmd(
                "scripts/export_views.py",
                str(report_dir),
                "--format",
                "patch",
                "--view",
                "Kernel 方向",
                "--field",
                "status",
                "--set-value",
                "reading",
                "--output",
                str(views_patch_path),
            )
            view_patch_rows = list(csv.DictReader(views_patch_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(view_patch_rows)
            self.assertIn("slug", view_patch_rows[0])
            self.assertTrue(all(row["status"] == "reading" for row in view_patch_rows))

            unsafe_views_export = self.run_cmd(
                "scripts/export_views.py",
                str(report_dir),
                "--output",
                str(report_dir / "views.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_views_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_views_export.stderr)

            collections_export_path = report_dir / "exports" / "collections.md"
            self.run_cmd(
                "scripts/export_collections.py",
                str(report_dir),
                "--type",
                "smart",
                "--min-count",
                "1",
                "--output",
                str(collections_export_path),
            )
            collections_export = collections_export_path.read_text(encoding="utf-8")
            self.assertIn("# AutoPaperReader Collections", collections_export)
            self.assertIn("needs_review_plan", collections_export)

            collections_project_path = report_dir / "exports" / "collections-project.csv"
            self.run_cmd(
                "scripts/export_collections.py",
                str(report_dir),
                "--format",
                "project",
                "--type",
                "research_line",
                "--assignee",
                "wiki-owner",
                "--task-status",
                "ready",
                "--output",
                str(collections_project_path),
            )
            collection_project_rows = list(csv.DictReader(collections_project_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(collection_project_rows)
            self.assertEqual(collection_project_rows[0]["status"], "ready")
            self.assertEqual(collection_project_rows[0]["assignee"], "wiki-owner")
            self.assertIn("collection", collection_project_rows[0]["labels"])
            self.assertEqual(collection_project_rows[0]["collection_type"], "research_line")

            unsafe_collections_export = self.run_cmd(
                "scripts/export_collections.py",
                str(report_dir),
                "--output",
                str(report_dir / "collections.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_collections_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_collections_export.stderr)

            ownership_export_path = report_dir / "exports" / "ownership.md"
            self.run_cmd(
                "scripts/export_ownership.py",
                str(report_dir),
                "--owner",
                "serving-owner",
                "--output",
                str(ownership_export_path),
            )
            ownership_export = ownership_export_path.read_text(encoding="utf-8")
            self.assertIn("# AutoPaperReader Ownership Workload", ownership_export)
            self.assertIn("serving-owner", ownership_export)
            self.assertIn("补复习计划", ownership_export)

            ownership_project_path = report_dir / "exports" / "ownership-project.csv"
            self.run_cmd(
                "scripts/export_ownership.py",
                str(report_dir),
                "--format",
                "project",
                "--only-open-queues",
                "--owner",
                "serving-owner",
                "--task-status",
                "ready",
                "--output",
                str(ownership_project_path),
            )
            ownership_project_rows = list(csv.DictReader(ownership_project_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(ownership_project_rows)
            self.assertEqual(ownership_project_rows[0]["status"], "ready")
            self.assertEqual(ownership_project_rows[0]["owner"], "serving-owner")
            self.assertIn("ownership", ownership_project_rows[0]["labels"])
            self.assertGreater(int(ownership_project_rows[0]["queue_count"]), 0)

            unsafe_ownership_export = self.run_cmd(
                "scripts/export_ownership.py",
                str(report_dir),
                "--output",
                str(report_dir / "ownership.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_ownership_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_ownership_export.stderr)

            roadmap_export_path = report_dir / "exports" / "roadmap.md"
            self.run_cmd(
                "scripts/export_roadmap.py",
                str(report_dir),
                "--role-gap",
                "yes",
                "--output",
                str(roadmap_export_path),
            )
            roadmap_export = roadmap_export_path.read_text(encoding="utf-8")
            self.assertIn("# AutoPaperReader Research Roadmap", roadmap_export)
            self.assertIn("LLM Serving", roadmap_export)
            self.assertIn("Actions", roadmap_export)

            roadmap_project_path = report_dir / "exports" / "roadmap-project.csv"
            self.run_cmd(
                "scripts/export_roadmap.py",
                str(report_dir),
                "--format",
                "project",
                "--owner",
                "serving-owner",
                "--assignee",
                "roadmap-owner",
                "--task-status",
                "ready",
                "--output",
                str(roadmap_project_path),
            )
            roadmap_project_rows = list(csv.DictReader(roadmap_project_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(roadmap_project_rows)
            self.assertEqual(roadmap_project_rows[0]["status"], "ready")
            self.assertEqual(roadmap_project_rows[0]["assignee"], "roadmap-owner")
            self.assertEqual(roadmap_project_rows[0]["line"], "LLM Serving")
            self.assertIn("roadmap", roadmap_project_rows[0]["labels"])
            self.assertTrue(roadmap_project_rows[0]["action_type"])

            unsafe_roadmap_export = self.run_cmd(
                "scripts/export_roadmap.py",
                str(report_dir),
                "--output",
                str(report_dir / "roadmap.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_roadmap_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_roadmap_export.stderr)

            stats = json.loads((report_dir / "stats.json").read_text(encoding="utf-8"))
            self.assertEqual(stats["count"], 2)
            self.assertIn("quality", stats["queue_sizes"])
            self.assertIn("review", stats["queue_sizes"])
            self.assertTrue(stats["research_lines"])
            line_by_name = {item["name"]: item for item in stats["research_lines"]}
            self.assertEqual(line_by_name["LLM Serving"]["owner"], "serving-owner")
            self.assertEqual(line_by_name["LLM Serving"]["team"], "systems")
            self.assertEqual(line_by_name["Attention Kernels"]["cadence"], "monthly")
            self.assertEqual(stats["shared_views"], 2)
            self.assertEqual(stats["controls"]["research_line_owners"]["LLM Serving"]["owner"], "serving-owner")
            self.assertEqual(stats["controls"]["review_stage"], ["fresh", "due", "reviewed"])
            self.assertIn("research", stats["controls"]["status_workflows"])
            self.assertEqual(stats["controls"]["governance_policy"]["taxonomy_load"]["min_tags"], 5)
            self.assertTrue(stats["taxonomy_balance"])
            balance_by_field = {item["field"]: item for item in stats["taxonomy_balance"]}
            self.assertEqual(balance_by_field["domains"]["max_value"], "LLM Systems")
            self.assertEqual(balance_by_field["domains"]["max_share"], 1.0)
            self.assertIn("balance_score", balance_by_field["topics"])
            manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["count"], 2)
            self.assertEqual(manifest["controls"]["governance_policy"]["taxonomy_load"]["min_tags"], 5)
            self.assertTrue(manifest["publish_checks"]["no_duplicate_reports"])
            self.assertIn("command.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("release.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("snapshot.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("workflow.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("status.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("views.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("batch.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("pivot.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("compare.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("taxonomy_map.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("clusters.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("roadmap.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("scale.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("ownership.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("routing.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("onboarding.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("catalog.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("intake.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("dedupe.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("registry.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("actions.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("freshness.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("balance.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("coverage.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("facets.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("taxonomy_actions.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("actions.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("command.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("workflow.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("status.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("views.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("batch.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("collections.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("coverage.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("gaps.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("pivot.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("compare.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("taxonomy_map.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("clusters.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("roadmap.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("scale.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("ownership.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("routing.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("onboarding.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("catalog.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("snapshot.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("intake.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("dedupe.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("registry.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("freshness.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("manifest.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("guides/report.template.md", {item["href"] for item in manifest["contract_files"]})
            self.assertIn("guides/metadata.schema.json", {item["href"] for item in manifest["contract_files"]})
            self.assertIn("guides/inbox.schema.json", {item["href"] for item in manifest["contract_files"]})
            self.assertIn("guides/taxonomy.schema.json", {item["href"] for item in manifest["contract_files"]})
            artifact_by_href = {item["href"]: item for item in manifest["artifact_inventory"]}
            self.assertEqual(artifact_by_href["index.html"]["status"], "ok")
            self.assertEqual(artifact_by_href["command.html"]["status"], "ok")
            self.assertEqual(artifact_by_href["command.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["index.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(artifact_by_href["index.html"]["size_bytes"], 0)
            self.assertEqual(artifact_by_href["guides/report.template.md"]["kind"], "contract")
            self.assertEqual(artifact_by_href["guides/metadata.schema.json"]["kind"], "contract")
            self.assertEqual(artifact_by_href["guides/inbox.schema.json"]["kind"], "contract")
            self.assertEqual(artifact_by_href["guides/taxonomy.schema.json"]["kind"], "contract")
            self.assertEqual(artifact_by_href["workflow.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["workflow.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["workflow.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["workflow.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["status.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["status.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["status.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["status.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["views.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["views.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["views.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["views.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["batch.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["batch.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["batch.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["batch.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["coverage.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["coverage.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["gaps.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["gaps.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["intake.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["intake.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["intake.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["intake.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["dedupe.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["dedupe.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["dedupe.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["dedupe.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["registry.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["registry.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["registry.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["registry.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["pivot.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["pivot.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["pivot.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["pivot.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["compare.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["compare.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["compare.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["compare.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["taxonomy_map.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["taxonomy_map.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["taxonomy_map.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["taxonomy_map.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["roadmap.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["roadmap.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["roadmap.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["roadmap.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["scale.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["scale.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["scale.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["scale.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["catalog.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["catalog.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["catalog.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["catalog.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["snapshot.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["snapshot.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["snapshot.json"]["status"], "ok")
            self.assertRegex(artifact_by_href["snapshot.json"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(artifact_by_href["manifest.json"]["status"], "generated_after_inventory")
            self.assertTrue(manifest["publish_checks"]["artifacts_present"])
            self.assertIn("python3 scripts/check_quality.py docs", manifest["commands"])
            self.assertIn("python3 scripts/apply_inbox_items.py docs --input <candidate_csv> --write", manifest["commands"])
            self.assertIn("python3 scripts/apply_shared_views.py docs --input <shared_views.json> --write", manifest["commands"])
            self.assertIn("python3 scripts/apply_status_workflow.py docs --input <taxonomy_status_workflow.json> --write", manifest["commands"])
            self.assertIn("python3 scripts/apply_governance_policy.py docs --input <taxonomy_governance_policy.json> --write", manifest["commands"])
            self.assertIn("python3 scripts/export_actions.py docs --output docs/exports/actions.md", manifest["commands"])
            self.assertIn("python3 scripts/export_batches.py docs --output docs/exports/batches.md", manifest["commands"])
            self.assertIn("python3 scripts/export_coverage.py docs --output docs/exports/coverage.md", manifest["commands"])
            self.assertIn("python3 scripts/export_gaps.py docs --output docs/exports/gaps.md", manifest["commands"])
            self.assertIn("python3 scripts/export_views.py docs --output docs/exports/views.md", manifest["commands"])
            self.assertIn("python3 scripts/export_views.py docs --format patch --view <view_id_or_name> --field status --set-value reading --output docs/exports/views-status-patch.csv", manifest["commands"])
            self.assertIn("python3 scripts/export_taxonomy_registry.py docs --output docs/exports/taxonomy-registry.md", manifest["commands"])
            self.assertIn("python3 scripts/export_taxonomy_load.py docs --format csv --output docs/exports/taxonomy-load.csv", manifest["commands"])
            self.assertIn("python3 scripts/export_collections.py docs --output docs/exports/collections.md", manifest["commands"])
            self.assertIn("python3 scripts/export_ownership.py docs --output docs/exports/ownership.md", manifest["commands"])
            self.assertIn("python3 scripts/export_roadmap.py docs --output docs/exports/roadmap.md", manifest["commands"])
            recipe_by_id = {item["id"]: item for item in manifest["command_recipes"]}
            self.assertEqual(recipe_by_id["quality_gate"]["kind"], "check")
            self.assertFalse(recipe_by_id["quality_gate"]["mutates"])
            self.assertFalse(recipe_by_id["apply_metadata_dry_run"]["mutates"])
            self.assertEqual(recipe_by_id["apply_metadata_dry_run"]["command"], "python3 scripts/apply_library_metadata.py docs --input <csv>")
            self.assertFalse(recipe_by_id["apply_metadata_audit"]["mutates"])
            self.assertEqual(recipe_by_id["apply_metadata_audit"]["output"], "docs/exports/metadata-audit.json")
            self.assertEqual(recipe_by_id["apply_inbox"]["output"], "docs/inbox.csv")
            self.assertEqual(recipe_by_id["apply_shared_views"]["output"], "docs/guides/taxonomy.json")
            self.assertEqual(recipe_by_id["apply_status_workflow"]["output"], "docs/guides/taxonomy.json")
            self.assertEqual(recipe_by_id["apply_governance_policy"]["output"], "docs/guides/taxonomy.json")
            self.assertFalse(recipe_by_id["apply_governance_policy_dry_run"]["mutates"])
            self.assertEqual(recipe_by_id["actions_project"]["output"], "docs/exports/actions-project.csv")
            self.assertEqual(recipe_by_id["taxonomy_registry_project"]["output"], "docs/exports/taxonomy-registry-project.csv")
            self.assertEqual(recipe_by_id["taxonomy_balance_project"]["output"], "docs/exports/taxonomy-balance-project.csv")
            self.assertEqual(recipe_by_id["taxonomy_actions_patch"]["output"], "docs/exports/taxonomy-action-patch.csv")
            self.assertEqual(recipe_by_id["batches_markdown"]["output"], "docs/exports/batches.md")
            self.assertEqual(recipe_by_id["batches_project"]["output"], "docs/exports/batches-project.csv")
            self.assertEqual(recipe_by_id["batches_review_patch"]["output"], "docs/exports/batches-review-patch.csv")
            self.assertEqual(recipe_by_id["coverage_markdown"]["output"], "docs/exports/coverage.md")
            self.assertEqual(recipe_by_id["coverage_project"]["output"], "docs/exports/coverage-project.csv")
            self.assertEqual(recipe_by_id["coverage_topic_patch"]["output"], "docs/exports/coverage-topic-patch.csv")
            self.assertEqual(recipe_by_id["gaps_markdown"]["output"], "docs/exports/gaps.md")
            self.assertEqual(recipe_by_id["gaps_project"]["output"], "docs/exports/gaps-project.csv")
            self.assertEqual(recipe_by_id["views_markdown"]["output"], "docs/exports/views.md")
            self.assertEqual(recipe_by_id["views_sidebar"]["output"], "docs/exports/views-sidebar.json")
            self.assertEqual(recipe_by_id["views_status_patch"]["output"], "docs/exports/views-status-patch.csv")
            self.assertEqual(recipe_by_id["collections_markdown"]["output"], "docs/exports/collections.md")
            self.assertEqual(recipe_by_id["collections_project"]["kind"], "export")
            self.assertEqual(recipe_by_id["ownership_markdown"]["output"], "docs/exports/ownership.md")
            self.assertEqual(recipe_by_id["ownership_project"]["output"], "docs/exports/ownership-project.csv")
            self.assertEqual(recipe_by_id["roadmap_markdown"]["output"], "docs/exports/roadmap.md")
            self.assertEqual(recipe_by_id["roadmap_project"]["output"], "docs/exports/roadmap-project.csv")
            playbook_by_id = {item["id"]: item for item in manifest["governance_playbooks"]}
            self.assertEqual(
                playbook_by_id["taxonomy_merge_batch"]["steps"],
                ["taxonomy_actions_markdown", "taxonomy_actions_patch", "apply_metadata_audit", "apply_metadata_dry_run", "quality_gate"],
            )
            self.assertEqual(playbook_by_id["weekly_action_review"]["steps"], ["actions_markdown", "actions_project", "quality_gate"])
            self.assertEqual(
                playbook_by_id["taxonomy_balance_review"]["steps"],
                ["taxonomy_registry_project", "taxonomy_balance_project", "taxonomy_actions_project", "quality_gate"],
            )
            self.assertEqual(
                playbook_by_id["status_workflow_rollout"]["steps"],
                ["apply_status_workflow_dry_run", "apply_status_workflow", "build_wiki", "strict_validate"],
            )
            self.assertEqual(
                playbook_by_id["shared_view_rollout"]["steps"],
                ["apply_shared_views_dry_run", "apply_shared_views", "build_wiki", "strict_validate"],
            )
            self.assertEqual(
                playbook_by_id["paper_intake_batch"]["steps"],
                ["apply_inbox_dry_run", "apply_inbox", "build_wiki", "strict_validate"],
            )
            release_html = (report_dir / "release.html").read_text(encoding="utf-8")
            self.assertIn("知识库发布摘要", release_html)
            self.assertIn("Manifest JSON", release_html)
            self.assertIn("推荐命令", release_html)
            self.assertIn("数据契约", release_html)
            self.assertIn("Artifact Inventory", release_html)
            self.assertIn("SHA-256", release_html)
            self.assertIn("guides/report.template.md", release_html)
            self.assertIn("freshness.html", release_html)
            self.assertIn("freshness.json", release_html)
            self.assertIn("workflow.html", release_html)
            self.assertIn("workflow.json", release_html)
            self.assertIn("collections.json", release_html)
            self.assertIn("pivot.html", release_html)
            self.assertIn("pivot.json", release_html)
            self.assertIn("compare.html", release_html)
            self.assertIn("compare.json", release_html)
            self.assertIn("taxonomy_map.html", release_html)
            self.assertIn("taxonomy_map.json", release_html)
            self.assertIn("scale.html", release_html)
            self.assertIn("scale.json", release_html)
            self.assertIn("catalog.html", release_html)
            self.assertIn("catalog.json", release_html)
            self.assertIn("snapshot.html", release_html)
            self.assertIn("snapshot.json", release_html)
            self.assertIn("guides/metadata.schema.json", release_html)
            self.assertIn("guides/inbox.schema.json", release_html)
            self.assertIn("guides/taxonomy.schema.json", release_html)
            self.assertIn("命令 Recipes", release_html)
            self.assertIn("治理 Playbooks", release_html)
            self.assertIn("Taxonomy merge batch", release_html)
            self.assertIn("复制命令组", release_html)
            self.assertIn("taxonomy_balance_project", release_html)
            self.assertIn("taxonomy_actions_patch", release_html)
            self.assertIn("apply_governance_policy", release_html)
            self.assertIn("shared_view_rollout", release_html)
            self.assertIn("status_workflow_rollout", release_html)
            self.assertIn("paper_intake_batch", release_html)
            self.assertIn("copy-release-command", release_html)
            self.assertIn("copyReleaseCommand", release_html)
            self.assertIn("Alpha 论文", release_html)
            self.assertIn("quick-kind", release_html)
            actions_html = (report_dir / "actions.html").read_text(encoding="utf-8")
            self.assertIn("行动中心", actions_html)
            self.assertIn('id="actionRows"', actions_html)
            self.assertIn("actions_filtered.csv", actions_html)
            self.assertIn("copyActionsQueue", actions_html)
            self.assertIn("renderActionRows", actions_html)
            self.assertIn("review.json", actions_html)
            self.assertIn("taxonomy_actions.json", actions_html)
            command_html = (report_dir / "command.html").read_text(encoding="utf-8")
            self.assertIn("命令中心", command_html)
            self.assertIn("Command JSON", command_html)
            self.assertIn("Daily Reading", command_html)
            self.assertIn("Taxonomy Governance", command_html)
            self.assertIn('id="commandSearch"', command_html)
            self.assertIn('id="copyCommandBootstrap"', command_html)
            self.assertIn("renderCommandLanes", command_html)
            dashboard_html = (report_dir / "dashboard.html").read_text(encoding="utf-8")
            self.assertIn("分类均衡度", dashboard_html)
            self.assertIn("均衡分", dashboard_html)
            self.assertIn("LLM Systems", dashboard_html)
            collections_html = (report_dir / "collections.html").read_text(encoding="utf-8")
            self.assertIn("集合视图", collections_html)
            self.assertIn("Collections JSON", collections_html)
            self.assertIn("共享视图", collections_html)
            self.assertIn("重点队列", collections_html)
            self.assertIn("智能集合", collections_html)
            self.assertIn("需建复习计划", collections_html)
            self.assertIn("分类偏薄", collections_html)
            self.assertIn("分类过密", collections_html)
            collections = json.loads((report_dir / "collections.json").read_text(encoding="utf-8"))
            self.assertEqual(collections["count"], 2)
            self.assertEqual(collections["shared_view_count"], len(collections["shared_views"]))
            self.assertEqual(collections["smart_collection_count"], len(collections["smart_collections"]))
            self.assertEqual(collections["research_line_count"], len(collections["research_lines"]))
            self.assertTrue(any(view["name"] == "重点队列" for view in collections["shared_views"]))
            self.assertTrue(any(item["id"] == "needs_review_plan" for item in collections["smart_collections"]))
            serving_line = next(item for item in collections["research_lines"] if item["name"] == "LLM Serving")
            self.assertIn("2601.00001-alpha-paper", serving_line["slugs"])
            self.assertIn("sample_papers", serving_line)
            balance_html = (report_dir / "balance.html").read_text(encoding="utf-8")
            self.assertIn("分类均衡复盘", balance_html)
            self.assertIn('id="balanceRows"', balance_html)
            self.assertIn('id="balanceSort"', balance_html)
            self.assertIn("taxonomy_balance_filtered.csv", balance_html)
            self.assertIn("copyBalanceMarkdownQueue", balance_html)
            self.assertIn("renderBalanceRows", balance_html)
            self.assertIn("LLM Systems", balance_html)
            coverage_html = (report_dir / "coverage.html").read_text(encoding="utf-8")
            self.assertIn("研究线分类覆盖地图", coverage_html)
            self.assertIn("Coverage JSON", coverage_html)
            self.assertIn("Owner", coverage_html)
            self.assertIn("serving-owner", coverage_html)
            self.assertIn('id="coverageRows"', coverage_html)
            self.assertIn('id="coverageSort"', coverage_html)
            self.assertIn("research_line_coverage.csv", coverage_html)
            self.assertIn("copyCoverageQueue", coverage_html)
            self.assertIn("renderCoverageRows", coverage_html)
            self.assertIn("LLM Serving", coverage_html)
            facets_html = (report_dir / "facets.html").read_text(encoding="utf-8")
            self.assertIn("分类工作台", facets_html)
            self.assertIn("字段概览", facets_html)
            self.assertIn('id="facetSearch"', facets_html)
            self.assertIn('id="facetField"', facets_html)
            self.assertIn('id="facetSeverity"', facets_html)
            self.assertIn('id="facetAction"', facets_html)
            self.assertIn('id="facetResultCount"', facets_html)
            self.assertIn('id="downloadFacetCsv"', facets_html)
            self.assertIn('id="copyFacetMarkdown"', facets_html)
            self.assertIn('id="copyFacetCommand"', facets_html)
            self.assertIn("taxonomyExportCommand", facets_html)
            self.assertIn("field_key", facets_html)
            self.assertIn("facet_actions_filtered.csv", facets_html)
            self.assertIn("long-tail", facets_html)
            self.assertIn("unused", facets_html)
            self.assertIn("taxonomy_actions.json", facets_html)
            self.assertIn("triaged", facets_html)
            self.assertIn("library.html?status=triaged", facets_html)
            related_html = (report_dir / "related.html").read_text(encoding="utf-8")
            self.assertIn("关联网络", related_html)
            self.assertIn("标签共现", related_html)
            self.assertIn("相似论文", related_html)
            self.assertIn("LLM Serving", related_html)
            taxonomy_html = (report_dir / "taxonomy.html").read_text(encoding="utf-8")
            self.assertIn("状态工作流配置", taxonomy_html)
            self.assertIn("状态工作流设计器", taxonomy_html)
            self.assertIn('id="workflowSource"', taxonomy_html)
            self.assertIn("knownWorkflows", taxonomy_html)
            self.assertIn("loadWorkflow", taxonomy_html)
            self.assertIn("taxonomy_status_workflow.json", taxonomy_html)
            self.assertIn("治理策略配置", taxonomy_html)
            self.assertIn("治理策略设计器", taxonomy_html)
            self.assertIn('id="downloadPolicy"', taxonomy_html)
            self.assertIn("taxonomy_governance_policy.json", taxonomy_html)
            self.assertIn("apply_governance_policy.py", taxonomy_html)
            self.assertIn("&quot;governance_policy&quot;: {", taxonomy_html)
            self.assertIn("分类变更预览", taxonomy_html)
            self.assertIn('id="taxonomyChangeField"', taxonomy_html)
            self.assertIn("taxonomy_change_patch.csv", taxonomy_html)
            self.assertIn("currentChanges", taxonomy_html)
            self.assertIn("&quot;status_values&quot;: [", taxonomy_html)
            self.assertIn("triaged", taxonomy_html)
            self.assertIn("KV-cache -&gt; KV Cache", taxonomy_html)
            timeline_html = (report_dir / "timeline.html").read_text(encoding="utf-8")
            self.assertIn("研究路线时间轴", timeline_html)
            self.assertIn('id="timelineLine"', timeline_html)
            self.assertIn('id="timelineWorkflow"', timeline_html)
            self.assertIn('id="timelineCopyLink"', timeline_html)
            self.assertIn('id="timelineActiveFilters"', timeline_html)
            self.assertIn("applyTimelineWorkflow", timeline_html)
            self.assertIn("workflowValuesFor", timeline_html)
            self.assertIn("readTimelineStateFromUrl", timeline_html)
            self.assertIn("writeTimelineStateToUrl", timeline_html)
            self.assertIn("renderTimelineActiveFilters", timeline_html)
            self.assertIn("clearTimelineFilter", timeline_html)
            self.assertIn('data-year="2026"', timeline_html)
            self.assertIn("LLM Serving", timeline_html)
            line_index_html = (report_dir / "lines" / "index.html").read_text(encoding="utf-8")
            self.assertIn('const prefix = "../";', line_index_html)
            matrix_html = (report_dir / "matrix.html").read_text(encoding="utf-8")
            self.assertIn("研究线年份矩阵", matrix_html)
            self.assertIn('id="matrixTrack"', matrix_html)
            self.assertIn('id="matrixWorkflow"', matrix_html)
            self.assertIn('id="matrixCopyLink"', matrix_html)
            self.assertIn('id="matrixActiveFilters"', matrix_html)
            self.assertIn("applyMatrixWorkflow", matrix_html)
            self.assertIn("matrixWorkflowValues", matrix_html)
            self.assertIn("readMatrixStateFromUrl", matrix_html)
            self.assertIn("writeMatrixStateToUrl", matrix_html)
            self.assertIn("renderMatrixActiveFilters", matrix_html)
            self.assertIn("clearMatrixFilter", matrix_html)
            self.assertIn('class="research-matrix"', matrix_html)
            self.assertIn("LLM Serving", matrix_html)
            gaps_html = (report_dir / "gaps.html").read_text(encoding="utf-8")
            self.assertIn("研究缺口与下一步行动", gaps_html)
            self.assertIn("研究线健康卡片", gaps_html)
            self.assertIn("Gaps JSON", gaps_html)
            self.assertIn("LLM Serving", gaps_html)
            self.assertIn("需建复习计划", gaps_html)
            self.assertIn("粒度提示", gaps_html)
            self.assertIn("分类偏薄", gaps_html)
            gaps = json.loads((report_dir / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual(gaps["count"], 2)
            self.assertTrue(gaps["actions"])
            self.assertIn("needs_review_plan", gaps["queues"])
            self.assertTrue(any(item["line"] == "LLM Serving" for item in gaps["lines"]))

            csv_path = report_dir / "library.csv"
            self.run_cmd("scripts/export_library_csv.py", str(report_dir), "--output", str(csv_path))
            rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))
            self.assertEqual(len(rows), 2)
            row_by_slug = {row["slug"]: row for row in rows}
            self.assertEqual(row_by_slug["2601.00001-alpha-paper"]["review_state"], "needs_plan")
            self.assertEqual(row_by_slug["2501.00002-beta-paper"]["review_state"], "scheduled")
            self.assertTrue(row_by_slug["2601.00001-alpha-paper"]["suggested_next_review"])
            self.assertTrue(row_by_slug["2601.00001-alpha-paper"]["quality_score"])

            dry_aliases = self.run_cmd("scripts/apply_taxonomy_aliases.py", str(report_dir))
            self.assertIn("DRY  KV-cache -> KV Cache", dry_aliases.stdout)
            taxonomy_before = json.loads((report_dir / "guides" / "taxonomy.json").read_text(encoding="utf-8"))
            self.assertNotIn("KV-cache", taxonomy_before["label_aliases"])
            self.run_cmd("scripts/apply_taxonomy_aliases.py", str(report_dir), "--write")
            taxonomy_after = json.loads((report_dir / "guides" / "taxonomy.json").read_text(encoding="utf-8"))
            self.assertEqual(taxonomy_after["label_aliases"]["KV-cache"], "KV Cache")
            self.run_cmd("scripts/build_wiki.py", str(report_dir))
            quality_after_alias = json.loads((report_dir / "quality.json").read_text(encoding="utf-8"))
            self.assertEqual(quality_after_alias["label_alias_suggestions"], [])

            registry_path = report_dir / "exports" / "taxonomy-registry.md"
            self.run_cmd(
                "scripts/export_taxonomy_registry.py",
                str(report_dir),
                "--signal",
                "singleton",
                "--output",
                str(registry_path),
            )
            registry_md = registry_path.read_text(encoding="utf-8")
            self.assertIn("# Taxonomy Label Registry", registry_md)
            self.assertIn("singleton", registry_md)

            registry_project_path = report_dir / "exports" / "taxonomy-registry-project.csv"
            self.run_cmd(
                "scripts/export_taxonomy_registry.py",
                str(report_dir),
                "--format",
                "project",
                "--severity",
                "medium",
                "--assignee",
                "taxonomy-owner",
                "--task-status",
                "ready",
                "--output",
                str(registry_project_path),
            )
            registry_project_rows = list(csv.DictReader(registry_project_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(registry_project_rows)
            self.assertEqual(registry_project_rows[0]["status"], "ready")
            self.assertEqual(registry_project_rows[0]["assignee"], "taxonomy-owner")
            self.assertIn("taxonomy_registry", registry_project_rows[0]["labels"])

            registry_patch_path = report_dir / "exports" / "taxonomy-registry-patch.csv"
            self.run_cmd(
                "scripts/export_taxonomy_registry.py",
                str(report_dir),
                "--format",
                "patch",
                "--signal",
                "singleton",
                "--target-value",
                "Unified Label",
                "--output",
                str(registry_patch_path),
            )
            registry_patch_rows = list(csv.DictReader(registry_patch_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(registry_patch_rows)
            self.assertIn("source_value", registry_patch_rows[0])
            self.assertIn("source_field", registry_patch_rows[0])
            self.assertIn("Unified Label", "; ".join(registry_patch_rows[0].values()))
            registry_patch_apply = self.run_cmd(
                "scripts/apply_library_metadata.py",
                str(report_dir),
                "--input",
                str(registry_patch_path),
            )
            self.assertIn("DRY", registry_patch_apply.stdout)

            unsafe_registry_export = self.run_cmd(
                "scripts/export_taxonomy_registry.py",
                str(report_dir),
                "--output",
                str(report_dir / "taxonomy-registry.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_registry_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_registry_export.stderr)

            taxonomy_actions_path = report_dir / "exports" / "taxonomy-actions.md"
            self.run_cmd(
                "scripts/export_taxonomy_actions.py",
                str(report_dir),
                "--action",
                "unused_config",
                "--output",
                str(taxonomy_actions_path),
            )
            taxonomy_actions_md = taxonomy_actions_path.read_text(encoding="utf-8")
            self.assertIn("# Taxonomy Action Queue", taxonomy_actions_md)
            self.assertIn("unused_config", taxonomy_actions_md)
            self.assertIn("triaged", taxonomy_actions_md)

            taxonomy_actions_csv_path = report_dir / "exports" / "taxonomy-actions.csv"
            self.run_cmd(
                "scripts/export_taxonomy_actions.py",
                str(report_dir),
                "--format",
                "csv",
                "--severity",
                "medium",
                "--output",
                str(taxonomy_actions_csv_path),
            )
            taxonomy_action_rows = list(csv.DictReader(taxonomy_actions_csv_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(taxonomy_action_rows)
            self.assertIn("severity", taxonomy_action_rows[0])

            taxonomy_actions_field_path = report_dir / "exports" / "taxonomy-actions-field.csv"
            self.run_cmd(
                "scripts/export_taxonomy_actions.py",
                str(report_dir),
                "--format",
                "csv",
                "--field",
                "status",
                "--output",
                str(taxonomy_actions_field_path),
            )
            taxonomy_field_rows = list(csv.DictReader(taxonomy_actions_field_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(taxonomy_field_rows)
            self.assertEqual({row["field"] for row in taxonomy_field_rows}, {"status"})

            taxonomy_project_path = report_dir / "exports" / "taxonomy-project.csv"
            self.run_cmd(
                "scripts/export_taxonomy_actions.py",
                str(report_dir),
                "--format",
                "project",
                "--severity",
                "medium",
                "--assignee",
                "taxonomy-owner",
                "--task-status",
                "ready",
                "--due-date",
                "2026-07-01",
                "--output",
                str(taxonomy_project_path),
            )
            taxonomy_project_rows = list(csv.DictReader(taxonomy_project_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(taxonomy_project_rows)
            self.assertEqual(taxonomy_project_rows[0]["status"], "ready")
            self.assertEqual(taxonomy_project_rows[0]["assignee"], "taxonomy-owner")
            self.assertEqual(taxonomy_project_rows[0]["due_date"], "2026-07-01")
            self.assertIn("taxonomy", taxonomy_project_rows[0]["labels"])
            self.assertIn("taxonomy value", taxonomy_project_rows[0]["title"])
            self.assertIn("Count:", taxonomy_project_rows[0]["body"])

            taxonomy_patch_path = report_dir / "exports" / "taxonomy-action-patch.csv"
            self.run_cmd(
                "scripts/export_taxonomy_actions.py",
                str(report_dir),
                "--format",
                "patch",
                "--action",
                "merge_candidate",
                "--target-value",
                "Unified Label",
                "--output",
                str(taxonomy_patch_path),
            )
            taxonomy_patch_rows = list(csv.DictReader(taxonomy_patch_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(taxonomy_patch_rows)
            self.assertIn("slug", taxonomy_patch_rows[0])
            self.assertIn("source_value", taxonomy_patch_rows[0])
            self.assertIn("action", taxonomy_patch_rows[0])
            self.assertIn("Unified Label", "; ".join(taxonomy_patch_rows[0].values()))
            taxonomy_patch_apply = self.run_cmd(
                "scripts/apply_library_metadata.py",
                str(report_dir),
                "--input",
                str(taxonomy_patch_path),
            )
            self.assertIn("DRY", taxonomy_patch_apply.stdout)

            taxonomy_balance_path = report_dir / "exports" / "taxonomy-balance.md"
            self.run_cmd(
                "scripts/export_taxonomy_balance.py",
                str(report_dir),
                "--max-score",
                "50",
                "--output",
                str(taxonomy_balance_path),
            )
            taxonomy_balance_md = taxonomy_balance_path.read_text(encoding="utf-8")
            self.assertIn("# Taxonomy Balance Review", taxonomy_balance_md)
            self.assertIn("LLM Systems", taxonomy_balance_md)
            self.assertIn("Recommendation:", taxonomy_balance_md)

            taxonomy_balance_project_path = report_dir / "exports" / "taxonomy-balance-project.csv"
            self.run_cmd(
                "scripts/export_taxonomy_balance.py",
                str(report_dir),
                "--format",
                "project",
                "--max-score",
                "50",
                "--assignee",
                "taxonomy-owner",
                "--output",
                str(taxonomy_balance_project_path),
            )
            taxonomy_balance_project_rows = list(csv.DictReader(taxonomy_balance_project_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(taxonomy_balance_project_rows)
            self.assertEqual(taxonomy_balance_project_rows[0]["assignee"], "taxonomy-owner")
            self.assertIn("Review taxonomy balance", taxonomy_balance_project_rows[0]["title"])
            self.assertIn("taxonomy_balance", taxonomy_balance_project_rows[0]["labels"])

            unsafe_taxonomy_export = self.run_cmd(
                "scripts/export_taxonomy_actions.py",
                str(report_dir),
                "--output",
                str(report_dir / "taxonomy-actions.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_taxonomy_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_taxonomy_export.stderr)

            unsafe_taxonomy_balance_export = self.run_cmd(
                "scripts/export_taxonomy_balance.py",
                str(report_dir),
                "--output",
                str(report_dir / "taxonomy-balance.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_taxonomy_balance_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_taxonomy_balance_export.stderr)

            taxonomy_load_path = report_dir / "exports" / "taxonomy-load.md"
            self.run_cmd(
                "scripts/export_taxonomy_load.py",
                str(report_dir),
                "--signal",
                "sparse_tags",
                "--output",
                str(taxonomy_load_path),
            )
            taxonomy_load_md = taxonomy_load_path.read_text(encoding="utf-8")
            self.assertIn("# Taxonomy Load Audit", taxonomy_load_md)
            self.assertIn("sparse_tags", taxonomy_load_md)
            self.assertIn("2601.00001-alpha-paper", taxonomy_load_md)

            taxonomy_load_csv_path = report_dir / "exports" / "taxonomy-load.csv"
            self.run_cmd(
                "scripts/export_taxonomy_load.py",
                str(report_dir),
                "--format",
                "csv",
                "--output",
                str(taxonomy_load_csv_path),
            )
            taxonomy_load_rows = list(csv.DictReader(taxonomy_load_csv_path.read_text(encoding="utf-8").splitlines()))
            self.assertTrue(taxonomy_load_rows)
            self.assertIn("signals", taxonomy_load_rows[0])

            taxonomy_load_patch_path = report_dir / "exports" / "taxonomy-load-patch.csv"
            self.run_cmd(
                "scripts/export_taxonomy_load.py",
                str(report_dir),
                "--format",
                "patch",
                "--signal",
                "sparse_tags",
                "--output",
                str(taxonomy_load_patch_path),
            )
            taxonomy_load_patch_rows = list(csv.DictReader(taxonomy_load_patch_path.read_text(encoding="utf-8").splitlines()))
            self.assertEqual(len(taxonomy_load_patch_rows), 2)
            self.assertEqual(
                sorted(row["slug"] for row in taxonomy_load_patch_rows),
                ["2501.00002-beta-paper", "2601.00001-alpha-paper"],
            )
            alpha_patch = next(row for row in taxonomy_load_patch_rows if row["slug"] == "2601.00001-alpha-paper")
            self.assertEqual(alpha_patch["topics"], "LLM Serving")
            self.assertEqual(alpha_patch["methods"], "Speculative Decoding")
            self.assertEqual(alpha_patch["research_line"], "LLM Serving")
            patch_dry_run = self.run_cmd(
                "scripts/apply_library_metadata.py",
                str(report_dir),
                "--input",
                str(taxonomy_load_patch_path),
                "--field",
                "topics",
            )
            self.assertIn("no metadata changes", patch_dry_run.stdout)

            unsafe_taxonomy_load_export = self.run_cmd(
                "scripts/export_taxonomy_load.py",
                str(report_dir),
                "--output",
                str(report_dir / "taxonomy-load.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_taxonomy_load_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_taxonomy_load_export.stderr)

            reading_list_path = report_dir / "exports" / "reading-list.md"
            self.run_cmd(
                "scripts/export_reading_list.py",
                str(report_dir),
                "--line",
                "LLM Serving",
                "--min-importance",
                "5",
                "--output",
                str(reading_list_path),
            )
            reading_list = reading_list_path.read_text(encoding="utf-8")
            self.assertIn("Alpha Paper", reading_list)
            self.assertNotIn("Beta Paper", reading_list)

            bib_path = report_dir / "exports" / "library.bib"
            self.run_cmd(
                "scripts/export_reading_list.py",
                str(report_dir),
                "--format",
                "bibtex",
                "--track",
                "Attention Kernels",
                "--output",
                str(bib_path),
            )
            bibtex = bib_path.read_text(encoding="utf-8")
            self.assertIn("@misc", bibtex)
            self.assertIn("Beta Paper", bibtex)
            self.assertNotIn("Alpha Paper", bibtex)
            unsafe_export = self.run_cmd(
                "scripts/export_reading_list.py",
                str(report_dir),
                "--output",
                str(report_dir / "reading-list.md"),
                check=False,
            )
            self.assertNotEqual(unsafe_export.returncode, 0)
            self.assertIn("Refusing to write a Markdown export", unsafe_export.stderr)

            patch_path = report_dir / "metadata_patch.csv"
            with patch_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["slug", "status", "topics", "methods"])
                writer.writeheader()
                writer.writerow(
                    {
                        "slug": "2601.00001-alpha-paper",
                        "status": "triaged",
                        "topics": "LLM Serving; Request Scheduling",
                        "methods": "Speculative Decoding; queueing",
                    }
                )

            dry_metadata = self.run_cmd(
                "scripts/apply_library_metadata.py",
                str(report_dir),
                "--input",
                str(patch_path),
            )
            self.assertIn("DRY  2601.00001-alpha-paper", dry_metadata.stdout)
            self.assertNotIn("status: triaged", (report_dir / "2601.00001-alpha-paper.md").read_text(encoding="utf-8"))
            audit_path = report_dir / "exports" / "metadata-audit.json"
            audited_metadata = self.run_cmd(
                "scripts/apply_library_metadata.py",
                str(report_dir),
                "--input",
                str(patch_path),
                "--audit-output",
                str(audit_path),
            )
            self.assertIn("audit written", audited_metadata.stdout)
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(audit["mode"], "dry_run")
            self.assertFalse(audit["write"])
            self.assertEqual(audit["summary"]["changed_reports"], 1)
            self.assertEqual(audit["summary"]["changed_fields"]["status"], 1)
            self.assertEqual(audit["reports"][0]["slug"], "2601.00001-alpha-paper")
            self.assertEqual(audit["reports"][0]["changes"][0]["field"], "status")
            self.assertEqual(audit["reports"][0]["changes"][0]["after"], "triaged")

            self.run_cmd(
                "scripts/apply_library_metadata.py",
                str(report_dir),
                "--input",
                str(patch_path),
                "--write",
            )
            metadata_updated = (report_dir / "2601.00001-alpha-paper.md").read_text(encoding="utf-8")
            self.assertIn("status: triaged", metadata_updated)
            self.assertIn("  - Request Scheduling", metadata_updated)
            self.assertIn("  - queueing", metadata_updated)

            append_patch_path = report_dir / "metadata_append_patch.csv"
            with append_patch_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["slug", "_list_mode", "topics", "methods"])
                writer.writeheader()
                writer.writerow(
                    {
                        "slug": "2601.00001-alpha-paper",
                        "_list_mode": "append",
                        "topics": "Long Context; Request Scheduling",
                        "methods": "Speculative Decoding",
                    }
                )

            append_dry = self.run_cmd(
                "scripts/apply_library_metadata.py",
                str(report_dir),
                "--input",
                str(append_patch_path),
            )
            self.assertIn("topics (append)", append_dry.stdout)
            self.run_cmd(
                "scripts/apply_library_metadata.py",
                str(report_dir),
                "--input",
                str(append_patch_path),
                "--write",
            )
            metadata_appended = (report_dir / "2601.00001-alpha-paper.md").read_text(encoding="utf-8")
            self.assertIn("  - Request Scheduling", metadata_appended)
            self.assertIn("  - Long Context", metadata_appended)
            self.assertIn("  - Speculative Decoding", metadata_appended)

            remove_patch_path = report_dir / "metadata_remove_patch.csv"
            with remove_patch_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["slug", "topics"])
                writer.writeheader()
                writer.writerow({"slug": "2601.00001-alpha-paper", "topics": "Request Scheduling"})

            remove_dry = self.run_cmd(
                "scripts/apply_library_metadata.py",
                str(report_dir),
                "--input",
                str(remove_patch_path),
                "--list-mode",
                "remove",
            )
            self.assertIn("topics (remove)", remove_dry.stdout)
            self.run_cmd(
                "scripts/apply_library_metadata.py",
                str(report_dir),
                "--input",
                str(remove_patch_path),
                "--list-mode",
                "remove",
                "--write",
            )
            metadata_removed = (report_dir / "2601.00001-alpha-paper.md").read_text(encoding="utf-8")
            self.assertNotIn("  - Request Scheduling", metadata_removed)
            self.assertIn("  - Long Context", metadata_removed)

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

    def test_apply_inbox_items_merges_candidate_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            report_dir = self.make_report_dir(Path(tmp_name))
            self.run_cmd("scripts/build_wiki.py", str(report_dir))

            candidate_path = Path(tmp_name) / "candidate_papers.csv"
            candidate_path.write_text(
                "name,url,status,priority,topics,notes,created_at\n"
                "Delta Paper,https://arxiv.org/abs/2603.00004,,high,LLM Serving|Planning,新候选,2026-07-02\n"
                "Gamma Paper,https://arxiv.org/abs/2602.00003,triaged,medium,LLM Serving;Batching,更新备注,2026-07-03\n",
                encoding="utf-8",
            )

            dry = self.run_cmd("scripts/apply_inbox_items.py", str(report_dir), "--input", str(candidate_path))
            self.assertIn("DRY  ADD inbox item Delta Paper", dry.stdout)
            self.assertIn("DRY  UPDATE inbox item Gamma Paper", dry.stdout)
            inbox_before = list(csv.DictReader((report_dir / "inbox.csv").read_text(encoding="utf-8").splitlines()))
            self.assertEqual(len(inbox_before), 2)

            write = self.run_cmd(
                "scripts/apply_inbox_items.py",
                str(report_dir),
                "--input",
                str(candidate_path),
                "--write",
            )
            self.assertIn("WRITE  ADD inbox item Delta Paper", write.stdout)
            inbox_after = list(csv.DictReader((report_dir / "inbox.csv").read_text(encoding="utf-8").splitlines()))
            self.assertEqual(len(inbox_after), 3)
            rows_by_title = {row["title"]: row for row in inbox_after}
            self.assertEqual(rows_by_title["Delta Paper"]["tags"], "LLM Serving; Planning")
            self.assertEqual(rows_by_title["Gamma Paper"]["status"], "triaged")
            self.assertEqual(rows_by_title["Gamma Paper"]["note"], "更新备注")

            self.run_cmd("scripts/build_wiki.py", str(report_dir))
            self.run_cmd("scripts/validate_wiki.py", str(report_dir), "--strict-taxonomy")
            inbox_json = json.loads((report_dir / "inbox.json").read_text(encoding="utf-8"))
            self.assertEqual(inbox_json["count"], 3)
            self.assertTrue(any(item["title"] == "Delta Paper" for item in inbox_json["items"]))
            actions = json.loads((report_dir / "actions.json").read_text(encoding="utf-8"))
            self.assertTrue(any(item["source"] == "inbox.json" and "Delta Paper" in item["title"] for item in actions["actions"]))

            broken_path = Path(tmp_name) / "broken_candidates.csv"
            broken_path.write_text("title,link,status\nBad,https://example.com,unknown\n", encoding="utf-8")
            broken = self.run_cmd(
                "scripts/apply_inbox_items.py",
                str(report_dir),
                "--input",
                str(broken_path),
                check=False,
            )
            self.assertNotEqual(broken.returncode, 0)
            self.assertIn("status must be one of", broken.stderr)

    def test_quality_detects_duplicate_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            report_dir = self.make_report_dir(Path(tmp_name))
            duplicate = REPORT_A.replace("2601.00001-alpha-paper", "2601.00001-alpha-paper-copy")
            duplicate = duplicate.replace("Alpha 论文", "Alpha 论文副本", 1)
            (report_dir / "2601.00001-alpha-paper-copy.md").write_text(duplicate, encoding="utf-8")
            (report_dir / "2601.00001-alpha-paper-copy.html").write_text(
                "<!doctype html><title>duplicate</title><h1>duplicate</h1>",
                encoding="utf-8",
            )

            self.run_cmd("scripts/build_wiki.py", str(report_dir))
            self.run_cmd("scripts/validate_wiki.py", str(report_dir))
            quality = json.loads((report_dir / "quality.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["duplicate_reports"][0]["reason"], "arxiv_id")
            self.assertEqual(
                quality["duplicate_reports"][0]["slugs"],
                ["2601.00001-alpha-paper", "2601.00001-alpha-paper-copy"],
            )
            self.assertEqual(
                quality["queues"]["duplicate_reports"],
                ["2601.00001-alpha-paper", "2601.00001-alpha-paper-copy"],
            )
            manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["publish_checks"]["no_duplicate_reports"])
            dedupe = json.loads((report_dir / "dedupe.json").read_text(encoding="utf-8"))
            self.assertEqual(dedupe["duplicate_report_count"], 1)
            self.assertEqual(dedupe["report_groups"][0]["severity"], "high")
            self.assertEqual(
                dedupe["report_groups"][0]["slugs"],
                ["2601.00001-alpha-paper", "2601.00001-alpha-paper-copy"],
            )
            quality_html = (report_dir / "quality.html").read_text(encoding="utf-8")
            self.assertIn("库内重复报告", quality_html)
            self.assertIn("2601.00001-alpha-paper-copy", quality_html)
            dedupe_html = (report_dir / "dedupe.html").read_text(encoding="utf-8")
            self.assertIn("去重工作台", dedupe_html)
            self.assertIn("2601.00001-alpha-paper-copy", dedupe_html)

    def test_apply_status_workflow_merges_dynamic_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            report_dir = self.make_report_dir(Path(tmp_name))
            self.run_cmd("scripts/build_wiki.py", str(report_dir))

            workflow_path = Path(tmp_name) / "taxonomy_status_workflow.json"
            workflow_path.write_text(
                json.dumps(
                    {
                        "active_status_workflow": "lab",
                        "status_workflows": {
                            "lab": {
                                "status_values": ["queued", "reading", "read", "implemented", "shelved"],
                                "reading_stage_values": ["skimmed", "deep_read", "code_checked"],
                                "review_stage_values": ["fresh", "due", "reviewed", "evergreen"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            dry = self.run_cmd("scripts/apply_status_workflow.py", str(report_dir), "--input", str(workflow_path))
            self.assertIn("DRY  ADD workflow lab", dry.stdout)
            taxonomy_before = json.loads((report_dir / "guides" / "taxonomy.json").read_text(encoding="utf-8"))
            self.assertEqual(taxonomy_before["active_status_workflow"], "research")
            self.assertNotIn("lab", taxonomy_before["status_workflows"])

            write = self.run_cmd(
                "scripts/apply_status_workflow.py",
                str(report_dir),
                "--input",
                str(workflow_path),
                "--write",
            )
            self.assertIn("WRITE  ADD workflow lab", write.stdout)
            taxonomy_after = json.loads((report_dir / "guides" / "taxonomy.json").read_text(encoding="utf-8"))
            self.assertEqual(taxonomy_after["active_status_workflow"], "lab")
            self.assertIn("research", taxonomy_after["status_workflows"])
            self.assertEqual(taxonomy_after["status_values"], ["queued", "reading", "read", "implemented", "shelved"])
            self.assertEqual(taxonomy_after["reading_stage_values"], ["skimmed", "deep_read", "code_checked"])
            self.assertEqual(taxonomy_after["review_stage_values"], ["fresh", "due", "reviewed", "evergreen"])

            self.run_cmd("scripts/build_wiki.py", str(report_dir))
            self.run_cmd("scripts/validate_wiki.py", str(report_dir), "--strict-taxonomy")
            papers = json.loads((report_dir / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(papers["controls"]["active_status_workflow"], "lab")
            self.assertEqual(papers["controls"]["status"], ["queued", "reading", "read", "implemented", "shelved"])
            self.assertIn("lab", papers["controls"]["status_workflows"])

            broken_path = Path(tmp_name) / "broken_status_workflow.json"
            broken_path.write_text(
                json.dumps({"name": "broken", "status_values": ["read"]}),
                encoding="utf-8",
            )
            broken = self.run_cmd(
                "scripts/apply_status_workflow.py",
                str(report_dir),
                "--input",
                str(broken_path),
                check=False,
            )
            self.assertNotEqual(broken.returncode, 0)
            self.assertIn("missing required keys", broken.stderr)

    def test_apply_governance_policy_merges_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            report_dir = self.make_report_dir(Path(tmp_name))
            self.run_cmd("scripts/build_wiki.py", str(report_dir))

            policy_path = Path(tmp_name) / "taxonomy_governance_policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "governance_policy": {
                            "taxonomy_load": {"min_tags": 7},
                            "taxonomy_actions": {"split_share": 0.5},
                        }
                    }
                ),
                encoding="utf-8",
            )

            dry = self.run_cmd("scripts/apply_governance_policy.py", str(report_dir), "--input", str(policy_path))
            self.assertIn("DRY  UPDATE taxonomy_load.min_tags 5 -> 7", dry.stdout)
            self.assertIn("DRY  UPDATE taxonomy_actions.split_share 0.6 -> 0.5", dry.stdout)
            taxonomy_before = json.loads((report_dir / "guides" / "taxonomy.json").read_text(encoding="utf-8"))
            self.assertEqual(taxonomy_before["governance_policy"]["taxonomy_load"]["min_tags"], 5)

            write = self.run_cmd(
                "scripts/apply_governance_policy.py",
                str(report_dir),
                "--input",
                str(policy_path),
                "--write",
            )
            self.assertIn("WRITE  UPDATE taxonomy_load.min_tags 5 -> 7", write.stdout)
            taxonomy_after = json.loads((report_dir / "guides" / "taxonomy.json").read_text(encoding="utf-8"))
            self.assertEqual(taxonomy_after["governance_policy"]["taxonomy_load"]["min_tags"], 7)
            self.assertEqual(taxonomy_after["governance_policy"]["taxonomy_actions"]["split_share"], 0.5)

            self.run_cmd("scripts/build_wiki.py", str(report_dir))
            self.run_cmd("scripts/validate_wiki.py", str(report_dir), "--strict-taxonomy")
            quality = json.loads((report_dir / "quality.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["governance_policy"]["taxonomy_load"]["min_tags"], 7)

            broken_path = Path(tmp_name) / "broken_governance_policy.json"
            broken_path.write_text(
                json.dumps({"governance_policy": {"taxonomy_load": {"min_tags": -1}}}),
                encoding="utf-8",
            )
            broken = self.run_cmd(
                "scripts/apply_governance_policy.py",
                str(report_dir),
                "--input",
                str(broken_path),
                check=False,
            )
            self.assertNotEqual(broken.returncode, 0)
            self.assertIn("must be a non-negative integer", broken.stderr)

    def test_apply_shared_views_merges_saved_view_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            report_dir = self.make_report_dir(Path(tmp_name))
            self.run_cmd("scripts/build_wiki.py", str(report_dir))

            views_path = Path(tmp_name) / "library_saved_views.json"
            views_path.write_text(
                json.dumps(
                    {
                        "page": "library",
                        "saved_views": [
                            {
                                "name": "Kernel Deep Reads",
                                "state": {
                                    "track": "Attention Kernels",
                                    "workflow": "research",
                                    "stage": "deep_read",
                                    "sort": "year",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            dry = self.run_cmd("scripts/apply_shared_views.py", str(report_dir), "--input", str(views_path))
            self.assertIn("DRY  ADD shared view library / Kernel Deep Reads", dry.stdout)
            taxonomy_before = json.loads((report_dir / "guides" / "taxonomy.json").read_text(encoding="utf-8"))
            self.assertEqual(len(taxonomy_before["shared_views"]), 2)

            write = self.run_cmd(
                "scripts/apply_shared_views.py",
                str(report_dir),
                "--input",
                str(views_path),
                "--write",
            )
            self.assertIn("WRITE  ADD shared view library / Kernel Deep Reads", write.stdout)
            taxonomy_after = json.loads((report_dir / "guides" / "taxonomy.json").read_text(encoding="utf-8"))
            view_by_name = {view["name"]: view for view in taxonomy_after["shared_views"]}
            self.assertEqual(view_by_name["Kernel Deep Reads"]["page"], "library")
            self.assertEqual(view_by_name["Kernel Deep Reads"]["state"]["workflow"], "research")

            self.run_cmd("scripts/build_wiki.py", str(report_dir))
            self.run_cmd("scripts/validate_wiki.py", str(report_dir), "--strict-taxonomy")
            library_html = (report_dir / "library.html").read_text(encoding="utf-8")
            self.assertIn("Kernel Deep Reads", library_html)
            self.assertIn('"workflow": "research"', library_html)

            broken_path = Path(tmp_name) / "broken_shared_views.json"
            broken_path.write_text(
                json.dumps({"shared_views": [{"name": "Bad", "state": {"unknown": "x"}}]}),
                encoding="utf-8",
            )
            broken = self.run_cmd(
                "scripts/apply_shared_views.py",
                str(report_dir),
                "--input",
                str(broken_path),
                check=False,
            )
            self.assertNotEqual(broken.returncode, 0)
            self.assertIn("unknown state key", broken.stderr)

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
                        "active_status_workflow": "missing",
                        "status_workflows": {
                            "broken": {
                                "status_values": ["read", "read"],
                                "reading_stage_values": "deep_read",
                                "review_stage_values": [""],
                            }
                        },
                        "shared_views": [
                            {"name": "bad", "page": "sidebar", "state": {"unknown": "x"}},
                            {"name": "", "page": "all", "state": {}},
                        ],
                        "research_line_owners": {
                            "": {"owner": "nobody"},
                            "Broken Line": {"owner": "", "unknown": "x"},
                        },
                        "governance_policy": {
                            "taxonomy_load": {"min_tags": -1},
                            "unknown": {"x": 1},
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_cmd("scripts/validate_wiki.py", str(report_dir), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("guides/taxonomy.json", result.stderr)
            self.assertIn("duplicate value", result.stderr)
            self.assertIn("status_values must be a list", result.stderr)
            self.assertIn("active_status_workflow 'missing' is not defined", result.stderr)
            self.assertIn("status_workflows.broken.status_values has duplicate value", result.stderr)
            self.assertIn("status_workflows.broken.reading_stage_values must be a list", result.stderr)
            self.assertIn("shared_views[0].page", result.stderr)
            self.assertIn("shared_views[0].state has unknown keys", result.stderr)
            self.assertIn("shared_views[1].name", result.stderr)
            self.assertIn("research_line_owners keys must be non-empty strings", result.stderr)
            self.assertIn("research_line_owners.Broken Line has unknown keys", result.stderr)
            self.assertIn("research_line_owners.Broken Line.owner", result.stderr)
            self.assertIn("governance_policy has unknown sections", result.stderr)
            self.assertIn("governance_policy.taxonomy_load.min_tags", result.stderr)

    def test_invalid_taxonomy_schema_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            report_dir = self.make_report_dir(Path(tmp_name))
            self.run_cmd("scripts/build_wiki.py", str(report_dir))

            (report_dir / "guides" / "taxonomy.schema.json").write_text(
                json.dumps({"type": "array", "properties": {}}),
                encoding="utf-8",
            )
            result = self.run_cmd("scripts/validate_wiki.py", str(report_dir), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("guides/taxonomy.schema.json: $schema must be a non-empty string", result.stderr)
            self.assertIn("guides/taxonomy.schema.json: type must be object", result.stderr)
            self.assertIn("properties.status_workflows is required", result.stderr)
            self.assertIn("properties.shared_views is required", result.stderr)

    def test_invalid_inbox_csv_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            report_dir = self.make_report_dir(Path(tmp_name))
            (report_dir / "inbox.csv").write_text(
                "id,title,status,priority,added_at\n"
                "paper-1,Broken Candidate,unknown,urgent,2026-99-99\n"
                "paper-1,Duplicate Candidate,queued,high,2026-06-11\n",
                encoding="utf-8",
            )
            self.run_cmd("scripts/build_wiki.py", str(report_dir))

            result = self.run_cmd("scripts/validate_wiki.py", str(report_dir), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("inbox.csv missing required column(s): link", result.stderr)
            self.assertIn("inbox.csv row 2: status must be one of", result.stderr)
            self.assertIn("inbox.csv row 2: priority must be one of", result.stderr)
            self.assertIn("inbox.csv row 2: added_at must be a valid YYYY-MM-DD date", result.stderr)
            self.assertIn("inbox.csv row 3: duplicate id 'paper-1'", result.stderr)

    def test_strict_taxonomy_detects_report_value_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            report_dir = self.make_report_dir(Path(tmp_name))
            self.run_cmd("scripts/build_wiki.py", str(report_dir))

            beta_path = report_dir / "2501.00002-beta-paper.md"
            beta_path.write_text(
                beta_path.read_text(encoding="utf-8").replace("status: read", "status: half_read"),
                encoding="utf-8",
            )
            self.run_cmd("scripts/build_wiki.py", str(report_dir))
            quality = json.loads((report_dir / "quality.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["queues"]["taxonomy_drift"], ["2501.00002-beta-paper"])
            self.assertEqual(quality["taxonomy_drift"][0]["field"], "status")
            self.assertEqual(quality["taxonomy_drift"][0]["value"], "half_read")
            quality_html = (report_dir / "quality.html").read_text(encoding="utf-8")
            self.assertIn("half_read", quality_html)

            relaxed = self.run_cmd("scripts/validate_wiki.py", str(report_dir))
            self.assertEqual(relaxed.returncode, 0)
            self.assertIn("status 'half_read' is not in guides/taxonomy.json", relaxed.stderr)

            strict = self.run_cmd(
                "scripts/validate_wiki.py",
                str(report_dir),
                "--strict-taxonomy",
                check=False,
            )
            self.assertNotEqual(strict.returncode, 0)
            self.assertIn("status 'half_read' is not in guides/taxonomy.json", strict.stderr)

    def test_metadata_schema_detects_invalid_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            report_dir = self.make_report_dir(Path(tmp_name))
            alpha_path = report_dir / "2601.00001-alpha-paper.md"
            alpha_path.write_text(
                alpha_path.read_text(encoding="utf-8")
                .replace("importance: 5", "importance: 9")
                .replace("has_code: true", "has_code: yes")
                .replace(
                    "reading_stage: deep_read",
                    "reading_stage: deep_read\nlast_reviewed: 2026-99-30\nnext_review: 2026/06/30",
                ),
                encoding="utf-8",
            )

            self.run_cmd("scripts/build_wiki.py", str(report_dir))
            result = self.run_cmd("scripts/validate_wiki.py", str(report_dir), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("metadata 'importance' must be <= 5", result.stderr)
            self.assertIn("metadata 'has_code' must be true or false", result.stderr)
            self.assertIn("metadata 'last_reviewed' must be a valid calendar date", result.stderr)
            self.assertIn("metadata 'next_review' must be a YYYY-MM-DD date", result.stderr)


if __name__ == "__main__":
    unittest.main()
