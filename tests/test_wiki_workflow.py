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
                "inbox.html",
                "quality.html",
                "review.html",
                "dashboard.html",
                "release.html",
                "collections.html",
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
                "taxonomy_actions.json",
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
            self.assertNotIn("Kernel 方向", index_html)
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
            self.assertIn('id="quickOpen"', index_html)
            self.assertIn("快速跳转", index_html)
            self.assertIn("Data: manifest.json", index_html)
            self.assertIn("Command: taxonomy_balance_project", index_html)
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
            self.assertIn('id="newStatusName"', board_html)
            self.assertIn("新增状态列", board_html)
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
            quality = json.loads((report_dir / "quality.json").read_text(encoding="utf-8"))
            self.assertIn("taxonomy_drift", quality)
            self.assertEqual(quality["taxonomy_drift"], [])
            self.assertEqual(quality["queues"]["taxonomy_drift"], [])
            self.assertEqual(quality["queues"]["taxonomy_sparse"], ["2601.00001-alpha-paper"])
            self.assertEqual(quality["queues"]["taxonomy_dense"], [])
            self.assertEqual(quality["taxonomy_load"][0]["signals"], ["sparse_tags"])
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
            self.assertIn("python3 scripts/export_taxonomy_actions.py docs --format project --output docs/exports/taxonomy-project.csv", quality_html)
            self.assertIn("python3 scripts/export_taxonomy_balance.py docs --format project --max-score 50 --output docs/exports/taxonomy-balance-project.csv", quality_html)
            self.assertIn("python3 scripts/export_taxonomy_load.py docs --format patch --output docs/exports/taxonomy-load-patch.csv", quality_html)

            review = json.loads((report_dir / "review.json").read_text(encoding="utf-8"))
            self.assertEqual(review["count"], 2)
            self.assertEqual(review["queues"]["needs_plan"], ["2601.00001-alpha-paper"])
            self.assertEqual(review["queues"]["scheduled"], ["2501.00002-beta-paper"])
            review_html = (report_dir / "review.html").read_text(encoding="utf-8")
            self.assertIn('id="downloadReviewPatch"', review_html)
            self.assertIn("review_plan_patch.csv", review_html)
            taxonomy_actions = json.loads((report_dir / "taxonomy_actions.json").read_text(encoding="utf-8"))
            self.assertEqual(taxonomy_actions["paper_count"], 2)
            self.assertGreater(taxonomy_actions["summary"]["unused_config"], 0)
            triaged_action = next(item for item in taxonomy_actions["actions"] if item["field"] == "status" and item["value"] == "triaged")
            self.assertEqual(triaged_action["action"], "unused_config")
            self.assertEqual(triaged_action["href"], "library.html?status=triaged")
            stats = json.loads((report_dir / "stats.json").read_text(encoding="utf-8"))
            self.assertEqual(stats["count"], 2)
            self.assertIn("quality", stats["queue_sizes"])
            self.assertIn("review", stats["queue_sizes"])
            self.assertTrue(stats["research_lines"])
            self.assertEqual(stats["shared_views"], 2)
            self.assertEqual(stats["controls"]["review_stage"], ["fresh", "due", "reviewed"])
            self.assertIn("research", stats["controls"]["status_workflows"])
            self.assertTrue(stats["taxonomy_balance"])
            balance_by_field = {item["field"]: item for item in stats["taxonomy_balance"]}
            self.assertEqual(balance_by_field["domains"]["max_value"], "LLM Systems")
            self.assertEqual(balance_by_field["domains"]["max_share"], 1.0)
            self.assertIn("balance_score", balance_by_field["topics"])
            manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["count"], 2)
            self.assertTrue(manifest["publish_checks"]["no_duplicate_reports"])
            self.assertIn("release.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("facets.html", {item["href"] for item in manifest["pages"]})
            self.assertIn("taxonomy_actions.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("manifest.json", {item["href"] for item in manifest["data_files"]})
            self.assertIn("guides/report.template.md", {item["href"] for item in manifest["contract_files"]})
            self.assertIn("guides/metadata.schema.json", {item["href"] for item in manifest["contract_files"]})
            self.assertIn("guides/inbox.schema.json", {item["href"] for item in manifest["contract_files"]})
            self.assertIn("guides/taxonomy.schema.json", {item["href"] for item in manifest["contract_files"]})
            artifact_by_href = {item["href"]: item for item in manifest["artifact_inventory"]}
            self.assertEqual(artifact_by_href["index.html"]["status"], "ok")
            self.assertRegex(artifact_by_href["index.html"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(artifact_by_href["index.html"]["size_bytes"], 0)
            self.assertEqual(artifact_by_href["guides/report.template.md"]["kind"], "contract")
            self.assertEqual(artifact_by_href["guides/metadata.schema.json"]["kind"], "contract")
            self.assertEqual(artifact_by_href["guides/inbox.schema.json"]["kind"], "contract")
            self.assertEqual(artifact_by_href["guides/taxonomy.schema.json"]["kind"], "contract")
            self.assertEqual(artifact_by_href["manifest.json"]["status"], "generated_after_inventory")
            self.assertTrue(manifest["publish_checks"]["artifacts_present"])
            self.assertIn("python3 scripts/check_quality.py docs", manifest["commands"])
            self.assertIn("python3 scripts/export_taxonomy_load.py docs --format csv --output docs/exports/taxonomy-load.csv", manifest["commands"])
            recipe_by_id = {item["id"]: item for item in manifest["command_recipes"]}
            self.assertEqual(recipe_by_id["quality_gate"]["kind"], "check")
            self.assertFalse(recipe_by_id["quality_gate"]["mutates"])
            self.assertFalse(recipe_by_id["apply_metadata_dry_run"]["mutates"])
            self.assertEqual(recipe_by_id["apply_metadata_dry_run"]["command"], "python3 scripts/apply_library_metadata.py docs --input <csv>")
            self.assertEqual(recipe_by_id["taxonomy_balance_project"]["output"], "docs/exports/taxonomy-balance-project.csv")
            self.assertEqual(recipe_by_id["taxonomy_actions_patch"]["output"], "docs/exports/taxonomy-action-patch.csv")
            playbook_by_id = {item["id"]: item for item in manifest["governance_playbooks"]}
            self.assertEqual(
                playbook_by_id["taxonomy_merge_batch"]["steps"],
                ["taxonomy_actions_markdown", "taxonomy_actions_patch", "apply_metadata_dry_run", "quality_gate"],
            )
            release_html = (report_dir / "release.html").read_text(encoding="utf-8")
            self.assertIn("知识库发布摘要", release_html)
            self.assertIn("Manifest JSON", release_html)
            self.assertIn("推荐命令", release_html)
            self.assertIn("数据契约", release_html)
            self.assertIn("Artifact Inventory", release_html)
            self.assertIn("SHA-256", release_html)
            self.assertIn("guides/report.template.md", release_html)
            self.assertIn("guides/metadata.schema.json", release_html)
            self.assertIn("guides/inbox.schema.json", release_html)
            self.assertIn("guides/taxonomy.schema.json", release_html)
            self.assertIn("命令 Recipes", release_html)
            self.assertIn("治理 Playbooks", release_html)
            self.assertIn("Taxonomy merge batch", release_html)
            self.assertIn("复制命令组", release_html)
            self.assertIn("taxonomy_balance_project", release_html)
            self.assertIn("taxonomy_actions_patch", release_html)
            self.assertIn("copy-release-command", release_html)
            self.assertIn("copyReleaseCommand", release_html)
            dashboard_html = (report_dir / "dashboard.html").read_text(encoding="utf-8")
            self.assertIn("分类均衡度", dashboard_html)
            self.assertIn("均衡分", dashboard_html)
            self.assertIn("LLM Systems", dashboard_html)
            collections_html = (report_dir / "collections.html").read_text(encoding="utf-8")
            self.assertIn("集合视图", collections_html)
            self.assertIn("共享视图", collections_html)
            self.assertIn("重点队列", collections_html)
            self.assertIn("智能集合", collections_html)
            self.assertIn("需建复习计划", collections_html)
            self.assertIn("分类偏薄", collections_html)
            self.assertIn("分类过密", collections_html)
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
            self.assertIn("LLM Serving", gaps_html)
            self.assertIn("需建复习计划", gaps_html)
            self.assertIn("粒度提示", gaps_html)
            self.assertIn("分类偏薄", gaps_html)

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
            self.assertEqual(len(taxonomy_load_patch_rows), 1)
            self.assertEqual(taxonomy_load_patch_rows[0]["slug"], "2601.00001-alpha-paper")
            self.assertEqual(taxonomy_load_patch_rows[0]["topics"], "LLM Serving")
            self.assertEqual(taxonomy_load_patch_rows[0]["methods"], "Speculative Decoding")
            self.assertEqual(taxonomy_load_patch_rows[0]["research_line"], "LLM Serving")
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
            quality_html = (report_dir / "quality.html").read_text(encoding="utf-8")
            self.assertIn("库内重复报告", quality_html)
            self.assertIn("2601.00001-alpha-paper-copy", quality_html)

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
