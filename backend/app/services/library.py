from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DuplicateCheck:
    duplicate: bool
    reason: str = ""
    slug: str = ""
    report_path: str = ""


def find_duplicate(conn: sqlite3.Connection, report_dir: Path, arxiv_id: str) -> DuplicateCheck:
    row = conn.execute(
        "SELECT slug, report_md_path FROM papers WHERE arxiv_id = ?",
        (arxiv_id,),
    ).fetchone()
    if row:
        return DuplicateCheck(
            duplicate=True,
            reason="database_arxiv_id",
            slug=str(row["slug"]),
            report_path=str(row["report_md_path"]),
        )

    matches = sorted(report_dir.glob(f"{arxiv_id}-*.md"))
    if matches:
        return DuplicateCheck(
            duplicate=True,
            reason="report_file_arxiv_prefix",
            slug=matches[0].stem,
            report_path=str(matches[0]),
        )

    return DuplicateCheck(duplicate=False)

