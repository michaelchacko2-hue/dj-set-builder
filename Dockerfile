FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py .
COPY library.json .

# Copy ChromaDB data if it exists (otherwise rebuild on first run)
COPY chroma_db/ ./chroma_db/

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
