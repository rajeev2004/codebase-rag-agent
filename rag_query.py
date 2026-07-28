#necessary imports
import chromadb
from chromadb.utils import embedding_functions
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph,END,START
from pydantic import BaseModel
import re
from typing import TypedDict, Annotated, Literal

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

#function to retrieve the info. and build the prompt for the llm 
def retrieve_chunk(state: CodeRetrievalAgent):
    question = state['user_question']
    response = collection.query(query_texts=[question], n_results=3)
    prompt = []
    documents = response['documents'][0]
    metadatas = response['metadatas'][0]
    for i in range(len(documents)):
        file_path = metadatas[i]['file_path']
        content = documents[i]
        prompt.append(f"file_path: {file_path}, content: {content}")
    return {"chunks": prompt}

#function to generate the final answer
def generate_answer(state: CodeRetrievalAgent):
    question = state['user_question']
    message = "Here is the relevant code from the user's codebase and the question from the user. Answer this question based on the code provided. Also state the filepath from which the answer was derived. "
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

#loop for user to ask question
print("Type quit to end the loop....\n")
while(True):
    question = input("What would you like to know about ABHI: ")
    if(question == 'quit'):
        break
    response = agent.invoke({"chunks": [], "user_question": question, "result": ''})
    print(response["result"])