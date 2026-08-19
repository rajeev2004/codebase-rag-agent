#imports
import os
import tree_sitter_javascript as tsjs
from tree_sitter import Language,Parser
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
import sqlite3
import hashlib
import datetime

#loading env variables
load_dotenv()

#setting the parser
JS_LANGUAGE = Language(tsjs.language())
parser = Parser(JS_LANGUAGE)

#setting up chromadb for storing embeddings
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
client = chromadb.PersistentClient(path=os.getenv("CHROMA_DB_PATH"))
collection = client.get_or_create_collection(
    name=os.getenv("COLLECTION_NAME"),
    embedding_function=embedding_function
)

#DB for indexing tracking
tracking_conn = sqlite3.connect("indexing_tracker.db", check_same_thread=False)
tracking_cursor = tracking_conn.cursor()
tracking_cursor.execute("""CREATE TABLE IF NOT EXISTS file_index_tracking (
                    file_path TEXT PRIMARY KEY,
                    content_hash TEXT,
                    last_indexed TEXT)"""
                )
tracking_conn.commit()

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

#To retrieve stored hash for the file
def get_stored_hash(file_path):
    rows = tracking_cursor.execute("SELECT content_hash FROM file_index_tracking WHERE file_path = ?", (file_path,))
    hash = rows.fetchone()
    if hash:
        return hash[0]
    else:
        return None

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
        previous_hash = get_stored_hash(path)
        current_hash = hashlib.sha256(content).hexdigest()
        
        if previous_hash == current_hash:
            continue
        else:
            chunks = extract_chunk_treesitter(content)
            if previous_hash:
                tracking_cursor.execute("update file_index_tracking set content_hash=? where file_path=?",(current_hash,path))
                tracking_cursor.execute("update file_index_tracking set last_indexed=? where file_path=?",(str(datetime.datetime.now()),path))

                #deleting previous vector from the chromadb
                collection.delete(where={"file_path": path})
            else:
                tracking_cursor.execute("Insert into file_index_tracking values(?,?,?)",(path, current_hash,str(datetime.datetime.now())))
            tracking_conn.commit()
            
            for i, chunk in enumerate(chunks):
                all_chunks.append({
                    "content": chunk,
                    "file_path": path,
                    "chunk_index": i,
                    "id": f"{path}_{i}"
                })

print(f"Total chunks created: {len(all_chunks)}")

#Deleting vectors from chromadb which are deleted from the repo
tracking_files = tracking_cursor.execute("Select file_path from file_index_tracking").fetchall()
previously_tracking_files = []
for file_path in tracking_files:
    previously_tracking_files.append(file_path[0])

deleted_files = []
for file_path in previously_tracking_files:
    if file_path not in file_paths:
        deleted_files.append(file_path)

for deleted_path in deleted_files:
    collection.delete(where={"file_path": deleted_path})
    tracking_cursor.execute("DELETE FROM file_index_tracking WHERE file_path = ?", (deleted_path,))

tracking_conn.commit()

#adding data in chromadb
if all_chunks:
    documents = [chunk['content'] for chunk in all_chunks]
    ids = [chunk['id'] for chunk in all_chunks]
    metadatas = [{"file_path":chunk['file_path'], "chunk_index":chunk['chunk_index']} for chunk in all_chunks]
    #.add required atleast one entry
    collection.add(
        documents=documents,
        ids=ids,
        metadatas=metadatas
    )
else:
    print("No new or changed chunks to add.")