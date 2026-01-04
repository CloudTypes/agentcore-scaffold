"""Integration tests for multi-agent system."""

import pytest
import httpx
from agents.shared.models import AgentRequest
from agents.shared.auth import InterAgentAuth


@pytest.fixture
def auth_token():
    """Create auth token for testing."""
    import os
    os.environ["AGENT_AUTH_SECRET"] = "test-secret-key-for-testing-only"
    auth = InterAgentAuth()
    return auth.create_token("test-client")


@pytest.mark.asyncio
async def test_orchestrator_to_vision_routing(auth_token):
    """Test that orchestrator routes vision requests to vision agent."""
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
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "orchestrator"
        assert "specialist" in data.get("metadata", {})


@pytest.mark.asyncio
async def test_direct_vision_agent_call(auth_token):
    """Test calling vision agent directly."""
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
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "vision"


@pytest.mark.asyncio
async def test_all_agents_health():
    """Test health endpoints for all agents."""
    agents = {
        "orchestrator": 8080,
        "vision": 8081,
        "document": 8082,
        "data": 8083,
        "tool": 8084
    }
    
    async with httpx.AsyncClient() as client:
        for agent_name, port in agents.items():
            response = await client.get(
                f"http://localhost:{port}/health",
                timeout=5.0
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["agent_name"] == agent_name


@pytest.mark.asyncio
async def test_a2a_authentication():
    """Test that A2A calls require valid authentication."""
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
            json=request.model_dump(),
            timeout=5.0
        )
        
        assert response.status_code == 403  # Forbidden without auth


@pytest.mark.asyncio
async def test_orchestrator_to_tool_routing(auth_token):
    """Test that orchestrator routes tool requests to tool agent."""
    async with httpx.AsyncClient() as client:
        request = AgentRequest(
            message="What's 15% of 200?",
            context=[],
            user_id="test-user",
            session_id="test-session"
        )
        
        response = await client.post(
            "http://localhost:8080/process",
            json=request.model_dump(),
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "orchestrator"
        # Should route to tool agent
        assert "specialist" in data.get("metadata", {})

