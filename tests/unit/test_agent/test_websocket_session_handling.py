"""Unit tests for WebSocket session handling in voice agent."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from fastapi import WebSocket
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from agent import app, websocket_endpoint
from auth.google_oauth2 import GoogleOAuth2Handler


@pytest.fixture
def mock_websocket():
    """Mock WebSocket object."""
    websocket = AsyncMock(spec=WebSocket)
    websocket.query_params = {}
    websocket.send_json = AsyncMock()
    websocket.receive_json = AsyncMock()
    websocket.accept = AsyncMock()
    websocket.close = AsyncMock()
    return websocket


@pytest.fixture
def mock_oauth2_handler():
    """Mock OAuth2 handler."""
    handler = MagicMock(spec=GoogleOAuth2Handler)
    handler.verify_token = Mock(return_value={"email": "user@example.com", "name": "Test User"})
    return handler


@pytest.fixture
def mock_memory_client():
    """Mock memory client."""
    client = MagicMock()
    client.memory_id = "test-memory-id"
    return client


class TestWebSocketSessionHandling:
    """Test cases for WebSocket session handling."""
    
    @pytest.mark.asyncio
    async def test_websocket_with_session_id(self, mock_websocket, mock_oauth2_handler, mock_memory_client):
        """Test WebSocket connection with pre-created session_id."""
        mock_websocket.query_params = {
            "token": "test-token",
            "session_id": "pre-created-session-123"
        }
        
        with patch('agent.oauth2_handler', mock_oauth2_handler), \
             patch('agent.memory_client', mock_memory_client), \
             patch('agent.MemorySessionManager') as mock_session_manager_class, \
             patch('agent.create_nova_sonic_model'), \
             patch('agent.create_agent'), \
             patch('agent.WebSocketInput'), \
             patch('agent.WebSocketOutput'):
            
            mock_manager = AsyncMock()
            mock_manager.session_id = "pre-created-session-123"
            mock_manager.initialize = AsyncMock(return_value=None)
            mock_manager.get_context = Mock(return_value=None)
            mock_session_manager_class.return_value = mock_manager
            
            # Call websocket_endpoint (will raise StopAsyncIteration when agent.run is called)
            try:
                await websocket_endpoint(mock_websocket)
            except (StopAsyncIteration, RuntimeError, AttributeError, TypeError):
                pass  # Expected when agent.run is mocked or other async issues
            
            # Verify session_id was passed to MemorySessionManager
            mock_session_manager_class.assert_called_once()
            call_kwargs = mock_session_manager_class.call_args[1]
            assert call_kwargs["session_id"] == "pre-created-session-123"
            mock_manager.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_websocket_without_session_id(self, mock_websocket, mock_oauth2_handler, mock_memory_client):
        """Test WebSocket connection without session_id (creates new)."""
        mock_websocket.query_params = {
            "token": "test-token"
        }
        
        with patch('agent.oauth2_handler', mock_oauth2_handler), \
             patch('agent.memory_client', mock_memory_client), \
             patch('agent.MemorySessionManager') as mock_session_manager_class, \
             patch('agent.create_nova_sonic_model'), \
             patch('agent.create_agent'), \
             patch('agent.WebSocketInput'), \
             patch('agent.WebSocketOutput'):
            
            mock_manager = AsyncMock()
            mock_manager.session_id = "new-session-456"
            mock_manager.initialize = AsyncMock(return_value=None)
            mock_manager.get_context = Mock(return_value=None)
            mock_session_manager_class.return_value = mock_manager
            
            try:
                await websocket_endpoint(mock_websocket)
            except (StopAsyncIteration, RuntimeError, AttributeError, TypeError):
                pass
            
            # Verify MemorySessionManager was called without session_id (will generate new)
            mock_session_manager_class.assert_called_once()
            call_kwargs = mock_session_manager_class.call_args[1]
            assert call_kwargs.get("session_id") is None  # No session_id provided
            mock_manager.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_websocket_authentication_required(self, mock_websocket):
        """Test WebSocket requires authentication token."""
        mock_websocket.query_params = {}  # No token
        
        with patch('agent.oauth2_handler', MagicMock()):
            await websocket_endpoint(mock_websocket)
            
            # Should close connection with authentication error
            mock_websocket.close.assert_called_once()
            call_args = mock_websocket.close.call_args
            assert "Authentication required" in str(call_args)
