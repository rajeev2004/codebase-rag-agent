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

## 🔲 Phase 6 — API + Web UI (Not Started)

- [ ] FastAPI backend exposing the RAG agent
- [ ] Simple web UI to ask questions and see answers with source file references

---

## 🔲 Phase 7 — Scale Up (Not Started)

- [ ] Expand indexing to more folders (migrations, frontend)
- [ ] Add re-indexing capability (detect changed files, update only those)