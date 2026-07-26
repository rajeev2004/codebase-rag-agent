#importing libraries
import re
import os
import chromadb
from chromadb.utils import embedding_functions

#using a embedding model of our choice instead of the default one
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

#saving data in a file
client = chromadb.PersistentClient(path='./chroma_db')
collection = client.create_collection(
    name='abhi-chord-code',
    embedding_function=embedding_function
)

#logic to create chunks
def split_into_chunks(content):
    lines = content.split("\n")
    
    start_patterns = [
        r'^\w+\.(get|post|put|delete|patch)\s*\(',
        r'^(const|let|var)\s+\w+\s*=\s*(async\s*)?\(',
        r'^(async\s+)?function\s+\w+\s*\(',
        r'^module\.exports',
    ]
    combined_pattern = re.compile('|'.join(start_patterns))
    
    raw_boundaries = [
        i for i, line in enumerate(lines) 
        if combined_pattern.match(line) and line == line.lstrip()
    ]
    
    if not raw_boundaries:
        return [content]
    
    adjusted_boundaries = []
    for b in raw_boundaries:
        start = b
        while start > 0 and lines[start - 1].strip().startswith("//"):
            start -= 1
        adjusted_boundaries.append(start)
    
    final_boundaries = []
    for b in adjusted_boundaries:
        if not final_boundaries or b > final_boundaries[-1]:
            final_boundaries.append(b)
    
    chunks = []
    if final_boundaries[0] > 0:
        setup = "\n".join(lines[0:final_boundaries[0]])
        if setup.strip():
            chunks.append(setup)
    
    for i in range(len(final_boundaries)):
        start = final_boundaries[i]
        end = final_boundaries[i + 1] if i + 1 < len(final_boundaries) else len(lines)
        chunks.append("\n".join(lines[start:end]))
    
    return chunks

#going through the each folder
SKIP_FOLDERS = {"node_modules", ".git", "dist", "build",}
VALID_EXTENSIONS = {".js", ".jsx"}
TARGET_FOLDERS = [
    "/home/rajeev/circlehealthNew/abhi-chord/packages/backend/src/routes",
    "/home/rajeev/circlehealthNew/abhi-chord/packages/backend/src/logic"
]
file_paths = []
for folder in TARGET_FOLDERS:
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_FOLDERS]
        
        for file in files:
            if any(file.endswith(ext) for ext in VALID_EXTENSIONS):
                full_path = os.path.join(root, file)
                file_paths.append(full_path)

#adding all the chunks in a list
all_chunks=[]
for path in file_paths:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    chunks = split_into_chunks(content)
    for i, chunk in enumerate(chunks):
        all_chunks.append({
            "content": chunk,
            "file_path": path,
            "chunk_index": i,
            "id": f"{path}_{i}"
        })

# print(f"Total chunks: {len(all_chunks)}")

#adding all the chunks in the collection (table like in chromadb)
documents=[chunk["content"] for chunk in all_chunks]
ids=[chunk["id"] for chunk in all_chunks]
metadatas=[{"file_path":chunk["file_path"], "chunk_index":chunk["chunk_index"]} for chunk in all_chunks]

collection.add(
    documents=documents,
    ids=ids,
    metadatas=metadatas,
)

