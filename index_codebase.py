#imports
import os
import tree_sitter_javascript as tsjs
from tree_sitter import Language,Parser
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

#loading env variables
load_dotenv()

#setting the parser
JS_LANGUAGE = Language(tsjs.language())
parser = Parser(JS_LANGUAGE)

#setting up chromadb
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
client = chromadb.PersistentClient(path=os.getenv("CHROMA_DB_PATH"))
collection = client.create_collection(
    name=os.getenv("COLLECTION_NAME"),
    embedding_function=embedding_function
)

#folders to skip
SKIP_FOLDERS = {"node_modules", ".git", "dist", "build"}

#valid file extensions
VALID_EXTENSIONS = {".js", ".jsx"}

#function to extract chunks using treesiter
def extract_chunk_treesitter(content):
    tree = parser.parse(content)
    root = tree.root_node
    chunks = []
    pending_comments = []
    pending_setup = []

    for child in root.children:
        if child.type == "comment":
            pending_comments.append(child)
            continue
        
        #check if this is a "simple data" declaration [simple data means a array, string, etc]
        is_simple_data = False
        if child.type == "lexical_declaration":
            is_simple_data = True 
            for sub_child in child.children:
                if sub_child.type == "variable_declarator":
                    value_node = sub_child.child_by_field_name("value")
                    if not (value_node and value_node.type in ("call_expression", "array", "string", "number", "true", "false")):
                        is_simple_data = False
        
        
        if is_simple_data:
            #combining comments and simple data together
            pending_setup.append((pending_comments, child))
            pending_comments = []
        else:
            #first, flush any stored setup as one combined chunk
            if pending_setup:
                start = pending_setup[0][0][0].start_byte if pending_setup[0][0] else pending_setup[0][1].start_byte
                end = pending_setup[-1][1].end_byte
                chunks.append(content[start:end].decode("utf-8"))
                pending_setup = []
            
            #then handle this real chunk (function/route/export), with its own comments
            if pending_comments:
                start = pending_comments[0].start_byte
            else:
                start = child.start_byte
            end = child.end_byte
            chunks.append(content[start:end].decode("utf-8"))
            pending_comments = []
    
    #flush any remaining setup at the very end
    if pending_setup:
        start = pending_setup[0][0][0].start_byte if pending_setup[0][0] else pending_setup[0][1].start_byte
        end = pending_setup[-1][1].end_byte
        chunks.append(content[start:end].decode("utf-8"))
    
    return chunks

#embedding only these folder
ABHI_CHORD_PATH = os.getenv("ABHI_CHORD_PATH")
TARGET_FOLDERS = [
    os.path.join(ABHI_CHORD_PATH, "packages/backend/src/routes"),
    os.path.join(ABHI_CHORD_PATH, "packages/backend/src/logic"),
    os.path.join(ABHI_CHORD_PATH, "packages/backend/src/common"),
    os.path.join(ABHI_CHORD_PATH, "packages/backend/src/middleware"),
    os.path.join(ABHI_CHORD_PATH, "packages/backend/src/partners"),
    os.path.join(ABHI_CHORD_PATH, "packages/backend/src/cron"),
    os.path.join(ABHI_CHORD_PATH, "packages/backend/migrations"),
]

#storing all the chunks here
all_chunks = []
file_paths = []
for folder in TARGET_FOLDERS:
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_FOLDERS]
        
        for file in files:
            if any(file.endswith(ext) for ext in VALID_EXTENSIONS):
                full_path = os.path.join(root, file)
                file_paths.append(full_path)

for path in file_paths:
    with open(path, "rb") as f:
        content = f.read()
        chunks = extract_chunk_treesitter(content)
        for i, chunk in enumerate(chunks):
            all_chunks.append({
                "content": chunk,
                "file_path": path,
                "chunk_index": i,
                "id": f"{path}_{i}"
            })

print(f"Total chunks created: {len(all_chunks)}")

#adding the chunks in chromaDB
documents = [chunk['content'] for chunk in all_chunks]
ids = [chunk['id'] for chunk in all_chunks]
metadatas = [{"file_path":chunk['file_path'], "chunk_index":chunk['chunk_index']} for chunk in all_chunks]
collection.add(
    documents=documents,
    ids=ids,
    metadatas=metadatas
)