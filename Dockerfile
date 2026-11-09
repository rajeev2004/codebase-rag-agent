FROM python:3.11-slim

WORKDIR /app

RUN pip install torch==2.13.0+cpu --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

COPY rag_api.py .

CMD ["uvicorn", "rag_api:app", "--host", "0.0.0.0", "--port", "8003"]