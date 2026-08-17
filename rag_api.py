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
llm = ChatGroq(model="qwen/qwen3.6-27b", max_tokens=4096)

#connecting to DB
client = chromadb.PersistentClient('./chroma_db_v2')
collection = client.get_collection(
    name = 'ABHI-CHORD-Full-Backend',
    embedding_function = embedding_function
)

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

#function to retrieve the info. and build the prompt for the llm 
def retrieve_chunk(state: CodeRetrievalAgent):
    question = state['user_question']
    history = state['history']
    #Formatting the questions and the asnwers
    history_text = "\n".join([f"Q: {q}\nA: {a}" for q, a in history])
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
    response = collection.query(query_texts=[updated_cleaner_question], n_results=5)
    prompt = []
    sources = []
    documents = response['documents'][0]
    metadatas = response['metadatas'][0]
    distances = response['distances'][0]
    print(f"Best match distance: {distances[0]}") 
    if distances[0] > 0.9:      # No relevant data found
        return {"chunks":[]}
    for i in range(len(documents)):
        file_path = metadatas[i]['file_path']
        content = documents[i][:800]
        prompt.append(f"file_path: {file_path}, content: {content}")
        sources.append(file_path)
    unique_sources = list(set(sources))
    return {"chunks": prompt, "sources": unique_sources}

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
    response = llm.invoke(prompt)
    cleaner_response = re.sub(r'<think>.*?</think>', '', response.content, flags=re.DOTALL).strip()
    return {"result": cleaner_response, "sources": state["sources"]}

#building the graph
graph = StateGraph(CodeRetrievalAgent)

#adding nodes
graph.add_node("retrieve_chunk", retrieve_chunk)
graph.add_node("generate_answer", generate_answer)

#starting point
graph.set_entry_point("retrieve_chunk")

#adding edges
graph.add_edge("retrieve_chunk", "generate_answer")

#ending point
graph.add_edge("generate_answer", END)

#compiling
agent = graph.compile()

#api route: when users ask a question
@app.post('/ask')
def ask_question(state: QuestionRequest):
    session_id = state.session_id
    #fetching history
    cursor = conn.cursor()
    cursor.execute("SELECT question, answer from conversation_history where session_id=? ORDER BY timestamp DESC LIMIT 3",(session_id,))
    history = cursor.fetchall()
    conn.commit()
    result = agent.invoke({"chunks":[], "user_question": state.question, "result":'', "sources": [], "history": history})

    #saving this question and answer in history
    cursor.execute("INSERT into conversation_history VALUES (?,?,?,?)",(session_id, state.question, result['result'], datetime.datetime.now()))
    conn.commit()
    return {"answer":result["result"], "sources": result["sources"]}
