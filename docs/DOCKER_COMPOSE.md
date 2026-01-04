# Docker Compose Guide

This guide explains how to start, stop, and manage the multi-agent system using Docker Compose.

## Overview

The multi-agent system consists of the following services:

- **orchestrator** (port 8080) - Routes requests to specialist agents
- **vision** (port 8081) - Image analysis and visual content
- **document** (port 8082) - Document processing and text extraction
- **data** (port 8083) - Data analysis and SQL queries
- **tool** (port 8084) - Calculator, weather, and utilities
- **voice** (port 8085) - Bi-directional streaming voice agent

## Prerequisites

1. **Docker and Docker Compose** installed on your system
2. **Environment variables** configured (see Configuration section below)
3. **AWS credentials** configured if using AgentCore Memory or Bedrock models

## Quick Start

### Start All Agents

```bash
# Build and start all agents
docker-compose up --build

# Or start in detached mode (background)
docker-compose up -d --build
```

### Stop All Agents

```bash
# Stop all agents
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## Configuration

### Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# AWS Configuration
AWS_PROFILE=Avrio
AWS_REGION=us-west-2

# Agent Authentication (for inter-agent communication)
# This is a secret key (not a JWT) used to sign/verify JWT tokens for A2A communication
# Generate using: openssl rand -hex 32
# Must be the same value for all agents (orchestrator, vision, document, data, tool)
AGENT_AUTH_SECRET=your-secret-key-here

# AgentCore Memory Configuration
# Note: AgentCore Memory uses AWS SDK, not HTTP endpoint or API key
# It uses AWS credentials (AWS_PROFILE or IAM role)
AGENTCORE_MEMORY_REGION=us-west-2
AGENTCORE_MEMORY_ID=voice_agent_memory-yupt8b5dkN
MEMORY_ENABLED=true

# Model Configuration
ORCHESTRATOR_MODEL=amazon.nova-pro-v1:0
VISION_MODEL=amazon.nova-canvas-v1:0
DOCUMENT_MODEL=amazon.nova-pro-v1:0
DATA_MODEL=amazon.nova-lite-v1:0
TOOL_MODEL=amazon.nova-lite-v1:0
MODEL_ID=amazon.nova-2-sonic-v1:0

# Voice Agent Configuration
VOICE=matthew
INPUT_SAMPLE_RATE=16000
OUTPUT_SAMPLE_RATE=24000
SYSTEM_PROMPT="You are a helpful voice assistant with access to calculator, weather, and database tools."

# Google OAuth2 Configuration (optional, for voice agent)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8080/api/auth/callback
GOOGLE_WORKSPACE_DOMAIN=cloudtypes.io

# JWT Configuration (optional, for voice agent)
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# Tool Configuration
WEATHER_API_KEY=your-weather-api-key  # Optional, for weather tool
```

### Default Values

If environment variables are not set, the following defaults are used:

- `AGENT_AUTH_SECRET`: `local-dev-secret-change-in-production`
- `ENVIRONMENT`: `development`
- `AWS_REGION`: `us-west-2`
- `AGENTCORE_MEMORY_REGION`: `us-west-2`
- Agent URLs use docker-compose service names (e.g., `http://vision:8080`)

### AWS Credentials

AgentCore Memory uses the AWS SDK (boto3) and requires AWS credentials. You can provide credentials in several ways:

1. **AWS Profile** (recommended for local development):
   ```bash
   AWS_PROFILE=Avrio
   ```
   The docker-compose.yml mounts your `~/.aws` directory to access profile credentials.

2. **Environment Variables**:
   ```bash
   AWS_ACCESS_KEY_ID=your-access-key
   AWS_SECRET_ACCESS_KEY=your-secret-key
   AWS_SESSION_TOKEN=your-session-token  # If using temporary credentials
   ```

3. **IAM Role** (when running in AWS, e.g., AgentCore Runtime):
   - Credentials are automatically provided by the IAM role attached to the runtime

## Common Commands

### View Logs

```bash
# View logs from all agents
docker-compose logs -f

# View logs from a specific agent
docker-compose logs -f orchestrator
docker-compose logs -f vision
docker-compose logs -f tool

# View last 100 lines
docker-compose logs --tail=100 orchestrator
```

### Restart a Specific Agent

```bash
# Restart orchestrator
docker-compose restart orchestrator

# Restart vision agent
docker-compose restart vision
```

### Rebuild a Specific Agent

```bash
# Rebuild and restart orchestrator
docker-compose up -d --build orchestrator

# Rebuild and restart all agents
docker-compose up -d --build
```

### Check Agent Status

```bash
# List all running containers
docker-compose ps

# Check if a specific agent is running
docker-compose ps orchestrator
```

## Testing Agents

### Health Checks

Test that all agents are running:

```bash
# Orchestrator
curl http://localhost:8080/health

# Vision
curl http://localhost:8081/health

# Document
curl http://localhost:8082/health

# Data
curl http://localhost:8083/health

# Tool
curl http://localhost:8084/health

# Voice
curl http://localhost:8085/ping
```

### Test A2A Communication

1. **Get an authentication token** (requires `AGENT_AUTH_SECRET`):

```python
from agents.shared.auth import InterAgentAuth
import os

os.environ["AGENT_AUTH_SECRET"] = "your-secret-key"
auth = InterAgentAuth()
token = auth.create_token("test-client")
print(token)
```

2. **Test orchestrator routing**:

```bash
curl -X POST http://localhost:8080/process \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is 15% of 200?",
    "context": [],
    "user_id": "test-user",
    "session_id": "test-session"
  }'
```

3. **Test direct agent call**:

```bash
curl -X POST http://localhost:8084/process \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Calculate 10 * 5",
    "context": [],
    "user_id": "test-user",
    "session_id": "test-session"
  }'
```

## Troubleshooting

### Agent Won't Start

1. **Check logs**:
   ```bash
   docker-compose logs orchestrator
   ```

2. **Verify environment variables**:
   ```bash
   docker-compose config
   ```

3. **Check port conflicts**:
   ```bash
   # See if ports are already in use
   lsof -i :8080
   lsof -i :8081
   ```

### Authentication Errors

If you see `403 Forbidden` errors:

1. **For A2A calls** (agent-to-agent):
   - Ensure `AGENT_AUTH_SECRET` is set in your `.env` file
   - Use the **same** secret value for all agents (orchestrator, vision, document, data, tool)
   - Generate a secure random key: `openssl rand -hex 32`
   - Regenerate tokens if you changed the secret

2. **For user authentication** (OAuth2):
   - Ensure `JWT_SECRET_KEY` is set in your `.env` file
   - This is different from `AGENT_AUTH_SECRET`
   - Generate a secure random key: `openssl rand -hex 32`

### Memory Connection Issues

If memory-related errors occur:

1. **Verify AWS credentials are configured**:
   ```bash
   # Check if AWS profile is accessible
   aws sts get-caller-identity --profile Avrio
   
   # Or verify environment variables
   echo $AWS_ACCESS_KEY_ID
   ```

2. **Check memory ID is correct**:
   ```bash
   # Verify the memory ID exists in your AWS account
   aws bedrock-agentcore get-memory --memory-id voice_agent_memory-yupt8b5dkN --region us-west-2
   ```

3. **Verify region matches**:
   - `AGENTCORE_MEMORY_REGION` should match the region where your memory resource was created
   - `AWS_REGION` should also match

4. **Check IAM permissions**:
   - Ensure your AWS credentials have permissions for `bedrock-agentcore:GetMemory`, `bedrock-agentcore:CreateEvent`, etc.

5. **For local development without memory**:
   ```bash
   MEMORY_ENABLED=false
   ```

### Network Issues

If agents can't communicate:

1. **Check network**:
   ```bash
   docker network ls
   docker network inspect agentcore-voice-agent_agent-network
   ```

2. **Verify service names**: Agents use docker-compose service names (e.g., `http://vision:8080`)

3. **Test connectivity**:
   ```bash
   # From orchestrator container
   docker-compose exec orchestrator curl http://vision:8080/health
   ```

### Build Failures

If Docker builds fail:

1. **Clear Docker cache**:
   ```bash
   docker-compose build --no-cache
   ```

2. **Check Dockerfile paths**: Ensure all COPY commands reference correct paths

3. **Verify dependencies**: Check that `requirements.txt` files are correct

## Development Workflow

### Making Changes

1. **Edit code** in `agents/` directory
2. **Rebuild affected agent**:
   ```bash
   docker-compose up -d --build orchestrator
   ```
3. **View logs** to verify changes:
   ```bash
   docker-compose logs -f orchestrator
   ```

### Running Tests

```bash
# Run integration tests (requires agents to be running)
pytest tests/integration/

# Run specific test file
pytest tests/integration/test_multi_agent.py -v
```

## Production Considerations

For production deployments:

1. **Use strong secrets**: Set `AGENT_AUTH_SECRET` to a secure random value
2. **Configure proper memory endpoint**: Use actual AgentCore Memory endpoint
3. **Set environment to production**: `ENVIRONMENT=production`
4. **Use production model IDs**: Verify model availability in your AWS region
5. **Monitor logs**: Set up log aggregation (CloudWatch, etc.)
6. **Health checks**: Configure load balancer health checks on `/ping` endpoints

## Stopping and Cleanup

### Graceful Shutdown

```bash
# Stop all agents gracefully
docker-compose stop

# Stop and remove containers
docker-compose down
```

### Complete Cleanup

```bash
# Stop, remove containers, networks, and volumes
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Remove everything including build cache
docker-compose down -v --rmi all --remove-orphans
```

## Service Dependencies

The orchestrator depends on all specialist agents. Docker Compose will:

1. Start specialist agents first (vision, document, data, tool)
2. Wait for them to be healthy
3. Start orchestrator last

If an agent fails to start, check its logs:

```bash
docker-compose logs vision
```

## Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Multi-Agent Architecture Plan](../docs/true_multi_agent_architecture_refactor_plan.md)
- [AgentCore Runtime Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-runtime.html)

