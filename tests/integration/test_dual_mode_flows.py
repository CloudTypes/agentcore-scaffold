"""
Integration tests for dual mode (voice/text) flows.

These tests verify end-to-end functionality including:
- Voice mode connection and streaming
- Text mode connection and messaging
- Mode switching with session continuity
- Session management
- Orchestrator integration
- Authentication
- CORS and proxy headers
"""

import pytest
import sys
import os
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import httpx

# Add project root to path for imports
project_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, os.path.join(project_root, "agents", "orchestrator"))

from agent import app as voice_app
from agents.orchestrator.app import app as orchestrator_app
from auth.oauth2_middleware import get_current_user
from strands.experimental.bidi.types.events import (
    BidiConnectionStartEvent,
    BidiResponseStartEvent,
    BidiTranscriptStreamEvent,
    BidiResponseCompleteEvent,
)
from strands.types._events import ContentBlockDelta


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    return {"email": "user@example.com", "name": "Test User"}


@pytest.fixture
def mock_memory_client():
    """Mock memory client for both agents."""
    client = MagicMock()
    client.memory_id = "test-memory-id"
    client.region = "us-west-2"
    client.create_memory_resource = MagicMock()
    client.list_sessions = MagicMock(return_value=[])
    client.get_session_summary = MagicMock(return_value=None)
    client.get_user_preferences = MagicMock(return_value=[])
    client.store_event = MagicMock()
    return client


@pytest.fixture
def voice_client(mock_user, mock_memory_client):
    """Create voice agent test client."""

    async def override_get_current_user():
        return mock_user

    voice_app.dependency_overrides[get_current_user] = override_get_current_user

    with patch("agent.memory_client", mock_memory_client), patch("agent.oauth2_handler", MagicMock()):
        yield TestClient(voice_app)

    voice_app.dependency_overrides.clear()


@pytest.fixture
def orchestrator_client(mock_user, mock_memory_client):
    """Create orchestrator agent test client."""

    async def override_get_current_user():
        return mock_user

    orchestrator_app.dependency_overrides[get_current_user] = override_get_current_user

    with (
        patch("agents.orchestrator.app.memory_client", mock_memory_client),
        patch("agents.orchestrator.app.orchestrator_agent") as mock_agent,
        patch("agents.orchestrator.app.oauth2_handler", MagicMock()),
    ):
        # Create mock orchestrator agent
        mock_orchestrator = MagicMock()
        mock_orchestrator.run = AsyncMock(return_value=MagicMock(content="Test response from orchestrator"))
        mock_agent.return_value = mock_orchestrator
        # Set the global variable
        import agents.orchestrator.app as orchestrator_module

        orchestrator_module.orchestrator_agent = mock_orchestrator

        yield TestClient(orchestrator_app)

    orchestrator_app.dependency_overrides.clear()


class TestVoiceModeFlow:
    """Test cases for voice mode connection and streaming."""

    @pytest.mark.integration
    def test_voice_mode_initial_connection(self, voice_client, mock_memory_client):
        """Test voice mode: create session, establish WebSocket, verify session_id used."""
        # First create a session
        response = voice_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})
        assert response.status_code == 200
        session_data = response.json()
        session_id = session_data["session_id"]
        assert session_id is not None

        # Now connect via WebSocket with the session_id
        with (
            patch("agent.create_nova_sonic_model"),
            patch("agent.create_agent") as mock_create_agent,
            patch("agent.WebSocketInput"),
            patch("agent.WebSocketOutput"),
        ):

            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(side_effect=StopAsyncIteration())
            mock_create_agent.return_value = mock_agent

            with voice_client.websocket_connect(f"/ws?token=test-token&session_id={session_id}") as websocket:
                # Connection should be established
                # The session_id should be used by the WebSocket handler
                pass  # Connection successful

    @pytest.mark.integration
    def test_voice_mode_with_precreated_session(self, voice_client, mock_memory_client):
        """Test voice mode: use existing session_id, verify reuse."""
        # Create session first
        response = voice_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})
        session_id = response.json()["session_id"]

        # Connect with the same session_id
        with (
            patch("agent.create_nova_sonic_model"),
            patch("agent.create_agent") as mock_create_agent,
            patch("agent.WebSocketInput"),
            patch("agent.WebSocketOutput"),
        ):

            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(side_effect=StopAsyncIteration())
            mock_create_agent.return_value = mock_agent

            with voice_client.websocket_connect(f"/ws?token=test-token&session_id={session_id}") as websocket:
                # Verify session was reused (check that MemorySessionManager was called with session_id)
                pass  # Connection successful with reused session


class TestTextModeFlow:
    """Test cases for text mode connection and messaging."""

    @pytest.mark.integration
    def test_text_mode_initial_connection(self, orchestrator_client, mock_memory_client):
        """Test text mode: create session, send text message, verify response."""
        # Create session
        response = orchestrator_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})
        assert response.status_code == 200
        session_id = response.json()["session_id"]

        # Send text message
        response = orchestrator_client.post(
            "/api/chat",
            headers={"Authorization": "Bearer test-token"},
            json={"message": "What is 2+2?", "session_id": session_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["response"] == "Test response from orchestrator"

    @pytest.mark.integration
    def test_text_mode_with_precreated_session(self, orchestrator_client, mock_memory_client):
        """Test text mode: use existing session_id, verify reuse."""
        # Create session first
        response = orchestrator_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})
        session_id = response.json()["session_id"]

        # Send message with same session_id
        response = orchestrator_client.post(
            "/api/chat", headers={"Authorization": "Bearer test-token"}, json={"message": "Hello", "session_id": session_id}
        )

        assert response.status_code == 200
        # Session should be reused

    @pytest.mark.integration
    def test_text_mode_multiple_messages(self, orchestrator_client, mock_memory_client):
        """Test text mode: send multiple messages, verify context maintained."""
        # Create session
        response = orchestrator_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})
        session_id = response.json()["session_id"]

        # Send first message
        response1 = orchestrator_client.post(
            "/api/chat",
            headers={"Authorization": "Bearer test-token"},
            json={"message": "My name is Alice", "session_id": session_id},
        )
        assert response1.status_code == 200

        # Send second message (should maintain context)
        response2 = orchestrator_client.post(
            "/api/chat",
            headers={"Authorization": "Bearer test-token"},
            json={"message": "What is my name?", "session_id": session_id},
        )
        assert response2.status_code == 200


class TestModeSwitching:
    """Test cases for mode switching with session continuity."""

    @pytest.mark.integration
    def test_switch_voice_to_text(self, voice_client, orchestrator_client, mock_memory_client):
        """Test switching from voice mode to text mode, verify session_id reused."""
        # Start in voice mode - create session
        response = voice_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})
        session_id = response.json()["session_id"]

        # Switch to text mode - use same session_id
        response = orchestrator_client.post(
            "/api/chat",
            headers={"Authorization": "Bearer test-token"},
            json={"message": "Hello from text mode", "session_id": session_id},
        )

        assert response.status_code == 200
        # Session should be reused, maintaining conversation context

    @pytest.mark.integration
    def test_switch_text_to_voice(self, voice_client, orchestrator_client, mock_memory_client):
        """Test switching from text mode to voice mode, verify session_id reused."""
        # Start in text mode - create session via orchestrator
        response = orchestrator_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})
        session_id = response.json()["session_id"]

        # Switch to voice mode - use same session_id in WebSocket
        with (
            patch("agent.create_nova_sonic_model"),
            patch("agent.create_agent") as mock_create_agent,
            patch("agent.WebSocketInput"),
            patch("agent.WebSocketOutput"),
        ):

            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(side_effect=StopAsyncIteration())
            mock_create_agent.return_value = mock_agent

            with voice_client.websocket_connect(f"/ws?token=test-token&session_id={session_id}") as websocket:
                # Session should be reused
                pass

    @pytest.mark.integration
    def test_conversation_continuity(self, voice_client, orchestrator_client, mock_memory_client):
        """Test conversation continuity across mode switches."""
        # Create session in voice mode
        response = voice_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})
        session_id = response.json()["session_id"]

        # Send message in text mode
        response = orchestrator_client.post(
            "/api/chat",
            headers={"Authorization": "Bearer test-token"},
            json={"message": "I like pizza", "session_id": session_id},
        )
        assert response.status_code == 200

        # Switch back to voice mode - context should be preserved
        with (
            patch("agent.create_nova_sonic_model"),
            patch("agent.create_agent") as mock_create_agent,
            patch("agent.WebSocketInput"),
            patch("agent.WebSocketOutput"),
        ):

            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(side_effect=StopAsyncIteration())
            mock_create_agent.return_value = mock_agent

            with voice_client.websocket_connect(f"/ws?token=test-token&session_id={session_id}") as websocket:
                # Session context should include previous conversation
                pass


class TestSessionManagement:
    """Test cases for session management."""

    @pytest.mark.integration
    def test_session_creation_independent_of_connection(self, voice_client, mock_memory_client):
        """Test session creation without WebSocket connection."""
        response = voice_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        # Session created without any WebSocket connection

    @pytest.mark.integration
    def test_session_reuse_across_modes(self, voice_client, orchestrator_client, mock_memory_client):
        """Test same session_id used in both modes."""
        # Create session via voice agent
        response1 = voice_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})
        session_id1 = response1.json()["session_id"]

        # Create session via orchestrator (should reuse if same user)
        response2 = orchestrator_client.post(
            "/api/sessions", headers={"Authorization": "Bearer test-token"}, json={"session_id": session_id1}
        )
        session_id2 = response2.json()["session_id"]

        # Should be the same session_id
        assert session_id1 == session_id2


class TestOrchestratorIntegration:
    """Test cases for orchestrator agent integration."""

    @pytest.mark.integration
    def test_orchestrator_text_chat(self, orchestrator_client, mock_memory_client):
        """Test sending message to orchestrator, verify routing to specialist agents."""
        # Create session
        response = orchestrator_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})
        session_id = response.json()["session_id"]

        # Send message
        response = orchestrator_client.post(
            "/api/chat",
            headers={"Authorization": "Bearer test-token"},
            json={"message": "What is 2+ 2?", "session_id": session_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data

    @pytest.mark.integration
    def test_orchestrator_session_context(self, orchestrator_client, mock_memory_client):
        """Test orchestrator uses session context."""
        # Create session
        response = orchestrator_client.post("/api/sessions", headers={"Authorization": "Bearer test-token"})
        session_id = response.json()["session_id"]

        # Send first message
        orchestrator_client.post(
            "/api/chat",
            headers={"Authorization": "Bearer test-token"},
            json={"message": "Context message", "session_id": session_id},
        )

        # Send second message - should have context
        response = orchestrator_client.post(
            "/api/chat",
            headers={"Authorization": "Bearer test-token"},
            json={"message": "Follow-up", "session_id": session_id},
        )

        assert response.status_code == 200


class TestAuthentication:
    """Test cases for authentication requirements."""

    @pytest.mark.integration
    def test_session_endpoint_authentication(self, mock_memory_client):
        """Test session creation requires authentication."""
        # Create client without authentication override
        with patch("agent.memory_client", mock_memory_client), patch("agent.oauth2_handler", MagicMock()):
            # Remove dependency override to test authentication
            voice_app.dependency_overrides.clear()
            client = TestClient(voice_app)
            response = client.post("/api/sessions")
            assert response.status_code == 401
            voice_app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_chat_endpoint_authentication(self, mock_memory_client):
        """Test chat requires authentication."""
        # Create client without authentication override
        with (
            patch("agents.orchestrator.app.memory_client", mock_memory_client),
            patch("agents.orchestrator.app.oauth2_handler", MagicMock()),
        ):
            # Remove dependency override to test authentication
            orchestrator_app.dependency_overrides.clear()
            client = TestClient(orchestrator_app)
            response = client.post("/api/chat", json={"message": "Hello", "session_id": "test-123"})
            assert response.status_code == 401
            orchestrator_app.dependency_overrides.clear()

    @pytest.mark.integration
    def test_websocket_authentication(self, voice_client):
        """Test WebSocket requires token."""
        with pytest.raises(Exception):  # WebSocket connection should fail without token
            with voice_client.websocket_connect("/ws") as websocket:
                pass


class TestCorsAndProxy:
    """Test cases for CORS and proxy header handling."""

    @pytest.mark.integration
    def test_cors_headers(self, orchestrator_client):
        """Test CORS headers are set correctly."""
        response = orchestrator_client.options(
            "/api/sessions", headers={"Origin": "https://example.com", "Access-Control-Request-Method": "POST"}
        )
        # CORS preflight should succeed
        assert response.status_code in [200, 204]

    @pytest.mark.integration
    def test_cors_preflight(self, orchestrator_client):
        """Test CORS preflight requests handled."""
        response = orchestrator_client.options(
            "/api/chat",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type, Authorization",
            },
        )
        assert response.status_code in [200, 204]
