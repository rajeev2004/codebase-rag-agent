import chromadb
from chromadb.utils import embedding_functions

embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

client = chromadb.PersistentClient(path='./chroma_db')
collection = client.get_collection(
    name='abhi-chord-code',
    embedding_function=embedding_function
)

print(f"Total documents in collection: {collection.count()}")

results = collection.query(
    query_texts=["how does soft delete work for activities"],
    n_results=3
)

for i in range(len(results['ids'][0])):
    print(f"\n--- Result {i+1} ---")
    print("File:", results['metadatas'][0][i]['file_path'])
    print("Distance:", results['distances'][0][i])
    print("Content preview:", results['documents'][0][i][:200])