# Quick Start Guide: Multi-Agent System with A2A Protocol

This guide will help you quickly test the multi-agent orchestrator system locally using Docker Compose.

## Prerequisites

- **Docker** and **Docker Compose** installed
- **AWS Account** with Bedrock access configured
- **AWS Credentials** configured (via `~/.aws/credentials` or environment variables)
- **AgentCore Memory** resource created (optional, for memory features)

**Note:** The voice agent uses Python 3.12 (for bidi support), while the multi-agent system uses Python 3.11. Both work together in Docker Compose.

## Environment Configuration

Create a `.env` file in the project root with the following variables:

```bash
# AWS Configuration
AWS_REGION=us-west-2
AWS_PROFILE=default  # Optional: if using named profiles (see MFA setup below)
AGENTCORE_MEMORY_REGION=us-west-2

# AgentCore Memory (optional - leave empty to disable memory features)
AGENTCORE_MEMORY_ID=your-memory-id-here

# Model Configuration (optional - defaults shown)
ORCHESTRATOR_MODEL=amazon.nova-pro-v1:0
VISION_MODEL=amazon.nova-canvas-v1:0
DOCUMENT_MODEL=amazon.nova-pro-v1:0
DATA_MODEL=amazon.nova-lite-v1:0
TOOL_MODEL=amazon.nova-lite-v1:0

# Tool Agent Configuration (optional)
WEATHER_API_KEY=your-weather-api-key  # Optional: for weather tool
```

### MFA Authentication Setup (Required if using AWS profiles with MFA)

If your AWS credentials require MFA (Multi-Factor Authentication), Docker containers cannot handle interactive MFA prompts. Use the `fix_mfa.py` script to generate temporary credentials:

1. **Run the MFA script** (will prompt for MFA code once):
   ```bash
   python scripts/fix_mfa.py
   ```

2. **Copy the export commands** from the script output and add them to your `.env` file:
   ```bash
   AWS_ACCESS_KEY_ID=<from script output>
   AWS_SECRET_ACCESS_KEY=<from script output>
   AWS_SESSION_TOKEN=<from script output>
   AWS_DEFAULT_REGION=<from script output>
   AWS_ACCOUNT_ID=<from script output>
   # Comment out AWS_PROFILE when using session tokens
   # AWS_PROFILE=
   ```

3. **Note**: These credentials expire after ~1 hour. When they expire, re-run `python scripts/fix_mfa.py` and update your `.env` file.

**Why this is needed**: Docker Compose uses `AWS_PROFILE` which requires interactive MFA prompts, but containers run in non-interactive mode. The `fix_mfa.py` script generates temporary session credentials that bypass MFA prompts.

### Key Changes from Previous Version

**No longer needed:**
- ❌ `AGENT_AUTH_SECRET` - Removed! A2A protocol uses Docker network isolation locally
- ❌ JWT authentication - Not required for local development

**Still needed:**
- ✅ AWS credentials (for Bedrock model access)
- ✅ AgentCore Memory ID (optional, for conversation memory)
- ✅ Model IDs (optional, defaults are provided)

## Local Testing

### 1. Start All Agents

```bash
# Build and start all agents
docker-compose up --build

# Or run in detached mode
docker-compose up -d --build
```

This will start:
- **Orchestrator** on port `9000`
- **Vision Agent** on port `9001`
- **Document Agent** on port `9002`
- **Data Agent** on port `9003`
- **Tool Agent** on port `9004`
- **Voice Agent** on port `8085` (uses Python 3.12 for bidi support)

### 2. Verify Agents Are Running

Check agent health and agent cards:

```bash
# Check orchestrator agent card
curl http://localhost:9000/.well-known/agent-card.json | jq

# Check vision agent card
curl http://localhost:9001/.well-known/agent-card.json | jq

# Check document agent card
curl http://localhost:9002/.well-known/agent-card.json | jq

# Check data agent card
curl http://localhost:9003/.well-known/agent-card.json | jq

# Check tool agent card
curl http://localhost:9004/.well-known/agent-card.json | jq
```

### 3. Test A2A Communication

#### Test Direct Agent Call (JSON-RPC 2.0)

```bash
# Test vision agent directly
curl -X POST http://localhost:9001 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "task",
    "params": {
      "task": "Analyze this image: https://example.com/image.jpg",
      "user_id": "test-user",
      "session_id": "test-session"
    },
    "id": 1
  }' | jq
```

#### Test Orchestrator Routing

```bash
# Test orchestrator routing to vision agent
curl -X POST http://localhost:9000 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "task",
    "params": {
      "task": "Analyze this image of a sunset",
      "user_id": "test-user",
      "session_id": "test-session"
    },
    "id": 1
  }' | jq
```

#### Test Different Agent Types

```bash
# Document agent
curl -X POST http://localhost:9000 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "task",
    "params": {
      "task": "Extract text from this PDF document",
      "user_id": "test-user",
      "session_id": "test-session"
    },
    "id": 1
  }' | jq

# Data agent
curl -X POST http://localhost:9000 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "task",
    "params": {
      "task": "Show me sales data for Q4",
      "user_id": "test-user",
      "session_id": "test-session"
    },
    "id": 1
  }' | jq

# Tool agent
curl -X POST http://localhost:9000 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "task",
    "params": {
      "task": "What is 15% of 200?",
      "user_id": "test-user",
      "session_id": "test-session"
    },
    "id": 1
  }' | jq
```

### 4. View Logs

```bash
# View all logs
docker-compose logs -f

# View specific agent logs
docker-compose logs -f orchestrator
docker-compose logs -f vision
docker-compose logs -f document
docker-compose logs -f data
docker-compose logs -f tool
```

### 5. Stop Agents

```bash
# Stop all agents
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## Architecture Overview

```
User Request (JSON-RPC 2.0)
    ↓
Orchestrator Agent (port 9000)
    ├─→ Classifies intent
    ├─→ Routes via A2A protocol (no authentication needed locally)
    └─→ Returns response
    ↓
Specialist Agents (ports 9001-9004):
    - Vision Agent (port 9001)
    - Document Agent (port 9002)
    - Data Agent (port 9003)
    - Tool Agent (port 9004)
```

## Troubleshooting

### Agents Won't Start

1. **Check AWS credentials:**
   ```bash
   aws sts get-caller-identity
   ```

2. **Verify Docker is running:**
   ```bash
   docker ps
   ```

3. **Check logs for errors:**
   ```bash
   docker-compose logs orchestrator
   ```

### "No module named 'strands'" Error

Make sure you've updated requirements:
```bash
docker-compose build --no-cache
```

### Memory Not Working

If memory features aren't working:
1. Verify `AGENTCORE_MEMORY_ID` is set in `.env`
2. Check that the memory resource exists in your AWS account
3. Verify AWS credentials have permissions for `bedrock-agentcore:CreateEvent`

### Port Already in Use

If ports 9000-9004 are already in use:
1. Stop conflicting services
2. Or modify `docker-compose.yml` to use different ports

### Voice Agent Issues

If the voice agent fails to start:
- Check logs: `docker-compose logs voice`
- Verify AWS credentials are configured
- Ensure AgentCore Memory ID is set if memory is enabled
- The voice agent uses Python 3.12 (separate from multi-agent system's Python 3.11)

## Next Steps

- **Deploy to Production**: See `infrastructure/cdk/README.md` for CDK deployment instructions
- **Learn More**: See `docs/agentcore_a2a_migration_guide__strands___cdk_.md` for architecture details
- **Test Memory**: See `scripts/manage_memory.py` for memory management

## Key Differences from Previous Version

| Aspect | Old (JWT) | New (A2A) |
|--------|-----------|-----------|
| **Port** | 8080 | 9000 |
| **Protocol** | Custom HTTP/REST | JSON-RPC 2.0 (A2A) |
| **Authentication** | JWT tokens required | None (Docker network isolation) |
| **Agent Cards** | Not available | Available at `/.well-known/agent-card.json` |
| **Framework** | FastAPI | Strands A2AServer |

## Support

For issues or questions:
- Check logs: `docker-compose logs -f`
- Review documentation in `docs/` folder
- See migration guide: `docs/agentcore_a2a_migration_guide__strands___cdk_.md`

