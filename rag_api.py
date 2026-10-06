#necessary imports
import sqlite3
import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import chromadb
from chromadb.utils import embedding_functions
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph,END,START
from pydantic import BaseModel
import re
from typing import TypedDict, Annotated, Literal
from dotenv import load_dotenv
import os
import logging
from sentence_transformers import CrossEncoder
from rank_bm25 import BM25Okapi

#Adding re-ranker
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

#load env file
load_dotenv()

#setting logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

#instance of the fastapi
app = FastAPI()

#setting up cors
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"]
)

#Using a particular model
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name = 'all-MiniLM-L6-v2'
)

#Initializing the model
llm = ChatGroq(model=os.getenv("LLM_MODEL"), max_tokens=4096)

STOP_WORDS = {"a", "an", "the", "is", "are", "and", "or", "of", "to", "in", "on", "for", "with", "from", "this", "that"}

#tokemize the words for keyword searching
def tokenize(text):
    raw_words = re.findall(r'\w+', text)
    tokens = []
    for words in raw_words:
        split_words = re.sub(r'([a-z])([A-Z])', r'\1 \2', words).replace('_', ' ')
        tokens.extend(split_words.lower().split())
    return [t for t in tokens if t not in STOP_WORDS]

#connecting to DB
client = chromadb.PersistentClient(path=os.getenv("CHROMA_DB_PATH"))
collection = client.get_collection(
    name = os.getenv("COLLECTION_NAME"),
    embedding_function = embedding_function
)

#building bm25 by fetching all data from the collection
all_data = collection.get()
bm25_documents = all_data['documents']
bm25_metadatas = all_data['metadatas']
tokenized_corpus = [tokenize(doc) for doc in bm25_documents]
bm25_index = BM25Okapi(tokenized_corpus)

#State of the agent
class CodeRetrievalAgent(TypedDict):
    chunks: list
    user_question: str
    result: str
    sources: list
    history: str

#connection to the database
conn = sqlite3.connect("rag_memory.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS conversation_history (
                    session_id TEXT,
                    question TEXT,
                    answer TEXT,
                    timestamp TEXT)"""
                )
conn.commit()
#Request modal
class QuestionRequest(BaseModel):
    question: str
    session_id: str

#function to retrieve the chunks based on keyword matching
def bm25_search(query, top_k=5):
    try:
        tokenized_query = tokenize(query)
        scores = bm25_index.get_scores(tokenized_query)
        bm25_sources = [meta['file_path'] for meta in bm25_metadatas]
        combined = list(zip(bm25_documents, bm25_sources, scores))
        sorted_top_5 = sorted(combined, key=lambda x: x[2], reverse=True)[:top_k]
        matches = [item for item in sorted_top_5 if item[2] > 0]
        top_keyword_chunks = [item[0] for item in matches]
        top_keyword_sources = [item[1] for item in matches]
        return top_keyword_chunks, top_keyword_sources
    except Exception as e:
        logger.error(f"Key word searching failed, {e}")
        return [],[]

#function to retrieve the info. and build the prompt for the llm 
def retrieve_chunk(state: CodeRetrievalAgent):
    question = state['user_question']
    history = state['history']
    # updated_cleaner_question = ''  Not necessary as python does not create blocks for if, else, try, except, for, while
    #Formatting the questions and the asnwers
    history_text = "\n".join([f"Q: {q}\nA: {a}" for q, a in history])
    prompt = []
    sources = []
    try:
        updated_question = llm.invoke(f"""You are a query optimization assistant for a code search system that uses semantic vector search.

                    Given the conversation history and a new question, produce the BEST possible search query for finding relevant code.

                    Rules:
                    1. If the new question references something from history (like "what about X", "and that"), incorporate the missing context explicitly.
                    2. Convert the result into a SHORT, keyword-focused search query (not a full sentence) — remove filler words like "how does", "work", "explain".
                    3. Focus on the CORE technical concepts and terms.
                    4. Return ONLY the search query. No explanations, no extra text, no quotes.

                    Conversation history:
                    {history_text}

                    New question: {question}"""
                )
        updated_cleaner_question = re.sub(r'<think>.*?</think>', '', updated_question.content, flags=re.DOTALL).strip().lower()
    except Exception as e:
        logger.error(f"Query rewriting fails, using user typed question: {e}")
        updated_cleaner_question = question
    try:
        response = collection.query(query_texts=[updated_cleaner_question], n_results=10)
    except Exception as e:
        logger.error(f"Error while fetching data from DB: {e}")
    else:
        documents = response['documents'][0]
        metadatas = response['metadatas'][0]
        distances = response['distances'][0]
        if documents:
            logger.info(f"Best match distance: {distances[0]}")
            if distances[0] <= 0.9:
                for i in range(len(documents)):
                    file_path = metadatas[i]['file_path']
                    content = documents[i][:800]
                    prompt.append(f"file_path: {file_path}, content: {content}")
                    sources.append(file_path)
            else:
                logger.warning("Semantic results too far away, ignoring them")

    #calling keyword match chunk retrieval
    keyword_chunks, keyword_sources = bm25_search(updated_cleaner_question, 10)
    formatted_keyword_chunks = []
    for i in range(len(keyword_chunks)):
        file_path = keyword_sources[i]
        content = keyword_chunks[i][:800]
        formatted_keyword_chunks.append(f"file_path: {file_path}, content: {content}")

    combined_dict = {}
    for chunk, source in zip(prompt, sources):
        combined_dict[chunk] = source
    for chunk, source in zip(formatted_keyword_chunks, keyword_sources):
        combined_dict[chunk] = source

    final_chunks = list(combined_dict.keys())
    final_sources = list(combined_dict.values())

    #printing final chunks length
    logger.info(f"semantic={len(prompt)} keyword={len(formatted_keyword_chunks)} merged={len(final_chunks)}")
    
    return {"chunks": final_chunks, "sources": final_sources}

#funciton to re-rank chunks for better answer for the user
def rerank_chunks(state: CodeRetrievalAgent):
    question = state['user_question']
    chunks = state['chunks']
    sources = state['sources']
    if chunks == []:
        return {'result': 'Sorry I Could not find any relevant data.'}
    paired_chunks = []
    for chunk in chunks:
        pair = (question, chunk)
        paired_chunks.append(pair)
    try:
        scores = reranker.predict(paired_chunks)
        combined = list(zip(chunks, sources, scores))
        combined_sorted = sorted(combined, key=lambda x: x[2], reverse=True)
        top_5 = combined_sorted[:5]
        reranked_chunks = [item[0] for item in top_5]
        reranked_sources = [item[1] for item in top_5]
        unique_sources = list(set(reranked_sources))
        return {"chunks": reranked_chunks, "sources": unique_sources}
    except Exception as e:
        logger.error(f"Re-ranking failed, falling back to the original output reteieved by the model, {e}")
        return {"chunks": chunks[:5], "sources": list(set(sources[:5]))}
    

#function to generate the final answer
def generate_answer(state: CodeRetrievalAgent):
    if state['chunks'] == []:
        return {"result": 'Sorry, I could not find any relevant data!'}
    question = state['user_question']
    history = state['history']
     # STEP 1: format history into text (same pattern as retrieve_chunk)
    history_text = "\n".join([f"Q: {q}\nA: {a}" for q, a in history])
    
    # STEP 2: update the instructions to MENTION history exists
    message = """Here is code retrieved from the user's codebase, their question, and the recent conversation history.
                If there is conversation history, use it to understand context or references in the current question.
                If the provided code does NOT actually relate to or answer the question, 
                clearly say "I couldn't find relevant code for this question" instead of guessing or forcing an answer.
                Otherwise, answer based on the code provided and cite the filepath."""
    chunks_text = "\n\n".join(state['chunks'])
    prompt = f"{message}\n\nQuestion: {question}\n\nRelevant Code:\n{chunks_text}\n\nHistory:\n{history_text}"
    try:
        response = llm.invoke(prompt)
    except Exception as e:
        logger.error(f"LLM did not produced the result")
        return {"result":"I am having trouble generating the response right now.", "sources":[]}
    cleaner_response = re.sub(r'<think>.*?</think>', '', response.content, flags=re.DOTALL).strip()
    if "find relevant code" in cleaner_response.lower():
        logger.warning("LLM could not find relevant code from the retrieved chunks")
    return {"result": cleaner_response, "sources": state["sources"]}

#building the graph
graph = StateGraph(CodeRetrievalAgent)

#adding nodes
graph.add_node("retrieve_chunk", retrieve_chunk)
graph.add_node("rerank_chunks", rerank_chunks)
graph.add_node("generate_answer", generate_answer)

#starting point
graph.set_entry_point("retrieve_chunk")

#adding edges
graph.add_edge("retrieve_chunk", "rerank_chunks")
graph.add_edge("rerank_chunks", "generate_answer")

#ending point
graph.add_edge("generate_answer", END)

#compiling
agent = graph.compile()

#api route: when users ask a question
@app.post('/ask')
def ask_question(state: QuestionRequest):
    logger.info(f"Question asked: {state.question}")
    session_id = state.session_id
    #fetching history
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT question, answer from conversation_history where session_id=? ORDER BY timestamp DESC LIMIT 3",(session_id,))       # comma added as sqlite's execute command excepts a tuple, and without the comma it is treated as a string
        history = cursor.fetchall()[::-1]
        conn.commit()
    except Exception as e:
        history = []
        logger.error(f"Cannot fetch the History from the DB, sending history as empty: {e}")

    try:
        result = agent.invoke({"chunks":[], "user_question": state.question, "result":'', "sources": [], "history": history})
    except Exception as e:
        logger.error(f"Agent invocation failed: {e}")
        return {"answer":"Something went wrong while processing your question. Please try again.", "sources": []}
    
    try:
        #saving this question and answer in history
        cursor.execute("INSERT into conversation_history VALUES (?,?,?,?)",(session_id, state.question, result['result'], datetime.datetime.now()))
        conn.commit()
    except Exception as e:
        logger.error(f"Error while saving the history in the DB: {e}")

    logger.info(f"Answer: {result['result']}")
    return {"answer":result["result"], "sources": result["sources"]}
