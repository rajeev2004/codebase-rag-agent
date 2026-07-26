import chromadb
from chromadb.utils import embedding_functions

embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

client = chromadb.Client()
collection = client.create_collection(
    name="test_collection",
    embedding_function=embedding_function
)

collection.add(
    documents=["This function handles soft delete for activities", "How do we archive a record", "Best pizza recipe in Bengaluru"],
    ids=["doc1", "doc2", "doc3"]
)

results = collection.query(
    query_texts=["how does soft delete work"],
    n_results=2
)

print(results)