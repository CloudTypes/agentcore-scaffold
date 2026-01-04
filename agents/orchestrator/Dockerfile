FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY agents/orchestrator/requirements.txt .
COPY agents/shared/requirements.txt ./shared-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r shared-requirements.txt

# Copy shared code
COPY agents/shared /app/agents/shared

# Copy orchestrator code
COPY agents/orchestrator /app/agents/orchestrator

# Expose A2A port
EXPOSE 9000

# Run application
CMD ["python", "-m", "agents.orchestrator.app"]

