# Implementation Plan: Mutual Fund FAQ RAG Chatbot

Phase-wise build guide derived from [architecture.md](./architecture.md) and [PRD.md](./PRD.md). Work through phases in order — each one produces a runnable, testable increment. Feed one phase at a time to Cursor, referencing `architecture.md` for component contracts and this file for the task list and acceptance checks.

---

## Phase 0 — Project Scaffolding
**Goal**: Repo skeleton in place, matching the structure in `architecture.md` §3.

**Tasks**
- Create directories: `config/`, `ingestion/`, `retrieval/`, `app/`, `data/chroma/`, `deliverables/`.
- Create `requirements.txt` with: `chromadb`, `sentence-transformers`, `streamlit`, `beautifulsoup4`, `requests`, `pyyaml`, `langchain-text-splitters` (or equivalent recursive splitter lib), plus an LLM client library once the model choice is finalized (e.g. `openai`, `anthropic`, or `transformers`).
- Add `.gitignore` covering `data/chroma/`, `__pycache__/`, `.venv/`, `*.pyc`.
- Create empty `README.md` (filled in Phase 9).
- Initialize git repo if not already done (`git init`), first commit = scaffolding only.

**Acceptance check**: `pip install -r requirements.txt` succeeds in a fresh venv; directory tree matches architecture.md §3.

---

## Phase 1 — Source Configuration
**Goal**: Single source of truth for the 5 HDFC scheme URLs.

**Tasks**
- Create `config/sources.yaml`:
  ```yaml
  amc: HDFC
  schemes:
    - category: Large Cap
      name: HDFC Large Cap Fund - Direct Growth
      url: https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth
    - category: Flexi Cap
      name: HDFC Flexi Cap Fund - Direct Growth
      url: https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth
    - category: ELSS
      name: HDFC ELSS Tax Saver Fund - Direct Plan Growth
      url: https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth
    - category: Small Cap
      name: HDFC Small Cap Fund - Direct Growth
      url: https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth
    - category: Balanced Advantage (Hybrid)
      name: HDFC Balanced Advantage Fund - Direct Growth
      url: https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth
  ```
- No code yet — this phase is data/config only, but it's the input every later phase reads from.

**Acceptance check**: YAML parses; exactly 5 schemes listed, matching PRD §6.1.

---

## Phase 2 — Loader
**Goal**: Fetch and clean the 5 source pages into structured `Document` objects (architecture.md §2.1).

**Tasks**
- Implement `ingestion/loader.py`:
  - `load_sources(config_path) -> list[Document]`
  - Fetch each URL with `requests`, parse with `BeautifulSoup`.
  - Strip nav/header/footer/ads/script tags; extract main content text (headings, fee tables, FAQ sections).
  - Attach metadata: `scheme_name`, `category`, `source_url`, `fetched_at` (today's date).
  - Handle fetch failures gracefully (log + skip, don't crash the whole run).
- Add a quick manual test script or `if __name__ == "__main__":` block that loads all 5 and prints text length + metadata per doc.

**Acceptance check**: Running the loader produces 5 `Document`s, each with non-trivial `raw_text` (sanity check: contains keywords like "expense ratio" or "exit load" for at least some docs) and correct metadata.

---

## Phase 3 — Chunker
**Goal**: Split each `Document` into retrieval-sized chunks with propagated metadata (architecture.md §2.2).

**Tasks**
- Implement `ingestion/chunker.py`:
  - `get_chunks(document) -> list[Chunk]`
  - Inspect actual fetched text structure first (print/log a sample from Phase 2 output) to decide: recursive character/markdown splitter for short fact/table sections, larger overlapping chunks for prose sections.
  - Implement recursive splitter path first (primary strategy per architecture.md); keep the interface swappable so a semantic splitter can be substituted later without touching downstream code.
  - Propagate `scheme_name`, `category`, `source_url`, `fetched_at` to every chunk; assign a unique `chunk_id`.
- Log chunk counts and a few sample chunks per scheme for manual sanity-checking (e.g., confirm "exit load" text isn't split mid-sentence from its value).

**Acceptance check**: Each of the 5 documents yields multiple chunks; spot-check that key facts (expense ratio, exit load, min SIP, lock-in for ELSS, riskometer, benchmark) each appear intact within a single chunk, not split across two.

---

## Phase 4 — Embedder + Vector Store
**Goal**: Embed all chunks and persist them in ChromaDB (architecture.md §2.3–2.4).

**Tasks**
- Implement `ingestion/embedder.py`:
  - Load `sentence-transformers/all-MiniLM-L6-v2` once (module-level singleton).
  - `embed(texts: list[str]) -> list[vector]`.
- Implement `ingestion/store.py`:
  - Initialize a persistent ChromaDB client at `./data/chroma/`.
  - `get_or_create_collection("hdfc_mf_faq")`.
  - `upsert(chunks, embeddings)` — writes `id`, `document` (chunk text), `embedding`, and full `metadata` per chunk.
- Implement `ingestion/run_ingest.py` as the CLI entrypoint: `load_sources → get_chunks (all docs) → embed → upsert`. Print a summary (schemes processed, total chunks, collection size after upsert).
- Make `run_ingest.py` idempotent: re-running should rebuild/replace the collection cleanly (e.g., delete-then-recreate the collection at the start of the run).

**Acceptance check**: `python ingestion/run_ingest.py` completes without error; `./data/chroma/` is populated; querying the collection directly (ad hoc script) for e.g. "expense ratio" returns chunks from the expected scheme.

---

## Phase 5 — Guardrail Router
**Goal**: PII and scope checks that run before any retrieval (architecture.md §2.5, PRD §7.4).

**Tasks**
- Implement `retrieval/guardrails.py`:
  - `contains_pii(query: str) -> bool` — regex checks for PAN pattern, 12-digit Aadhaar, long digit sequences resembling account numbers, email pattern, phone number pattern, OTP-like short digit codes in context.
  - `classify_scope(query: str) -> Literal["in_scope", "advice", "performance"]` — start with a keyword/pattern-based classifier (e.g., "should i", "buy", "sell", "which fund is better" → advice; "returns", "cagr", "compare performance" → performance; else in_scope). Leave a clear extension point to swap in an LLM-based intent check later if the keyword approach proves too brittle.
  - `route(query) -> GuardrailResult` combining both checks, returning one of: `PII_BLOCKED`, `ADVICE_REFUSED`, `PERFORMANCE_REFUSED`, `PROCEED`.
- Define the three fixed response templates (PII decline, advice refusal + educational link, performance refusal + factsheet-link instruction) as constants here, matching architecture.md §4 table.
- **No query content is logged anywhere when `PII_BLOCKED`.**

**Acceptance check**: Unit-test guardrails.py directly with the sample queries from PRD §6.4 (advice questions) and a few synthetic PII strings (fake PAN/email/phone) — confirm correct routing for each, and confirm in-scope factual questions (PRD §6.3 list) route to `PROCEED`.

---

## Phase 6 — Retriever
**Goal**: Query embedding + top-k similarity search against ChromaDB (architecture.md §2.6).

**Tasks**
- Implement `retrieval/retriever.py`:
  - `search(query: str, k: int = 4, scheme_filter: str | None = None) -> list[RetrievedChunk]`.
  - Embed query using the same embedder module from Phase 4 (import, don't duplicate model loading).
  - Optional: detect a scheme/category name mentioned in the query (simple string match against `config/sources.yaml` scheme names) and pass as a metadata filter to Chroma's query.
  - Return chunks sorted by similarity with their metadata intact.

**Acceptance check**: For each of the 7 factual question types in PRD §6.3, run `search()` manually against a hand-written sample query and confirm the top result comes from the correct scheme's chunk.

---

## Phase 7 — Answer Composer
**Goal**: Turn retrieved chunks into a grounded, constrained answer with citation (architecture.md §2.7).

**Tasks**
- Implement `retrieval/composer.py`:
  - `compose(query: str, chunks: list[RetrievedChunk]) -> Answer`.
  - Build a strict system prompt: answer only from provided context; if the fact isn't present, say so explicitly; never mention/compute returns or performance; ≤3 sentences.
  - Call the chosen LLM (finalize provider/model here — see PRD §13 open question) with query + concatenated top-k chunk text as context.
  - Deterministic post-processing (not delegated to the LLM):
    - Pick citation = `source_url` of the top-ranked chunk.
    - Append `"Last updated from sources: <fetched_at>"`.
    - Enforce ≤3 sentences (truncate/regenerate if the LLM overruns).
  - Add a minimum-similarity threshold check: if the top chunk's score is below threshold, skip the LLM call and return the fixed "not found in the sources I have" response (no citation fabricated).

**Acceptance check**: For each PRD §6.3 sample question, `compose()` returns an answer that (a) is factually correct against the source page, (b) is ≤3 sentences, (c) includes exactly one citation link, (d) includes the "Last updated from sources" line.

---

## Phase 8 — Wire the Query Pipeline
**Goal**: Single function tying guardrails → retriever → composer together, per architecture.md §5 "Query" sequence.

**Tasks**
- Implement `retrieval/pipeline.py`:
  - `answer_query(query: str) -> Response` — calls `guardrails.route()`, branches to the fixed refusal templates or continues to `retriever.search()` → `composer.compose()`.
  - This is the single function the UI will call — keep it dependency-free of any UI framework.

**Acceptance check**: Run the full PRD §6.3 + §6.4 question sets through `answer_query()` end-to-end and confirm behavior matches architecture.md §4's guardrail table exactly.

---

## Phase 9 — UI
**Goal**: Minimal Streamlit chat UI per architecture.md §2.8, PRD §7.3.

**Tasks**
- Implement `app/ui.py`:
  - Welcome line naming the AMC (HDFC) and the 5 schemes in scope.
  - 3 clickable example questions (pick from PRD §6.3 categories, e.g. expense ratio, ELSS lock-in, exit load).
  - Persistent banner: **"Facts-only. No investment advice."**
  - Chat input → calls `retrieval.pipeline.answer_query()` → renders answer text, citation as a clickable link, and the "Last updated from sources" line.
  - No storage of chat history beyond the in-session Streamlit state (nothing persisted to disk, consistent with the no-PII/no-storage constraint).

**Acceptance check**: `streamlit run app/ui.py` launches; manually run through the example questions plus one advice question plus one PII-containing question and confirm correct UI behavior for each.

---

## Phase 10 — Deliverables
**Goal**: Produce the 5 submission artifacts listed in PRD §10.

**Tasks**
- `deliverables/sources.csv` — the 5 URLs with category/scheme name columns (can be generated directly from `config/sources.yaml`).
- `deliverables/sample_qna.md` — run 5–10 queries (mix of all PRD §6.3 categories plus at least one refusal case) through the live pipeline and record query + answer + citation.
- `deliverables/disclaimer.txt` — the exact "Facts-only. No investment advice." snippet plus any refusal template text used in the UI.
- `README.md` — setup steps (env, `pip install`, `run_ingest.py`, `streamlit run app/ui.py`), scope statement (AMC + 5 schemes), known limitations (copy/adapt from PRD §12).
- Record the ≤3-min demo video only if hosting the working prototype isn't possible (per PRD §10).

**Acceptance check**: All 5 deliverables present and internally consistent with each other and with PRD/architecture docs.

---

## Phase 11 — Validation Against Acceptance Criteria
**Goal**: Final pass against PRD §11 before calling the build done.

**Tasks**
- Re-run every PRD §11 acceptance scenario (factual question, advice question, PII input, performance-comparison question) against the deployed/running app, not just unit-level pipeline calls.
- Confirm no PII is logged anywhere (check terminal/app logs after a PII-containing test query).
- Confirm re-running `run_ingest.py` from scratch reproduces a working app (tests idempotency claim from architecture.md §7).

**Acceptance check**: Every PRD §11 bullet passes manually; project is demo-ready.

---

## Notes for Guiding Cursor
- Point Cursor at `architecture.md` for *why* a component is shaped the way it is (interfaces, metadata schema, guardrail table) and at this file for *what to build next* and *how to know it's done*.
- Do phases strictly in order — each phase's acceptance check is the input contract the next phase assumes.
- Phase 7's LLM provider choice is the one open decision blocking full end-to-end testing (flagged in PRD §13) — resolve it before starting Phase 7.
