---
slug: semantic-search-evaluation
title: "Semantic Search Evaluation"
title_zh: "语义搜索评估"
title_en: "Semantic Search Evaluation"
arxiv_id: "noarxiv-semantic-search-evaluation"
year: 2025
authors:
  - Waldron
topics:
  - Semantic Search
  - Vector Database
  - SQLite
methods:
  - Local Hash Embeddings
  - Cosine Similarity
domains:
  - AI Systems
tracks:
  - Search & Retrieval
problems:
  - Semantic Search
  - Vector Storage
research_line: "LLM Serving"
line_role: "variant"
status: read
reading_stage: "deep_read"
importance: 3
confidence: 4
reproducibility: 4
has_code: false
---

# Semantic Search Evaluation

## Current MVP Choice

The MVP keeps semantic search optional and local:

- Storage: SQLite `embeddings` table.
- Provider: `local-hash`.
- Model label: `hashing-v1`.
- Query: Python cosine similarity over stored chunk vectors.

This is intentionally modest. It gives the UI and API a stable semantic-search path without requiring a native SQLite extension, a Docker service, or paid embedding calls.

## Options Reviewed

### sqlite-vec

`sqlite-vec` is the most natural future upgrade because it keeps vectors inside SQLite and is designed to run locally. It is also described by the project as pre-v1, so the MVP avoids making it a hard dependency until the API stabilizes.

### sqlite-vss

`sqlite-vss` brings vector search to SQLite using Faiss. It can be faster for vector search, but it adds a heavier native dependency path than the MVP needs.

### Chroma

Chroma supports local persistence through a persistent client, which is useful if the app later wants a richer embedding database. It is a separate storage layer, so the MVP would need extra lifecycle and packaging work.

### Qdrant Local Mode

Qdrant client supports local mode with in-memory or persisted on-disk storage. It is a strong option for a later “real semantic search” upgrade, but it is more than the current local library needs.

## Upgrade Path

The app now has:

- `embeddings` table
- `/api/semantic/reindex`
- `/api/semantic/search`
- settings for provider, model, and dimension

Future providers can keep the API stable and only replace the indexing/search backend.
