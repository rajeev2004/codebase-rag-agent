#necessary imports
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
client = chromadb.PersistentClient('./chroma_db')
collection = client.get_collection(
    name = 'abhi-chord-code',
    embedding_function = embedding_function
)

#State of the agent
class CodeRetrievalAgent(TypedDict):
    chunks: list
    user_question: str
    result: str

#Request modal
class QuestionRequest(BaseModel):
    question: str

#function to retrieve the info. and build the prompt for the llm 
def retrieve_chunk(state: CodeRetrievalAgent):
    question = state['user_question']
    response = collection.query(query_texts=[question], n_results=5)
    prompt = []
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
    return {"chunks": prompt}

#function to generate the final answer
def generate_answer(state: CodeRetrievalAgent):
    if state['chunks'] == []:
        return {"result": 'Sorry, I could not find any relevant data!'}
    question = state['user_question']
    message = """Here is code retrieved from the user's codebase and their question. 
                If the provided code does NOT actually relate to or answer the question, 
                clearly say "I couldn't find relevant code for this question" instead of guessing or forcing an answer.
                Otherwise, answer based on the code provided and cite the filepath."""
    chunks_text = "\n\n".join(state['chunks'])
    prompt = f"{message}\n\nQuestion: {question}\n\nRelevant Code:\n{chunks_text}"
    response = llm.invoke(prompt)
    cleaner_response = re.sub(r'<think>.*?</think>', '', response.content, flags=re.DOTALL).strip()
    return {"result": cleaner_response}

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
    result = agent.invoke({"chunks":[], "user_question": state.question, "result":''})
    return {"answer":result["result"]}
