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

## 🔲 Phase 5 — Connect Retrieval to LLM (Complete)

- [ ] Build a function that takes a question, retrieves top chunks, and builds a prompt
- [ ] Send prompt + retrieved code to Groq LLM
- [ ] Get back a natural language answer grounded in real code
- [ ] Wrap in LangGraph for proper agent structure

---

## 🔲 Phase 6 — API + Web UI (Complete)

- [ ] FastAPI backend exposing the RAG agent
- [ ] Simple web UI to ask questions and see answers with source file references

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