FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY agents/vision/requirements.txt .
COPY agents/shared/requirements.txt ./shared-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r shared-requirements.txt

# Copy shared code
COPY agents/shared /app/agents/shared

# Copy vision agent code
COPY agents/vision /app/agents/vision

EXPOSE 9000

CMD ["python", "-m", "agents.vision.app"]

