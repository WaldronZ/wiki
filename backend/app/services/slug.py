from __future__ import annotations

import re


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "with",
}


def slugify_words(text: str, *, max_words: int = 4) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    selected = [word for word in words if word not in STOPWORDS]
    if not selected:
        selected = words
    return "-".join(selected[:max_words]) or "paper"


def make_paper_slug(arxiv_id: str, title: str) -> str:
    return f"{arxiv_id}-{slugify_words(title)}"

