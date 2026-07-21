from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from typing import Any

from ..db import row_to_dict, utc_now


DEFAULT_EMBEDDING_PROVIDER = "local-hash"
DEFAULT_EMBEDDING_MODEL = "hashing-v1"
DEFAULT_EMBEDDING_DIMENSION = 64


def normalize_embedding_settings(
    *,
    provider: str = "",
    model: str = "",
    dimension: int | str | None = None,
) -> dict[str, Any]:
    provider = provider.strip()
    model = model.strip()
    if not provider:
        return {"enabled": False, "provider": "", "model": "", "dimension": DEFAULT_EMBEDDING_DIMENSION}
    parsed_dimension = int(dimension or DEFAULT_EMBEDDING_DIMENSION)
    parsed_dimension = max(16, min(512, parsed_dimension))
    return {
        "enabled": True,
        "provider": provider,
        "model": model or DEFAULT_EMBEDDING_MODEL,
        "dimension": parsed_dimension,
    }


def embed_text_local_hash(text: str, *, dimension: int = DEFAULT_EMBEDDING_DIMENSION) -> list[float]:
    vector = [0.0 for _ in range(dimension)]
    tokens = re.findall(r"[\w\-]+", text.lower())
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    length = math.sqrt(sum(value * value for value in vector))
    if length == 0:
        return vector
    return [value / length for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def rebuild_semantic_index(
    conn: sqlite3.Connection,
    *,
    provider: str = DEFAULT_EMBEDDING_PROVIDER,
    model: str = DEFAULT_EMBEDDING_MODEL,
    dimension: int = DEFAULT_EMBEDDING_DIMENSION,
) -> dict[str, int | str]:
    if provider != DEFAULT_EMBEDDING_PROVIDER:
        raise ValueError(f"Unsupported local embedding provider: {provider}")
    now = utc_now()
    conn.execute(
        "DELETE FROM embeddings WHERE provider = ? AND model = ?",
        (provider, model),
    )
    chunks = conn.execute(
        """
        SELECT pc.id AS chunk_id, pc.paper_slug, pc.text
        FROM paper_chunks pc
        JOIN papers p ON p.slug = pc.paper_slug
        WHERE trim(pc.text) != ''
        ORDER BY pc.paper_slug, pc.id
        """
    ).fetchall()
    rows = []
    for chunk in chunks:
        text = str(chunk["text"])
        vector = embed_text_local_hash(text, dimension=dimension)
        rows.append(
            (
                str(chunk["paper_slug"]),
                int(chunk["chunk_id"]),
                provider,
                model,
                dimension,
                json.dumps(vector),
                text,
                now,
            )
        )
    conn.executemany(
        """
        INSERT INTO embeddings (
            paper_slug, chunk_id, provider, model, dimension, vector_json, text, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return {
        "provider": provider,
        "model": model,
        "dimension": dimension,
        "indexed_chunks": len(rows),
    }


def semantic_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    provider: str = DEFAULT_EMBEDDING_PROVIDER,
    model: str = DEFAULT_EMBEDDING_MODEL,
    dimension: int = DEFAULT_EMBEDDING_DIMENSION,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if provider != DEFAULT_EMBEDDING_PROVIDER:
        raise ValueError(f"Unsupported local embedding provider: {provider}")
    query_vector = embed_text_local_hash(query, dimension=dimension)
    rows = conn.execute(
        """
        SELECT e.*, p.*
        FROM embeddings e
        JOIN papers p ON p.slug = e.paper_slug
        WHERE e.provider = ? AND e.model = ? AND e.dimension = ?
        """,
        (provider, model, dimension),
    ).fetchall()
    best_by_paper: dict[str, dict[str, Any]] = {}
    for row in rows:
        vector = json.loads(str(row["vector_json"]))
        score = cosine_similarity(query_vector, [float(value) for value in vector])
        slug = str(row["paper_slug"])
        existing = best_by_paper.get(slug)
        if existing is None or score > float(existing["score"]):
            paper = row_to_dict(row) or {}
            paper["score"] = score
            paper["matched_chunk"] = str(row["text"])
            paper["chunk_id"] = int(row["chunk_id"]) if row["chunk_id"] is not None else None
            best_by_paper[slug] = paper
    return sorted(best_by_paper.values(), key=lambda item: float(item["score"]), reverse=True)[:limit]
