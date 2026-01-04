# Multi-Agent System Implementation Plan

## Executive Summary

This plan defines the architecture and implementation requirements for a **true multi-agent system** with separate AgentCore Runtime deployments, independent scaling, and Agent-to-Agent (A2A) protocol communication.

**Architecture:** Production-ready, cloud-scale multi-agent system
**Deployment:** AWS CDK (Infrastructure as Code)
**Scaling:** Serverless (AgentCore Runtime handles automatically)

---

## Architecture Requirements

### ⚠️ CRITICAL: True Multi-Agent System

**This is NOT a monolithic routing pattern.**

Each agent must be:
- ✅ **Separate AgentCore Runtime deployment** (independent container)
- ✅ **Independent FastAPI application** with its own endpoints
- ✅ **Communicates via A2A protocol** (HTTP/REST, not Python method calls)
- ✅ **Independently scalable** (AgentCore Runtime handles this automatically)
- ✅ **Fault isolated** (one agent failure doesn't affect others)

### Voice Agent (Existing - Keep Intact)

**The existing voice agent should remain unchanged:**
- ✅ **Keep current implementation** - Already uses bi-directional streaming
- ✅ **Separate deployment** - Independent from text-based multi-agent system
- ✅ **WebSocket-based** - Real-time voice communication
- ✅ **Direct Bedrock integration** - Uses Amazon Nova Sonic or Strands bi-directional agent
- ✅ **No orchestration needed** - Voice agent handles conversations directly

**Voice agent is NOT part of the multi-agent orchestration system.** It's a separate, specialized agent for real-time voice interactions.

### Target Architecture

```
Text-Based Multi-Agent System (NEW)
├── Orchestrator Runtime
│   ├── FastAPI app with /process, /health, /ping endpoints
│   ├── Routes requests to specialists via A2A (HTTP calls)
│   └── Deployed to AgentCore Runtime (serverless)
│
├── Vision Agent Runtime
│   ├── FastAPI app with /process, /health, /ping endpoints
│   ├── Handles image analysis requests
│   └── Deployed to AgentCore Runtime (serverless)
│
├── Document Agent Runtime
│   ├── FastAPI app with /process, /health, /ping endpoints
│   ├── Handles document processing requests
│   └── Deployed to AgentCore Runtime (serverless)
│
├── Data Agent Runtime
│   ├── FastAPI app with /process, /health, /ping endpoints
│   ├── Handles data analysis requests
│   └── Deployed to AgentCore Runtime (serverless)
│
└── Tool Agent Runtime
    ├── FastAPI app with /process, /health, /ping endpoints
    ├── Handles calculator, weather, utilities
    └── Deployed to AgentCore Runtime (serverless)

Voice Agent (EXISTING - KEEP INTACT)
└── Voice Agent Runtime
    ├── WebSocket-based bi-directional streaming
    ├── Direct Bedrock integration (Nova Sonic/Strands)
    ├── Real-time voice conversations
    └── Deployed to AgentCore Runtime (serverless)

Communication: 
  - Text agents: HTTP/REST A2A protocol (NOT Python method calls)
  - Voice agent: WebSocket bi-directional streaming
Deployment: Separate CDK stacks per agent
Scaling: AgentCore Runtime (serverless, automatic)
```

---

## Project Structure

### Directory Layout

```
project-root/
├── agents/
│   ├── shared/                    # Shared utilities
│   │   ├── __init__.py
│   │   ├── memory_client.py       # AgentCore Memory client
│   │   ├── service_discovery.py   # Agent endpoint discovery
│   │   ├── auth.py                # Inter-agent authentication (JWT)
│   │   ├── models.py              # Shared Pydantic models
│   │   ├── observability.py       # Logging/metrics
│   │   ├── circuit_breaker.py     # Circuit breaker pattern
│   │   └── retry.py               # Retry with exponential backoff
│   │
│   ├── orchestrator/              # Orchestrator Agent (NEW)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app.py                 # FastAPI application
│   │   ├── agent.py               # Orchestrator logic
│   │   └── a2a_client.py          # A2A communication client
│   │
│   ├── vision/                    # Vision Agent (NEW)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app.py                 # FastAPI application
│   │   ├── agent.py               # Vision processing logic
│   │   └── tools.py               # Vision-specific tools
│   │
│   ├── document/                  # Document Agent (NEW)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app.py
│   │   ├── agent.py
│   │   └── tools.py
│   │
│   ├── data/                      # Data Agent (NEW)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app.py
│   │   ├── agent.py
│   │   └── tools.py
│   │
│   ├── tool/                      # Tool Agent (NEW)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app.py
│   │   ├── agent.py
│   │   └── tools.py
│   │
│   └── voice/                     # Voice Agent (EXISTING - KEEP INTACT)
│       ├── Dockerfile             # Keep existing
│       ├── requirements.txt       # Keep existing
│       ├── app.py                 # Keep existing WebSocket implementation
│       └── agent.py               # Keep existing bi-directional streaming
│
├── infrastructure/                # AWS CDK Infrastructure
│   ├── lib/
│   │   ├── shared-resources-stack.ts   # ECR repos, Secrets Manager
│   │   ├── base-agent-stack.ts         # Reusable agent stack
│   │   ├── orchestrator-stack.ts       # Orchestrator deployment (NEW)
│   │   ├── vision-stack.ts             # Vision deployment (NEW)
│   │   ├── document-stack.ts           # Document deployment (NEW)
│   │   ├── data-stack.ts               # Data deployment (NEW)
│   │   ├── tool-stack.ts               # Tool deployment (NEW)
│   │   └── voice-stack.ts              # Voice deployment (EXISTING - KEEP)
│   ├── bin/
│   │   └── app.ts                      # CDK app entry point
│   ├── config/
│   │   ├── dev.ts                      # Dev environment config
│   │   └── prod.ts                     # Prod environment config
│   ├── cdk.json
│   ├── package.json
│   └── tsconfig.json
│
├── web-client/                    # Web Client (UPDATES NEEDED)
│   ├── src/
│   │   ├── components/
│   │   │   ├── TextChat.tsx       # Text-based chat interface (UPDATE)
│   │   │   └── VoiceChat.tsx      # Voice chat interface (EXISTING - KEEP)
│   │   ├── services/
│   │   │   ├── textAgentService.ts    # HTTP client for text agents (NEW)
│   │   │   └── voiceAgentService.ts   # WebSocket client for voice (EXISTING)
│   │   └── App.tsx                # Main app with modality selector (UPDATE)
│   └── package.json
│
├── tests/
│   ├── unit/                      # Unit tests
│   ├── integration/               # Integration tests
│   └── e2e/                       # End-to-end tests
│
├── .env.example                   # Environment variables template
└── README.md                      # Documentation
```

---

## Core Components

### 1. Shared Components (`agents/shared/`)

**File: `agents/shared/models.py`**
```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class AgentRequest(BaseModel):
    """Standard request format for A2A communication"""
    message: str
    context: List[Dict[str, str]] = []
    user_id: str
    session_id: str
    metadata: Optional[Dict[str, Any]] = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class AgentResponse(BaseModel):
    """Standard response format for A2A communication"""
    content: str
    agent_name: str
    processing_time_ms: float
    metadata: Optional[Dict[str, Any]] = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    agent_name: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

**File: `agents/shared/memory_client.py`**
```python
import os
from typing import List, Dict, Any, Optional
import httpx

class MemoryClient:
    """Shared AgentCore Memory client for all agents"""
    
    def __init__(self):
        self.endpoint = os.getenv("AGENTCORE_MEMORY_ENDPOINT")
        self.api_key = os.getenv("AGENTCORE_MEMORY_API_KEY")
        self.client = httpx.AsyncClient(
            base_url=self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30.0
        )
    
    async def get_recent_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int = 10
    ) -> List[Dict[str, str]]:
        """Retrieve recent conversation history"""
        response = await self.client.get(
            "/messages/recent",
            params={
                "user_id": user_id,
                "session_id": session_id,
                "limit": limit
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def semantic_search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for relevant past context"""
        response = await self.client.post(
            "/search/semantic",
            json={
                "user_id": user_id,
                "query": query,
                "limit": limit,
                "min_similarity": min_similarity
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def store_interaction(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        agent_response: str,
        agent_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Store interaction in memory"""
        await self.client.post(
            "/interactions",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "user_message": user_message,
                "agent_response": agent_response,
                "agent_name": agent_name,
                "metadata": metadata or {}
            }
        )
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
```

**File: `agents/shared/service_discovery.py`**
```python
import os
from typing import Dict, Optional
import boto3
from functools import lru_cache

class ServiceDiscovery:
    """Discover agent endpoints in AgentCore Runtime"""
    
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self._endpoints: Dict[str, str] = {}
        self._load_endpoints()
    
    def _load_endpoints(self):
        """Load agent endpoints from environment or service discovery"""
        if self.environment == "development":
            # Local development - use docker-compose service names
            self._endpoints = {
                "orchestrator": os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8080"),
                "vision": os.getenv("VISION_AGENT_URL", "http://vision:8080"),
                "document": os.getenv("DOCUMENT_AGENT_URL", "http://document:8080"),
                "data": os.getenv("DATA_AGENT_URL", "http://data:8080"),
                "tool": os.getenv("TOOL_AGENT_URL", "http://tool:8080")
            }
        else:
            # Production - use environment variables set by CDK
            self._endpoints = {
                "orchestrator": os.getenv("ORCHESTRATOR_URL"),
                "vision": os.getenv("VISION_AGENT_URL"),
                "document": os.getenv("DOCUMENT_AGENT_URL"),
                "data": os.getenv("DATA_AGENT_URL"),
                "tool": os.getenv("TOOL_AGENT_URL")
            }
    
    def get_endpoint(self, agent_name: str) -> str:
        """Get endpoint URL for a specific agent"""
        endpoint = self._endpoints.get(agent_name)
        if not endpoint:
            raise ValueError(f"No endpoint found for agent: {agent_name}")
        return endpoint
    
    def get_all_endpoints(self) -> Dict[str, str]:
        """Get all agent endpoints"""
        return self._endpoints.copy()

@lru_cache()
def get_service_discovery() -> ServiceDiscovery:
    """Singleton service discovery instance"""
    return ServiceDiscovery()
```

**File: `agents/shared/auth.py`**
```python
import os
import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

class InterAgentAuth:
    """Authentication for agent-to-agent communication"""
    
    def __init__(self):
        self.secret_key = os.getenv("AGENT_AUTH_SECRET")
        if not self.secret_key:
            raise ValueError("AGENT_AUTH_SECRET not set")
        self.algorithm = "HS256"
        self.token_expiry_minutes = 5
    
    def create_token(self, agent_name: str) -> str:
        """Create JWT token for agent-to-agent calls"""
        payload = {
            "agent_name": agent_name,
            "exp": datetime.utcnow() + timedelta(minutes=self.token_expiry_minutes),
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> dict:
        """Verify JWT token from another agent"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

# Dependency for FastAPI endpoints
async def verify_agent_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """FastAPI dependency to verify agent tokens"""
    auth = InterAgentAuth()
    return auth.verify_token(credentials.credentials)
```

**File: `agents/shared/observability.py`**
```python
import logging
import time
from typing import Optional, Dict, Any
from functools import wraps
import json

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class AgentLogger:
    """Structured logging for agents"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.logger = logging.getLogger(agent_name)
    
    def log_request(
        self,
        user_id: str,
        session_id: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log incoming request"""
        self.logger.info(
            "Request received",
            extra={
                "agent": self.agent_name,
                "user_id": user_id,
                "session_id": session_id,
                "message_length": len(message),
                "metadata": metadata or {}
            }
        )
    
    def log_response(
        self,
        user_id: str,
        session_id: str,
        processing_time_ms: float,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log response"""
        self.logger.info(
            "Response sent",
            extra={
                "agent": self.agent_name,
                "user_id": user_id,
                "session_id": session_id,
                "processing_time_ms": processing_time_ms,
                "success": success,
                "metadata": metadata or {}
            }
        )
    
    def log_a2a_call(
        self,
        target_agent: str,
        user_id: str,
        session_id: str,
        latency_ms: float,
        success: bool
    ):
        """Log agent-to-agent call"""
        self.logger.info(
            "A2A call",
            extra={
                "source_agent": self.agent_name,
                "target_agent": target_agent,
                "user_id": user_id,
                "session_id": session_id,
                "latency_ms": latency_ms,
                "success": success
            }
        )
    
    def log_error(
        self,
        error: Exception,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log error"""
        self.logger.error(
            f"Error: {str(error)}",
            extra={
                "agent": self.agent_name,
                "user_id": user_id,
                "session_id": session_id,
                "error_type": type(error).__name__,
                "context": context or {}
            },
            exc_info=True
        )

def track_latency(agent_name: str):
    """Decorator to track function latency"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                latency_ms = (time.time() - start_time) * 1000
                logger = AgentLogger(agent_name)
                logger.logger.info(
                    f"{func.__name__} completed",
                    extra={
                        "function": func.__name__,
                        "latency_ms": latency_ms,
                        "success": True
                    }
                )
                return result
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                logger = AgentLogger(agent_name)
                logger.log_error(e, context={"function": func.__name__, "latency_ms": latency_ms})
                raise
        return wrapper
    return decorator
```

### 2. Individual Agent Structure

Each agent (orchestrator, vision, document, data, tool) follows this pattern:

**File: `agents/orchestrator/agent.py`**
```python
from typing import List, Dict, Any
import time
from strands import Agent
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.memory_client import MemoryClient
from agents.shared.observability import AgentLogger, track_latency

class OrchestratorAgent:
    """Orchestrator agent that routes requests to specialists"""
    
    def __init__(self, a2a_client):
        self.agent_name = "orchestrator"
        self.logger = AgentLogger(self.agent_name)
        self.memory = MemoryClient()
        self.a2a_client = a2a_client
        
        # Initialize Strands agent for intent classification
        self.strands_agent = Agent(
            model="anthropic.claude-3-5-sonnet-20241022-v2:0",
            system_prompt=self._get_system_prompt()
        )
    
    def _get_system_prompt(self) -> str:
        return """You are an orchestrator agent that classifies user intents and routes to specialists.

Available specialists:
- vision: Image analysis, visual content understanding
- document: Document processing, text extraction, PDF analysis
- data: Data analysis, SQL queries, chart generation
- tool: Calculator, weather, general utilities

Respond with ONLY the specialist name (vision, document, data, or tool).
If unclear, respond with 'orchestrator' to handle directly."""
    
    @track_latency("orchestrator")
    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process request and route to appropriate specialist"""
        start_time = time.time()
        
        self.logger.log_request(
            user_id=request.user_id,
            session_id=request.session_id,
            message=request.message
        )
        
        try:
            # 1. Load context from memory
            context = await self._load_context(request)
            
            # 2. Classify intent
            specialist = await self._classify_intent(request.message, context)
            
            # 3. Route to specialist or handle directly
            if specialist == "orchestrator":
                response_content = await self._handle_directly(request, context)
            else:
                response_content = await self._route_to_specialist(
                    specialist, request, context
                )
            
            # 4. Store interaction in memory
            await self.memory.store_interaction(
                user_id=request.user_id,
                session_id=request.session_id,
                user_message=request.message,
                agent_response=response_content,
                agent_name=specialist,
                metadata={"routed_to": specialist}
            )
            
            processing_time = (time.time() - start_time) * 1000
            
            self.logger.log_response(
                user_id=request.user_id,
                session_id=request.session_id,
                processing_time_ms=processing_time,
                success=True,
                metadata={"specialist": specialist}
            )
            
            return AgentResponse(
                content=response_content,
                agent_name=self.agent_name,
                processing_time_ms=processing_time,
                metadata={"specialist": specialist}
            )
            
        except Exception as e:
            self.logger.log_error(e, request.user_id, request.session_id)
            raise
    
    async def _load_context(self, request: AgentRequest) -> List[Dict[str, str]]:
        """Load conversation context from memory"""
        # Get recent history
        recent = await self.memory.get_recent_messages(
            user_id=request.user_id,
            session_id=request.session_id,
            limit=10
        )
        
        # Get relevant semantic context
        relevant = await self.memory.semantic_search(
            user_id=request.user_id,
            query=request.message,
            limit=5
        )
        
        # Combine with request context
        return request.context + relevant + recent
    
    async def _classify_intent(
        self,
        message: str,
        context: List[Dict[str, str]]
    ) -> str:
        """Classify user intent to determine specialist"""
        classification_prompt = f"User message: {message}\n\nWhich specialist should handle this?"
        
        response = await self.strands_agent.run(
            messages=[{"role": "user", "content": classification_prompt}]
        )
        
        specialist = response.content.strip().lower()
        
        # Validate specialist
        valid_specialists = ["vision", "document", "data", "tool", "orchestrator"]
        if specialist not in valid_specialists:
            specialist = "orchestrator"
        
        return specialist
    
    async def _route_to_specialist(
        self,
        specialist: str,
        request: AgentRequest,
        context: List[Dict[str, str]]
    ) -> str:
        """Route request to specialist agent via A2A"""
        start_time = time.time()
        
        try:
            # Make A2A call
            response = await self.a2a_client.call_agent(
                agent_name=specialist,
                request=AgentRequest(
                    message=request.message,
                    context=context,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    metadata=request.metadata
                )
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            self.logger.log_a2a_call(
                target_agent=specialist,
                user_id=request.user_id,
                session_id=request.session_id,
                latency_ms=latency_ms,
                success=True
            )
            
            return response.content
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self.logger.log_a2a_call(
                target_agent=specialist,
                user_id=request.user_id,
                session_id=request.session_id,
                latency_ms=latency_ms,
                success=False
            )
            raise
    
    async def _handle_directly(
        self,
        request: AgentRequest,
        context: List[Dict[str, str]]
    ) -> str:
        """Handle request directly without routing"""
        messages = context + [{"role": "user", "content": request.message}]
        response = await self.strands_agent.run(messages=messages)
        return response.content
```

**File: `agents/orchestrator/a2a_client.py`**
```python
import httpx
from typing import Dict
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.service_discovery import get_service_discovery
from agents.shared.auth import InterAgentAuth
from agents.shared.observability import AgentLogger

class A2AClient:
    """Client for agent-to-agent communication"""
    
    def __init__(self, source_agent_name: str):
        self.source_agent_name = source_agent_name
        self.service_discovery = get_service_discovery()
        self.auth = InterAgentAuth()
        self.logger = AgentLogger(source_agent_name)
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def call_agent(
        self,
        agent_name: str,
        request: AgentRequest
    ) -> AgentResponse:
        """Make A2A call to another agent"""
        # Get agent endpoint
        endpoint = self.service_discovery.get_endpoint(agent_name)
        
        # Create auth token
        token = self.auth.create_token(self.source_agent_name)
        
        # Make HTTP call
        response = await self.client.post(
            f"{endpoint}/process",
            json=request.model_dump(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        response.raise_for_status()
        
        return AgentResponse(**response.json())
    
    async def health_check(self, agent_name: str) -> Dict:
        """Check health of another agent"""
        endpoint = self.service_discovery.get_endpoint(agent_name)
        response = await self.client.get(f"{endpoint}/health")
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
```

**File: `agents/orchestrator/app.py`**
```python
from fastapi import FastAPI, Depends, HTTPException
from contextlib import asynccontextmanager
from agents.shared.models import AgentRequest, AgentResponse, HealthCheckResponse
from agents.shared.auth import verify_agent_token
from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.a2a_client import A2AClient

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.a2a_client = A2AClient("orchestrator")
    app.state.agent = OrchestratorAgent(app.state.a2a_client)
    yield
    # Shutdown
    await app.state.a2a_client.close()
    await app.state.agent.memory.close()

app = FastAPI(
    title="Orchestrator Agent",
    version="1.0.0",
    lifespan=lifespan
)

@app.post("/process", response_model=AgentResponse)
async def process_request(
    request: AgentRequest,
    token_payload: dict = Depends(verify_agent_token)
):
    """Process request and route to specialists"""
    try:
        response = await app.state.agent.process(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint"""
    return HealthCheckResponse(
        status="healthy",
        agent_name="orchestrator",
        version="1.0.0"
    )

@app.get("/ping")
async def ping():
    """Simple ping endpoint for load balancer"""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

**File: `agents/orchestrator/Dockerfile`**
```dockerfile
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

# Expose port
EXPOSE 8080

# Run application
CMD ["python", "-m", "agents.orchestrator.app"]
```

**File: `agents/orchestrator/requirements.txt`**
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
strands-agents==1.0.0
httpx==0.25.1
pydantic==2.5.0
python-jose[cryptography]==3.3.0
```

#### Orchestrator Agent Specifics

The orchestrator has additional responsibilities:
- **Intent classification**: Determines which specialist to route to
- **A2A client**: Makes HTTP calls to specialist agents
- **Response synthesis**: Combines specialist responses if needed

---

## A2A Communication Protocol

### Requirements

**Agent-to-Agent calls MUST use HTTP/REST, NOT Python method calls.**

### Communication Flow

```
User Request
    ↓
Orchestrator Agent (FastAPI)
    ↓ (HTTP POST via A2A Client)
Vision Agent (FastAPI)
    ↓ (HTTP Response)
Orchestrator Agent
    ↓
User Response
```

### A2A Request Format

```python
POST http://vision-agent-endpoint/process
Headers:
  Authorization: Bearer <JWT-token>
  Content-Type: application/json

Body:
{
  "message": "Analyze this image",
  "context": [...],
  "user_id": "user-123",
  "session_id": "session-456",
  "metadata": {}
}
```

### A2A Response Format

```python
{
  "content": "The image shows...",
  "agent_name": "vision",
  "processing_time_ms": 1234.56,
  "metadata": {}
}
```

### Authentication

- **JWT tokens** for inter-agent authentication
- Tokens created by calling agent, verified by receiving agent
- Short expiry (5 minutes)
- Shared secret from AWS Secrets Manager

### Resilience Patterns

**Circuit Breaker:**
- Open after 5 consecutive failures
- Half-open after 60 seconds
- Close after 2 successful requests

**Retry Logic:**
- 3 retries with exponential backoff
- Base delay: 1 second
- Max delay: 10 seconds

---

## Infrastructure (AWS CDK)

### Key Principles

✅ **Infrastructure as Code** - All infrastructure defined in CDK
✅ **Separate stacks per agent** - Independent deployment
✅ **AgentCore Runtime** - Serverless, auto-scaling
✅ **Secrets Manager** - For auth tokens, API keys
✅ **ECR** - Container registry for agent images
✅ **Multi-environment** - Dev, staging, prod configurations

### CDK Stack Structure

**SharedResourcesStack:**
- ECR repositories (one per agent)
- Secrets Manager secrets (auth token, memory API key)

**BaseAgentStack (reusable):**
- AgentCore Runtime deployment
- IAM roles
- Environment variables
- Secrets injection

**Individual Agent Stacks:**
- OrchestratorStack (depends on specialist endpoints)
- VisionStack
- DocumentStack
- DataStack
- ToolStack

### AgentCore Runtime Deployment

```typescript
// Each agent deployed to AgentCore Runtime (serverless)
const runtime = new agentcore.Runtime(this, 'Runtime', {
  runtimeName: `${agentName}-${environment}`,
  containerImage: agentcore.ContainerImage.fromEcrRepository(
    ecrRepository,
    imageTag
  ),
  environment: {
    AGENTCORE_MEMORY_ENDPOINT: memoryEndpoint,
    VISION_AGENT_URL: visionEndpoint,  // For orchestrator only
    // ... other agent URLs
  },
  secrets: {
    AGENT_AUTH_SECRET: agentcore.Secret.fromSecretsManager(authSecret),
    AGENTCORE_MEMORY_API_KEY: agentcore.Secret.fromSecretsManager(memorySecret),
  },
});
```

### Service Discovery

Agents discover each other via **environment variables** set by CDK:
- `VISION_AGENT_URL` → Vision agent's AgentCore Runtime endpoint
- `DOCUMENT_AGENT_URL` → Document agent's AgentCore Runtime endpoint
- `DATA_AGENT_URL` → Data agent's AgentCore Runtime endpoint
- `TOOL_AGENT_URL` → Tool agent's AgentCore Runtime endpoint

### Deployment Flow

1. **Build Docker images** for each agent
2. **Push to ECR** (one repository per agent)
3. **Deploy CDK stacks**:
   - SharedResourcesStack (first)
   - Specialist stacks (parallel)
   - OrchestratorStack (last, needs specialist endpoints)
4. **AgentCore Runtime** handles scaling automatically

---

## Configuration

### Environment Variables

**All Agents:**
```bash
ENVIRONMENT=dev|prod
AGENT_NAME=orchestrator|vision|document|data|tool
AGENTCORE_MEMORY_ENDPOINT=https://memory.agentcore.example.com
AGENT_AUTH_SECRET=<from-secrets-manager>
AGENTCORE_MEMORY_API_KEY=<from-secrets-manager>
```

**Orchestrator Only:**
```bash
VISION_AGENT_URL=https://vision-runtime-endpoint
DOCUMENT_AGENT_URL=https://document-runtime-endpoint
DATA_AGENT_URL=https://data-runtime-endpoint
TOOL_AGENT_URL=https://tool-runtime-endpoint
```

### AgentCore Memory

- **Already deployed** (provided by user)
- Endpoint configured via environment variable
- API key stored in Secrets Manager
- All agents connect to same memory instance

---

## Testing Strategy

### Unit Tests
- Test individual agent logic
- Mock A2A calls
- Test shared components

### Integration Tests
- Test A2A communication between agents
- Verify authentication
- Test circuit breakers and retry logic

### End-to-End Tests
- Test complete user request flow
- Orchestrator → Specialist → Response
- Multi-turn conversations with context

---

## Success Criteria

### Architecture
- ✅ Each agent is a separate AgentCore Runtime deployment
- ✅ Agents communicate via A2A protocol (HTTP/REST)
- ✅ No Python method calls between agents
- ✅ Independent scaling per agent (AgentCore handles)
- ✅ Fault isolation (one agent failure doesn't affect others)

### Infrastructure
- ✅ All infrastructure defined in CDK
- ✅ Separate stacks per agent
- ✅ Multi-environment support (dev, prod)
- ✅ Secrets managed via Secrets Manager
- ✅ Container images in ECR

### Resilience
- ✅ Circuit breakers implemented
- ✅ Retry logic with exponential backoff
- ✅ JWT authentication for A2A calls
- ✅ Health checks (/health, /ping endpoints)
- ✅ Structured logging

### Production-Ready
- ✅ Can deploy agents independently
- ✅ Can scale agents independently (automatic)
- ✅ Reproducible deployments (CDK)
- ✅ Version-controlled infrastructure
- ✅ Comprehensive testing

---

## Implementation Checklist

### Shared Components
- [ ] `agents/shared/models.py` - AgentRequest, AgentResponse models
- [ ] `agents/shared/memory_client.py` - AgentCore Memory client
- [ ] `agents/shared/service_discovery.py` - Agent endpoint discovery
- [ ] `agents/shared/auth.py` - JWT authentication
- [ ] `agents/shared/observability.py` - Structured logging
- [ ] `agents/shared/circuit_breaker.py` - Circuit breaker pattern
- [ ] `agents/shared/retry.py` - Retry with exponential backoff

### Orchestrator Agent
- [ ] `agents/orchestrator/app.py` - FastAPI app with /process, /health, /ping
- [ ] `agents/orchestrator/agent.py` - Intent classification, routing logic
- [ ] `agents/orchestrator/a2a_client.py` - HTTP client for A2A calls
- [ ] `agents/orchestrator/Dockerfile` - Container image
- [ ] `agents/orchestrator/requirements.txt` - Dependencies

### Specialist Agents (Vision, Document, Data, Tool) - NEW (All use Strands)
- [ ] `agents/{agent}/app.py` - FastAPI app with /process, /health, /ping
- [ ] `agents/{agent}/agent.py` - **Specialist logic using Strands Agent framework**
- [ ] `agents/{agent}/tools.py` - Agent-specific tools (from strands_tools)
- [ ] `agents/{agent}/Dockerfile` - Container image
- [ ] `agents/{agent}/requirements.txt` - Dependencies (strands, strands_tools, fastapi)

### Voice Agent - EXISTING (KEEP INTACT)
- [ ] `agents/voice/app.py` - Keep existing WebSocket implementation
- [ ] `agents/voice/agent.py` - Keep existing bi-directional streaming
- [ ] `agents/voice/Dockerfile` - Keep existing
- [ ] `agents/voice/requirements.txt` - Keep existing

### Infrastructure (CDK)
- [ ] `infrastructure/lib/shared-resources-stack.ts` - ECR, Secrets
- [ ] `infrastructure/lib/base-agent-stack.ts` - Reusable agent stack
- [ ] `infrastructure/lib/orchestrator-stack.ts` - Orchestrator deployment (NEW)
- [ ] `infrastructure/lib/vision-stack.ts` - Vision deployment (NEW)
- [ ] `infrastructure/lib/document-stack.ts` - Document deployment (NEW)
- [ ] `infrastructure/lib/data-stack.ts` - Data deployment (NEW)
- [ ] `infrastructure/lib/tool-stack.ts` - Tool deployment (NEW)
- [ ] `infrastructure/lib/voice-stack.ts` - Voice deployment (EXISTING - KEEP)
- [ ] `infrastructure/bin/app.ts` - CDK app entry point (UPDATE)
- [ ] `infrastructure/config/dev.ts` - Dev environment config
- [ ] `infrastructure/config/prod.ts` - Prod environment config

### Web Client Updates
- [ ] `web-client/src/App.tsx` - Add modality selector (text vs voice)
- [ ] `web-client/src/components/TextChat.tsx` - New text chat interface
- [ ] `web-client/src/components/VoiceChat.tsx` - Keep existing voice interface
- [ ] `web-client/src/services/textAgentService.ts` - HTTP client for text agents
- [ ] `web-client/src/services/voiceAgentService.ts` - Keep existing WebSocket client

### Testing
- [ ] `tests/unit/` - Unit tests for each agent
- [ ] `tests/integration/` - A2A communication tests
- [ ] `tests/e2e/` - End-to-end flow tests

---

## Key Reminders

### ⚠️ CRITICAL: This is NOT a Monolithic Router

**WRONG:**
```python
# Single container with Python classes
class Orchestrator:
    def route(self, message):
        if "image" in message:
            return self.vision_agent.process(message)  # ❌ Method call
```

**CORRECT:**
```python
# Separate containers with HTTP calls
class Orchestrator:
    async def route(self, message):
        if "image" in message:
            response = await self.a2a_client.call_agent(  # ✅ HTTP call
                agent_name="vision",
                request=AgentRequest(message=message, ...)
            )
            return response.content
```

### AgentCore Runtime is Serverless

- **No scaling configuration needed** - AgentCore handles automatically
- **No resource allocation needed** - AgentCore optimizes
- **No VPC/networking needed** - AgentCore manages
- **Just deploy container** - AgentCore does the rest

### Infrastructure as Code

- **All infrastructure in CDK** - No manual CLI commands
- **Version controlled** - Git tracks all changes
- **Reproducible** - Same deployment every time
- **Multi-environment** - Dev and prod from same code

---

## Web Client Updates

### Current State
The web client currently has a voice chat interface that connects to the voice agent via WebSocket.

### Required Changes

**1. Add Modality Selector**
```typescript
// App.tsx - Add toggle between text and voice modes
<ModalitySelector 
  mode={mode}  // 'text' | 'voice'
  onChange={setMode}
/>
```

**2. Text Chat Component (NEW)**
```typescript
// TextChat.tsx - HTTP-based chat interface
- Send messages to orchestrator via HTTP POST
- Display streaming responses (SSE or polling)
- Support file uploads (images, documents)
- Show agent routing information (which specialist handled request)
- Display conversation history from AgentCore Memory
```

**3. Voice Chat Component (EXISTING - KEEP)**
```typescript
// VoiceChat.tsx - Keep existing WebSocket implementation
- Maintains current bi-directional streaming
- No changes needed
```

**4. Service Layer**
```typescript
// textAgentService.ts (NEW)
class TextAgentService {
  async sendMessage(message: string, context: any[]): Promise<Response>
  async uploadFile(file: File): Promise<string>
  async getHistory(sessionId: string): Promise<Message[]>
}

// voiceAgentService.ts (EXISTING - KEEP)
// Keep existing WebSocket service
```

### User Experience

**Text Mode:**
- Traditional chat interface
- Type messages, upload files
- See which specialist agent handled the request
- View conversation history
- Support for images, documents, data queries

**Voice Mode:**
- Real-time voice conversation
- Push-to-talk or continuous listening
- Voice activity detection
- Transcription display (optional)

---

## Questions to Address Before Implementation

### AgentCore Platform
1. **AgentCore Memory Endpoint**: What is the endpoint URL?
2. **AgentCore Identity Endpoint**: What is the endpoint URL for inter-agent authentication?
3. **Agent Identity Credentials**: How to provision agent IDs and secrets for each agent?
4. **AgentCore Observability**: Is there a specific endpoint or configuration needed?
5. **Memory API Key**: How to obtain/set in Secrets Manager?

### AWS Infrastructure
6. **AWS Account**: Which account for dev? Which for prod?
7. **AWS Region**: Which region to deploy to?
8. **VPC Configuration**: Existing VPC to use or create new?
9. **Custom Domain**: Do we want custom domains (e.g., agents.innovativesol.com)?
10. **ACM Certificate**: Do we need to provision SSL certificates?

### Agent Configuration
11. **Specialist Agents**: Which specialists are needed? (Vision, Document, Data, Tool confirmed?)
12. **Voice Agent**: Is the current voice agent implementation working and should remain unchanged?
13. **Tool Selection**: Which specific tools should each specialist agent have access to?

### Web Client
14. **Authentication**: Do we need user authentication (Cognito, API keys, etc.)?
15. **Custom Branding**: Any specific branding/styling requirements?
16. **Analytics**: Do we need to integrate analytics (CloudWatch RUM, Google Analytics, etc.)?

---

## Next Steps

1. **Review this plan** - Ensure alignment on architecture
2. **Answer configuration questions** - Memory endpoint, AWS accounts, etc.
3. **Implement shared components** - Foundation for all agents
4. **Implement orchestrator** - Core routing logic with A2A client
5. **Implement specialists** - Vision, document, data, tool agents (NEW)
6. **Keep voice agent intact** - No changes to existing voice implementation
7. **Create CDK infrastructure** - Deployment automation for all agents
8. **Update web client** - Add text mode alongside existing voice mode
9. **Test locally** - Verify A2A communication between text agents
10. **Deploy to dev** - First cloud deployment
11. **Test in dev** - Integration and e2e tests
12. **Deploy to prod** - Production release

---

## Reference: Complete Code Examples

The artifact contains complete, production-ready code examples for:
- Shared components (models, memory client, auth, circuit breaker, retry)
- Orchestrator agent (FastAPI app, agent logic, A2A client)
- Vision agent (FastAPI app, agent logic)
- CDK infrastructure (base stack, individual stacks, main app)
- Docker configurations
- Testing examples

Refer to the detailed code sections above for implementation guidance.

**File: `agents/vision/agent.py`**
```python
from typing import List, Dict
import time
from strands import Agent
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.memory_client import MemoryClient
from agents.shared.observability import AgentLogger, track_latency

class VisionAgent:
    """Specialist agent for image analysis and visual content"""
    
    def __init__(self):
        self.agent_name = "vision"
        self.logger = AgentLogger(self.agent_name)
        self.memory = MemoryClient()
        
        # Initialize Strands agent with vision model
        self.strands_agent = Agent(
            model="anthropic.claude-3-5-sonnet-20241022-v2:0",
            system_prompt=self._get_system_prompt()
        )
    
    def _get_system_prompt(self) -> str:
        return """You are a vision specialist agent focused on image analysis and visual content understanding.

Your capabilities:
- Analyze images and describe their content
- Identify objects, people, text in images
- Provide detailed visual descriptions
- Answer questions about images
- Extract information from visual content

Be detailed and accurate in your visual analysis."""
    
    @track_latency("vision")
    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process vision-related request"""
        start_time = time.time()
        
        self.logger.log_request(
            user_id=request.user_id,
            session_id=request.session_id,
            message=request.message
        )
        
        try:
            # Build messages with context
            messages = request.context + [
                {"role": "user", "content": request.message}
            ]
            
            # Process with Strands agent
            response = await self.strands_agent.run(messages=messages)
            
            processing_time = (time.time() - start_time) * 1000
            
            self.logger.log_response(
                user_id=request.user_id,
                session_id=request.session_id,
                processing_time_ms=processing_time,
                success=True
            )
            
            return AgentResponse(
                content=response.content,
                agent_name=self.agent_name,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            self.logger.log_error(e, request.user_id, request.session_id)
            raise
```

**File: `agents/vision/app.py`**
```python
from fastapi import FastAPI, Depends, HTTPException
from contextlib import asynccontextmanager
from agents.shared.models import AgentRequest, AgentResponse, HealthCheckResponse
from agents.shared.auth import verify_agent_token
from agents.vision.agent import VisionAgent

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.agent = VisionAgent()
    yield
    # Shutdown
    await app.state.agent.memory.close()

app = FastAPI(
    title="Vision Agent",
    version="1.0.0",
    lifespan=lifespan
)

@app.post("/process", response_model=AgentResponse)
async def process_request(
    request: AgentRequest,
    token_payload: dict = Depends(verify_agent_token)
):
    """Process vision request"""
    try:
        response = await app.state.agent.process(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint"""
    return HealthCheckResponse(
        status="healthy",
        agent_name="vision",
        version="1.0.0"
    )

@app.get("/ping")
async def ping():
    """Simple ping endpoint"""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

**File: `agents/vision/Dockerfile`**
```dockerfile
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

EXPOSE 8080

CMD ["python", "-m", "agents.vision.app"]
```

### 2.3 Document, Data, and Tool Agents

Follow the same pattern as Vision Agent:
- Each has its own `agent.py` with specialized logic
- Each has its own `app.py` with FastAPI endpoints
- Each has its own `Dockerfile`
- Each implements the same `/process`, `/health`, and `/ping` endpoints
- Each uses shared components (models, memory, auth, observability)

### 2.4 Deliverables (Days 4-7)
- ✅ Orchestrator agent implemented with A2A client
- ✅ Vision agent implemented
- ✅ Document agent implemented
- ✅ Data agent implemented
- ✅ Tool agent implemented
- ✅ All agents have FastAPI endpoints
- ✅ All agents have Dockerfiles
- ✅ All agents use shared components

---

## Phase 3: Local Multi-Agent Testing (Week 2, Days 1-2)

### Objective
Test the multi-agent system locally using Docker Compose.

### 3.1 Docker Compose Configuration

**File: `docker-compose.yml`**
```yaml
version: '3.8'

services:
  orchestrator:
    build:
      context: .
      dockerfile: agents/orchestrator/Dockerfile
    ports:
      - "8080:8080"
    environment:
      - ENVIRONMENT=development
      - AGENT_AUTH_SECRET=local-dev-secret-change-in-production
      - AGENTCORE_MEMORY_ENDPOINT=http://memory:8081
      - AGENTCORE_MEMORY_API_KEY=local-dev-key
      - VISION_AGENT_URL=http://vision:8080
      - DOCUMENT_AGENT_URL=http://document:8080
      - DATA_AGENT_URL=http://data:8080
      - TOOL_AGENT_URL=http://tool:8080
    depends_on:
      - vision
      - document
      - data
      - tool
    networks:
      - agent-network

  vision:
    build:
      context: .
      dockerfile: agents/vision/Dockerfile
    ports:
      - "8081:8080"
    environment:
      - ENVIRONMENT=development
      - AGENT_AUTH_SECRET=local-dev-secret-change-in-production
      - AGENTCORE_MEMORY_ENDPOINT=http://memory:8081
      - AGENTCORE_MEMORY_API_KEY=local-dev-key
    networks:
      - agent-network

  document:
    build:
      context: .
      dockerfile: agents/document/Dockerfile
    ports:
      - "8082:8080"
    environment:
      - ENVIRONMENT=development
      - AGENT_AUTH_SECRET=local-dev-secret-change-in-production
      - AGENTCORE_MEMORY_ENDPOINT=http://memory:8081
      - AGENTCORE_MEMORY_API_KEY=local-dev-key
    networks:
      - agent-network

  data:
    build:
      context: .
      dockerfile: agents/data/Dockerfile
    ports:
      - "8083:8080"
    environment:
      - ENVIRONMENT=development
      - AGENT_AUTH_SECRET=local-dev-secret-change-in-production
      - AGENTCORE_MEMORY_ENDPOINT=http://memory:8081
      - AGENTCORE_MEMORY_API_KEY=local-dev-key
    networks:
      - agent-network

  tool:
    build:
      context: .
      dockerfile: agents/tool/Dockerfile
    ports:
      - "8084:8080"
    environment:
      - ENVIRONMENT=development
      - AGENT_AUTH_SECRET=local-dev-secret-change-in-production
      - AGENTCORE_MEMORY_ENDPOINT=http://memory:8081
      - AGENTCORE_MEMORY_API_KEY=local-dev-key
    networks:
      - agent-network

  # Mock memory service for local testing
  memory:
    image: mockserver/mockserver:latest
    ports:
      - "8081:8081"
    environment:
      - MOCKSERVER_PROPERTY_FILE=/config/mockserver.properties
    volumes:
      - ./test/mock-memory-config.json:/config/mockserver.properties
    networks:
      - agent-network

networks:
  agent-network:
    driver: bridge
```

### 3.2 Integration Tests

**File: `tests/integration/test_multi_agent.py`**
```python
import pytest
import httpx
from agents.shared.models import AgentRequest
from agents.shared.auth import InterAgentAuth

@pytest.fixture
def auth_token():
    """Create auth token for testing"""
    auth = InterAgentAuth()
    return auth.create_token("test-client")

@pytest.mark.asyncio
async def test_orchestrator_to_vision_routing(auth_token):
    """Test that orchestrator routes vision requests to vision agent"""
    async with httpx.AsyncClient() as client:
        request = AgentRequest(
            message="Analyze this image of a sunset",
            context=[],
            user_id="test-user",
            session_id="test-session"
        )
        
        response = await client.post(
            "http://localhost:8080/process",
            json=request.model_dump(),
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "orchestrator"
        assert data["metadata"]["specialist"] == "vision"

@pytest.mark.asyncio
async def test_direct_vision_agent_call(auth_token):
    """Test calling vision agent directly"""
    async with httpx.AsyncClient() as client:
        request = AgentRequest(
            message="Describe this image",
            context=[],
            user_id="test-user",
            session_id="test-session"
        )
        
        response = await client.post(
            "http://localhost:8081/process",
            json=request.model_dump(),
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "vision"

@pytest.mark.asyncio
async def test_all_agents_health():
    """Test health endpoints for all agents"""
    agents = {
        "orchestrator": 8080,
        "vision": 8081,
        "document": 8082,
        "data": 8083,
        "tool": 8084
    }
    
    async with httpx.AsyncClient() as client:
        for agent_name, port in agents.items():
            response = await client.get(f"http://localhost:{port}/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["agent_name"] == agent_name

@pytest.mark.asyncio
async def test_a2a_authentication():
    """Test that A2A calls require valid authentication"""
    async with httpx.AsyncClient() as client:
        request = AgentRequest(
            message="Test message",
            context=[],
            user_id="test-user",
            session_id="test-session"
        )
        
        # Call without auth token
        response = await client.post(
            "http://localhost:8081/process",
            json=request.model_dump()
        )
        
        assert response.status_code == 403  # Forbidden without auth
```

### 3.3 Testing Commands

```bash
# Build all containers
docker-compose build

# Start all agents
docker-compose up -d

# View logs
docker-compose logs -f orchestrator
docker-compose logs -f vision

# Run integration tests
pytest tests/integration/test_multi_agent.py -v

# Test individual agent health
curl http://localhost:8080/health  # Orchestrator
curl http://localhost:8081/health  # Vision
curl http://localhost:8082/health  # Document
curl http://localhost:8083/health  # Data
curl http://localhost:8084/health  # Tool

# Test A2A routing
curl -X POST http://localhost:8080/process \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Analyze this image",
    "context": [],
    "user_id": "test-user",
    "session_id": "test-session"
  }'

# Stop all agents
docker-compose down
```

### 3.4 Deliverables (Days 1-2)
- ✅ Docker Compose configuration
- ✅ Integration tests written
- ✅ All agents running locally
- ✅ A2A communication verified
- ✅ Authentication working
- ✅ Health checks passing

---

## Phase 4: AWS Infrastructure (Week 2, Days 3-7)

### Objective
Deploy each agent as a separate AgentCore Runtime with independent scaling.

### 4.1 Base Agent Runtime Stack

**File: `infrastructure/lib/agent-runtime-stack.ts`**
```typescript
import * as cdk from 'aws-cdk-lib';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

export interface AgentRuntimeProps extends cdk.StackProps {
  agentName: string;
  vpc: ec2.IVpc;
  cluster: ecs.ICluster;
  imageUri: string;
  memoryLimitMiB: number;
  cpu: number;
  minCapacity: number;
  maxCapacity: number;
  environmentVariables?: { [key: string]: string };
  secrets?: { [key: string]: ecs.Secret };
  requiresGpu?: boolean;
}

export class AgentRuntimeStack extends cdk.Stack {
  public readonly service: ecs.FargateService;
  public readonly loadBalancer: elbv2.ApplicationLoadBalancer;
  public readonly serviceUrl: string;

  constructor(scope: Construct, id: string, props: AgentRuntimeProps) {
    super(scope, id, props);

    // Task Definition
    const taskDefinition = new ecs.FargateTaskDefinition(this, 'TaskDef', {
      memoryLimitMiB: props.memoryLimitMiB,
      cpu: props.cpu,
      runtimePlatform: props.requiresGpu ? {
        cpuArchitecture: ecs.CpuArchitecture.X86_64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      } : undefined,
    });

    // Container Definition
    const container = taskDefinition.addContainer('AgentContainer', {
      image: ecs.ContainerImage.fromRegistry(props.imageUri),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: props.agentName,
        logRetention: logs.RetentionDays.ONE_WEEK,
      }),
      environment: {
        ENVIRONMENT: 'production',
        AGENT_NAME: props.agentName,
        ...props.environmentVariables,
      },
      secrets: props.secrets,
      healthCheck: {
        command: ['CMD-SHELL', 'curl -f http://localhost:8080/ping || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
    });

    container.addPortMappings({
      containerPort: 8080,
      protocol: ecs.Protocol.TCP,
    });

    // Security Group
    const securityGroup = new ec2.SecurityGroup(this, 'SecurityGroup', {
      vpc: props.vpc,
      description: `Security group for ${props.agentName} agent`,
      allowAllOutbound: true,
    });

    // Fargate Service
    this.service = new ecs.FargateService(this, 'Service', {
      cluster: props.cluster,
      taskDefinition,
      desiredCount: props.minCapacity,
      securityGroups: [securityGroup],
      assignPublicIp: false,
      enableExecuteCommand: true,
    });

    // Auto Scaling
    const scaling = this.service.autoScaleTaskCount({
      minCapacity: props.minCapacity,
      maxCapacity: props.maxCapacity,
    });

    scaling.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    scaling.scaleOnMemoryUtilization('MemoryScaling', {
      targetUtilizationPercent: 80,
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // Application Load Balancer
    this.loadBalancer = new elbv2.ApplicationLoadBalancer(this, 'ALB', {
      vpc: props.vpc,
      internetFacing: false,
      securityGroup: securityGroup,
    });

    const listener = this.loadBalancer.addListener('Listener', {
      port: 80,
      protocol: elbv2.ApplicationProtocol.HTTP,
    });

    listener.addTargets('Target', {
      port: 8080,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [this.service],
      healthCheck: {
        path: '/health',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
      },
    });

    // Allow ALB to reach service
    this.service.connections.allowFrom(
      this.loadBalancer,
      ec2.Port.tcp(8080),
      'Allow ALB to reach agent'
    );

    // Service URL
    this.serviceUrl = `http://${this.loadBalancer.loadBalancerDnsName}`;

    // Outputs
    new cdk.CfnOutput(this, 'ServiceUrl', {
      value: this.serviceUrl,
      description: `URL for ${props.agentName} agent`,
    });

    new cdk.CfnOutput(this, 'ServiceName', {
      value: this.service.serviceName,
      description: `Service name for ${props.agentName} agent`,
    });
  }
}
```

### 4.2 Orchestrator Stack

**File: `infrastructure/lib/orchestrator-stack.ts`**
```typescript
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';
import { AgentRuntimeStack } from './agent-runtime-stack';

export interface OrchestratorStackProps extends cdk.StackProps {
  vpc: ec2.IVpc;
  cluster: ecs.ICluster;
  agentAuthSecret: secretsmanager.ISecret;
  memoryEndpoint: string;
  memoryApiKeySecret: secretsmanager.ISecret;
  visionAgentUrl: string;
  documentAgentUrl: string;
  dataAgentUrl: string;
  toolAgentUrl: string;
}

export class OrchestratorStack extends AgentRuntimeStack {
  constructor(scope: Construct, id: string, props: OrchestratorStackProps) {
    super(scope, id, {
      agentName: 'orchestrator',
      vpc: props.vpc,
      cluster: props.cluster,
      imageUri: `${cdk.Aws.ACCOUNT_ID}.dkr.ecr.${cdk.Aws.REGION}.amazonaws.com/orchestrator:latest`,
      memoryLimitMiB: 2048,
      cpu: 1024,
      minCapacity: 1,
      maxCapacity: 10,
      environmentVariables: {
        AGENTCORE_MEMORY_ENDPOINT: props.memoryEndpoint,
        VISION_AGENT_URL: props.visionAgentUrl,
        DOCUMENT_AGENT_URL: props.documentAgentUrl,
        DATA_AGENT_URL: props.dataAgentUrl,
        TOOL_AGENT_URL: props.toolAgentUrl,
      },
      secrets: {
        AGENT_AUTH_SECRET: ecs.Secret.fromSecretsManager(props.agentAuthSecret),
        AGENTCORE_MEMORY_API_KEY: ecs.Secret.fromSecretsManager(props.memoryApiKeySecret),
      },
    });
  }
}
```

### 4.3 Vision Agent Stack

**File: `infrastructure/lib/vision-stack.ts`**
```typescript
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';
import { AgentRuntimeStack } from './agent-runtime-stack';

export interface VisionStackProps extends cdk.StackProps {
  vpc: ec2.IVpc;
  cluster: ecs.ICluster;
  agentAuthSecret: secretsmanager.ISecret;
  memoryEndpoint: string;
  memoryApiKeySecret: secretsmanager.ISecret;
}

export class VisionStack extends AgentRuntimeStack {
  constructor(scope: Construct, id: string, props: VisionStackProps) {
    super(scope, id, {
      agentName: 'vision',
      vpc: props.vpc,
      cluster: props.cluster,
      imageUri: `${cdk.Aws.ACCOUNT_ID}.dkr.ecr.${cdk.Aws.REGION}.amazonaws.com/vision:latest`,
      memoryLimitMiB: 4096,
      cpu: 2048,
      minCapacity: 0,  // Scale to zero
      maxCapacity: 100,
      requiresGpu: true,  // Vision processing benefits from GPU
      environmentVariables: {
        AGENTCORE_MEMORY_ENDPOINT: props.memoryEndpoint,
      },
      secrets: {
        AGENT_AUTH_SECRET: ecs.Secret.fromSecretsManager(props.agentAuthSecret),
        AGENTCORE_MEMORY_API_KEY: ecs.Secret.fromSecretsManager(props.memoryApiKeySecret),
      },
    });
  }
}
```

### 4.4 Main CDK App

**File: `infrastructure/bin/app.ts`**
```typescript
#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { OrchestratorStack } from '../lib/orchestrator-stack';
import { VisionStack } from '../lib/vision-stack';
import { DocumentStack } from '../lib/document-stack';
import { DataStack } from '../lib/data-stack';
import { ToolStack } from '../lib/tool-stack';

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION || 'us-east-1',
};

// Networking Stack
const networkingStack = new cdk.Stack(app, 'NetworkingStack', { env });

const vpc = new ec2.Vpc(networkingStack, 'VPC', {
  maxAzs: 2,
  natGateways: 1,
});

const cluster = new ecs.Cluster(networkingStack, 'Cluster', {
  vpc,
  containerInsights: true,
});

// Secrets
const agentAuthSecret = new secretsmanager.Secret(networkingStack, 'AgentAuthSecret', {
  description: 'Secret for inter-agent authentication',
  generateSecretString: {
    secretStringTemplate: JSON.stringify({}),
    generateStringKey: 'secret',
    excludePunctuation: true,
    passwordLength: 32,
  },
});

const memoryApiKeySecret = new secretsmanager.Secret(networkingStack, 'MemoryApiKeySecret', {
  description: 'API key for AgentCore Memory',
});

// Deploy specialist agents first (no dependencies)
const visionStack = new VisionStack(app, 'VisionStack', {
  env,
  vpc,
  cluster,
  agentAuthSecret,
  memoryEndpoint: 'https://memory.agentcore.example.com',
  memoryApiKeySecret,
});

const documentStack = new DocumentStack(app, 'DocumentStack', {
  env,
  vpc,
  cluster,
  agentAuthSecret,
  memoryEndpoint: 'https://memory.agentcore.example.com',
  memoryApiKeySecret,
});

const dataStack = new DataStack(app, 'DataStack', {
  env,
  vpc,
  cluster,
  agentAuthSecret,
  memoryEndpoint: 'https://memory.agentcore.example.com',
  memoryApiKeySecret,
});

const toolStack = new ToolStack(app, 'ToolStack', {
  env,
  vpc,
  cluster,
  agentAuthSecret,
  memoryEndpoint: 'https://memory.agentcore.example.com',
  memoryApiKeySecret,
});

// Deploy orchestrator last (depends on specialist URLs)
const orchestratorStack = new OrchestratorStack(app, 'OrchestratorStack', {
  env,
  vpc,
  cluster,
  agentAuthSecret,
  memoryEndpoint: 'https://memory.agentcore.example.com',
  memoryApiKeySecret,
  visionAgentUrl: visionStack.serviceUrl,
  documentAgentUrl: documentStack.serviceUrl,
  dataAgentUrl: dataStack.serviceUrl,
  toolAgentUrl: toolStack.serviceUrl,
});

orchestratorStack.addDependency(visionStack);
orchestratorStack.addDependency(documentStack);
orchestratorStack.addDependency(dataStack);
orchestratorStack.addDependency(toolStack);

app.synth();
```

### 4.5 Deployment Scripts

**File: `scripts/deploy.sh`**
```bash
#!/bin/bash
set -e

echo "Building and deploying multi-agent system..."

# Build Docker images
echo "Building Docker images..."
docker build -t orchestrator:latest -f agents/orchestrator/Dockerfile .
docker build -t vision:latest -f agents/vision/Dockerfile .
docker build -t document:latest -f agents/document/Dockerfile .
docker build -t data:latest -f agents/data/Dockerfile .
docker build -t tool:latest -f agents/tool/Dockerfile .

# Tag and push to ECR
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}

echo "Pushing images to ECR..."
for agent in orchestrator vision document data tool; do
  aws ecr get-login-password --region $REGION | \
    docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
  
  docker tag $agent:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$agent:latest
  docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$agent:latest
done

# Deploy CDK stacks
echo "Deploying CDK stacks..."
cd infrastructure
npm install
npx cdk bootstrap
npx cdk deploy --all --require-approval never

echo "Deployment complete!"
```

### 4.6 Deliverables (Days 3-7)
- ✅ Base agent runtime stack created
- ✅ Individual agent stacks created
- ✅ Networking stack with VPC and ECS cluster
- ✅ Secrets management configured
- ✅ Auto-scaling configured per agent
- ✅ Load balancers configured
- ✅ Service discovery via environment variables
- ✅ Deployment scripts created
- ✅ All agents deployed to AWS

---

## Phase 5: Production Hardening (Week 3, Days 1-5)

### Objective
Add resilience, observability, and production-grade features.

### 5.1 Circuit Breaker Pattern

**File: `agents/shared/circuit_breaker.py`**
```python
import time
from enum import Enum
from typing import Callable, Any
import asyncio

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered

class CircuitBreaker:
    """Circuit breaker for A2A calls"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        success_threshold: int = 2
    ):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.success_threshold = success_threshold
        
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.success_count = 0
    
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.success_count = 0
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        return (
            self.last_failure_time is not None and
            time.time() - self.last_failure_time >= self.timeout_seconds
        )
```

### 5.2 Retry Logic with Exponential Backoff

**File: `agents/shared/retry.py`**
```python
import asyncio
from typing import Callable, Any, Type
from functools import wraps

async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """Retry function with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return await func()
        except exceptions as e:
            if attempt == max_retries - 1:
                raise
            
            delay = min(base_delay * (2 ** attempt), max_delay)
            await asyncio.sleep(delay)
    
    raise Exception("Max retries exceeded")

def with_retry(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator for retry with exponential backoff"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_with_backoff(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                base_delay=base_delay
            )
        return wrapper
    return decorator
```

### 5.3 Enhanced A2A Client with Resilience

**File: `agents/orchestrator/a2a_client.py` (updated)**
```python
import httpx
from typing import Dict
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.service_discovery import get_service_discovery
from agents.shared.auth import InterAgentAuth
from agents.shared.observability import AgentLogger
from agents.shared.circuit_breaker import CircuitBreaker
from agents.shared.retry import with_retry

class A2AClient:
    """Enhanced client for agent-to-agent communication with resilience"""
    
    def __init__(self, source_agent_name: str):
        self.source_agent_name = source_agent_name
        self.service_discovery = get_service_discovery()
        self.auth = InterAgentAuth()
        self.logger = AgentLogger(source_agent_name)
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # Circuit breakers per agent
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
    
    def _get_circuit_breaker(self, agent_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for agent"""
        if agent_name not in self.circuit_breakers:
            self.circuit_breakers[agent_name] = CircuitBreaker(
                failure_threshold=5,
                timeout_seconds=60,
                success_threshold=2
            )
        return self.circuit_breakers[agent_name]
    
    @with_retry(max_retries=3, base_delay=1.0)
    async def call_agent(
        self,
        agent_name: str,
        request: AgentRequest
    ) -> AgentResponse:
        """Make A2A call with circuit breaker and retry"""
        circuit_breaker = self._get_circuit_breaker(agent_name)
        
        async def make_call():
            endpoint = self.service_discovery.get_endpoint(agent_name)
            token = self.auth.create_token(self.source_agent_name)
            
            response = await self.client.post(
                f"{endpoint}/process",
                json=request.model_dump(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            
            response.raise_for_status()
            return AgentResponse(**response.json())
        
        return await circuit_breaker.call(make_call)
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
```

### 5.4 Distributed Tracing

**File: `agents/shared/tracing.py`**
```python
import uuid
from typing import Optional, Dict, Any
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime

# Context variable for trace ID
trace_id_var: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)

@dataclass
class TraceContext:
    """Trace context for distributed tracing"""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    agent_name: str
    timestamp: datetime

class TracingManager:
    """Manage distributed tracing across agents"""
    
    @staticmethod
    def start_trace(agent_name: str) -> TraceContext:
        """Start a new trace"""
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        trace_id_var.set(trace_id)
        
        return TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,
            agent_name=agent_name,
            timestamp=datetime.utcnow()
        )
    
    @staticmethod
    def continue_trace(
        trace_id: str,
        parent_span_id: str,
        agent_name: str
    ) -> TraceContext:
        """Continue existing trace"""
        span_id = str(uuid.uuid4())
        trace_id_var.set(trace_id)
        
        return TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            agent_name=agent_name,
            timestamp=datetime.utcnow()
        )
    
    @staticmethod
    def get_current_trace_id() -> Optional[str]:
        """Get current trace ID"""
        return trace_id_var.get()
    
    @staticmethod
    def inject_headers(headers: Dict[str, str]) -> Dict[str, str]:
        """Inject trace headers for A2A calls"""
        trace_id = trace_id_var.get()
        if trace_id:
            headers['X-Trace-Id'] = trace_id
        return headers
    
    @staticmethod
    def extract_trace_id(headers: Dict[str, str]) -> Optional[str]:
        """Extract trace ID from headers"""
        return headers.get('X-Trace-Id')
```

### 5.5 Metrics Collection

**File: `agents/shared/metrics.py`**
```python
from typing import Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import json

@dataclass
class Metric:
    """Metric data point"""
    name: str
    value: float
    unit: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    dimensions: Dict[str, str] = field(default_factory=dict)

class MetricsCollector:
    """Collect and emit metrics"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.metrics: list[Metric] = []
    
    def record_latency(
        self,
        operation: str,
        latency_ms: float,
        dimensions: Dict[str, str] = None
    ):
        """Record operation latency"""
        metric = Metric(
            name="latency",
            value=latency_ms,
            unit="milliseconds",
            dimensions={
                "agent": self.agent_name,
                "operation": operation,
                **(dimensions or {})
            }
        )
        self.metrics.append(metric)
        self._emit_metric(metric)
    
    def record_count(
        self,
        metric_name: str,
        count: int = 1,
        dimensions: Dict[str, str] = None
    ):
        """Record count metric"""
        metric = Metric(
            name=metric_name,
            value=count,
            unit="count",
            dimensions={
                "agent": self.agent_name,
                **(dimensions or {})
            }
        )
        self.metrics.append(metric)
        self._emit_metric(metric)
    
    def _emit_metric(self, metric: Metric):
        """Emit metric to CloudWatch or other backend"""
        # In production, send to CloudWatch, Prometheus, etc.
        print(json.dumps({
            "metric": metric.name,
            "value": metric.value,
            "unit": metric.unit,
            "timestamp": metric.timestamp.isoformat(),
            "dimensions": metric.dimensions
        }))
```

### 5.6 Deliverables (Days 1-5)
- ✅ Circuit breaker implemented
- ✅ Retry logic with exponential backoff
- ✅ Enhanced A2A client with resilience
- ✅ Distributed tracing implemented
- ✅ Metrics collection implemented
- ✅ Error handling improved
- ✅ Logging enhanced

---

## Phase 6: Testing & Validation (Week 3, Days 6-7 + Week 4, Days 1-2)

### Objective
Comprehensive testing of the multi-agent system.

### 6.1 Load Testing

**File: `tests/load/locustfile.py`**
```python
from locust import HttpUser, task, between
import json

class MultiAgentUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """Get auth token"""
        # In production, implement proper auth
        self.token = "test-token"
    
    @task(3)
    def vision_request(self):
        """Test vision routing"""
        self.client.post(
            "/process",
            json={
                "message": "Analyze this image of a sunset",
                "context": [],
                "user_id": "load-test-user",
                "session_id": "load-test-session"
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )
    
    @task(2)
    def document_request(self):
        """Test document routing"""
        self.client.post(
            "/process",
            json={
                "message": "Extract text from this PDF",
                "context": [],
                "user_id": "load-test-user",
                "session_id": "load-test-session"
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )
    
    @task(2)
    def data_request(self):
        """Test data routing"""
        self.client.post(
            "/process",
            json={
                "message": "Show me sales data for Q4",
                "context": [],
                "user_id": "load-test-user",
                "session_id": "load-test-session"
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )
    
    @task(1)
    def tool_request(self):
        """Test tool routing"""
        self.client.post(
            "/process",
            json={
                "message": "What's 15% of 200?",
                "context": [],
                "user_id": "load-test-user",
                "session_id": "load-test-session"
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )
```

**Run load tests:**
```bash
# Install locust
pip install locust

# Run load test
locust -f tests/load/locustfile.py --host=http://orchestrator-alb-url

# Access web UI at http://localhost:8089
```

### 6.2 Chaos Testing

**File: `tests/chaos/test_resilience.py`**
```python
import pytest
import httpx
import asyncio
from agents.shared.models import AgentRequest

@pytest.mark.asyncio
async def test_vision_agent_failure():
    """Test orchestrator handles vision agent failure"""
    # Simulate vision agent being down
    # Orchestrator should handle gracefully
    pass

@pytest.mark.asyncio
async def test_circuit_breaker():
    """Test circuit breaker opens after failures"""
    # Make multiple failing requests
    # Verify circuit breaker opens
    # Verify requests are rejected
    # Wait for timeout
    # Verify circuit breaker closes
    pass

@pytest.mark.asyncio
async def test_retry_logic():
    """Test retry logic with transient failures"""
    # Simulate transient failures
    # Verify retries occur
    # Verify eventual success
    pass
```

### 6.3 End-to-End Tests

**File: `tests/e2e/test_multi_agent_flows.py`**
```python
import pytest
import httpx
from agents.shared.models import AgentRequest

@pytest.mark.asyncio
async def test_complete_vision_flow():
    """Test complete flow from user to vision agent and back"""
    async with httpx.AsyncClient() as client:
        # Send request to orchestrator
        response = await client.post(
            "http://orchestrator-url/process",
            json={
                "message": "Analyze this image",
                "context": [],
                "user_id": "e2e-test-user",
                "session_id": "e2e-test-session"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["specialist"] == "vision"
        assert len(data["content"]) > 0

@pytest.mark.asyncio
async def test_multi_turn_conversation():
    """Test multi-turn conversation with context"""
    async with httpx.AsyncClient() as client:
        session_id = "multi-turn-session"
        
        # Turn 1
        response1 = await client.post(
            "http://orchestrator-url/process",
            json={
                "message": "Show me sales data",
                "context": [],
                "user_id": "e2e-test-user",
                "session_id": session_id
            }
        )
        assert response1.status_code == 200
        
        # Turn 2 (with context)
        response2 = await client.post(
            "http://orchestrator-url/process",
            json={
                "message": "Now compare it to last quarter",
                "context": [
                    {"role": "user", "content": "Show me sales data"},
                    {"role": "assistant", "content": response1.json()["content"]}
                ],
                "user_id": "e2e-test-user",
                "session_id": session_id
            }
        )
        assert response2.status_code == 200
```

### 6.4 Deliverables (Days 6-7, Week 4 Days 1-2)
- ✅ Load tests implemented and run
- ✅ Chaos tests implemented
- ✅ End-to-end tests passing
- ✅ Performance benchmarks established
- ✅ Resilience validated
- ✅ Documentation updated

---

## Phase 7: Documentation & Handoff (Week 4, Days 3-5)

### Objective
Complete documentation for production use.

### 7.1 Architecture Documentation

**File: `docs/ARCHITECTURE.md`**
```markdown
# Multi-Agent Architecture

## Overview
This system implements a true multi-agent architecture with separate AgentCore Runtime deployments for each agent.

## Components

### Orchestrator Agent
- **Purpose**: Routes requests to specialist agents
- **Scaling**: 1-10 instances
- **Dependencies**: All specialist agents

### Vision Agent
- **Purpose**: Image analysis and visual content
- **Scaling**: 0-100 instances (scales to zero)
- **Resources**: GPU-enabled

### Document Agent
- **Purpose**: Document processing and text extraction
- **Scaling**: 0-50 instances

### Data Agent
- **Purpose**: Data analysis and SQL queries
- **Scaling**: 0-200 instances

### Tool Agent
- **Purpose**: Calculator, weather, utilities
- **Scaling**: 0-50 instances

## Communication
Agents communicate via HTTP/REST using the A2A protocol with JWT authentication.

## Resilience
- Circuit breakers per agent
- Retry with exponential backoff
- Distributed tracing
- Health checks

## Deployment
Each agent is deployed as a separate ECS Fargate service with independent scaling.
```

### 7.2 Deployment Guide

**File: `docs/DEPLOYMENT.md`**
```markdown
# Deployment Guide

## Prerequisites
- AWS Account
- AWS CLI configured
- Docker installed
- Node.js 18+ (for CDK)

## Initial Deployment

1. **Build Docker images**
   ```bash
   ./scripts/deploy.sh
   ```

2. **Deploy infrastructure**
   ```bash
   cd infrastructure
   npx cdk deploy --all
   ```

3. **Verify deployment**
   ```bash
   ./scripts/verify-deployment.sh
   ```

## Updating Individual Agents

To update only the vision agent:
```bash
docker build -t vision:latest -f agents/vision/Dockerfile .
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/vision:latest
aws ecs update-service --cluster multi-agent-cluster --service vision --force-new-deployment
```

## Monitoring
- CloudWatch Logs: `/ecs/multi-agent/*`
- Metrics: CloudWatch dashboard
- Traces: X-Ray (if enabled)
```

### 7.3 Operations Runbook

**File: `docs/RUNBOOK.md`**
```markdown
# Operations Runbook

## Common Issues

### Agent Not Responding
1. Check health endpoint: `curl http://agent-url/health`
2. Check CloudWatch logs
3. Verify security group rules
4. Check ECS service status

### High Latency
1. Check A2A call latency in logs
2. Verify circuit breaker status
3. Check agent scaling metrics
4. Review CloudWatch metrics

### Circuit Breaker Open
1. Check target agent health
2. Review error logs
3. Wait for timeout (60s default)
4. Monitor for recovery

## Scaling

### Manual Scaling
```bash
aws ecs update-service \
  --cluster multi-agent-cluster \
  --service vision \
  --desired-count 10
```

### Auto-Scaling Configuration
Edit CDK stack and redeploy.
```

### 7.4 Deliverables (Days 3-5)
- ✅ Architecture documentation
- ✅ Deployment guide
- ✅ Operations runbook
- ✅ API documentation
- ✅ Troubleshooting guide
- ✅ README updated

---

## Success Criteria

### Technical
- ✅ Each agent deployed as separate AgentCore Runtime
- ✅ A2A communication working via HTTP/REST
- ✅ Independent scaling per agent
- ✅ Circuit breakers and retry logic implemented
- ✅ Distributed tracing working
- ✅ Health checks passing
- ✅ Load tests passing (1000+ req/min)

### Operational
- ✅ Can deploy individual agents independently
- ✅ Can scale agents independently
- ✅ Fault isolation working (one agent failure doesn't affect others)
- ✅ Monitoring and observability in place
- ✅ Documentation complete

### Business
- ✅ Production-ready scaffolding
- ✅ Demonstrates cloud-scale patterns
- ✅ Cost-optimized (scale to zero for low-traffic agents)
- ✅ Maintainable and extensible

---

## Risk Mitigation

### Risk: Increased Complexity
**Mitigation**: 
- Comprehensive documentation
- Shared components reduce duplication
- Docker Compose for local testing

### Risk: Network Latency
**Mitigation**:
- Keep agents in same VPC
- Use internal load balancers
- Implement caching where appropriate

### Risk: Debugging Difficulty
**Mitigation**:
- Distributed tracing with trace IDs
- Structured logging
- Correlation IDs across agents

### Risk: Deployment Complexity
**Mitigation**:
- Automated deployment scripts
- CDK for infrastructure as code
- Gradual rollout capability

---

## Timeline Summary

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| Phase 1: Project Restructuring | 3 days | New directory structure, shared components |
| Phase 2: Individual Agents | 4 days | All agents implemented with FastAPI |
| Phase 3: Local Testing | 2 days | Docker Compose, integration tests |
| Phase 4: AWS Infrastructure | 5 days | CDK stacks, deployment to AWS |
| Phase 5: Production Hardening | 5 days | Circuit breakers, retry, tracing |
| Phase 6: Testing & Validation | 4 days | Load tests, chaos tests, e2e tests |
| Phase 7: Documentation | 3 days | Complete documentation |
| **Total** | **26 days (~4 weeks)** | Production-ready multi-agent system |

---

## Next Steps

1. **Review this plan** with your team
2. **Set up project structure** (Phase 1)
3. **Implement orchestrator agent** (Phase 2)
4. **Implement specialist agents** (Phase 2)
5. **Test locally** (Phase 3)
6. **Deploy to AWS** (Phase 4)
7. **Harden for production** (Phase 5)
8. **Validate** (Phase 6)
9. **Document** (Phase 7)

---

## Questions to Address

1. **AgentCore Memory**: Do you have an existing AgentCore Memory deployment, or do we need to include that in the infrastructure?

2. **Authentication**: For production, do you want to integrate with an existing identity provider (Cognito, Auth0, etc.)?

3. **Monitoring**: Do you have existing monitoring infrastructure (Datadog, New Relic) or should we use CloudWatch?

4. **Cost Budget**: What's your target cost for running this system? This affects scaling parameters.

5. **SLA Requirements**: What are your uptime and latency requirements? This affects redundancy and scaling.
