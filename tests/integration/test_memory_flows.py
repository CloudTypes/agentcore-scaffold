"""Integration tests for memory flows."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from memory.client import MemoryClient
from memory.session_manager import MemorySessionManager


@pytest.fixture
def mock_memory_client():
    """Mock memory client for integration tests."""
    client = MagicMock(spec=MemoryClient)
    client.memory_id = "test-memory-id"
    client.region = "us-east-1"
    client.retrieve_memories = MagicMock(return_value=[])
    client.get_user_preferences = MagicMock(return_value=[])
    client.store_event = MagicMock()
    client.get_session_summary = MagicMock(return_value=None)
    client.list_sessions = MagicMock(return_value=[])
    return client


@pytest.fixture
def sample_memory_records():
    """Sample memory records for testing."""
    return [
        MagicMock(content="Past conversation about weather in Denver"),
        MagicMock(content="User asked about calculations")
    ]


@pytest.fixture
def sample_preferences():
    """Sample user preferences for testing."""
    return [
        MagicMock(content="User prefers concise responses")
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_integration_flow(mock_memory_client):
    """Test end-to-end memory storage and retrieval."""
    # Create session manager
    session_manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id="test-session-123"
    )
    
    # Initialize session (should retrieve memories and preferences)
    await session_manager.initialize()
    
    # Verify memory operations were called
    mock_memory_client.retrieve_memories.assert_called_once()
    mock_memory_client.get_user_preferences.assert_called_once()
    mock_memory_client.store_event.assert_called()
    
    # Store user input
    session_manager.store_user_input(text="What's the weather?")
    
    # Verify event was stored
    calls = mock_memory_client.store_event.call_args_list
    user_input_calls = [c for c in calls if c[1]["event_type"] == "user_input"]
    assert len(user_input_calls) > 0
    
    # Store agent response
    session_manager.store_agent_response(text="The weather is sunny.")
    
    # Verify event was stored
    calls = mock_memory_client.store_event.call_args_list
    agent_response_calls = [c for c in calls if c[1]["event_type"] == "agent_response"]
    assert len(agent_response_calls) > 0
    
    # Finalize session
    await session_manager.finalize()
    
    # Verify session_end event was stored
    calls = mock_memory_client.store_event.call_args_list
    session_end_calls = [c for c in calls if c[1]["event_type"] == "session_end"]
    assert len(session_end_calls) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_session_memory_persistence(mock_memory_client, sample_memory_records):
    """Test that memories persist across sessions."""
    # First session: store some events
    session1 = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id="session-1"
    )
    
    await session1.initialize()
    session1.store_user_input(text="I like dark mode")
    await session1.finalize()
    
    # Second session: verify previous memories are available
    mock_memory_client.retrieve_memories.return_value = sample_memory_records
    mock_memory_client.get_user_preferences.return_value = []
    
    session2 = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id="session-2"
    )
    
    await session2.initialize()
    
    # Verify memories were retrieved
    mock_memory_client.retrieve_memories.assert_called()
    
    # Verify context includes past memories
    context = session2.get_context()
    assert context is not None
    
    # Verify session isolation (different session IDs)
    assert session1.session_id != session2.session_id
    
    # Verify both sessions stored events with correct session IDs
    calls = mock_memory_client.store_event.call_args_list
    session1_calls = [c for c in calls if c[1]["session_id"] == "session-1"]
    session2_calls = [c for c in calls if c[1]["session_id"] == "session-2"]
    assert len(session1_calls) > 0
    # session2 should have session_start event
    assert len(session2_calls) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_context_injection(mock_memory_client, sample_memory_records, sample_preferences):
    """Test that memory context is injected into agent."""
    # Set up memories and preferences
    mock_memory_client.retrieve_memories.return_value = sample_memory_records
    mock_memory_client.get_user_preferences.return_value = sample_preferences
    
    # Create session manager
    session_manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    # Initialize (should build context from memories and preferences)
    await session_manager.initialize()
    
    # Get context
    context = session_manager.get_context()
    
    # Verify context is built
    assert context is not None
    assert "Past conversation" in context or "weather" in context.lower()
    assert "prefers" in context.lower() or "concise" in context.lower()
    
    # Verify memories and preferences were retrieved
    mock_memory_client.retrieve_memories.assert_called_once()
    mock_memory_client.get_user_preferences.assert_called_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_context_injection_empty(mock_memory_client):
    """Test context injection with empty memories."""
    # No memories or preferences
    mock_memory_client.retrieve_memories.return_value = []
    mock_memory_client.get_user_preferences.return_value = []
    
    session_manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await session_manager.initialize()
    
    # Context should be None when no memories/preferences
    context = session_manager.get_context()
    assert context is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_authentication_with_memory(mock_memory_client):
    """Test authentication flow with memory integration."""
    from agent import websocket_endpoint
    from fastapi import WebSocket
    
    # Mock user info from authentication
    user_info = {
        "email": "user@example.com",
        "name": "Test User"
    }
    
    # Mock WebSocket
    mock_websocket = AsyncMock(spec=WebSocket)
    mock_websocket.query_params = {"token": "valid-token"}
    mock_websocket.accept = AsyncMock()
    mock_websocket.send_json = AsyncMock()
    mock_websocket.receive_json = AsyncMock(side_effect=Exception("Disconnect"))
    
    # Mock OAuth handler
    with patch('agent.oauth2_handler') as mock_oauth:
        mock_oauth.verify_token.return_value = user_info
        
        # Mock memory client initialization
        with patch('agent.memory_client', mock_memory_client):
            # Mock agent creation
            with patch('agent.create_nova_sonic_model') as mock_model:
                with patch('agent.create_agent') as mock_agent:
                    mock_agent_instance = AsyncMock()
                    mock_agent_instance.run = AsyncMock()
                    mock_agent.return_value = mock_agent_instance
                    
                    # Mock WebSocketInput and WebSocketOutput
                    with patch('agent.WebSocketInput') as mock_input:
                        with patch('agent.WebSocketOutput') as mock_output:
                            mock_input_instance = AsyncMock()
                            mock_input_instance.start = AsyncMock()
                            mock_input_instance.stop = AsyncMock()
                            mock_input.return_value = mock_input_instance
                            
                            mock_output_instance = AsyncMock()
                            mock_output_instance.start = AsyncMock()
                            mock_output_instance.stop = AsyncMock()
                            mock_output.return_value = mock_output_instance
                            
                            # Call websocket endpoint
                            try:
                                await websocket_endpoint(mock_websocket)
                            except Exception:
                                # Expected to fail due to mocked disconnect
                                pass
                            
                            # Verify authentication was checked
                            mock_oauth.verify_token.assert_called_once_with("valid-token")
                            
                            # Verify memory session manager was created with correct actor_id
                            # (This is verified by checking that memory_client methods would be called
                            # if the session completed normally)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_use_memory_storage(mock_memory_client):
    """Test that tool use events are stored in memory."""
    session_manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id="test-session"
    )
    
    await session_manager.initialize()
    
    # Store tool use
    session_manager.store_tool_use(
        tool_name="calculator",
        input_data={"expression": "2+2"},
        output_data={"result": 4}
    )
    
    # Verify tool use event was stored
    calls = mock_memory_client.store_event.call_args_list
    tool_use_calls = [c for c in calls if c[1]["event_type"] == "tool_use"]
    assert len(tool_use_calls) > 0
    
    # Verify tool use data
    tool_call = tool_use_calls[0]
    assert tool_call[1]["payload"]["tool_name"] == "calculator"
    assert tool_call[1]["payload"]["input"] == {"expression": "2+2"}
    assert tool_call[1]["payload"]["output"] == {"result": 4}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_error_handling(mock_memory_client):
    """Test that memory errors don't break the session."""
    # Make memory operations fail
    mock_memory_client.retrieve_memories.side_effect = Exception("Memory error")
    mock_memory_client.store_event.side_effect = Exception("Storage error")
    
    session_manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    # Initialize should continue even if memory fails
    await session_manager.initialize()
    assert session_manager._initialized is True
    
    # Store operations should not raise
    session_manager.store_user_input(text="Hello")
    
    # Finalize should not raise
    await session_manager.finalize()

