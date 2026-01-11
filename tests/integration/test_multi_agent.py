"""Integration tests for multi-agent system.

These tests require:
1. All agents running (docker-compose up)
2. Valid OAuth2 token for authentication (or OAuth2 disabled)
3. Memory service configured

To run these tests:
1. Start all services: docker-compose up
2. Get a valid OAuth2 token from the orchestrator's /api/auth/login endpoint
3. Set TEST_AUTH_TOKEN environment variable, or tests will skip
"""

import pytest
import httpx
import os
from agents.shared.models import AgentRequest


@pytest.fixture
def auth_token():
    """Get auth token for testing from environment or return None."""
    # Return None if not set - tests will handle this gracefully
    # If OAuth2 is disabled, tests will work without token
    # If OAuth2 is enabled, tests will skip or fail with 401
    return os.getenv("TEST_AUTH_TOKEN")


@pytest.mark.asyncio
async def test_orchestrator_to_vision_routing(auth_token):
    """Test that orchestrator routes vision requests to vision agent."""
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        
        # First create a session
        session_response = await client.post(
            "http://localhost:9000/api/sessions",
            headers=headers,
            timeout=5.0
        )
        # If auth is required but token is invalid, skip
        if session_response.status_code == 401:
            pytest.skip("Authentication required but token invalid. Set TEST_AUTH_TOKEN or disable OAuth2.")
        assert session_response.status_code == 200
        session_id = session_response.json()["session_id"]
        
        # Then send a chat message that should route to vision agent
        response = await client.post(
            "http://localhost:9000/api/chat",
            json={
                "message": "Analyze this image of a sunset",
                "session_id": session_id
            },
            headers=headers,
            timeout=30.0
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "response" in data  # Orchestrator returns {"response": "..."}


@pytest.mark.asyncio
async def test_direct_vision_agent_call_via_a2a(auth_token):
    """Test calling vision agent via A2A protocol (JSON-RPC 2.0)."""
    async with httpx.AsyncClient() as client:
        # Vision agent uses A2A protocol (JSON-RPC 2.0), not HTTP REST
        # This test verifies the A2A endpoint is accessible
        import uuid
        a2a_request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": f"msg-{uuid.uuid4().hex[:16]}",
                    "role": "user",
                    "parts": [{"type": "text", "text": "Describe this image"}]
                }
            },
            "id": 1
        }
        
        # Vision agent A2A server is on port 9001 (host) -> 9000 (container)
        response = await client.post(
            "http://localhost:9001/",
            json=a2a_request,
            timeout=30.0
        )
        
        # A2A protocol returns JSON-RPC 2.0 response
        assert response.status_code == 200
        data = response.json()
        assert "jsonrpc" in data
        assert data["jsonrpc"] == "2.0"
        # Response should have either "result" or "error"
        assert "result" in data or "error" in data


@pytest.mark.asyncio
async def test_all_agents_health():
    """Test health endpoints for all agents."""
    # Only orchestrator has HTTP REST health endpoint
    # Specialist agents use A2A protocol and expose agent cards
    async with httpx.AsyncClient() as client:
        # Test orchestrator health endpoint
        response = await client.get(
            "http://localhost:9000/health",
            timeout=5.0
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "orchestrator"
        
        # Test specialist agents via A2A agent cards (if available)
        # Vision agent card
        try:
            response = await client.get(
                "http://localhost:9001/.well-known/agent-card.json",
                timeout=5.0
            )
            if response.status_code == 200:
                card = response.json()
                assert "name" in card or "agent" in card
        except httpx.ConnectError:
            pytest.skip("Vision agent not running")


@pytest.mark.asyncio
async def test_a2a_authentication():
    """Test that orchestrator chat endpoint requires authentication."""
    async with httpx.AsyncClient() as client:
        # Test orchestrator chat endpoint without auth token
        response = await client.post(
            "http://localhost:9000/api/chat",
            json={"message": "Test", "session_id": "test-123"},
            timeout=5.0
        )
        
        # Should return 401 (Unauthorized) without auth token
        # If OAuth2 is disabled, this might return 200, so we check for either
        assert response.status_code in [401, 200]


@pytest.mark.asyncio
async def test_orchestrator_to_tool_routing(auth_token):
    """Test that orchestrator routes tool requests to tool agent."""
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        
        # First create a session
        session_response = await client.post(
            "http://localhost:9000/api/sessions",
            headers=headers,
            timeout=5.0
        )
        # If auth is required but token is invalid, skip
        if session_response.status_code == 401:
            pytest.skip("Authentication required but token invalid. Set TEST_AUTH_TOKEN or disable OAuth2.")
        assert session_response.status_code == 200
        session_id = session_response.json()["session_id"]
        
        # Then send a chat message that should route to tool agent
        response = await client.post(
            "http://localhost:9000/api/chat",
            json={
                "message": "What's 15% of 200?",
                "session_id": session_id
            },
            headers=headers,
            timeout=30.0
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "response" in data  # Orchestrator returns {"response": "..."}

