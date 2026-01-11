"""Unit tests for voice agent session endpoint."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from agent import app
from auth.oauth2_middleware import get_current_user


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    return {"email": "user@example.com", "name": "Test User"}


@pytest.fixture
def mock_memory_client():
    """Mock memory client."""
    client = MagicMock()
    client.memory_id = "test-memory-id"
    client.region = os.getenv("AGENTCORE_MEMORY_REGION") or os.getenv("AWS_REGION", "us-west-2")
    return client


@pytest.fixture
def app_client_with_memory(mock_memory_client, mock_user):
    """Create test client with memory enabled."""
    async def override_get_current_user():
        return mock_user
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    with patch('agent.memory_client', mock_memory_client):
        yield TestClient(app)
    
    app.dependency_overrides.clear()


@pytest.fixture
def app_client_no_memory(mock_user):
    """Create test client with memory disabled."""
    async def override_get_current_user():
        return mock_user
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    with patch('agent.memory_client', None):
        yield TestClient(app)
    
    app.dependency_overrides.clear()


@pytest.fixture
def app_client_unauthorized():
    """Create test client without authentication."""
    async def override_get_current_user():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    with patch('agent.memory_client', MagicMock()):
        yield TestClient(app)
    
    app.dependency_overrides.clear()


class TestCreateSession:
    """Test cases for POST /api/sessions endpoint."""
    
    def test_create_session_new(self, app_client_with_memory, mock_memory_client, mock_user):
        """Test creating a new session."""
        with patch('agent.MemorySessionManager') as mock_session_manager_class:
            mock_manager = MagicMock()
            mock_manager.session_id = "new-session-123"
            mock_manager.initialize = AsyncMock()
            mock_session_manager_class.return_value = mock_manager
            
            response = app_client_with_memory.post(
                "/api/sessions",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert data["session_id"] == "new-session-123"
            mock_manager.initialize.assert_called_once()
    
    def test_create_session_reuse_existing(self, app_client_with_memory, mock_memory_client, mock_user):
        """Test reusing an existing session when session_id provided."""
        with patch('agent.MemorySessionManager') as mock_session_manager_class:
            mock_manager = MagicMock()
            mock_manager.session_id = "existing-session-456"
            mock_manager.initialize = AsyncMock()
            mock_session_manager_class.return_value = mock_manager
            
            response = app_client_with_memory.post(
                "/api/sessions",
                headers={"Authorization": "Bearer test-token"},
                json={"session_id": "existing-session-456"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == "existing-session-456"
            # Verify session_id was passed to MemorySessionManager
            mock_session_manager_class.assert_called_once()
            call_kwargs = mock_session_manager_class.call_args[1]
            assert call_kwargs["session_id"] == "existing-session-456"
    
    def test_create_session_authentication_required(self, app_client_unauthorized):
        """Test session creation requires authentication."""
        response = app_client_unauthorized.post("/api/sessions")
        assert response.status_code == 401
    
    def test_create_session_memory_disabled(self, app_client_no_memory):
        """Test session creation fails when memory is disabled."""
        response = app_client_no_memory.post(
            "/api/sessions",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 503
        assert "Memory not enabled" in response.json()["detail"]
