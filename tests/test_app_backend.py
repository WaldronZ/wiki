from __future__ import annotations

import tempfile
import tarfile
import time
import unittest
from contextlib import closing
from os import environ, utime
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import AppConfig, load_config
from backend.app.db import (
    connect,
    create_job,
    get_quality_report,
    get_taxonomy_cleanup,
    get_job,
    get_paper,
    filter_papers,
    init_db,
    list_review_queue,
    list_research_lines,
    record_model_run,
    replace_paper_chunks,
    replace_paper_tags,
    search_papers,
    set_setting,
    update_job,
    update_paper_classification,
    upsert_paper,
    upsert_paper_search,
)
import backend.app.main as main_module
from backend.app.main import app
from backend.app.services.agent_runtime import CodeAnalystRuntime, HtmlPresenterRuntime
from backend.app.services.llm import LLMGenerationError, OpenAICompatibleProvider, effective_llm_settings, summarize_llm_http_error
from backend.app.services import ingestion
from backend.app.services.arxiv import ArxivMetadata, normalize_arxiv_input, parse_arxiv_atom
from backend.app.services.code import (
    CodeDiscovery,
    build_code_observation,
    find_code_url,
    normalize_repo_url,
    summarize_code_repo,
    validate_code_observation,
)
from backend.app.services.library import find_duplicate
from backend.app.services.report import (
    ReportContext,
    apply_code_observation,
    chunk_report,
    extract_external_arxiv_ids,
    extract_report_tags,
    parse_report_frontmatter,
)
from backend.app.services.semantic import (
    embed_text_local_hash,
    rebuild_semantic_index,
    semantic_search,
)
from backend.app.services.source import extract_source_package, find_main_tex


class BackendFoundationTest(unittest.TestCase):
    def test_normalize_arxiv_abs_and_pdf_links(self) -> None:
        abs_input = normalize_arxiv_input("https://arxiv.org/abs/1706.03762")
        pdf_input = normalize_arxiv_input("https://arxiv.org/pdf/1706.03762v5")

        self.assertEqual(abs_input.arxiv_id, "1706.03762")
        self.assertEqual(abs_input.pdf_url, "https://arxiv.org/pdf/1706.03762")
        self.assertEqual(pdf_input.arxiv_id, "1706.03762")
        self.assertEqual(pdf_input.eprint_url, "https://arxiv.org/e-print/1706.03762")

    def test_reject_non_arxiv_input(self) -> None:
        with self.assertRaises(ValueError):
            normalize_arxiv_input("not a paper")

    def test_schema_initializes_and_creates_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                job_id = create_job(
                    conn,
                    job_type="paper_import",
                    input_payload={"arxiv_id": "1706.03762"},
                )
                job = get_job(conn, job_id)

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["input"]["arxiv_id"], "1706.03762")

    def test_model_run_records_prompt_response_and_error_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                job_id = create_job(
                    conn,
                    job_type="paper_import",
                    input_payload={"arxiv_id": "1706.03762"},
                )
                run_id = record_model_run(
                    conn,
                    job_id=job_id,
                    provider="mock",
                    model="test-model",
                    prompt_version="report:v1",
                    prompt_text="Generate a report.",
                    response_text="Report body.",
                    input_tokens=5,
                    output_tokens=3,
                    error_message="",
                )
                row = conn.execute(
                    "SELECT * FROM model_runs WHERE id = ?",
                    (run_id,),
                ).fetchone()

        self.assertEqual(row["provider"], "mock")
        self.assertEqual(row["model"], "test-model")
        self.assertEqual(row["prompt_text"], "Generate a report.")
        self.assertEqual(row["response_text"], "Report body.")
        self.assertEqual(row["input_tokens"], 5)
        self.assertEqual(row["output_tokens"], 3)

    def test_duplicate_detection_checks_database_and_report_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "docs"
            report_dir.mkdir()
            db_path = root / "app.db"

            with closing(connect(db_path)) as conn:
                init_db(conn)
                report_match = report_dir / "1706.03762-attention.md"
                report_match.write_text("---\nslug: 1706.03762-attention\n---\n", encoding="utf-8")

                duplicate = find_duplicate(conn, report_dir, "1706.03762")
                self.assertTrue(duplicate.duplicate)
                self.assertEqual(duplicate.reason, "report_file_arxiv_prefix")
                self.assertEqual(duplicate.slug, "1706.03762-attention")

                conn.execute(
                    """
                    INSERT INTO papers (
                        slug, arxiv_id, title, report_md_path, created_at, updated_at
                    )
                    VALUES (
                        '2307.08691-flashattention-2',
                        '2307.08691',
                        'FlashAttention-2',
                        'docs/2307.08691-flashattention-2.md',
                        '2026-06-15T00:00:00+00:00',
                        '2026-06-15T00:00:00+00:00'
                    )
                    """
                )
                conn.commit()

                db_duplicate = find_duplicate(conn, report_dir, "2307.08691")

        self.assertTrue(db_duplicate.duplicate)
        self.assertEqual(db_duplicate.reason, "database_arxiv_id")
        self.assertEqual(db_duplicate.slug, "2307.08691-flashattention-2")

    def test_parse_arxiv_atom_metadata(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/1706.03762v7</id>
            <updated>2023-08-02T00:00:00Z</updated>
            <published>2017-06-12T17:57:34Z</published>
            <title>Attention Is All You Need</title>
            <summary>We propose a new simple network architecture, the Transformer.</summary>
            <author><name>Ashish Vaswani</name></author>
            <author><name>Noam Shazeer</name></author>
            <link href="http://arxiv.org/abs/1706.03762v7" rel="alternate" type="text/html"/>
            <link title="pdf" href="http://arxiv.org/pdf/1706.03762v7" rel="related" type="application/pdf"/>
          </entry>
        </feed>
        """
        metadata = parse_arxiv_atom(xml, "1706.03762")

        self.assertEqual(metadata.title, "Attention Is All You Need")
        self.assertEqual(metadata.year, 2017)
        self.assertEqual(metadata.authors, ["Ashish Vaswani", "Noam Shazeer"])
        self.assertEqual(metadata.pdf_url, "http://arxiv.org/pdf/1706.03762v7")

    def test_extract_source_package_and_find_main_tex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "src"
            fixture = root / "paper.tar.gz"
            tex_path = root / "paper.tex"
            tex_path.write_text(
                "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n",
                encoding="utf-8",
            )
            with tarfile.open(fixture, "w:gz") as archive:
                archive.add(tex_path, arcname="paper.tex")

            kind = extract_source_package(fixture, source_dir)
            main_tex = find_main_tex(source_dir)

        self.assertEqual(kind, "tar")
        self.assertIsNotNone(main_tex)
        self.assertEqual(main_tex.name, "paper.tex")

    def test_chunk_report_and_fts_search(self) -> None:
        markdown = """---
slug: 2601.00001-alpha-paper
title: Alpha Paper
title_zh: Alpha
title_en: Alpha Paper
arxiv_id: "2601.00001"
year: 2026
authors:
  - Ada
topics:
  - Serving
methods:
  - speculative decoding
status: unread
importance: 3
has_code: false
---

# Alpha

## 1. 基本情况

This report discusses speculative decoding verification.

## 8. 方法细节

Verification accepts or rejects draft tokens.
"""
        chunks = chunk_report(markdown, max_chars=80)
        self.assertGreaterEqual(len(chunks), 2)

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00001-alpha-paper",
                        "arxiv_id": "2601.00001",
                        "title": "Alpha Paper",
                        "authors": ["Ada"],
                        "abstract": "Speculative decoding paper.",
                    },
                )
                replace_paper_chunks(conn, "2601.00001-alpha-paper", chunks)
                upsert_paper_search(
                    conn,
                    slug="2601.00001-alpha-paper",
                    title="Alpha Paper",
                    abstract="Speculative decoding paper.",
                    report_text=markdown,
                    chunks="\n".join(chunk["text"] for chunk in chunks),
                )
                results = search_papers(conn, "draft tokens")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["slug"], "2601.00001-alpha-paper")

    def test_local_hash_embeddings_are_deterministic(self) -> None:
        first = embed_text_local_hash("speculative decoding verification", dimension=32)
        second = embed_text_local_hash("speculative decoding verification", dimension=32)

        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0)

    def test_semantic_index_and_search_over_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00001-alpha-paper",
                        "arxiv_id": "2601.00001",
                        "title": "Alpha Paper",
                        "abstract": "Draft model verification.",
                    },
                )
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00002-beta-paper",
                        "arxiv_id": "2601.00002",
                        "title": "Beta Paper",
                        "abstract": "Graph search planning.",
                    },
                )
                replace_paper_chunks(
                    conn,
                    "2601.00001-alpha-paper",
                    [
                        {
                            "source_type": "report",
                            "section": "Method",
                            "text": "Speculative decoding verifies draft tokens using a target model.",
                        }
                    ],
                )
                replace_paper_chunks(
                    conn,
                    "2601.00002-beta-paper",
                    [
                        {
                            "source_type": "report",
                            "section": "Method",
                            "text": "Tree search explores graph planning states.",
                        }
                    ],
                )
                indexed = rebuild_semantic_index(conn)
                results = semantic_search(conn, "draft token verification", limit=2)

        self.assertEqual(indexed["indexed_chunks"], 2)
        self.assertEqual(results[0]["slug"], "2601.00001-alpha-paper")
        self.assertIn("draft tokens", results[0]["matched_chunk"].lower())

    def test_report_frontmatter_extracts_tag_taxonomy(self) -> None:
        markdown = """---
slug: 2601.00001-alpha-paper
title: Alpha Paper
topics:
  - RAG
  - Long Context
methods:
  - KV cache
domains:
  - LLM
has_code: false
---

# Alpha
"""
        frontmatter = parse_report_frontmatter(markdown)
        tags = extract_report_tags(markdown)

        self.assertEqual(frontmatter["slug"], "2601.00001-alpha-paper")
        self.assertEqual(tags["topic"], ["RAG", "Long Context"])
        self.assertEqual(tags["method"], ["KV cache"])
        self.assertEqual(tags["domain"], ["LLM"])

    def test_filter_papers_by_topic_and_method_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00001-alpha-paper",
                        "arxiv_id": "2601.00001",
                        "title": "Alpha Paper",
                        "status": "read",
                        "research_line": "LLM Serving",
                    },
                )
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00002-beta-paper",
                        "arxiv_id": "2601.00002",
                        "title": "Beta Paper",
                        "status": "read",
                        "research_line": "Reasoning",
                    },
                )
                replace_paper_tags(
                    conn,
                    "2601.00001-alpha-paper",
                    {"topic": ["Long Context"], "method": ["KV Cache"]},
                )
                replace_paper_tags(
                    conn,
                    "2601.00002-beta-paper",
                    {"topic": ["Reasoning"], "method": ["Tree Search"]},
                )
                topic_results = filter_papers(conn, topic="long")
                method_results = filter_papers(conn, method="kv cache")
                line_results = filter_papers(conn, research_line="LLM Serving")

        self.assertEqual([paper["slug"] for paper in topic_results], ["2601.00001-alpha-paper"])
        self.assertEqual([paper["slug"] for paper in method_results], ["2601.00001-alpha-paper"])
        self.assertEqual(method_results[0]["tags"]["method"], ["KV Cache"])
        self.assertEqual([paper["slug"] for paper in line_results], ["2601.00001-alpha-paper"])

    def test_filter_papers_by_status_importance_and_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00001-alpha-paper",
                        "arxiv_id": "2601.00001",
                        "title": "Alpha Paper",
                        "status": "read",
                        "importance": 5,
                        "has_code": True,
                    },
                )
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00002-beta-paper",
                        "arxiv_id": "2601.00002",
                        "title": "Beta Paper",
                        "status": "unread",
                        "importance": 3,
                        "has_code": False,
                    },
                )
                results = filter_papers(conn, status="read", importance=5, has_code=True)

        self.assertEqual([paper["slug"] for paper in results], ["2601.00001-alpha-paper"])

    def test_research_lines_group_papers_by_line_and_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00001-alpha-paper",
                        "arxiv_id": "2601.00001",
                        "title": "Alpha Paper",
                        "research_line": "LLM Serving",
                        "line_role": "main",
                        "year": 2026,
                    },
                )
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00002-beta-paper",
                        "arxiv_id": "2601.00002",
                        "title": "Beta Paper",
                        "research_line": "LLM Serving",
                        "line_role": "baseline",
                        "year": 2025,
                    },
                )
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00003-gamma-paper",
                        "arxiv_id": "2601.00003",
                        "title": "Gamma Paper",
                    },
                )
                lines = list_research_lines(conn)

        self.assertEqual(lines[0]["name"], "LLM Serving")
        self.assertEqual(lines[0]["count"], 2)
        self.assertEqual(lines[0]["roles"]["main"][0]["slug"], "2601.00001-alpha-paper")
        self.assertEqual(lines[0]["roles"]["baseline"][0]["slug"], "2601.00002-beta-paper")
        self.assertEqual(lines[1]["name"], "Unassigned")

    def test_update_paper_classification_updates_line_and_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00001-alpha-paper",
                        "arxiv_id": "2601.00001",
                        "title": "Alpha Paper",
                    },
                )
                paper = update_paper_classification(
                    conn,
                    "2601.00001-alpha-paper",
                    research_line="RAG",
                    line_role="main",
                    tags={
                        "topic": ["Retrieval"],
                        "method": ["Hybrid Search"],
                    },
                )

        self.assertEqual(paper["research_line"], "RAG")
        self.assertEqual(paper["line_role"], "main")
        self.assertEqual(paper["tags"]["topic"], ["Retrieval"])
        self.assertEqual(paper["tags"]["method"], ["Hybrid Search"])

    def test_review_queue_orders_due_then_scheduled_then_unscheduled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                for payload in [
                    {
                        "slug": "2601.00001-due-paper",
                        "arxiv_id": "2601.00001",
                        "title": "Due Paper",
                        "importance": 3,
                        "review_stage": "second_pass",
                        "last_reviewed": "2026-05-01",
                        "next_review": "2026-06-01",
                    },
                    {
                        "slug": "2601.00002-scheduled-paper",
                        "arxiv_id": "2601.00002",
                        "title": "Scheduled Paper",
                        "importance": 5,
                        "review_stage": "fresh",
                        "next_review": "2026-07-01",
                    },
                    {
                        "slug": "2601.00003-unscheduled-paper",
                        "arxiv_id": "2601.00003",
                        "title": "Unscheduled Paper",
                        "importance": 5,
                    },
                ]:
                    upsert_paper(conn, payload)
                queue = list_review_queue(conn, today="2026-06-15")

        self.assertEqual(
            [paper["slug"] for paper in queue],
            [
                "2601.00001-due-paper",
                "2601.00002-scheduled-paper",
                "2601.00003-unscheduled-paper",
            ],
        )
        self.assertEqual(queue[0]["review_priority"], "due")
        self.assertEqual(queue[1]["review_priority"], "scheduled")
        self.assertEqual(queue[2]["review_priority"], "unscheduled")

    def test_taxonomy_cleanup_reports_sparse_duplicates_and_missing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00001-alpha-paper",
                        "arxiv_id": "2601.00001",
                        "title": "Alpha Paper",
                        "research_line": "LLM Serving",
                    },
                )
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00002-beta-paper",
                        "arxiv_id": "2601.00002",
                        "title": "Beta Paper",
                    },
                )
                replace_paper_tags(
                    conn,
                    "2601.00001-alpha-paper",
                    {"topic": ["Serving"], "method": ["KV Cache"], "domain": ["Serving"]},
                )
                cleanup = get_taxonomy_cleanup(conn)

        self.assertTrue(any(tag["name"] == "KV Cache" for tag in cleanup["sparse"]))
        self.assertTrue(any(row["normalized_name"] == "serving" for row in cleanup["duplicates"]))
        self.assertEqual(cleanup["missing_metadata"][0]["slug"], "2601.00002-beta-paper")

    def test_quality_report_finds_missing_files_stale_wiki_and_malformed_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "docs"
            report_dir.mkdir()
            md_path = report_dir / "2601.00001-alpha-paper.md"
            html_path = report_dir / "2601.00001-alpha-paper.html"
            md_path.write_text("---\nslug: wrong-slug\ntitle: Alpha\n---\n# Alpha\n", encoding="utf-8")
            html_path.write_text("<html></html>", encoding="utf-8")
            for name in ("papers.json", "search_index.json", "index.html", "tags.html"):
                wiki_path = report_dir / name
                wiki_path.write_text("{}", encoding="utf-8")
                old_time = time.time() - 100
                utime(wiki_path, (old_time, old_time))

            db_path = root / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00001-alpha-paper",
                        "arxiv_id": "2601.00001",
                        "title": "Duplicate Title",
                        "report_md_path": str(md_path),
                        "report_html_path": str(html_path),
                    },
                )
                upsert_paper(
                    conn,
                    {
                        "slug": "2601.00002-beta-paper",
                        "arxiv_id": "2601.00002",
                        "title": "Duplicate Title",
                        "report_md_path": str(report_dir / "missing.md"),
                        "report_html_path": str(report_dir / "missing.html"),
                    },
                )
                report = get_quality_report(conn, report_dir)

        self.assertGreaterEqual(report["summary"]["issue_count"], 4)
        self.assertEqual(report["duplicate_titles"][0]["paper_count"], 2)
        self.assertTrue(report["missing_report_files"])
        self.assertEqual(report["malformed_metadata"][0]["issue"], "missing_frontmatter_field:arxiv_id")
        self.assertTrue(any(issue["issue"] == "stale" for issue in report["wiki_issues"]))

    def test_library_queries_handle_500_generated_papers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                for index in range(500):
                    slug = f"2601.{index:05d}-scale-paper"
                    upsert_paper(
                        conn,
                        {
                            "slug": slug,
                            "arxiv_id": f"2601.{index:05d}",
                            "title": f"Scale Paper {index}",
                            "year": 2026 - (index % 5),
                            "status": "read" if index % 3 == 0 else "unread",
                            "importance": (index % 5) + 1,
                            "has_code": index % 4 == 0,
                            "research_line": f"Line {index % 10}",
                            "line_role": "main" if index % 2 == 0 else "baseline",
                            "next_review": "2026-06-01" if index % 7 == 0 else "",
                        },
                    )
                    replace_paper_tags(
                        conn,
                        slug,
                        {
                            "topic": [f"Topic {index % 12}"],
                            "method": [f"Method {index % 8}"],
                        },
                    )
                    upsert_paper_search(
                        conn,
                        slug=slug,
                        title=f"Scale Paper {index}",
                        abstract="generated scale fixture",
                        report_text=f"Scale benchmark body topic {index % 12}",
                        chunks=f"chunk method {index % 8}",
                    )

                start = time.perf_counter()
                filtered = filter_papers(conn, topic="Topic 3", method="Method 3", limit=50)
                search_results = search_papers(conn, "scale benchmark", limit=25)
                lines = list_research_lines(conn)
                queue = list_review_queue(conn, today="2026-06-15", limit=50)
                elapsed = time.perf_counter() - start

        self.assertTrue(filtered)
        self.assertLessEqual(len(filtered), 50)
        self.assertEqual(len(search_results), 25)
        self.assertEqual(len(lines), 10)
        self.assertEqual(queue[0]["review_priority"], "due")
        self.assertLess(elapsed, 2.0)

    def test_code_url_detection_normalizes_repository_links(self) -> None:
        text = "Code: https://github.com/example/repo/tree/main for experiments."

        self.assertEqual(
            normalize_repo_url("https://github.com/example/repo/tree/main."),
            "https://github.com/example/repo",
        )
        self.assertEqual(find_code_url(text), "https://github.com/example/repo")

    def test_code_summary_builds_code_observation_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("Usage", encoding="utf-8")
            (repo / "LICENSE").write_text("MIT", encoding="utf-8")
            (repo / "train.py").write_text("print('train')", encoding="utf-8")
            scripts = repo / "scripts"
            scripts.mkdir()
            (scripts / "infer.py").write_text("print('infer')", encoding="utf-8")

            summary = summarize_code_repo(
                CodeDiscovery(
                    url="https://github.com/example/repo",
                    cloned=True,
                    path=str(repo),
                )
            )
            observation = build_code_observation(summary)
            markdown = "# Paper\n\n## 9. 实验\n\nResult\n"
            updated = apply_code_observation(markdown, observation)

        self.assertIn("## 10. 代码实现观察", updated)
        self.assertIn("### 10.1 仓库基本情况", updated)
        self.assertIn("### 10.2 方法实现核对", updated)
        self.assertIn("### 10.3 真实算力规模", updated)
        self.assertIn("### 10.4 可复现性评价", updated)
        self.assertIn("train.py", updated)
        self.assertIn("LICENSE", updated)
        self.assertEqual(validate_code_observation(observation), [])

    def test_related_arxiv_extraction_excludes_current_paper(self) -> None:
        ids = extract_external_arxiv_ids(
            "We compare with arXiv:1706.03762 and 2307.08691v2.",
            "The current paper is 2601.00001 and should be ignored.",
            current_arxiv_id="2601.00001",
        )

        self.assertEqual(ids, ["1706.03762", "2307.08691"])

    def test_code_runtime_can_revise_existing_report_when_model_output_is_valid(self) -> None:
        class SequenceProvider:
            def __init__(self, responses: list[str]) -> None:
                self.responses = responses

            def generate(self, _prompt: str) -> str:
                return self.responses.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("Run train.py", encoding="utf-8")
            (repo / "train.py").write_text("WORLD_SIZE=8\n", encoding="utf-8")
            report_path = root / "docs" / "2601.00001-demo.md"
            html_path = root / "docs" / "2601.00001-demo.html"
            base_markdown = """---
slug: 2601.00001-demo
title: Demo
title_zh: 演示论文
title_en: Demo
arxiv_id: "2601.00001"
year: 2026
authors:
  - Ada
topics:
  - LLM
methods:
  - Training
research_line: Demo
line_role: main
status: read
importance: 3
has_code: true
---

# 演示论文（Demo）

## 1. 基本情况
基础信息。

## 2. 核心贡献概述
贡献。

## 3. 一句话精髓
一句话。

## 4. 学术贡献清单
贡献清单。

## 5. 写作故事线
故事线。

## 6. 核心参考文献
参考文献。

## 7. 批判性分析
批判。

## 8. 方法细节
原报告说没有训练并行信息。

## 9. 实验
实验。
"""
            observation = """## 10. 代码实现观察
### 10.1 仓库基本情况
- README 指向 train.py。
### 10.2 方法实现核对
- 与论文一致：训练入口存在。
### 10.3 真实算力规模
- train.py 暴露 WORLD_SIZE=8。
### 10.4 可复现性评价
- README 较少，复现性中等。
"""
            revised = base_markdown.replace(
                "原报告说没有训练并行信息。",
                "原报告说没有训练并行信息；代码显示 WORLD_SIZE=8（已据代码核对修订）。",
            ).rstrip() + "\n\n" + observation
            context = ReportContext(
                slug="2601.00001-demo",
                metadata=ArxivMetadata(
                    arxiv_id="2601.00001",
                    title="Demo",
                    authors=["Ada"],
                    abstract="Demo abstract.",
                    published="2026-01-01T00:00:00Z",
                    year=2026,
                    abs_url="https://arxiv.org/abs/2601.00001",
                    pdf_url="https://arxiv.org/pdf/2601.00001",
                    eprint_url="https://arxiv.org/e-print/2601.00001",
                ),
                source_dir=root / "sources",
                main_tex_path=None,
                report_md_path=report_path,
                report_html_path=html_path,
            )
            summary = summarize_code_repo(
                CodeDiscovery(
                    url="https://github.com/example/demo",
                    cloned=True,
                    path=str(repo),
                )
            )
            provider = SequenceProvider([observation, revised])
            runtime = CodeAnalystRuntime(
                context,
                provider,
                root_dir=Path(__file__).resolve().parents[1],
                summary=summary,
            )
            result = runtime.run(base_markdown)

        self.assertIn("（已据代码核对修订）", result.markdown)
        self.assertIn("WORLD_SIZE=8", result.markdown)
        self.assertEqual([run.stage for run in result.runs], ["code_analyst", "code_report_revision"])

    def test_html_presenter_runtime_uses_llm_mindmap_artifact(self) -> None:
        class MindmapProvider:
            def generate(self, _prompt: str) -> str:
                return """# 演示论文
## 问题动机
- 训练瓶颈
- 评测缺口
## 方法核心
- 新模块
- 数据流
## 实验闭环
- 主结果
- 消融
## 局限判断
- 复现门槛
- 外部有效性
"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "docs"
            report_dir.mkdir()
            report_path = report_dir / "2601.00001-demo.md"
            html_path = report_dir / "2601.00001-demo.html"
            report_path.write_text(
                """---
slug: 2601.00001-demo
title: Demo
title_zh: 演示论文
title_en: Demo
arxiv_id: "2601.00001"
year: 2026
authors:
  - Ada
topics:
  - LLM
methods:
  - Training
status: read
importance: 3
has_code: false
---

# 演示论文（Demo）

## 1. 基本情况
基础信息。

## 2. 核心贡献概述
贡献。

## 3. 一句话精髓
一句话。

## 4. 学术贡献清单
贡献清单。

## 5. 写作故事线
故事线。

## 6. 核心参考文献
参考文献。

## 7. 批判性分析
批判。

## 8. 方法细节
方法。

## 9. 实验
实验。
""",
                encoding="utf-8",
            )
            context = ReportContext(
                slug="2601.00001-demo",
                metadata=ArxivMetadata(
                    arxiv_id="2601.00001",
                    title="Demo",
                    authors=["Ada"],
                    abstract="Demo abstract.",
                    published="2026-01-01T00:00:00Z",
                    year=2026,
                    abs_url="https://arxiv.org/abs/2601.00001",
                    pdf_url="https://arxiv.org/pdf/2601.00001",
                    eprint_url="https://arxiv.org/e-print/2601.00001",
                ),
                source_dir=root / "sources",
                main_tex_path=None,
                report_md_path=report_path,
                report_html_path=html_path,
            )
            runtime = HtmlPresenterRuntime(
                context,
                MindmapProvider(),
                root_dir=Path(__file__).resolve().parents[1],
            )
            result = runtime.run()

            self.assertTrue(result.html_path.exists())
            self.assertEqual(result.validation_errors, [])
            self.assertIn("html_mindmap", [run.stage for run in runtime.runs])
            accepted_mindmap = report_dir / "artifacts" / "2601.00001-demo" / "html_mindmap.accepted.md"
            self.assertTrue(accepted_mindmap.exists())
            self.assertIn("训练瓶颈", html_path.read_text(encoding="utf-8"))

    def test_settings_drive_default_import_provider_and_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_db = environ.get("AUTOPAPER_DB_PATH")
            old_report = environ.get("AUTOPAPER_REPORT_DIR")
            old_source = environ.get("AUTOPAPER_SOURCE_DIR")
            environ["AUTOPAPER_DB_PATH"] = str(root / "app.db")
            environ["AUTOPAPER_REPORT_DIR"] = str(root / "docs")
            environ["AUTOPAPER_SOURCE_DIR"] = str(root / "sources")
            original_run_import_job = main_module.run_import_job
            try:
                main_module.run_import_job = lambda *_args, **_kwargs: None
                client = TestClient(app)
                settings_response = client.patch(
                    "/api/settings",
                    json={
                        "llm_provider": "mock",
                        "llm_model": "test-model",
                        "openai_base_url": "https://example.test/v1",
                        "openai_api_key": "secret",
                    },
                )
                self.assertEqual(settings_response.status_code, 200)
                self.assertEqual(settings_response.json()["llm_provider"], "mock")
                self.assertEqual(settings_response.json()["openai_api_key_set"], True)

                import_response = client.post(
                    "/api/papers/import",
                    json={"url": "https://arxiv.org/abs/1706.03762"},
                )
                self.assertEqual(import_response.status_code, 200)
                job_id = import_response.json()["job_id"]
                with closing(connect(root / "app.db")) as conn:
                    job = get_job(conn, job_id)
                self.assertEqual(job["input"]["llm_provider"], "mock")
                self.assertEqual(job["input"]["model"], "test-model")
            finally:
                main_module.run_import_job = original_run_import_job
                if old_db is None:
                    environ.pop("AUTOPAPER_DB_PATH", None)
                else:
                    environ["AUTOPAPER_DB_PATH"] = old_db
                if old_report is None:
                    environ.pop("AUTOPAPER_REPORT_DIR", None)
                else:
                    environ["AUTOPAPER_REPORT_DIR"] = old_report
                if old_source is None:
                    environ.pop("AUTOPAPER_SOURCE_DIR", None)
                else:
                    environ["AUTOPAPER_SOURCE_DIR"] = old_source

    def test_llm_timeout_is_classified_as_llm_generation_failure(self) -> None:
        self.assertEqual(
            ingestion.classify_job_error(LLMGenerationError("LLM provider request timed out")),
            "llm_generation_failed",
        )
        self.assertEqual(
            OpenAICompatibleProvider(
                api_key="key",
                base_url="https://example.test/v1",
                model="model",
            ).timeout,
            900,
        )

    def test_preferred_needs_llm_job_can_resume_from_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                job_id = create_job(
                    conn,
                    job_type="paper_import",
                    input_payload={"arxiv_id": "2601.00001"},
                )
                update_job(
                    conn,
                    job_id,
                    status="needs_llm",
                    output_payload={"slug": "2601.00001-demo"},
                )
                selected = ingestion.next_runnable_import_job(conn, job_id)

        self.assertEqual(selected, job_id)

    def test_semantic_api_is_optional_and_can_be_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_db = environ.get("AUTOPAPER_DB_PATH")
            old_report = environ.get("AUTOPAPER_REPORT_DIR")
            old_source = environ.get("AUTOPAPER_SOURCE_DIR")
            environ["AUTOPAPER_DB_PATH"] = str(root / "app.db")
            environ["AUTOPAPER_REPORT_DIR"] = str(root / "docs")
            environ["AUTOPAPER_SOURCE_DIR"] = str(root / "sources")
            try:
                client = TestClient(app)
                disabled = client.get("/api/semantic/search?q=draft")
                self.assertEqual(disabled.status_code, 409)

                with closing(connect(root / "app.db")) as conn:
                    init_db(conn)
                    upsert_paper(
                        conn,
                        {
                            "slug": "2601.00001-alpha-paper",
                            "arxiv_id": "2601.00001",
                            "title": "Alpha Paper",
                        },
                    )
                    replace_paper_chunks(
                        conn,
                        "2601.00001-alpha-paper",
                        [
                            {
                                "source_type": "report",
                                "section": "Method",
                                "text": "Speculative decoding verifies draft tokens.",
                            }
                        ],
                    )

                settings_response = client.patch(
                    "/api/settings",
                    json={
                        "embedding_provider": "local-hash",
                        "embedding_model": "hashing-v1",
                        "embedding_dimension": "64",
                    },
                )
                self.assertEqual(settings_response.status_code, 200)
                self.assertEqual(settings_response.json()["embedding_enabled"], True)
                reindex_response = client.post("/api/semantic/reindex")
                self.assertEqual(reindex_response.status_code, 200)
                self.assertEqual(reindex_response.json()["indexed_chunks"], 1)
                search_response = client.get("/api/semantic/search?q=draft%20tokens")
                self.assertEqual(search_response.status_code, 200)
                self.assertEqual(search_response.json()["items"][0]["slug"], "2601.00001-alpha-paper")
            finally:
                if old_db is None:
                    environ.pop("AUTOPAPER_DB_PATH", None)
                else:
                    environ["AUTOPAPER_DB_PATH"] = old_db
                if old_report is None:
                    environ.pop("AUTOPAPER_REPORT_DIR", None)
                else:
                    environ["AUTOPAPER_REPORT_DIR"] = old_report
                if old_source is None:
                    environ.pop("AUTOPAPER_SOURCE_DIR", None)
                else:
                    environ["AUTOPAPER_SOURCE_DIR"] = old_source

    def test_fastapi_serves_built_frontend_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "frontend" / "dist"
            assets = dist / "assets"
            assets.mkdir(parents=True)
            (dist / "index.html").write_text("<html>desktop app</html>", encoding="utf-8")
            (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")
            old_db = environ.get("AUTOPAPER_DB_PATH")
            old_report = environ.get("AUTOPAPER_REPORT_DIR")
            old_source = environ.get("AUTOPAPER_SOURCE_DIR")
            original_load_config = main_module.load_config
            try:
                config = AppConfig(
                    root_dir=root,
                    report_dir=root / "docs",
                    source_dir=root / "sources",
                    db_path=root / "app.db",
                    openai_api_key="",
                    openai_base_url="https://api.openai.com/v1",
                )
                main_module.load_config = lambda: config
                client = TestClient(app)
                index_response = client.get("/")
                asset_response = client.get("/assets/app.js")
            finally:
                main_module.load_config = original_load_config
                if old_db is None:
                    environ.pop("AUTOPAPER_DB_PATH", None)
                else:
                    environ["AUTOPAPER_DB_PATH"] = old_db
                if old_report is None:
                    environ.pop("AUTOPAPER_REPORT_DIR", None)
                else:
                    environ["AUTOPAPER_REPORT_DIR"] = old_report
                if old_source is None:
                    environ.pop("AUTOPAPER_SOURCE_DIR", None)
                else:
                    environ["AUTOPAPER_SOURCE_DIR"] = old_source

        self.assertEqual(index_response.status_code, 200)
        self.assertIn("desktop app", index_response.text)
        self.assertEqual(asset_response.status_code, 200)
        self.assertIn("console.log", asset_response.text)

    def test_fastapi_serves_report_files_from_data_dirs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "docs"
            report_dir.mkdir()
            report = report_dir / "paper.html"
            report.write_text("<html>paper report</html>", encoding="utf-8")
            original_load_config = main_module.load_config
            try:
                config = AppConfig(
                    root_dir=root,
                    report_dir=report_dir,
                    source_dir=root / "sources",
                    db_path=root / "app.db",
                    openai_api_key="",
                    openai_base_url="https://api.openai.com/v1",
                )
                main_module.load_config = lambda: config
                client = TestClient(app)
                report_response = client.get(f"/api/files?path={report}")
                outside_response = client.get("/api/files?path=/etc/passwd")
            finally:
                main_module.load_config = original_load_config

        self.assertEqual(report_response.status_code, 200)
        self.assertIn("paper report", report_response.text)
        self.assertEqual(outside_response.status_code, 403)

    def test_fastapi_serves_report_assets_for_in_app_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "docs"
            asset_dir = report_dir / "assets" / "2601.00001-alpha"
            asset_dir.mkdir(parents=True)
            figure = asset_dir / "figure.png"
            figure.write_bytes(b"fake-png")
            outside = root / "outside.png"
            outside.write_bytes(b"outside")
            original_load_config = main_module.load_config
            try:
                config = AppConfig(
                    root_dir=root,
                    report_dir=report_dir,
                    source_dir=root / "sources",
                    db_path=root / "app.db",
                    openai_api_key="",
                    openai_base_url="https://api.openai.com/v1",
                )
                main_module.load_config = lambda: config
                client = TestClient(app)
                asset_response = client.get("/api/assets/2601.00001-alpha/figure.png")
                traversal_response = client.get("/api/assets/../outside.png")
            finally:
                main_module.load_config = original_load_config

        self.assertEqual(asset_response.status_code, 200)
        self.assertEqual(asset_response.content, b"fake-png")
        self.assertEqual(traversal_response.status_code, 404)

    def test_effective_llm_settings_use_sqlite_then_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                root_dir=root,
                report_dir=root / "docs",
                source_dir=root / "sources",
                db_path=root / "app.db",
                openai_api_key="env-key",
                openai_base_url="https://env.example/v1",
            )
            with closing(connect(config.db_path)) as conn:
                init_db(conn)
                set_setting(conn, "llm_provider", "mock")
                set_setting(conn, "llm_model", "stored-model")
                settings = effective_llm_settings(conn, config)

        self.assertEqual(settings["provider"], "mock")
        self.assertEqual(settings["model"], "stored-model")
        self.assertEqual(settings["openai_api_key"], "env-key")

    def test_settings_can_test_llm_connection_with_current_form_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            captured: dict[str, str] = {}
            old_db = environ.get("AUTOPAPER_DB_PATH")
            old_report = environ.get("AUTOPAPER_REPORT_DIR")
            old_source = environ.get("AUTOPAPER_SOURCE_DIR")
            original_test = main_module.test_llm_connection

            def fake_test(settings: dict[str, str]) -> str:
                captured.update(settings)
                return "success"

            try:
                environ["AUTOPAPER_DB_PATH"] = str(root / "app.db")
                environ["AUTOPAPER_REPORT_DIR"] = str(root / "docs")
                environ["AUTOPAPER_SOURCE_DIR"] = str(root / "sources")
                main_module.test_llm_connection = fake_test
                client = TestClient(app)
                response = client.post(
                    "/api/settings/test-llm",
                    json={
                        "llm_provider": "openai-compatible",
                        "llm_model": "paper-test-model",
                        "openai_base_url": "https://llm.example/v1",
                        "openai_api_key": "form-key",
                    },
                )
            finally:
                main_module.test_llm_connection = original_test
                if old_db is None:
                    environ.pop("AUTOPAPER_DB_PATH", None)
                else:
                    environ["AUTOPAPER_DB_PATH"] = old_db
                if old_report is None:
                    environ.pop("AUTOPAPER_REPORT_DIR", None)
                else:
                    environ["AUTOPAPER_REPORT_DIR"] = old_report
                if old_source is None:
                    environ.pop("AUTOPAPER_SOURCE_DIR", None)
                else:
                    environ["AUTOPAPER_SOURCE_DIR"] = old_source

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(captured["provider"], "openai-compatible")
        self.assertEqual(captured["model"], "paper-test-model")
        self.assertEqual(captured["openai_base_url"], "https://llm.example/v1")
        self.assertEqual(captured["openai_api_key"], "form-key")

    def test_llm_http_error_summary_keeps_api_test_readable(self) -> None:
        body = '{"error":{"message":"Incorrect API key provided: 111. You can find your API key at https://platform.openai.com/account/api-keys.","type":"invalid_request_error","code":"invalid_api_key"}}'
        summary = summarize_llm_http_error(401, body)

        self.assertEqual(summary, "HTTP 401：API Key 无效或未被当前服务接受，请检查密钥是否粘贴正确。")
        self.assertNotIn("platform.openai.com", summary)

    def test_api_profiles_can_be_saved_and_activated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            captured: dict[str, str] = {}
            old_db = environ.get("AUTOPAPER_DB_PATH")
            old_report = environ.get("AUTOPAPER_REPORT_DIR")
            old_source = environ.get("AUTOPAPER_SOURCE_DIR")
            original_test = main_module.test_llm_connection

            def fake_test(settings: dict[str, str]) -> str:
                captured.update(settings)
                return "success"

            try:
                environ["AUTOPAPER_DB_PATH"] = str(root / "app.db")
                environ["AUTOPAPER_REPORT_DIR"] = str(root / "docs")
                environ["AUTOPAPER_SOURCE_DIR"] = str(root / "sources")
                main_module.test_llm_connection = fake_test
                client = TestClient(app)
                create_response = client.post(
                    "/api/settings/api-profiles",
                    json={
                        "name": "实验室网关",
                        "llm_provider": "openai-compatible",
                        "llm_model": "lab-model",
                        "openai_base_url": "https://lab.example/v1",
                        "openai_api_key": "lab-secret-key",
                    },
                )
                self.assertEqual(create_response.status_code, 200)
                profile = create_response.json()["items"][0]
                self.assertEqual(profile["name"], "实验室网关")
                self.assertTrue(profile["api_key_set"])

                activate_response = client.post(f"/api/settings/api-profiles/{profile['id']}/activate")
                self.assertEqual(activate_response.status_code, 200)
                payload = activate_response.json()
                self.assertEqual(payload["settings"]["llm_provider"], "openai-compatible")
                self.assertEqual(payload["settings"]["llm_model"], "lab-model")
                self.assertEqual(payload["settings"]["openai_base_url"], "https://lab.example/v1")
                self.assertEqual(payload["settings"]["active_api_profile_id"], profile["id"])
                self.assertTrue(payload["items"][0]["is_active"])

                test_response = client.post(f"/api/settings/api-profiles/{profile['id']}/test")
                self.assertEqual(test_response.status_code, 200)
                self.assertTrue(test_response.json()["ok"])
                self.assertEqual(captured["openai_api_key"], "lab-secret-key")
                self.assertEqual(captured["model"], "lab-model")

                update_response = client.post(
                    "/api/settings/api-profiles",
                    json={
                        "id": profile["id"],
                        "name": "实验室网关",
                        "llm_provider": "openai-compatible",
                        "llm_model": "lab-model-2",
                        "openai_base_url": "https://lab.example/v2",
                    },
                )
                self.assertEqual(update_response.status_code, 200)
                updated_payload = update_response.json()
                self.assertEqual(updated_payload["settings"]["llm_model"], "lab-model-2")
                self.assertEqual(updated_payload["settings"]["openai_base_url"], "https://lab.example/v2")
                self.assertTrue(updated_payload["items"][0]["is_active"])

                deactivate_response = client.post(f"/api/settings/api-profiles/{profile['id']}/deactivate")
                self.assertEqual(deactivate_response.status_code, 200)
                deactivated_payload = deactivate_response.json()
                self.assertEqual(deactivated_payload["settings"]["active_api_profile_id"], "")
                self.assertFalse(deactivated_payload["items"][0]["is_active"])
            finally:
                main_module.test_llm_connection = original_test
                if old_db is None:
                    environ.pop("AUTOPAPER_DB_PATH", None)
                else:
                    environ["AUTOPAPER_DB_PATH"] = old_db
                if old_report is None:
                    environ.pop("AUTOPAPER_REPORT_DIR", None)
                else:
                    environ["AUTOPAPER_REPORT_DIR"] = old_report
                if old_source is None:
                    environ.pop("AUTOPAPER_SOURCE_DIR", None)
                else:
                    environ["AUTOPAPER_SOURCE_DIR"] = old_source

    def test_desktop_mode_defaults_to_macos_application_support_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            isolated_db = Path(tmp) / "app.db"
            old_desktop = environ.get("AUTOPAPER_DESKTOP")
            old_db = environ.get("AUTOPAPER_DB_PATH")
            old_report = environ.get("AUTOPAPER_REPORT_DIR")
            old_source = environ.get("AUTOPAPER_SOURCE_DIR")
            try:
                environ["AUTOPAPER_DESKTOP"] = "1"
                environ["AUTOPAPER_DB_PATH"] = str(isolated_db)
                environ.pop("AUTOPAPER_REPORT_DIR", None)
                environ.pop("AUTOPAPER_SOURCE_DIR", None)
                config = load_config()
            finally:
                if old_desktop is None:
                    environ.pop("AUTOPAPER_DESKTOP", None)
                else:
                    environ["AUTOPAPER_DESKTOP"] = old_desktop
                if old_db is None:
                    environ.pop("AUTOPAPER_DB_PATH", None)
                else:
                    environ["AUTOPAPER_DB_PATH"] = old_db
                if old_report is None:
                    environ.pop("AUTOPAPER_REPORT_DIR", None)
                else:
                    environ["AUTOPAPER_REPORT_DIR"] = old_report
                if old_source is None:
                    environ.pop("AUTOPAPER_SOURCE_DIR", None)
                else:
                    environ["AUTOPAPER_SOURCE_DIR"] = old_source

        self.assertEqual(config.db_path, isolated_db.resolve())
        self.assertTrue(str(config.report_dir).endswith("AutoPaperReader/docs"))
        self.assertTrue(str(config.source_dir).endswith("AutoPaperReader/sources"))

    def test_settings_can_override_local_storage_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom_reports = root / "my reports"
            custom_sources = root / "my sources"
            old_db = environ.get("AUTOPAPER_DB_PATH")
            old_report = environ.get("AUTOPAPER_REPORT_DIR")
            old_source = environ.get("AUTOPAPER_SOURCE_DIR")
            try:
                environ["AUTOPAPER_DB_PATH"] = str(root / "app.db")
                environ.pop("AUTOPAPER_REPORT_DIR", None)
                environ.pop("AUTOPAPER_SOURCE_DIR", None)

                client = TestClient(app)
                response = client.patch(
                    "/api/settings",
                    json={
                        "report_dir": str(custom_reports),
                        "source_dir": str(custom_sources),
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["report_dir"], str(custom_reports.resolve()))
                self.assertEqual(response.json()["source_dir"], str(custom_sources.resolve()))
                self.assertTrue(custom_reports.exists())
                self.assertTrue(custom_sources.exists())

                config = load_config()
                self.assertEqual(config.report_dir, custom_reports.resolve())
                self.assertEqual(config.source_dir, custom_sources.resolve())
            finally:
                if old_db is None:
                    environ.pop("AUTOPAPER_DB_PATH", None)
                else:
                    environ["AUTOPAPER_DB_PATH"] = old_db
                if old_report is None:
                    environ.pop("AUTOPAPER_REPORT_DIR", None)
                else:
                    environ["AUTOPAPER_REPORT_DIR"] = old_report
                if old_source is None:
                    environ.pop("AUTOPAPER_SOURCE_DIR", None)
                else:
                    environ["AUTOPAPER_SOURCE_DIR"] = old_source

    def test_select_directory_uses_native_macos_dialog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            selected = Path(tmp)
            captured: dict[str, object] = {}
            original_run = main_module.subprocess.run

            class Result:
                returncode = 0
                stdout = f"{selected}\n"
                stderr = ""

            def fake_run(args, **kwargs):
                captured["args"] = args
                captured["kwargs"] = kwargs
                return Result()

            try:
                main_module.subprocess.run = fake_run
                client = TestClient(app)
                response = client.post(
                    "/api/system/select-directory",
                    json={"current_path": str(selected), "prompt": "选择源码目录"},
                )
            finally:
                main_module.subprocess.run = original_run

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["path"], str(selected.resolve()))
        self.assertEqual(captured["args"][0], "osascript")
        self.assertIn("choose folder", captured["args"][2])
        self.assertTrue(captured["kwargs"]["capture_output"])

    def test_retry_operation_retries_transient_failures(self) -> None:
        calls: list[int] = []

        def flaky_operation() -> str:
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("temporary network failure")
            return "ok"

        result = ingestion.retry_operation(flaky_operation, attempts=3)

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual(ingestion.classify_job_error(RuntimeError("No TeX file found")), "missing_tex_source")

    def test_import_worker_prepares_source_and_marks_needs_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                root_dir=root,
                report_dir=root / "docs",
                source_dir=root / "sources",
                db_path=root / "app.db",
                openai_api_key="",
                openai_base_url="https://api.openai.com/v1",
            )
            config.report_dir.mkdir()
            config.source_dir.mkdir()

            with closing(connect(config.db_path)) as conn:
                init_db(conn)
                job_id = create_job(
                    conn,
                    job_type="paper_import",
                    input_payload={"arxiv_id": "1706.03762"},
                )

            original_fetch = ingestion.fetch_arxiv_metadata
            original_download = ingestion.download_eprint
            original_discover = ingestion.discover_and_clone_code

            def fake_fetch(arxiv_id: str) -> ArxivMetadata:
                return ArxivMetadata(
                    arxiv_id=arxiv_id,
                    title="Attention Is All You Need",
                    authors=["Ashish Vaswani"],
                    abstract="Transformer paper.",
                    published="2017-06-12T17:57:34Z",
                    year=2017,
                    abs_url="https://arxiv.org/abs/1706.03762",
                    pdf_url="https://arxiv.org/pdf/1706.03762",
                    eprint_url="https://arxiv.org/e-print/1706.03762",
                )

            def fake_discover(**_kwargs):
                from backend.app.services.code import CodeDiscovery

                return CodeDiscovery(
                    url="https://github.com/example/attention",
                    cloned=False,
                    path=str(root / "sources" / "code"),
                    error="network unavailable",
                )

            def fake_download(_arxiv_id: str, target_path: Path) -> Path:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                tex_path = root / "fixture.tex"
                tex_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n",
                    encoding="utf-8",
                )
                with tarfile.open(target_path, "w:gz") as archive:
                    archive.add(tex_path, arcname="main.tex")
                return target_path

            try:
                ingestion.fetch_arxiv_metadata = fake_fetch
                ingestion.download_eprint = fake_download
                ingestion.discover_and_clone_code = fake_discover
                ingestion.run_import_job(job_id, config)
            finally:
                ingestion.fetch_arxiv_metadata = original_fetch
                ingestion.download_eprint = original_download
                ingestion.discover_and_clone_code = original_discover

            with closing(connect(config.db_path)) as conn:
                job = get_job(conn, job_id)
                paper = get_paper(conn, "1706.03762-attention-all-you-need")

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "needs_llm")
        self.assertEqual(job["current_step"], "needs_llm_report_generation")
        self.assertEqual(job["output"]["main_tex_path"].endswith("main.tex"), True)
        self.assertEqual(job["output"]["code_url"], "https://github.com/example/attention")
        self.assertEqual(job["output"]["code_cloned"], False)
        self.assertIsNotNone(paper)
        self.assertEqual(paper["title"], "Attention Is All You Need")
        self.assertEqual(paper["has_code"], 1)
        self.assertEqual(paper["code_url"], "https://github.com/example/attention")

    def test_import_worker_reports_missing_tex_source_as_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                root_dir=root,
                report_dir=root / "docs",
                source_dir=root / "sources",
                db_path=root / "app.db",
                openai_api_key="",
                openai_base_url="https://api.openai.com/v1",
            )
            config.report_dir.mkdir()
            config.source_dir.mkdir()

            with closing(connect(config.db_path)) as conn:
                init_db(conn)
                job_id = create_job(
                    conn,
                    job_type="paper_import",
                    input_payload={"arxiv_id": "1706.03762"},
                )

            original_fetch = ingestion.fetch_arxiv_metadata
            original_download = ingestion.download_eprint

            def fake_fetch(arxiv_id: str) -> ArxivMetadata:
                return ArxivMetadata(
                    arxiv_id=arxiv_id,
                    title="Attention Is All You Need",
                    authors=["Ashish Vaswani"],
                    abstract="Transformer paper.",
                    published="2017-06-12T17:57:34Z",
                    year=2017,
                    abs_url="https://arxiv.org/abs/1706.03762",
                    pdf_url="https://arxiv.org/pdf/1706.03762",
                    eprint_url="https://arxiv.org/e-print/1706.03762",
                )

            def fake_download(_arxiv_id: str, target_path: Path) -> Path:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                readme_path = root / "README.md"
                readme_path.write_text("no tex here", encoding="utf-8")
                with tarfile.open(target_path, "w:gz") as archive:
                    archive.add(readme_path, arcname="README.md")
                return target_path

            try:
                ingestion.fetch_arxiv_metadata = fake_fetch
                ingestion.download_eprint = fake_download
                ingestion.run_import_job(job_id, config)
            finally:
                ingestion.fetch_arxiv_metadata = original_fetch
                ingestion.download_eprint = original_download

            with closing(connect(config.db_path)) as conn:
                job = get_job(conn, job_id)

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["output"]["error_type"], "missing_tex_source")
        self.assertIn("No TeX file found", job["output"]["error_detail"])

    def test_import_worker_completes_with_mock_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                root_dir=Path(__file__).resolve().parents[1],
                report_dir=root / "docs",
                source_dir=root / "sources",
                db_path=root / "app.db",
                openai_api_key="",
                openai_base_url="https://api.openai.com/v1",
            )
            config.report_dir.mkdir()
            config.source_dir.mkdir()

            with closing(connect(config.db_path)) as conn:
                init_db(conn)
                job_id = create_job(
                    conn,
                    job_type="paper_import",
                    input_payload={"arxiv_id": "1706.03762", "llm_provider": "mock"},
                )

            original_fetch = ingestion.fetch_arxiv_metadata
            original_download = ingestion.download_eprint

            def fake_fetch(arxiv_id: str) -> ArxivMetadata:
                return ArxivMetadata(
                    arxiv_id=arxiv_id,
                    title="Attention Is All You Need",
                    authors=["Ashish Vaswani"],
                    abstract="We propose the Transformer architecture.",
                    published="2017-06-12T17:57:34Z",
                    year=2017,
                    abs_url="https://arxiv.org/abs/1706.03762",
                    pdf_url="https://arxiv.org/pdf/1706.03762",
                    eprint_url="https://arxiv.org/e-print/1706.03762",
                )

            def fake_download(_arxiv_id: str, target_path: Path) -> Path:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                tex_path = root / "fixture.tex"
                tex_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\nTransformer\n\\end{document}\n",
                    encoding="utf-8",
                )
                with tarfile.open(target_path, "w:gz") as archive:
                    archive.add(tex_path, arcname="main.tex")
                return target_path

            try:
                ingestion.fetch_arxiv_metadata = fake_fetch
                ingestion.download_eprint = fake_download
                ingestion.run_import_job(job_id, config)
            finally:
                ingestion.fetch_arxiv_metadata = original_fetch
                ingestion.download_eprint = original_download

            report_md = config.report_dir / "1706.03762-attention-all-you-need.md"
            report_html = config.report_dir / "1706.03762-attention-all-you-need.html"
            with closing(connect(config.db_path)) as conn:
                job = get_job(conn, job_id)
                search_results = search_papers(conn, "Transformer architecture")
                topic_results = filter_papers(conn, topic="paper reading")
                method_results = filter_papers(conn, method="assisted")
                model_runs = conn.execute(
                    "SELECT * FROM model_runs WHERE job_id = ?",
                    (job_id,),
                ).fetchall()

            self.assertIsNotNone(job)
            self.assertEqual(job["status"], "completed")
            self.assertTrue(report_md.exists())
            self.assertTrue(report_html.exists())
            self.assertTrue((config.report_dir / "index.html").exists())
            self.assertIn("## 8. 方法细节", report_md.read_text(encoding="utf-8"))
            self.assertEqual(len(search_results), 1)
            self.assertEqual(search_results[0]["slug"], "1706.03762-attention-all-you-need")
            self.assertEqual(len(topic_results), 1)
            self.assertEqual(topic_results[0]["tags"]["topic"], ["Paper Reading"])
            self.assertEqual(len(method_results), 1)
            self.assertEqual(method_results[0]["tags"]["method"], ["LLM-assisted analysis"])
            self.assertEqual(len(model_runs), 4)
            prompt_versions = [row["prompt_version"] for row in model_runs]
            self.assertEqual(
                set(prompt_versions),
                {
                    "report:paper-analyst-deep-v1:reading_notes",
                    "report:paper-analyst-deep-v1:critical_memo",
                    "report:paper-analyst-deep-v1:final_report",
                    "report:paper-analyst-deep-v1:html_mindmap",
                },
            )
            self.assertTrue(all(row["provider"] == "mock" for row in model_runs))
            self.assertTrue(any("Attention Is All You Need" in row["prompt_text"] for row in model_runs))
            self.assertTrue(all(row["input_tokens"] > 0 for row in model_runs))
            self.assertTrue(all(row["output_tokens"] > 0 for row in model_runs))

    def test_mock_import_adds_code_observation_when_code_repo_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                root_dir=Path(__file__).resolve().parents[1],
                report_dir=root / "docs",
                source_dir=root / "sources",
                db_path=root / "app.db",
                openai_api_key="",
                openai_base_url="https://api.openai.com/v1",
            )
            config.report_dir.mkdir()
            config.source_dir.mkdir()
            with closing(connect(config.db_path)) as conn:
                init_db(conn)
                job_id = create_job(
                    conn,
                    job_type="paper_import",
                    input_payload={"arxiv_id": "1706.03762", "llm_provider": "mock"},
                )

            original_fetch = ingestion.fetch_arxiv_metadata
            original_download = ingestion.download_eprint
            original_discover = ingestion.discover_and_clone_code

            def fake_fetch(arxiv_id: str) -> ArxivMetadata:
                return ArxivMetadata(
                    arxiv_id=arxiv_id,
                    title="Attention Is All You Need",
                    authors=["Ashish Vaswani"],
                    abstract="Transformer implementation at https://github.com/example/attention.",
                    published="2017-06-12T17:57:34Z",
                    year=2017,
                    abs_url="https://arxiv.org/abs/1706.03762",
                    pdf_url="https://arxiv.org/pdf/1706.03762",
                    eprint_url="https://arxiv.org/e-print/1706.03762",
                )

            def fake_download(_arxiv_id: str, target_path: Path) -> Path:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                tex_path = root / "fixture.tex"
                tex_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\nTransformer\n\\end{document}\n",
                    encoding="utf-8",
                )
                with tarfile.open(target_path, "w:gz") as archive:
                    archive.add(tex_path, arcname="main.tex")
                return target_path

            def fake_discover(**kwargs):
                target_dir = Path(kwargs["target_dir"])
                target_dir.mkdir(parents=True)
                (target_dir / "README.md").write_text("Run training", encoding="utf-8")
                (target_dir / "train.py").write_text("print('train')", encoding="utf-8")
                return CodeDiscovery(
                    url="https://github.com/example/attention",
                    cloned=True,
                    path=str(target_dir),
                )

            try:
                ingestion.fetch_arxiv_metadata = fake_fetch
                ingestion.download_eprint = fake_download
                ingestion.discover_and_clone_code = fake_discover
                ingestion.run_import_job(job_id, config)
            finally:
                ingestion.fetch_arxiv_metadata = original_fetch
                ingestion.download_eprint = original_download
                ingestion.discover_and_clone_code = original_discover

            report_md = config.report_dir / "1706.03762-attention-all-you-need.md"
            with closing(connect(config.db_path)) as conn:
                job = get_job(conn, job_id)
                search_results = search_papers(conn, "train.py")

            report_text = report_md.read_text(encoding="utf-8")
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["output"]["code_observation_added"], True)
            self.assertIn("## 10. 代码实现观察", report_text)
            self.assertIn("train.py", report_text)
            self.assertEqual(len(search_results), 1)


if __name__ == "__main__":
    unittest.main()
