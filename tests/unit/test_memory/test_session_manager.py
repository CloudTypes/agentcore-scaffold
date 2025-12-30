"""Tests for memory session manager."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock


@pytest.fixture
def mock_memory_client():
    """Mock memory client."""
    client = MagicMock()
    client.retrieve_memories = MagicMock(return_value=[])
    client.get_user_preferences = MagicMock(return_value=[])
    client.store_event = MagicMock()
    return client


def test_session_manager_initialization(mock_memory_client):
    """Test session manager initialization."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id="session-123"
    )
    
    assert manager.actor_id == "user@example.com"
    assert manager.session_id == "session-123"


@pytest.mark.asyncio
async def test_session_manager_initialize(mock_memory_client):
    """Test session initialization."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    
    assert manager._initialized is True
    mock_memory_client.store_event.assert_called()


def test_store_user_input(mock_memory_client):
    """Test storing user input."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    manager.store_user_input(text="Hello")
    
    mock_memory_client.store_event.assert_called_once()
    call_args = mock_memory_client.store_event.call_args
    assert call_args[1]["event_type"] == "user_input"
    assert call_args[1]["payload"]["text"] == "Hello"


def test_store_agent_response(mock_memory_client):
    """Test storing agent response."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    manager.store_agent_response(text="Hi there!")
    
    mock_memory_client.store_event.assert_called_once()
    call_args = mock_memory_client.store_event.call_args
    assert call_args[1]["event_type"] == "agent_response"


def test_store_tool_use(mock_memory_client):
    """Test storing tool use."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    manager.store_tool_use(
        tool_name="calculator",
        input_data={"expression": "2+2"},
        output_data={"result": 4}
    )
    
    mock_memory_client.store_event.assert_called_once()
    call_args = mock_memory_client.store_event.call_args
    assert call_args[1]["event_type"] == "tool_use"
    assert call_args[1]["payload"]["tool_name"] == "calculator"


@pytest.mark.asyncio
async def test_finalize_session(mock_memory_client):
    """Test session finalization."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.finalize()
    
    mock_memory_client.store_event.assert_called()
    # Check that session_end event was stored
    calls = [call[1]["event_type"] for call in mock_memory_client.store_event.call_args_list]
    assert "session_end" in calls

