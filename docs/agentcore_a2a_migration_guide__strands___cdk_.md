# AgentCore A2A Protocol Migration Guide (Strands + CDK)

## Overview

This guide provides step-by-step instructions to migrate your multi-agent orchestrator system from JWT-based authentication to the **Agent-to-Agent (A2A) protocol** using **Strands framework** with **AWS CDK deployment**.

### What You're Building

**Current Architecture (JWT-based):**
```
User/App → Orchestrator Agent (FastAPI + JWT)
              ↓ (HTTP + JWT tokens)
         Specialty Agents (FastAPI + JWT)
         - Vision, Document, Data, Tool
```

**Target Architecture (A2A + Strands):**
```
User/App → [IAM Auth] → Orchestrator Agent (Strands A2A)
                              ↓ (A2A Protocol + AgentCore Auth)
                         AgentCore Runtime
                              ↓
                         Specialty Agents (Strands A2A)
                         - Vision, Document, Data, Tool
```

### Key Benefits

- ✅ **Strands Framework**: 10x less code than custom implementation
- ✅ **A2A Protocol**: Industry-standard agent communication
- ✅ **No Local Auth**: Docker network isolation for development
- ✅ **AgentCore Auth**: Automatic IAM authentication in production
- ✅ **CDK Deployment**: Infrastructure as code, version controlled
- ✅ **Agent Discovery**: Dynamic capability discovery via Agent Cards

---

## Part 1: Understanding the Stack

### Strands Framework

Strands is AWS's open-source SDK for building AI agents with native A2A support:

```python
from strands import Agent
from strands.multiagent.a2a import A2AServer

# Create agent (just a few lines!)
agent = Agent(
    model="amazon.nova-pro-v1:0",
    tools=[calculator, weather],
    system_prompt="You are a helpful assistant..."
)

# Expose as A2A server
server = A2AServer(agent=agent, port=9000)
server.start()
```

### A2A Protocol

- **Transport**: JSON-RPC 2.0 over HTTP
- **Port**: 9000 (AgentCore standard)
- **Discovery**: Agent Cards at `/.well-known/agent-card.json`
- **Authentication**: Handled by AgentCore Runtime (not your code)

### AWS CDK

Infrastructure as code for deploying to AgentCore Runtime:
- Version controlled deployment
- Automated Docker builds and ECR pushes
- IAM role management
- Environment configuration

---

## Part 2: Prerequisites

### Install Required Tools

```bash
# Install Strands with A2A support
pip install 'strands-agents[a2a]'

# Install AWS CDK
npm install -g aws-cdk

# Install CDK Python dependencies
pip install aws-cdk-lib constructs

# Install experimental AgentCore constructs
pip install aws-cdk.aws-bedrock-agentcore-alpha

# Verify installations
strands --version
cdk --version
aws sts get-caller-identity
```

### Project Structure

```
project/
├── agents/
│   ├── orchestrator/
│   │   ├── app.py              # Strands A2A server
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── vision/
│   │   ├── app.py              # Strands A2A server
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── document/
│   │   ├── app.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── data/
│   │   ├── app.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── tool/
│       ├── app.py
│       ├── Dockerfile
│       └── requirements.txt
├── cdk/
│   ├── app.py                  # CDK app entry point
│   ├── stacks/
│   │   └── agentcore_stack.py  # AgentCore infrastructure
│   ├── cdk.json
│   └── requirements.txt
├── docker-compose.yaml          # Local development
└── README.md

# Files to DELETE:
├── agents/shared/auth.py        # Remove JWT auth
```

---

## Part 3: Implement Strands A2A Agents

### Step 3.1: Vision Agent with Strands

**File:** `agents/vision/app.py`

```python
"""Vision Agent using Strands framework with A2A protocol."""

import os
import logging
from strands import Agent
from strands.multiagent.a2a import A2AServer
from strands.models.bedrock import BedrockModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_vision_agent():
    """Create vision agent with Strands."""
    
    # Configure Bedrock model
    model = BedrockModel(
        model_id=os.getenv("VISION_MODEL", "amazon.nova-canvas-v1:0"),
        region=os.getenv("AWS_REGION", "us-west-2")
    )
    
    # Define vision tools (your existing logic)
    def analyze_image(image_url: str) -> dict:
        """Analyze an image and return insights."""
        logger.info(f"Analyzing image: {image_url}")
        # Your existing vision processing logic here
        return {
            "objects": ["person", "car", "building"],
            "scene": "urban street",
            "confidence": 0.95
        }
    
    def detect_objects(image_url: str) -> dict:
        """Detect objects in an image."""
        logger.info(f"Detecting objects: {image_url}")
        # Your existing object detection logic
        return {"objects": []}
    
    def extract_text(image_url: str) -> str:
        """Extract text from an image (OCR)."""
        logger.info(f"Extracting text: {image_url}")
        # Your existing OCR logic
        return ""
    
    # Create Strands agent with tools
    agent = Agent(
        model=model,
        tools=[analyze_image, detect_objects, extract_text],
        system_prompt="""You are a specialized vision agent. 
        You can analyze images, detect objects, and extract text.
        Always provide detailed, accurate analysis."""
    )
    
    return agent


def main():
    """Start vision agent A2A server."""
    logger.info("Starting Vision Agent A2A Server...")
    
    # Create agent
    agent = create_vision_agent()
    
    # Create A2A server
    server = A2AServer(
        agent=agent,
        name="vision-agent",
        description="Specialized agent for image analysis and vision tasks",
        port=9000
    )
    
    logger.info("Vision Agent ready on port 9000")
    logger.info("Agent Card: http://0.0.0.0:9000/.well-known/agent-card.json")
    
    # Start server
    server.start()


if __name__ == "__main__":
    main()
```

**File:** `agents/vision/requirements.txt`

```
strands-agents[a2a]>=1.0.0
boto3>=1.34.0
pillow>=10.0.0
```

**File:** `agents/vision/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy agent code
COPY agents/vision/app.py .
COPY agents/vision/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose A2A port
EXPOSE 9000

# Run Strands A2A server
CMD ["python", "app.py"]
```

### Step 3.2: Document Agent with Strands

**File:** `agents/document/app.py`

```python
"""Document Agent using Strands framework with A2A protocol."""

import os
import logging
from strands import Agent
from strands.multiagent.a2a import A2AServer
from strands.models.bedrock import BedrockModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_document_agent():
    """Create document agent with Strands."""
    
    model = BedrockModel(
        model_id=os.getenv("DOCUMENT_MODEL", "amazon.nova-pro-v1:0"),
        region=os.getenv("AWS_REGION", "us-west-2")
    )
    
    # Define document processing tools
    def process_document(document_url: str) -> dict:
        """Process and analyze a document."""
        logger.info(f"Processing document: {document_url}")
        # Your existing document processing logic
        return {"summary": "Document processed", "pages": 10}
    
    def extract_document_text(document_url: str) -> str:
        """Extract text from a document."""
        logger.info(f"Extracting text: {document_url}")
        # Your existing text extraction logic
        return "Extracted text..."
    
    agent = Agent(
        model=model,
        tools=[process_document, extract_document_text],
        system_prompt="""You are a specialized document processing agent.
        You can analyze documents, extract text, and summarize content."""
    )
    
    return agent


def main():
    """Start document agent A2A server."""
    logger.info("Starting Document Agent A2A Server...")
    
    agent = create_document_agent()
    
    server = A2AServer(
        agent=agent,
        name="document-agent",
        description="Specialized agent for document processing",
        port=9000
    )
    
    logger.info("Document Agent ready on port 9000")
    server.start()


if __name__ == "__main__":
    main()
```

### Step 3.3: Data Agent with Strands

**File:** `agents/data/app.py`

```python
"""Data Agent using Strands framework with A2A protocol."""

import os
import logging
from strands import Agent
from strands.multiagent.a2a import A2AServer
from strands.models.bedrock import BedrockModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_data_agent():
    """Create data agent with Strands."""
    
    model = BedrockModel(
        model_id=os.getenv("DATA_MODEL", "amazon.nova-lite-v1:0"),
        region=os.getenv("AWS_REGION", "us-west-2")
    )
    
    # Define data tools
    def query_data(query: str) -> dict:
        """Query data sources."""
        logger.info(f"Querying data: {query}")
        # Your existing data query logic
        return {"results": []}
    
    def analyze_data(data: dict) -> dict:
        """Analyze data and provide insights."""
        logger.info(f"Analyzing data")
        # Your existing data analysis logic
        return {"insights": []}
    
    agent = Agent(
        model=model,
        tools=[query_data, analyze_data],
        system_prompt="""You are a specialized data analysis agent.
        You can query databases and provide data insights."""
    )
    
    return agent


def main():
    """Start data agent A2A server."""
    logger.info("Starting Data Agent A2A Server...")
    
    agent = create_data_agent()
    
    server = A2AServer(
        agent=agent,
        name="data-agent",
        description="Specialized agent for data analysis",
        port=9000
    )
    
    logger.info("Data Agent ready on port 9000")
    server.start()


if __name__ == "__main__":
    main()
```

### Step 3.4: Tool Agent with Strands

**File:** `agents/tool/app.py`

```python
"""Tool Agent using Strands framework with A2A protocol."""

import os
import logging
from strands import Agent
from strands.multiagent.a2a import A2AServer
from strands.models.bedrock import BedrockModel
from strands_tools.calculator import calculator
from strands_tools.weather import weather_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_tool_agent():
    """Create tool agent with Strands."""
    
    model = BedrockModel(
        model_id=os.getenv("TOOL_MODEL", "amazon.nova-lite-v1:0"),
        region=os.getenv("AWS_REGION", "us-west-2")
    )
    
    # Use built-in Strands tools + custom tools
    agent = Agent(
        model=model,
        tools=[calculator, weather_api],  # Strands built-in tools
        system_prompt="""You are a specialized tool agent.
        You can perform calculations and get weather information."""
    )
    
    return agent


def main():
    """Start tool agent A2A server."""
    logger.info("Starting Tool Agent A2A Server...")
    
    agent = create_tool_agent()
    
    server = A2AServer(
        agent=agent,
        name="tool-agent",
        description="Specialized agent for tools and utilities",
        port=9000
    )
    
    logger.info("Tool Agent ready on port 9000")
    server.start()


if __name__ == "__main__":
    main()
```

---

## Part 4: Implement Orchestrator with Strands

**File:** `agents/orchestrator/app.py`

```python
"""Orchestrator Agent using Strands framework with A2A protocol."""

import os
import logging
from strands import Agent
from strands.multiagent.a2a import A2AServer, A2AClient
from strands.models.bedrock import BedrockModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """Orchestrator that routes tasks to specialty agents."""
    
    def __init__(self):
        """Initialize orchestrator with specialty agent clients."""
        
        # Initialize A2A clients for specialty agents
        self.vision_client = A2AClient(
            os.getenv("VISION_AGENT_URL", "http://vision:9000")
        )
        self.document_client = A2AClient(
            os.getenv("DOCUMENT_AGENT_URL", "http://document:9000")
        )
        self.data_client = A2AClient(
            os.getenv("DATA_AGENT_URL", "http://data:9000")
        )
        self.tool_client = A2AClient(
            os.getenv("TOOL_AGENT_URL", "http://tool:9000")
        )
        
        logger.info("Orchestrator initialized with specialty agents")
        self._discover_agents()
    
    def _discover_agents(self):
        """Discover capabilities of all specialty agents."""
        agents = {
            "vision": self.vision_client,
            "document": self.document_client,
            "data": self.data_client,
            "tool": self.tool_client
        }
        
        for name, client in agents.items():
            try:
                card = client.get_agent_card()
                logger.info(f"Discovered {name}: {card.get('capabilities', [])}")
            except Exception as e:
                logger.warning(f"Could not discover {name}: {e}")
    
    def route_to_vision(self, task: str, **kwargs) -> dict:
        """Route task to vision agent."""
        logger.info(f"Routing to vision: {task}")
        return self.vision_client.send_task(task, **kwargs)
    
    def route_to_document(self, task: str, **kwargs) -> dict:
        """Route task to document agent."""
        logger.info(f"Routing to document: {task}")
        return self.document_client.send_task(task, **kwargs)
    
    def route_to_data(self, task: str, **kwargs) -> dict:
        """Route task to data agent."""
        logger.info(f"Routing to data: {task}")
        return self.data_client.send_task(task, **kwargs)
    
    def route_to_tool(self, task: str, **kwargs) -> dict:
        """Route task to tool agent."""
        logger.info(f"Routing to tool: {task}")
        return self.tool_client.send_task(task, **kwargs)


def create_orchestrator_agent():
    """Create orchestrator agent with Strands."""
    
    model = BedrockModel(
        model_id=os.getenv("ORCHESTRATOR_MODEL", "amazon.nova-pro-v1:0"),
        region=os.getenv("AWS_REGION", "us-west-2")
    )
    
    # Initialize orchestrator
    orchestrator = OrchestratorAgent()
    
    # Create Strands agent with routing tools
    agent = Agent(
        model=model,
        tools=[
            orchestrator.route_to_vision,
            orchestrator.route_to_document,
            orchestrator.route_to_data,
            orchestrator.route_to_tool
        ],
        system_prompt="""You are an orchestrator agent that routes tasks to specialized agents.
        
        Available agents:
        - vision: Image analysis, object detection, OCR
        - document: Document processing, text extraction
        - data: Data queries and analysis
        - tool: Calculator, weather, utilities
        
        Analyze the user's request and route to the appropriate specialist."""
    )
    
    return agent


def main():
    """Start orchestrator A2A server."""
    logger.info("Starting Orchestrator Agent A2A Server...")
    
    # Create agent
    agent = create_orchestrator_agent()
    
    # Create A2A server
    server = A2AServer(
        agent=agent,
        name="orchestrator-agent",
        description="Main orchestrator that routes tasks to specialized agents",
        port=9000
    )
    
    logger.info("Orchestrator Agent ready on port 9000")
    logger.info("Agent Card: http://0.0.0.0:9000/.well-known/agent-card.json")
    
    # Start server
    server.start()


if __name__ == "__main__":
    main()
```

**File:** `agents/orchestrator/requirements.txt`

```
strands-agents[a2a]>=1.0.0
boto3>=1.34.0
```

---

## Part 5: Update Docker Compose (No Authentication)

**File:** `docker-compose.yaml`

```yaml
version: '3.8'

services:
  orchestrator:
    build:
      context: .
      dockerfile: agents/orchestrator/Dockerfile
    ports:
      - "9000:9000"
    environment:
      - ENVIRONMENT=development
      - AWS_REGION=${AWS_REGION:-us-west-2}
      - ORCHESTRATOR_MODEL=${ORCHESTRATOR_MODEL:-amazon.nova-pro-v1:0}
      - VISION_AGENT_URL=http://vision:9000
      - DOCUMENT_AGENT_URL=http://document:9000
      - DATA_AGENT_URL=http://data:9000
      - TOOL_AGENT_URL=http://tool:9000
      # NO AGENT_AUTH_SECRET - authentication removed
    depends_on:
      - vision
      - document
      - data
      - tool
    volumes:
      - ${HOME}/.aws:/root/.aws:ro
    networks:
      - agent-network

  vision:
    build:
      context: .
      dockerfile: agents/vision/Dockerfile
    ports:
      - "9001:9000"
    environment:
      - ENVIRONMENT=development
      - AWS_REGION=${AWS_REGION:-us-west-2}
      - VISION_MODEL=${VISION_MODEL:-amazon.nova-canvas-v1:0}
    volumes:
      - ${HOME}/.aws:/root/.aws:ro
    networks:
      - agent-network

  document:
    build:
      context: .
      dockerfile: agents/document/Dockerfile
    ports:
      - "9002:9000"
    environment:
      - ENVIRONMENT=development
      - AWS_REGION=${AWS_REGION:-us-west-2}
      - DOCUMENT_MODEL=${DOCUMENT_MODEL:-amazon.nova-pro-v1:0}
    volumes:
      - ${HOME}/.aws:/root/.aws:ro
    networks:
      - agent-network

  data:
    build:
      context: .
      dockerfile: agents/data/Dockerfile
    ports:
      - "9003:9000"
    environment:
      - ENVIRONMENT=development
      - AWS_REGION=${AWS_REGION:-us-west-2}
      - DATA_MODEL=${DATA_MODEL:-amazon.nova-lite-v1:0}
    volumes:
      - ${HOME}/.aws:/root/.aws:ro
    networks:
      - agent-network

  tool:
    build:
      context: .
      dockerfile: agents/tool/Dockerfile
    ports:
      - "9004:9000"
    environment:
      - ENVIRONMENT=development
      - AWS_REGION=${AWS_REGION:-us-west-2}
      - TOOL_MODEL=${TOOL_MODEL:-amazon.nova-lite-v1:0}
      - WEATHER_API_KEY=${WEATHER_API_KEY:-}
    volumes:
      - ${HOME}/.aws:/root/.aws:ro
    networks:
      - agent-network

networks:
  agent-network:
    driver: bridge
```

---

## Part 6: Test Locally (No Authentication)

```bash
# Start all agents
docker-compose up --build

# Test vision agent card
curl http://localhost:9001/.well-known/agent-card.json | jq

# Test vision agent directly (no auth needed)
curl -X POST http://localhost:9001 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "task",
    "params": {
      "task": "Analyze this image: https://example.com/image.jpg"
    },
    "id": 1
  }' | jq

# Test orchestrator routing (no auth needed)
curl -X POST http://localhost:9000 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "task",
    "params": {
      "task": "Analyze this image: https://example.com/image.jpg"
    },
    "id": 1
  }' | jq
```

---

## Part 7: CDK Infrastructure

### Step 7.1: Initialize CDK Project

```bash
# Create CDK directory
mkdir -p cdk
cd cdk

# Initialize CDK app
cdk init app --language python

# Install AgentCore constructs
pip install aws-cdk.aws-bedrock-agentcore-alpha
```

### Step 7.2: Create AgentCore Stack

**File:** `cdk/stacks/agentcore_stack.py`

```python
"""CDK Stack for AgentCore multi-agent system."""

from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
)
from aws_cdk.aws_bedrock_agentcore_alpha import (
    AgentRuntime,
    RuntimeType,
    ContainerImage,
)
from constructs import Construct
import os


class AgentCoreStack(Stack):
    """CDK Stack for deploying multi-agent system to AgentCore."""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Create IAM roles
        self.create_iam_roles()
        
        # Deploy specialty agents first
        self.vision_agent = self.create_vision_agent()
        self.document_agent = self.create_document_agent()
        self.data_agent = self.create_data_agent()
        self.tool_agent = self.create_tool_agent()
        
        # Deploy orchestrator (depends on specialty agents)
        self.orchestrator_agent = self.create_orchestrator_agent()
    
    def create_iam_roles(self):
        """Create IAM roles for all agents."""
        
        # Orchestrator role (can invoke other agents)
        self.orchestrator_role = iam.Role(
            self, "OrchestratorRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Role for orchestrator agent"
        )
        
        self.orchestrator_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock-agentcore:InvokeAgent"],
            resources=["*"]  # Will be scoped after agent creation
        ))
        
        self.orchestrator_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=["*"]
        ))
        
        # Specialty agent roles
        self.vision_role = self.create_specialty_role("Vision")
        self.document_role = self.create_specialty_role("Document")
        self.data_role = self.create_specialty_role("Data")
        self.tool_role = self.create_specialty_role("Tool")
    
    def create_specialty_role(self, agent_name: str) -> iam.Role:
        """Create IAM role for specialty agent."""
        role = iam.Role(
            self, f"{agent_name}AgentRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description=f"Role for {agent_name.lower()} agent"
        )
        
        role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=["*"]
        ))
        
        return role
    
    def create_vision_agent(self) -> AgentRuntime:
        """Create vision agent runtime."""
        
        # Build Docker image
        image = ecr_assets.DockerImageAsset(
            self, "VisionAgentImage",
            directory="../agents/vision",
            platform=ecr_assets.Platform.LINUX_AMD64
        )
        
        # Create AgentCore Runtime
        agent = AgentRuntime(
            self, "VisionAgent",
            runtime_name="vision-agent",
            runtime_type=RuntimeType.A2A,
            container_image=ContainerImage.from_docker_image_asset(image),
            execution_role=self.vision_role,
            environment={
                "VISION_MODEL": "amazon.nova-canvas-v1:0",
                "AWS_REGION": self.region,
                "ENVIRONMENT": "production"
            },
            memory_size_mib=2048,
            cpu_units=1024
        )
        
        return agent
    
    def create_document_agent(self) -> AgentRuntime:
        """Create document agent runtime."""
        
        image = ecr_assets.DockerImageAsset(
            self, "DocumentAgentImage",
            directory="../agents/document",
            platform=ecr_assets.Platform.LINUX_AMD64
        )
        
        agent = AgentRuntime(
            self, "DocumentAgent",
            runtime_name="document-agent",
            runtime_type=RuntimeType.A2A,
            container_image=ContainerImage.from_docker_image_asset(image),
            execution_role=self.document_role,
            environment={
                "DOCUMENT_MODEL": "amazon.nova-pro-v1:0",
                "AWS_REGION": self.region,
                "ENVIRONMENT": "production"
            },
            memory_size_mib=2048,
            cpu_units=1024
        )
        
        return agent
    
    def create_data_agent(self) -> AgentRuntime:
        """Create data agent runtime."""
        
        image = ecr_assets.DockerImageAsset(
            self, "DataAgentImage",
            directory="../agents/data",
            platform=ecr_assets.Platform.LINUX_AMD64
        )
        
        agent = AgentRuntime(
            self, "DataAgent",
            runtime_name="data-agent",
            runtime_type=RuntimeType.A2A,
            container_image=ContainerImage.from_docker_image_asset(image),
            execution_role=self.data_role,
            environment={
                "DATA_MODEL": "amazon.nova-lite-v1:0",
                "AWS_REGION": self.region,
                "ENVIRONMENT": "production"
            },
            memory_size_mib=2048,
            cpu_units=1024
        )
        
        return agent
    
    def create_tool_agent(self) -> AgentRuntime:
        """Create tool agent runtime."""
        
        image = ecr_assets.DockerImageAsset(
            self, "ToolAgentImage",
            directory="../agents/tool",
            platform=ecr_assets.Platform.LINUX_AMD64
        )
        
        agent = AgentRuntime(
            self, "ToolAgent",
            runtime_name="tool-agent",
            runtime_type=RuntimeType.A2A,
            container_image=ContainerImage.from_docker_image_asset(image),
            execution_role=self.tool_role,
            environment={
                "TOOL_MODEL": "amazon.nova-lite-v1:0",
                "AWS_REGION": self.region,
                "ENVIRONMENT": "production",
                "WEATHER_API_KEY": os.getenv("WEATHER_API_KEY", "")
            },
            memory_size_mib=2048,
            cpu_units=1024
        )
        
        return agent
    
    def create_orchestrator_agent(self) -> AgentRuntime:
        """Create orchestrator agent runtime."""
        
        image = ecr_assets.DockerImageAsset(
            self, "OrchestratorAgentImage",
            directory="../agents/orchestrator",
            platform=ecr_assets.Platform.LINUX_AMD64
        )
        
        agent = AgentRuntime(
            self, "OrchestratorAgent",
            runtime_name="orchestrator-agent",
            runtime_type=RuntimeType.A2A,
            container_image=ContainerImage.from_docker_image_asset(image),
            execution_role=self.orchestrator_role,
            environment={
                "ORCHESTRATOR_MODEL": "amazon.nova-pro-v1:0",
                "AWS_REGION": self.region,
                "ENVIRONMENT": "production",
                # Agent URLs will be set after deployment
                "VISION_AGENT_URL": self.vision_agent.agent_runtime_url,
                "DOCUMENT_AGENT_URL": self.document_agent.agent_runtime_url,
                "DATA_AGENT_URL": self.data_agent.agent_runtime_url,
                "TOOL_AGENT_URL": self.tool_agent.agent_runtime_url
            },
            memory_size_mib=2048,
            cpu_units=1024
        )
        
        # Orchestrator depends on specialty agents
        agent.node.add_dependency(self.vision_agent)
        agent.node.add_dependency(self.document_agent)
        agent.node.add_dependency(self.data_agent)
        agent.node.add_dependency(self.tool_agent)
        
        return agent
```

### Step 7.3: Create CDK App

**File:** `cdk/app.py`

```python
#!/usr/bin/env python3
"""CDK App for AgentCore multi-agent system."""

import aws_cdk as cdk
from stacks.agentcore_stack import AgentCoreStack

app = cdk.App()

AgentCoreStack(
    app,
    "AgentCoreMultiAgentStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION", "us-west-2")
    ),
    description="Multi-agent system with A2A protocol on AgentCore Runtime"
)

app.synth()
```

**File:** `cdk/cdk.json`

```json
{
  "app": "python app.py",
  "watch": {
    "include": ["**"],
    "exclude": [
      "README.md",
      "cdk*.json",
      "requirements*.txt",
      "source.bat",
      "**/__init__.py",
      "**/__pycache__",
      "**/*.pyc"
    ]
  },
  "context": {
    "@aws-cdk/aws-lambda:recognizeLayerVersion": true,
    "@aws-cdk/core:checkSecretUsage": true,
    "@aws-cdk/core:target-partitions": ["aws", "aws-cn"]
  }
}
```

**File:** `cdk/requirements.txt`

```
aws-cdk-lib>=2.150.0
aws-cdk.aws-bedrock-agentcore-alpha>=2.150.0a0
constructs>=10.0.0
```

---

## Part 8: Deploy with CDK

### Step 8.1: Bootstrap CDK (First Time Only)

```bash
cd cdk

# Bootstrap CDK in your account
cdk bootstrap aws://ACCOUNT_ID/us-west-2
```

### Step 8.2: Deploy Infrastructure

```bash
# Synthesize CloudFormation template
cdk synth

# Review changes
cdk diff

# Deploy all agents
cdk deploy --all

# Or deploy with auto-approval
cdk deploy --all --require-approval never
```

### Step 8.3: Get Agent URLs

```bash
# Get stack outputs
aws cloudformation describe-stacks \
  --stack-name AgentCoreMultiAgentStack \
  --query 'Stacks[0].Outputs' \
  --output table

# Or use CDK
cdk deploy --outputs-file outputs.json
cat outputs.json
```

### Step 8.4: Test Production Deployment

```bash
# Get orchestrator URL from outputs
ORCHESTRATOR_URL=$(cat outputs.json | jq -r '.AgentCoreMultiAgentStack.OrchestratorAgentUrl')

# Invoke orchestrator
aws bedrock-agentcore invoke-agent \
  --agent-id orchestrator-agent \
  --region us-west-2 \
  --input-text '{
    "jsonrpc": "2.0",
    "method": "task",
    "params": {
      "task": "Analyze this image: https://example.com/test.jpg"
    },
    "id": 1
  }'
```

---

## Part 9: Clean Up Old Authentication Code

### Step 9.1: Remove JWT Files

```bash
# Remove JWT authentication module
rm agents/shared/auth.py

# Remove JWT from requirements (if present)
# Edit agents/*/requirements.txt and remove:
# PyJWT==2.8.0
```

### Step 9.2: Verify Clean Migration

```bash
# Search for any remaining JWT references
grep -r "AGENT_AUTH_SECRET" .
grep -r "InterAgentAuth" .
grep -r "verify_agent_token" .
grep -r "create_token" .
grep -r "PyJWT" .

# Should return no results
```

---

## Part 10: CDK Commands Reference

```bash
# Synthesize CloudFormation template
cdk synth

# Compare deployed stack with current state
cdk diff

# Deploy all stacks
cdk deploy --all

# Deploy specific stack
cdk deploy AgentCoreMultiAgentStack

# Destroy all resources
cdk destroy --all

# List all stacks
cdk list

# Watch for changes and auto-deploy
cdk watch

# View CloudFormation template
cdk synth --no-staging > template.yaml
```

---

## Part 11: Migration Checklist

### Phase 1: Local Implementation (Days 1-2)
- [ ] Install Strands framework: `pip install 'strands-agents[a2a]'`
- [ ] Convert vision agent to Strands A2A
- [ ] Convert document agent to Strands A2A
- [ ] Convert data agent to Strands A2A
- [ ] Convert tool agent to Strands A2A
- [ ] Convert orchestrator to Strands A2A
- [ ] Update docker-compose.yaml (remove AGENT_AUTH_SECRET)
- [ ] Update all Dockerfiles to use port 9000
- [ ] Remove `agents/shared/auth.py`

### Phase 2: Local Testing (Day 3)
- [ ] Test each agent independently
- [ ] Test agent card discovery
- [ ] Test orchestrator routing
- [ ] Verify no authentication errors
- [ ] Load test with concurrent requests

### Phase 3: CDK Setup (Day 4)
- [ ] Initialize CDK project
- [ ] Install CDK dependencies
- [ ] Create AgentCore stack
- [ ] Define IAM roles
- [ ] Configure agent runtimes
- [ ] Test `cdk synth`

### Phase 4: AWS Deployment (Day 5)
- [ ] Bootstrap CDK (if first time)
- [ ] Review `cdk diff`
- [ ] Deploy with `cdk deploy --all`
- [ ] Verify all agents deployed
- [ ] Get agent URLs from outputs
- [ ] Test end-to-end flow

### Phase 5: Validation (Day 6)
- [ ] Test orchestrator in production
- [ ] Verify AgentCore authentication works
- [ ] Monitor CloudWatch logs
- [ ] Performance testing
- [ ] Update documentation

---

## Part 12: Key Differences

### What Changed

| Aspect | Old (JWT) | New (Strands + A2A) |
|--------|-----------|---------------------|
| **Framework** | Custom FastAPI | Strands Agents SDK |
| **Protocol** | Custom HTTP/REST | JSON-RPC 2.0 (A2A) |
| **Auth (Local)** | JWT tokens | None (network isolation) |
| **Auth (Production)** | JWT tokens | AgentCore-managed IAM |
| **Deployment** | Manual | AWS CDK |
| **Code Complexity** | ~500 lines | ~100 lines |
| **Port** | 8080 | 9000 |

### Complexity Reduction

**Removed:**
- ❌ `agents/shared/auth.py` (150+ lines)
- ❌ JWT token creation/validation
- ❌ `AGENT_AUTH_SECRET` management
- ❌ FastAPI security dependencies
- ❌ Custom HTTP request handling
- ❌ Manual authentication logic

**Added:**
- ✅ Strands framework (handles everything)
- ✅ A2A protocol (industry standard)
- ✅ CDK infrastructure (version controlled)

**Net Result:** 
- **80% less code** to maintain
- **Standardized** communication
- **Enterprise security** in production
- **Infrastructure as code**

---

## Summary

This migration guide provides a complete path from JWT authentication to Strands A2A protocol with CDK deployment:

### Local Development
- **No authentication** - Docker network isolation
- **Strands framework** - Simple agent implementation
- **A2A protocol** - Standardized communication
- **Fast iteration** - No security overhead

### Production Deployment
- **CDK infrastructure** - Version controlled, reproducible
- **AgentCore Runtime** - Managed hosting and scaling
- **Automatic authentication** - IAM-based, enterprise-grade
- **Session isolation** - Built-in security

### The Authentication Answer

**Your original question:** "Is this a use-case for AgentCore Identity? Specifically, do I use outbound auth?"

**The answer:** Yes, AgentCore Identity handles authentication automatically when you deploy A2A agents to AgentCore Runtime. You don't configure outbound auth yourself - it's built into the platform:

1. **You implement**: A2A protocol with Strands framework
2. **AgentCore provides**: Authentication, authorization, session management
3. **Result**: Secure agent-to-agent communication without custom auth code

When your orchestrator calls specialty agents in production, AgentCore Runtime automatically validates identities, authorizes calls, and manages sessions. You just write agent logic using Strands.

---

## Additional Resources

- [Strands Agents Documentation](https://strandsagents.com/latest/)
- [Strands A2A Examples](https://github.com/strands-agents/samples/tree/main/03-integrations/Native-A2A-Support)
- [AWS CDK AgentCore Constructs](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_bedrock_agentcore_alpha/)
- [AgentCore Samples - Infrastructure as Code](https://github.com/awslabs/amazon-bedrock-agentcore-samples/tree/main/04-infrastructure-as-code)
- [A2A Protocol Specification](https://google.github.io/A2A/specification/)
