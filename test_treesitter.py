#imports
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser

#setting up the parser
JS_LANGUAGE = Language(tsjs.language())
parser = Parser(JS_LANGUAGE)

with open("/home/rajeev/circlehealthNew/abhi-chord/packages/backend/src/logic/claimwebhook.js", "rb") as f:
    content = f.read()

tree= parser.parse(content)

def extract_chunks(tree, content):
    root = tree.root_node
    chunks = []
    pending_comments = []
    pending_setup = []  #holds nodes that are just data/imports, waiting to be merged
    
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

chunks = extract_chunks(tree, content)
print(f"Total chunks: {len(chunks)}")
for i, chunk in enumerate(chunks):
    print(f"\n--- Chunk {i} ({len(chunk)} chars) ---")
    print(chunk[:150])

