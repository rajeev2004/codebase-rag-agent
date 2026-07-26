from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer('all-MiniLM-L6-v2')

text1 = "This function handles soft delete for activities"
text2 = "How do we archive an activity record"
text3 = "Best pizza recipe in Bengaluru"

emb1 = model.encode(text1)
emb2 = model.encode(text2)
emb3 = model.encode(text3)

# cosine similarity - closer to 1 means more similar
similarity_1_2 = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
similarity_1_3 = np.dot(emb1, emb3) / (np.linalg.norm(emb1) * np.linalg.norm(emb3))

print(f"Similarity (soft delete vs archive): {similarity_1_2:.4f}")
print(f"Similarity (soft delete vs pizza): {similarity_1_3:.4f}")