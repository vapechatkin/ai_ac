FROM python:3.11-slim
WORKDIR /app
RUN pip install fastapi uvicorn requests faiss-cpu numpy --no-cache-dir
COPY server.py .
COPY chat.html .
COPY data/ ./data/
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
