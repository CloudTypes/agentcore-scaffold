"""Integration tests for A2A communication."""

import os
import pytest
import httpx
from agents.shared.models import AgentRequest
from agents.shared.service_discovery import ServiceDiscovery
from agents.shared.circuit_breaker import CircuitBreaker, CircuitState
from agents.shared.retry import retry_with_backoff


@pytest.fixture
def auth_token():
    """Get auth token for testing from environment or return None."""
    # Return None if not set - tests will handle this gracefully
    return os.getenv("TEST_AUTH_TOKEN")


@pytest.mark.asyncio
async def test_service_discovery():
    """Test service discovery loads endpoints correctly."""
    import os

    os.environ["ENVIRONMENT"] = "development"
    discovery = ServiceDiscovery()

    # In development mode, service discovery uses localhost with default ports
    # These match the DEFAULT_DEV_ENDPOINTS in service_discovery.py
    assert discovery.get_endpoint("orchestrator") == "http://localhost:9005"
    assert discovery.get_endpoint("vision") == "http://localhost:9001"
    assert discovery.get_endpoint("document") == "http://localhost:9002"
    assert discovery.get_endpoint("data") == "http://localhost:9003"
    assert discovery.get_endpoint("tool") == "http://localhost:9004"


@pytest.mark.asyncio
async def test_a2a_call_with_retry(auth_token):
    """Test A2A call with retry logic."""
    async with httpx.AsyncClient() as client:
        # Vision agent uses A2A protocol (JSON-RPC 2.0)
        import uuid

        a2a_request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": f"msg-{uuid.uuid4().hex[:16]}",
                    "role": "user",
                    "parts": [{"type": "text", "text": "Test message"}],
                }
            },
            "id": 1,
        }

        # Vision agent A2A server is on port 9001 (host) -> 9000 (container)
        response = await client.post("http://localhost:9001/", json=a2a_request, timeout=30.0)

        # A2A protocol returns JSON-RPC 2.0 response
        assert response.status_code == 200
        data = response.json()
        assert "jsonrpc" in data
        assert data["jsonrpc"] == "2.0"


@pytest.mark.asyncio
async def test_circuit_breaker():
    """Test circuit breaker behavior."""
    breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=1)

    # Initially closed
    assert breaker.state == CircuitState.CLOSED

    # Simulate failures
    breaker._on_failure()
    assert breaker.state == CircuitState.CLOSED

    breaker._on_failure()
    assert breaker.state == CircuitState.OPEN

    # Test reset after timeout
    import time

    time.sleep(1.1)
    assert breaker._should_attempt_reset()


@pytest.mark.asyncio
async def test_retry_with_backoff():
    """Test retry logic with exponential backoff."""
    call_count = 0

    async def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Temporary failure")
        return "success"

    result = await retry_with_backoff(failing_func, max_retries=3, base_delay=0.1)

    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_a2a_call_error_handling(auth_token):
    """Test error handling in A2A calls."""
    async with httpx.AsyncClient() as client:
        request = AgentRequest(message="Test message", context=[], user_id="test-user", session_id="test-session")

        # Try to call non-existent agent endpoint
        import uuid

        a2a_request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": f"msg-{uuid.uuid4().hex[:16]}",
                    "role": "user",
                    "parts": [{"type": "text", "text": "Test message"}],
                }
            },
            "id": 1,
        }

        try:
            response = await client.post("http://localhost:9999/", json=a2a_request, timeout=5.0)
        except httpx.ConnectError:
            # Expected - agent doesn't exist
            pass
