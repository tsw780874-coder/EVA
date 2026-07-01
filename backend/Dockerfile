FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 eva && chown -R eva:eva /app
USER eva

EXPOSE 8000

# Use multiple workers to avoid single-event-loop blocking during LLM calls.
# --workers 4: 4 independent event loops; one slow LLM call won't block other requests.
# --limit-max-connections 200: prevent connection exhaustion under load.
# --timeout-keep-alive 5: aggressively close idle keep-alive connections (default 5s is ok).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--limit-max-connections", "200", "--timeout-keep-alive", "5"]
