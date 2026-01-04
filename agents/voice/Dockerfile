FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libsndfile1 \
    portaudio19-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY agents/voice/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY agents/voice/ ./agents/voice/
COPY client/web/ ./client/web/

# Note: .env file is not copied - environment variables are passed via docker-compose

# Expose port 8080 (required by AgentCore Runtime)
EXPOSE 8080

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "agents.voice.app:app", "--host", "0.0.0.0", "--port", "8080"]

