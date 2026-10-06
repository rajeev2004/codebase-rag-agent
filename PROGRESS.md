# Codebase RAG Agent — Progress Log

Building a Retrieval-Augmented Generation (RAG) system to answer questions about the `abhi-chord` codebase using semantic search + LLM.

---

## ✅ Phase 1 — Learning Fundamentals (Complete)

- Learned what embeddings are and how they represent meaning as vectors
- Tested `sentence-transformers` (`all-MiniLM-L6-v2` model) — confirmed 384-dimension output
- Manually calculated cosine similarity to understand how semantic matching works
- Learned ChromaDB basics — collections, adding documents, querying
- Understood the difference between vectors (general math term) and embeddings (meaning-specific vectors)

**Files:** `test_embedding.py`, `test_chromadb.py`

---

## ✅ Phase 2 — Code Chunking Strategy (Complete)

- Explored chunking strategies: by file, by fixed lines, by function/route
- Chose function/route-based chunking — respects code's natural logical boundaries
- Built `split_into_chunks()` using regex to detect function/route/export boundaries
- Added indentation check to avoid incorrectly splitting nested functions
- Added comment-pulling logic — comments above functions get included in the right chunk
- Validated on 2 real files (`claims.js` → 5 chunks, `claimwebhook.js` → 11 chunks) — both structurally correct

**Files:** `test_chunking.py`

---

## ✅ Phase 3 — Full Indexing Pipeline (Complete)

- Walked through `abhi-chord/packages/backend/src/routes` and `/logic` folders (102 files)
- Applied chunking to all files → 1151 total chunks generated
- Attached metadata to each chunk: `file_path`, `chunk_index`, unique `id`
- Set up persistent ChromaDB client (`./chroma_db`)
- Batch-embedded and stored all 1151 chunks in one efficient `.add()` call

**Files:** `index_codebase.py`

---

## ✅ Phase 4 — Retrieval Validation (Complete)

- Queried the stored collection with real question: *"how does soft delete work for activities"*
- Correctly retrieved the 2 most relevant delete-activity routes as top matches
- Confirmed semantic search works — found relevant code by MEANING, not just keyword match

**Files:** `test_retrieval.py`

---

## ✅ Phase 5 — Connect Retrieval to LLM (Complete)

- Build a function that takes a question, retrieves top chunks, and builds a prompt
- Send prompt + retrieved code to Groq LLM
- Get back a natural language answer grounded in real code
- Wrap in LangGraph for proper agent structure

---

## ✅ Phase 6 — API + Web UI (Complete)

- FastAPI backend exposing the RAG agent
- Simple web UI to ask questions and see answers with source file references

---

## ✅ Phase 7 — Tree-sitter Based Chunking (Complete)

- Replaced regex-based chunking with proper AST parsing using `tree-sitter` + `tree-sitter-javascript`
- Built `extract_chunk_treesitter()` — walks the syntax tree, correctly distinguishes real logic (functions) from simple data (imports, arrays, constants), merges consecutive simple declarations, attaches comments precisely
- Fixed edge cases discovered during testing:
  - Multi-declarator lines (e.g. `const x = ..., y = ...`) — now correctly flips to "complex" if ANY declarator is a function
  - Boolean literal values (`true`/`false`) — added to the simple-data whitelist
- Re-indexed routes + logic folders into a new collection (`chroma_db_v2`) → 1815 chunks (vs 1151 with regex) — more precise, granular boundaries
- Increased `n_results` from 3 to 5 in the RAG agent — fixed cases where the correct answer ranked just outside top-3 among semantically similar files (e.g. diet plan generation question)
- Verified accuracy on real questions: staffuser deletion, appointment booking, diet plan generation — all returning detailed, correctly-cited, accurate answers

**Files:** `index_codebase.py` (rewritten with tree-sitter), `test_treesitter.py` (prototyping/validation)

### Key learnings
- Tree-sitter parses actual JavaScript grammar (AST) rather than guessing with regex — far more robust across different code styles
- Clarified token limit mechanics: `max_tokens` controls LLM output only; Groq's account-level TPM rate limit covers input+output combined — this is why chunk truncation (`[:800]`) was necessary
- Confirmed embedding model weights load once per process (at server/script startup), not per-request — efficient by design

---

## ✅ Phase 8 — Expanded Backend Coverage (Complete)

- Expanded `TARGET_FOLDERS` to include: `common`, `middleware`, `partners`, `cron`, `migrations` (in addition to `routes` and `logic`)
- Re-indexed into a new collection (`ABHI-CHORD-Full-Backend` in `chroma_db_v2`) → 2283 total chunks (up from 1815)
- Confirmed migrations folder correctly indexed and retrievable (e.g. `create_patients_table_creation.js` found via debug queries)

### ⚠️ Known Limitation — Phrasing sensitivity in semantic search

Discovered that the SAME underlying question, phrased differently, can retrieve significantly different (and sometimes worse) results:
- Short/keyword query: `"patients table columns schema"` → correctly ranked the actual table-creation migration file at position 3
- Longer/conversational query: `"what are all the columns in the patients table schema"` → the SAME file dropped out of top-10 entirely

This is an inherent characteristic of embedding-based semantic search — longer, natural-language phrasing can dilute the question's embedding, shifting which chunks rank closest. Not a bug in the chunking or retrieval logic itself, but a genuine limitation of the current approach.

**Future improvement — Query Rewriting/Transformation:**
Before searching ChromaDB, use the LLM to rewrite the user's natural-language question into a shorter, more keyword-focused search query first, then use THAT rewritten query for retrieval. This is a well-known RAG technique ("query transformation") that would make retrieval more robust to phrasing variation, at the cost of an extra LLM call (slightly slower, more tokens per request). Planned as a future enhancement.

**Files:** `index_codebase.py` (updated TARGET_FOLDERS + collection name)

---

## ✅ Phase 9 — Conversational Memory with Query Rewriting (Complete)

- Added `conversation_history` SQLite table (`session_id`, `question`, `answer`, `timestamp`) to persist conversation context
- Added `session_id` to frontend (generated per page load via `Date.now()`) and backend request model
- Built query rewriting step inside `retrieve_chunk` — uses conversation history + new question to produce a standalone, keyword-focused search query BEFORE retrieval. This resolves the Phase 8 "phrasing sensitivity" limitation AND solves the "dangling reference" problem for follow-up questions (e.g. "what about staffusers?")
- Updated `generate_answer` to include formatted conversation history in its final prompt, so answers stay contextually coherent across turns
- History is fetched in the API route (outside the LangGraph, before invoking) and passed into agent state as part of the initial invoke; new Q&A pairs are saved back to SQLite after each response
- Tested successfully: 
  - Q1: "how does soft delete work for activities?" → correctly identified as a hard delete
  - Q2: "what about staffusers?" → correctly understood the dangling reference, rewrote it into a standalone query, retrieved `staffuser.js`, and gave a coherent answer consistent with Q1's reasoning

**Files:** `rag_api.py` (added memory/rewriting logic), `index.html` (added `session_id` to requests)

### Key learnings
- Query rewriting solves two problems at once: resolving conversational references AND normalizing phrasing for more consistent retrieval
- Kept SQLite reads/writes OUTSIDE the LangGraph (in the API route), consistent with how history is saved — cleaner separation than adding a dedicated "fetch_history" node
- `session_id` (identifies an ongoing conversation) is a fundamentally different concept from `thread_id`-style caching (matching on identical repeatable inputs) — free-form questions can't be reliably deduplicated the same way structured quiz inputs can

---

## ✅ Phase 10 — Production Hardening: Config & Logging (Complete)

- Moved all hardcoded config (API keys, model names, paths, collection names) to `.env`
- Created `.env.example` for documentation, added `.env` to `.gitignore`
- Replaced `print()` statements with proper `logging` module (INFO/WARNING levels, timestamped output via `logging.basicConfig()`)
- Discovered Groq API rate limiting (429) happens in real usage — confirmed `langchain-groq`'s built-in retry logic handles it automatically

**Files:** `rag_api.py`, `index_codebase.py`, `.env`, `.env.example`

### Key learnings
- `os.getenv()` and `os.environ.get()` are functionally identical
- `logging.basicConfig()` configures the root logger, which third-party libraries (httpx, sentence-transformers) also report through — explains why external library logs (e.g. Groq HTTP requests) appear alongside application logs
- `logging.getLogger(__name__)` names the logger after the current module, using Python's built-in `__name__` variable

---

## ✅ Phase 11 — Production Hardening: Error Handling & Retry Resilience (Complete)

- Wrapped every external call (LLM invocations, ChromaDB queries, SQLite operations) in try/except blocks
- Each failure point has a sensible fallback: query rewriting failure → use original question; retrieval failure → empty chunks; generation failure → user-friendly error message; history fetch/save failures → logged but don't block the user from getting an answer
- Separated fetch/save history into independent try/except blocks so a save failure never discards an already-generated answer
- Added a warning log when the LLM itself determines retrieved code isn't relevant (a semantic check complementing the earlier mechanical distance threshold)

**Files:** `rag_api.py`

### Key learnings
- Python does not have block-scoping like JavaScript — variables assigned inside `try`/`except`/`if` blocks remain accessible afterward, as long as one branch always executes
- Two complementary safety nets exist for irrelevant questions: a mechanical distance threshold (fast, catches extreme mismatches) and LLM-based semantic judgment (catches subtler mismatches the threshold misses)

---

## ✅ Phase 12 — Incremental Re-Indexing (Complete)

- Built a content-hash-based change detection system to avoid full re-indexing on every run
- Added `file_index_tracking` SQLite table (`file_path` PRIMARY KEY, `content_hash`, `last_indexed`)
- On each indexing run: compute SHA256 hash of each file's content, compare against stored hash
  - Unchanged files → skipped entirely (no re-chunking, no re-embedding)
  - Changed files → old chunks deleted from ChromaDB (via `file_path` metadata filter), file re-chunked and re-embedded, tracking table updated
  - New files → chunked, embedded, and added to tracking table
  - Deleted files (tracked previously but no longer found on disk) → chunks removed from ChromaDB, tracking row deleted
- Switched from `create_collection` to `get_or_create_collection` to support repeated runs against the same collection
- Guarded the final `collection.add()` call against empty chunk lists (ChromaDB rejects empty add requests)
- Verified end-to-end: fresh index (2294 chunks) → re-run unchanged (0 chunks, all skipped) → edit one file → re-run (5 chunks, only the changed file reprocessed, tracking table correctly updated without being wiped)

**Files:** `index_codebase.py` (rewritten with incremental logic), `indexing_tracker.db` (new tracking database, gitignored)

### Key learnings / bugs debugged
- `fetchall()` on a single-column query returns a list of tuples, not plain values — must extract with `row[0]`, otherwise string comparisons silently fail (caused the entire tracking table to be wiped on the second run)
- Deleted-file detection logic must iterate over *previously tracked* files checking against the *current* file list — not the reverse (which instead finds newly added files)
- Metadata filter key names must match exactly (`file_path` vs `file_paths` typo caused a silent no-op delete)
- Python does not have block scoping — but SQLite tuple-vs-string mismatches are a much easier trap to fall into when reading query results

---

## ✅ Phase 13 — Cross-Encoder Re-Ranking (Complete)

- Widened initial ChromaDB retrieval from 5 to 10 candidates
- Added a dedicated re-ranking step using `cross-encoder/ms-marco-MiniLM-L-6-v2` (via `sentence-transformers`) — a model purpose-built for scoring (query, document) pairs jointly, more precise than comparing separately-computed embedding vectors
- New `rerank_chunks` node inserted between `retrieve_chunk` and `generate_answer`: builds (question, chunk) pairs, scores them with the cross-encoder, sorts by score, keeps top 5
- Removed premature source deduplication from `retrieve_chunk` (was breaking the parallel chunks/sources/scores alignment needed for `zip()`-based sorting) — deduplication now happens after re-ranking finalizes the top 5
- Verified empirically with before/after logging: for the "diet plan generation" question, `mealtags.js` moved from rank 7 (by raw embedding distance) to rank 2 (after re-ranking) — concrete proof the cross-encoder performs genuine, independent relevance judgment rather than passing through ChromaDB's original order
- Fixed a model deprecation issue along the way — `qwen/qwen3.6-27b` was retired by Groq; switched to `openai/gpt-oss-120b` (also free tier)

**Files:** `rag_api.py`

### Key learnings
- Bi-encoders (embedding models) encode query and document separately, then compare vectors — fast, enables pre-computation, but less precise
- Cross-encoders process query and document together in one pass — slower (can't pre-compute), but more accurate at judging relevance — the standard "retrieve wide with bi-encoder, re-rank narrow with cross-encoder" pattern used in production RAG systems
- `CrossEncoder.predict(pairs)` returns raw scores in the SAME order as input — it does not sort; sorting is the caller's responsibility (via `zip()` + `sorted(..., key=lambda x: x[2], reverse=True)`)
- Cross-encoder scores are unbounded logits (can be negative) — only relative ranking matters, not absolute thresholds

---

## ✅ Phase 14 — Hybrid Search (Semantic + Keyword/BM25) (Complete)

- Added BM25 keyword search alongside existing ChromaDB semantic search, addressing the weakness that pure embedding search can be imprecise for exact identifier lookups (specific function/table/variable names)
- Built a custom code-aware tokenizer: regex-based word extraction, stop-word removal, and camelCase/snake_case splitting (e.g. `processClaimWebhook` → `process`, `claim`, `webhook`) — validated empirically that naive `.split()` tokenization fails to match multi-word identifiers, and that stop words can cause false-positive matches
- BM25 index built once at server startup by pulling all chunks from ChromaDB via `collection.get()` — kept in sync automatically since it's rebuilt from whatever ChromaDB currently holds, no separate persistence needed
- New `bm25_search()` helper function (not a graph node) mirrors the existing re-ranking sort pattern (zip + sorted by score descending)
- `retrieve_chunk` now combines semantic (top 10) and keyword (top 10) results, deduplicated via a dict keyed by the full formatted chunk string, before passing the combined pool to the existing (unchanged) `rerank_chunks` node
- Verified with a real test case: "what does processClaimWebhook do" — correctly retrieved the exact function via keyword matching and produced a comprehensive, accurate answer

**Files:** `rag_api.py`

### Key learnings
- BM25 measures keyword overlap, not meaning — complementary to embeddings, which measure semantic similarity but can be imprecise on exact terms
- Tokenization is used only internally for BM25's scoring math; the actual returned content remains the original untokenized text throughout
- Scoring conventions differ by system: ChromaDB distance (lower = better) vs. cross-encoder/BM25 scores (higher = better) — both correctly handled in this codebase via `reverse=True` sorting where appropriate
- Deduplication by exact chunk-string match is reliable here specifically because both retrieval paths (ChromaDB `.query()` and `.get()`) pull from the same underlying stored text with identical truncation applied

---

## ✅ Phase 15 — Retrieval Hardening (Complete)

- Reworked `retrieve_chunk` so the two retrieval paths are independent: a failed or distant semantic search no longer blocks keyword search. The 0.9 distance gate now only discards the semantic results, and the request ends empty only if both paths return nothing.
- `bm25_search` now drops zero-score chunks. Before, a query with no keyword match returned arbitrary chunks in corpus order, and those flowed into the re-ranker.
- Used `try/except/else` so the code that depends on the ChromaDB response runs only when the query succeeded.
- Added a per-request log line (`semantic=… keyword=… merged=…`) to show which path contributed.
- Fixed two small bugs: conversation history was reaching the LLM newest-first (now reversed), and the "no relevant code" warning never fired because the string comparison was case- and punctuation-sensitive.

**Files:** `rag_api.py`

### Key learnings
- The distance gate rarely fires. Best distances were about 0.40-0.47 for real questions, 0.59 for an off-topic one, and 0.75 for gibberish, all under 0.9. The LLM's own "couldn't find relevant code" check does the real rejecting.
- `else` after `try/except` runs only if the `try` raised nothing.

### ⚠️ Known limitations / next steps
- BM25 is built at server startup, so it goes stale if indexing runs while the server is up. Restart after re-indexing.
- Off-topic questions still send 5 irrelevant chunks to the LLM before it refuses, which spends tokens.
- Next: Docker and deployment.