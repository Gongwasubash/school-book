FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for Google Drive cache
RUN mkdir -p /app/gdrive_cache /app/pdf_cache

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "rag_api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]