# Architecture: Mutual Fund FAQ RAG Chatbot

Derived from [PRD.md](./PRD.md). This document specifies the technical design for the two pipelines called out in the PRD — **Data Ingestion** and **Data Retrieval** — plus the UI and guardrail layers that sit around them.

## 1. System Context

```
                         ┌─────────────────────────────────────────┐
                         │              Offline / Batch              │
                         │            DATA INGESTION PIPELINE         │
                         │                                             │
   5 Public Scheme  ───▶ │  Loader → Chunker → Embedder → ChromaDB   │
   Pages (HDFC/Groww)    │                                             │
                         └─────────────────────┬───────────────────────┘
                                                │ persisted collection
                                                ▼
                         ┌─────────────────────────────────────────┐
                         │               Online / Runtime             │
                         │           DATA RETRIEVAL PIPELINE          │
                         │                                             │
   User ──▶ UI  ───────▶ │ Guardrail Router → Retriever → Answer     │ ───▶ Answer + Citation
                         │  (scope/PII check)   (ChromaDB)  Composer  │
                         └─────────────────────────────────────────┘
```

Two independent runs: ingestion is run once (or re-run when sources change) to populate the vector store; retrieval runs per user query against the already-populated store. This separation matches the PRD's "Loading → Chunking → Embedding → Store Vector Data" ingestion stage and the query-time "Data Retrieval" stage.

## 2. Component Breakdown

### 2.1 Loader (`ingestion/loader.py`)
- **Input**: List of the 5 source URLs (config-driven, see `config/sources.yaml`), one per HDFC scheme category.
- **Responsibility**: Fetch each page, strip nav/ads/boilerplate HTML, extract the meaningful text blocks (scheme overview, fees & expenses, exit load, lock-in, riskometer, benchmark, min SIP/lumpsum, statement/tax-doc instructions).
- **Output**: One `Document` per source page:
  ```json
  {
    "scheme_name": "HDFC Large Cap Fund - Direct Growth",
    "category": "Large Cap",
    "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "fetched_at": "2026-09-27",
    "raw_text": "..."
  }
  ```
- **Notes**: No screenshots, no non-official sources (PRD constraint). Store `fetched_at` — it feeds the "Last updated from sources" line at answer time.

### 2.2 Chunker (`ingestion/chunker.py`)
- **Strategy selection** (per PRD: "decide chunking strategy based on the data"):
  - Fee/fact tables (expense ratio, exit load, min SIP, lock-in, riskometer, benchmark) are short, structured key-value facts → use **recursive character/markdown-aware splitting** with small chunk size (~200–400 tokens) and section-aware separators (headings, table rows) so one fact isn't split across chunks.
  - Any long-form prose (fund objective, FAQ narrative sections) → allow slightly larger chunks (~500 tokens) with overlap (~50–75 tokens) to preserve context.
  - Decision is made per-document after inspecting actual page structure during implementation; both splitters are available behind one interface (`get_chunks(document) -> list[Chunk]`) so the choice is swappable without touching downstream code.
- **Metadata propagated to every chunk**: `scheme_name`, `category`, `source_url`, `fetched_at`, `chunk_id`.

### 2.3 Embedder (`ingestion/embedder.py`)
- **Model**: `sentence-transformers/all-MiniLM-L6-v2` (384-dim embeddings, CPU-friendly, fast — appropriate for a 5-page demo corpus).
- Same model instance/config used for both corpus chunks (batch, offline) and live user queries (single, online) — embedding space must match.

### 2.4 Vector Store (`ingestion/store.py`)
- **ChromaDB**, one persistent collection, e.g. `hdfc_mf_faq`.
- Each record: `embedding`, `document` (chunk text), `metadata` (scheme_name, category, source_url, fetched_at, chunk_id), `id`.
- Persisted to local disk (`./data/chroma/`) so the app can start without re-ingesting every run.

### 2.5 Guardrail Router (`retrieval/guardrails.py`)
Runs **before** retrieval on every incoming query:
1. **PII check** — regex/heuristic detection for PAN (`[A-Z]{5}[0-9]{4}[A-Z]`), Aadhaar (12-digit), account numbers, emails, phone numbers, OTP-like 4–6 digit codes in context. If matched → short-circuit with a decline-and-remind message; never log/store the raw query.
2. **Scope classifier** — determines if the query is a factual MF lookup (expense ratio, exit load, min SIP, lock-in, riskometer, benchmark, statement download) vs. an opinion/advice/performance-comparison query (e.g., "should I buy", "which is best", "what returns will I get"). Implementation: a small keyword/pattern classifier first (cheap, deterministic for a demo), optionally backed by an LLM intent check if ambiguous.
   - **Out of scope** → return the standard refusal + educational link (Section 4), skip retrieval entirely.
   - **In scope** → proceed to Retriever.

### 2.6 Retriever (`retrieval/retriever.py`)
- Embeds the query with the same `all-MiniLM-L6-v2` model.
- Runs a similarity search against ChromaDB (top-k, default k=4), optionally filtered by `scheme_name`/`category` metadata if the query names a specific scheme or category.
- Returns ranked chunks with metadata (including `source_url`, `fetched_at`).

### 2.7 Answer Composer (`retrieval/composer.py`)
- Feeds the user query + retrieved chunks (context only, nothing else) to an LLM with a strict system prompt: *answer only from the provided context; if the fact isn't present, say so; never mention returns/performance; keep to ≤3 sentences.*
- Post-processing (deterministic, not left to the LLM):
  - Appends exactly **one** citation link — the `source_url` of the top-ranked retrieved chunk.
  - Appends **"Last updated from sources: `<fetched_at>`"**.
  - Truncates/validates the answer is ≤3 sentences before returning.
- If no chunk clears a minimum similarity threshold, returns a "not found in the sources I have" response with no fabricated fact (still no citation fabrication).

### 2.8 UI (`app/ui.py`)
- Single-page chat UI (Streamlit, as the simplest option for a class demo).
- Static elements: welcome line, 3 clickable example questions, persistent banner: **"Facts-only. No investment advice."**
- Chat area renders: assistant answer text, the citation link (as a clickable link), and the "Last updated from sources" line.
- No user auth, no session persistence beyond the browser tab — matches demo scope.

## 3. Proposed Project Structure

```
Rag/
├── Docs/
│   ├── problemstatement.txt
│   ├── PRD.md
│   └── architecture.md
├── config/
│   └── sources.yaml            # the 5 scheme URLs + category labels
├── ingestion/
│   ├── loader.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── store.py
│   └── run_ingest.py           # CLI entrypoint: loads → chunks → embeds → writes to Chroma
├── retrieval/
│   ├── guardrails.py
│   ├── retriever.py
│   └── composer.py
├── app/
│   └── ui.py                   # Streamlit entrypoint
├── data/
│   └── chroma/                 # persisted vector store (gitignored)
├── deliverables/
│   ├── sources.csv             # source list deliverable
│   ├── sample_qna.md           # 5–10 sample Q&A deliverable
│   └── disclaimer.txt          # UI disclaimer snippet deliverable
├── requirements.txt
└── README.md
```

## 4. Guardrail Behavior Reference

| Trigger | Response |
|---|---|
| Opinion/advice question ("should I buy/sell", "which fund is best") | Polite refusal + one educational (non-recommendation) link. |
| Performance/return question ("what returns will I get", "compare CAGR") | Refusal to compute/compare + link to the scheme's official factsheet. |
| PII detected in query (PAN, Aadhaar, account no., OTP, email, phone) | Decline to process; remind user not to share such data; nothing logged/stored. |
| Fact not present in retrieved context | "Not found in the sources I have" — no citation fabricated, no guess. |
| In-scope factual question | Grounded answer, ≤3 sentences, 1 citation link, "Last updated from sources" line. |

## 5. Sequence Flows

**Ingestion (run once / on source refresh):**
`run_ingest.py` → Loader.fetch(urls) → Chunker.split(docs) → Embedder.embed(chunks) → Store.upsert(chunks, embeddings, metadata) → ChromaDB persisted.

**Query (per user turn):**
User query → Guardrails.check(query) →
  - if PII → decline response (end)
  - if out-of-scope → refusal + educational link (end)
  - if in-scope → Retriever.search(query) → Composer.generate(query, chunks) → answer + citation + last-updated line → UI render.

## 6. Technology Choices

| Layer | Choice | Rationale |
|---|---|---|
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` | Per PRD; small, fast, CPU-only, sufficient for a 5-page corpus. |
| Vector DB | ChromaDB | Per PRD; zero-ops local persistence, simple Python API. |
| Chunking | Recursive (default) with markdown/section-aware separators; semantic splitting as fallback for prose sections | Decided per actual page structure, per PRD instruction. |
| LLM (answer synthesis) | Any instruction-following chat model reachable via API/local runtime, constrained to context-only answers via system prompt | Not fixed in PRD; pick based on available access at build time. |
| UI | Streamlit | Fastest path to a demoable chat UI for a class prototype. |
| Language | Python | Ecosystem fit for sentence-transformers, Chroma, and Streamlit. |

## 7. Non-Functional Notes
- **Scale**: single-user demo, small corpus (5 pages) — no need for sharding, caching layers, or async workers.
- **Latency**: embedding + top-k retrieval over a few hundred chunks is near-instant; LLM call dominates response time.
- **Security/Privacy**: no PII storage by design (Section 2.5); no auth needed since no user data is retained.
- **Reproducibility**: `run_ingest.py` is idempotent — re-running rebuilds the collection from the same 5 sources so the demo can be reset cleanly.
