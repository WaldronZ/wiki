from __future__ import annotations

import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from xml.etree import ElementTree


ARXIV_ID_RE = re.compile(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?(?!\d)")


@dataclass(frozen=True)
class ArxivInput:
    arxiv_id: str
    abs_url: str
    pdf_url: str
    eprint_url: str


@dataclass(frozen=True)
class ArxivMetadata:
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: str
    year: int | None
    abs_url: str
    pdf_url: str
    eprint_url: str


def normalize_arxiv_input(value: str) -> ArxivInput:
    text = value.strip()
    match = ARXIV_ID_RE.search(text)
    if not match:
        raise ValueError("Input does not contain a supported arXiv id.")
    arxiv_id = match.group(1)
    return ArxivInput(
        arxiv_id=arxiv_id,
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        eprint_url=f"https://arxiv.org/e-print/{arxiv_id}",
    )


def parse_arxiv_atom(xml_text: str, arxiv_id: str) -> ArxivMetadata:
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    root = ElementTree.fromstring(xml_text)
    entry = root.find("atom:entry", namespace)
    if entry is None:
        raise ValueError(f"arXiv metadata not found for {arxiv_id}")

    title = " ".join((entry.findtext("atom:title", "", namespace) or "").split())
    abstract = " ".join((entry.findtext("atom:summary", "", namespace) or "").split())
    published = entry.findtext("atom:published", "", namespace) or ""
    authors = [
        " ".join((author.findtext("atom:name", "", namespace) or "").split())
        for author in entry.findall("atom:author", namespace)
    ]
    authors = [author for author in authors if author]
    year = None
    if published:
        try:
            year = datetime.fromisoformat(published.replace("Z", "+00:00")).year
        except ValueError:
            year = None

    normalized = normalize_arxiv_input(arxiv_id)
    abs_url = normalized.abs_url
    pdf_url = normalized.pdf_url
    for link in entry.findall("atom:link", namespace):
        rel = link.attrib.get("rel")
        title_attr = link.attrib.get("title")
        href = link.attrib.get("href", "")
        if rel == "alternate" and href:
            abs_url = href
        if title_attr == "pdf" and href:
            pdf_url = href

    return ArxivMetadata(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        abstract=abstract,
        published=published,
        year=year,
        abs_url=abs_url,
        pdf_url=pdf_url,
        eprint_url=normalized.eprint_url,
    )


def fetch_arxiv_metadata(arxiv_id: str, *, timeout: int = 30) -> ArxivMetadata:
    query = urllib.parse.urlencode({"id_list": arxiv_id})
    url = f"https://export.arxiv.org/api/query?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "AutoPaperReader/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        xml_text = response.read().decode("utf-8")
    return parse_arxiv_atom(xml_text, arxiv_id)
