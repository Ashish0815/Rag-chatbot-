# PRD: Mutual Fund FAQ RAG Chatbot (Facts-Only)

## 1. Summary
A small Retrieval-Augmented Generation (RAG) chatbot that answers **factual** questions about a scoped set of HDFC mutual fund schemes (expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, statement downloads, etc.) using only official public pages as its knowledge source. Every answer cites exactly one source link, gives no investment advice, and refuses opinion/portfolio questions. This is a class demo project — scope is intentionally small and time-boxed.

## 2. Problem Statement
Retail investors and support/content teams repeatedly look up the same factual details about mutual fund schemes (fees, lock-ins, risk category, how to get statements). This information is scattered across official pages and is tedious to search manually. A narrow, trustworthy FAQ assistant that only answers from vetted public sources — and clearly cites where each answer came from — solves this without wading into performance predictions or investment advice, which is out of scope and regulatorily risky.

## 3. Goals
- Demonstrate a complete, working RAG pipeline end-to-end: ingestion → chunking → embedding → vector storage → retrieval → grounded answer generation.
- Answer factual questions about 5 HDFC mutual fund schemes accurately, with a source citation on every answer.
- Refuse non-factual (advice/opinion) questions gracefully, pointing to educational resources instead.
- Ship a minimal, demoable UI plus supporting deliverables (README, source list, sample Q&A, disclaimer) suitable for a class submission.

## 4. Non-Goals
- No investment advice, buy/sell recommendations, or portfolio suggestions.
- No performance computation or comparison across schemes (e.g., CAGR, returns).
- No handling or storage of PII (PAN, Aadhaar, account numbers, OTPs, emails, phone numbers).
- No scraping/using non-official sources (third-party blogs, forums, screenshots of app back-ends).
- No production-grade scale, auth, multi-tenant support, or monitoring — this is a demo prototype.

## 5. Target Users
- **Retail users** comparing HDFC scheme facts before deciding where to invest (they still do their own research/advice elsewhere).
- **Support/content teams** who need quick, sourced answers to repetitive MF questions.
- **Class evaluator/instructor** reviewing the working prototype and deliverables.

## 6. Scope

### 6.1 AMC & Schemes
Single AMC: **HDFC**. 5 schemes, one per category, all Direct–Growth plans:

| Category | Scheme | Source Page |
|---|---|---|
| Large Cap | HDFC Large Cap Fund | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| Flexi Cap | HDFC Flexi Cap (Equity) Fund | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| ELSS | HDFC ELSS Tax Saver Fund | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| Small Cap | HDFC Small Cap Fund | https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth |
| Balanced Advantage (Hybrid) | HDFC Balanced Advantage Fund | https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth |

### 6.2 Corpus
- The 5 scheme pages above form the core corpus (public pages only).
- Optionally supplement with official AMC/SEBI/AMFI pages for the same schemes (factsheets, KIM/SID, scheme FAQs, fee/charges pages, riskometer/benchmark notes, statement/tax-doc guides) — still counted within the "5 public pages" deliverable unless the assignment allows more.
- No third-party blogs, forums, or non-official aggregator commentary as sources.

### 6.3 Question Types In Scope
- Expense ratio
- Exit load
- Minimum SIP / minimum lumpsum investment
- ELSS lock-in period
- Riskometer level
- Benchmark index
- How to download capital-gains / account statements

### 6.4 Question Types Out of Scope (Must Refuse)
- "Should I buy/sell this fund?"
- "Which fund is better?"
- Return/performance predictions or comparisons
- Any question requiring PII to answer

## 7. Functional Requirements

### 7.1 Data Ingestion Pipeline
1. **Loading** — Fetch and parse the 5 (or more) public source pages into raw text, preserving scheme identity and source URL as metadata per document.
2. **Chunking** — Split documents into retrieval-sized chunks. Strategy (recursive vs. semantic) is chosen based on inspection of the actual page structure (e.g., recursive character/markdown-aware splitting for tabular fee/FAQ sections; semantic chunking if content is long-form prose). Each chunk retains source URL + scheme name metadata.
3. **Embedding** — Generate vector embeddings using `sentence-transformers/all-MiniLM-L6-v2`.
4. **Vector Storage** — Persist chunks + embeddings + metadata in **ChromaDB**.

### 7.2 Retrieval & Answer Generation
1. Accept a user query via the UI.
2. Embed the query with the same embedding model.
3. Retrieve top-k relevant chunks from ChromaDB (filtered/boosted by scheme name if a scheme is mentioned in the query).
4. Classify whether the query is a factual MF question or an out-of-scope (advice/opinion/PII) query.
   - If factual: generate an answer grounded strictly in retrieved chunks.
   - If out-of-scope: return the standard refusal message (see 7.4).
5. Attach exactly one source citation link (the URL of the most relevant retrieved chunk) to every factual answer.
6. Append the line: **"Last updated from sources: <date(s)>"** to every factual answer.
7. Keep factual answers to **≤3 sentences**.

### 7.3 UI Requirements
- Minimal chat UI with:
  - A welcome line introducing the assistant and its scope (HDFC, 5 named schemes).
  - 3 example questions the user can click/try.
  - A persistent note: **"Facts-only. No investment advice."**
- Chat input + response area showing the answer and its citation link.

### 7.4 Guardrails
- **Refusal behavior**: For opinion/portfolio/advice questions, respond with a polite facts-only refusal message plus a relevant educational link (e.g., a general investor-education page, not a recommendation). Example: *"I can only share factual scheme details, not investment advice. Here's an educational resource on how to evaluate mutual funds: <link>."*
- **PII handling**: Do not accept, process, log, or store PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers. If a user submits any of these, the assistant must decline and remind the user not to share such data.
- **No performance claims**: Never compute or compare returns/CAGR. If asked, redirect to the official factsheet link.
- **Grounding**: Answers must come only from retrieved corpus content — no fabrication when a fact isn't present in the corpus (respond with "not found in the sources I have" instead of guessing).

## 8. Architecture Overview

```
                 DATA INGESTION                                  DATA RETRIEVAL
 ┌────────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌──────────────┐   ┌────────────┐
 │  5 Public  │──▶│  Loading  │──▶│ Chunking  │──▶│ Embedding │──▶│  ChromaDB    │   │  User Query │
 │   Pages    │   │ (parse to │   │(recursive/│   │(all-MiniLM│   │ (vector store│   └─────┬──────┘
 │ (HDFC AMC) │   │   text)   │   │ semantic) │   │  -L6-v2)  │   │  + metadata) │         │
 └────────────┘   └───────────┘   └───────────┘   └───────────┘   └──────┬───────┘         ▼
                                                                          │          ┌────────────┐
                                                                          │◀─────────┤ Embed Query│
                                                                          │  top-k   └────────────┘
                                                                          ▼
                                                                  ┌───────────────┐
                                                                  │ Scope check → │
                                                                  │ grounded LLM  │
                                                                  │ answer + 1    │
                                                                  │ citation link │
                                                                  └───────────────┘
```

**Stack**
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (Hugging Face)
- Chunking: recursive and/or semantic, decided from actual page content
- Vector DB: ChromaDB
- LLM for answer synthesis: any instruction-following model wired to only use retrieved context (implementation detail, chosen during build)

## 9. Constraints
- **Public sources only** — no screenshots of app back-ends, no third-party blogs.
- **No PII** — never accept or store PAN, Aadhaar, account numbers, OTPs, emails, phone numbers.
- **No performance claims** — no return computation/comparison; defer to the official factsheet.
- **Clarity & transparency** — answers ≤3 sentences; every answer includes "Last updated from sources: <date>".

## 10. Deliverables
1. Working prototype link (app/notebook), or a ≤3-minute demo video if hosting isn't possible.
2. Source list (CSV/MD) of the URLs used to build the corpus.
3. README with setup steps, scope (AMC + schemes), and known limitations.
4. Sample Q&A file: 5–10 queries with the assistant's answers and citation links.
5. Disclaimer snippet used in the UI (facts-only, no advice).

## 11. Success Criteria (Acceptance)
- Given a factual question about one of the 5 HDFC schemes, the assistant returns a correct, sourced, ≤3-sentence answer with exactly one citation link and a "Last updated from sources" line.
- Given an opinion/advice question (e.g., "Should I buy this fund?"), the assistant refuses politely and offers an educational link instead of an opinion.
- Given a query containing PII-like input, the assistant declines to process/store it.
- Given a performance/return comparison question, the assistant does not compute or compare returns and instead links to the official factsheet.
- All deliverables listed in Section 10 are present and consistent with the scoped AMC/schemes.

## 12. Known Limitations (anticipated, to confirm post-build)
- Corpus is limited to 5 schemes under 1 AMC — no cross-AMC comparison possible.
- Source pages (Groww) are third-party display pages for official scheme data, not the AMC/SEBI/AMFI original filings directly; freshness depends on when those pages were last scraped/loaded into the corpus.
- No real-time data — figures are as of the ingestion date, not live.
- Small demo scale — not tested for concurrent users, adversarial inputs beyond basic PII/opinion guardrails, or long-tail phrasing.

## 13. Open Questions
- Confirm whether Groww pages alone satisfy "public pages from AMC/SEBI/AMFI," or whether official HDFC AMC/SEBI/AMFI pages should be added/substituted for the final corpus.
- Confirm the LLM/hosting choice for answer generation (not specified in the problem statement).
- Confirm hosting target for the working prototype (local notebook vs. deployed app) given the ≤3-min demo video fallback.
