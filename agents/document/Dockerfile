FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY agents/document/requirements.txt .
COPY agents/shared/requirements.txt ./shared-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r shared-requirements.txt

# Copy shared code
COPY agents/shared /app/agents/shared

# Copy document agent code
COPY agents/document /app/agents/document

EXPOSE 9000

CMD ["python", "-m", "agents.document.app"]

