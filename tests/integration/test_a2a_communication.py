"""Integration tests for A2A communication."""

import pytest
import httpx
from agents.shared.models import AgentRequest
from agents.shared.auth import InterAgentAuth
from agents.shared.service_discovery import ServiceDiscovery
from agents.shared.circuit_breaker import CircuitBreaker, CircuitState
from agents.shared.retry import retry_with_backoff


@pytest.fixture
def auth_token():
    """Create auth token for testing."""
    import os
    os.environ["AGENT_AUTH_SECRET"] = "test-secret-key-for-testing-only"
    auth = InterAgentAuth()
    return auth.create_token("test-client")


@pytest.mark.asyncio
async def test_service_discovery():
    """Test service discovery loads endpoints correctly."""
    import os
    os.environ["ENVIRONMENT"] = "development"
    discovery = ServiceDiscovery()
    
    assert discovery.get_endpoint("orchestrator") == "http://orchestrator:8080"
    assert discovery.get_endpoint("vision") == "http://vision:8080"
    assert discovery.get_endpoint("document") == "http://document:8080"
    assert discovery.get_endpoint("data") == "http://data:8080"
    assert discovery.get_endpoint("tool") == "http://tool:8080"


@pytest.mark.asyncio
async def test_a2a_call_with_retry(auth_token):
    """Test A2A call with retry logic."""
    async with httpx.AsyncClient() as client:
        request = AgentRequest(
            message="Test message",
            context=[],
            user_id="test-user",
            session_id="test-session"
        )
        
        # Make call to vision agent
        response = await client.post(
            "http://localhost:8081/process",
            json=request.model_dump(),
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=30.0
        )
        
        assert response.status_code == 200


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
    
    result = await retry_with_backoff(
        failing_func,
        max_retries=3,
        base_delay=0.1
    )
    
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_a2a_call_error_handling(auth_token):
    """Test error handling in A2A calls."""
    async with httpx.AsyncClient() as client:
        request = AgentRequest(
            message="Test message",
            context=[],
            user_id="test-user",
            session_id="test-session"
        )
        
        # Try to call non-existent agent endpoint
        try:
            response = await client.post(
                "http://localhost:9999/process",
                json=request.model_dump(),
                headers={"Authorization": f"Bearer {auth_token}"},
                timeout=5.0
            )
        except httpx.ConnectError:
            # Expected - agent doesn't exist
            pass

