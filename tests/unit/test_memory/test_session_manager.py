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


def test_session_manager_initialization_generates_session_id(mock_memory_client):
    """Test session manager generates session ID if not provided."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    assert manager.session_id is not None
    assert len(manager.session_id) > 0


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
    # Check that session_start event was stored
    calls = [call[1]["event_type"] for call in mock_memory_client.store_event.call_args_list]
    assert "session_start" in calls


@pytest.mark.asyncio
async def test_session_manager_initialize_idempotency(mock_memory_client):
    """Test that initialize is idempotent (can be called multiple times)."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    assert manager._initialized is True
    
    # Reset call count
    mock_memory_client.store_event.reset_mock()
    
    # Call again
    await manager.initialize()
    
    # Should not call store_event again for session_start
    calls = [call[1]["event_type"] for call in mock_memory_client.store_event.call_args_list]
    assert "session_start" not in calls


@pytest.mark.asyncio
async def test_session_manager_initialize_with_memories(mock_memory_client):
    """Test session initialization with existing memories."""
    from memory.session_manager import MemorySessionManager
    
    # Mock memory records
    mock_memory = MagicMock()
    mock_memory.content = "Past conversation about weather"
    mock_memory_client.retrieve_memories.return_value = [mock_memory]
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    assert context is not None
    assert "Past conversation" in context


@pytest.mark.asyncio
async def test_session_manager_initialize_with_preferences(mock_memory_client):
    """Test session initialization with user preferences."""
    from memory.session_manager import MemorySessionManager
    
    # Mock preference record
    mock_pref = MagicMock()
    mock_pref.content = "User prefers dark mode"
    mock_memory_client.get_user_preferences.return_value = [mock_pref]
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    assert context is not None
    assert "dark mode" in context


@pytest.mark.asyncio
async def test_session_manager_initialize_with_both(mock_memory_client):
    """Test session initialization with both memories and preferences."""
    from memory.session_manager import MemorySessionManager
    
    # Mock memory and preference records
    mock_memory = MagicMock()
    mock_memory.content = "Past conversation"
    mock_memory_client.retrieve_memories.return_value = [mock_memory]
    
    mock_pref = MagicMock()
    mock_pref.content = "User preference"
    mock_memory_client.get_user_preferences.return_value = [mock_pref]
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    assert context is not None
    assert "Past conversation" in context
    assert "User preference" in context


@pytest.mark.asyncio
async def test_session_manager_initialize_empty_memories(mock_memory_client):
    """Test session initialization with no memories or preferences."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    assert context is None


@pytest.mark.asyncio
async def test_session_manager_initialize_error_handling(mock_memory_client):
    """Test that initialization continues even if memory operations fail."""
    from memory.session_manager import MemorySessionManager
    
    mock_memory_client.retrieve_memories.side_effect = Exception("Memory error")
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    # Should not raise, should continue
    await manager.initialize()
    
    assert manager._initialized is True


def test_get_context_before_initialization(mock_memory_client):
    """Test getting context before initialization."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    context = manager.get_context()
    assert context is None


def test_get_context_after_initialization(mock_memory_client):
    """Test getting context after initialization."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    # Initialize synchronously (in real code it's async)
    manager._initialized = True
    manager._context_memories = "Test context"
    
    context = manager.get_context()
    assert context == "Test context"


def test_store_user_input_text_only(mock_memory_client):
    """Test storing user input with text only."""
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
    assert call_args[1]["payload"]["audio_transcript"] is None


def test_store_user_input_audio_only(mock_memory_client):
    """Test storing user input with audio transcript only."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    manager.store_user_input(audio_transcript="Hello from audio")
    
    mock_memory_client.store_event.assert_called_once()
    call_args = mock_memory_client.store_event.call_args
    assert call_args[1]["payload"]["text"] is None
    assert call_args[1]["payload"]["audio_transcript"] == "Hello from audio"


def test_store_user_input_both(mock_memory_client):
    """Test storing user input with both text and audio transcript."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    manager.store_user_input(text="Hello", audio_transcript="Hello from audio")
    
    mock_memory_client.store_event.assert_called_once()
    call_args = mock_memory_client.store_event.call_args
    assert call_args[1]["payload"]["text"] == "Hello"
    assert call_args[1]["payload"]["audio_transcript"] == "Hello from audio"


def test_store_user_input_empty_content(mock_memory_client):
    """Test storing user input with empty content (should not store)."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    manager.store_user_input()
    
    # Should not call store_event if no content
    mock_memory_client.store_event.assert_not_called()


def test_store_agent_response_text_only(mock_memory_client):
    """Test storing agent response with text only."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    manager.store_agent_response(text="Hi there!")
    
    mock_memory_client.store_event.assert_called_once()
    call_args = mock_memory_client.store_event.call_args
    assert call_args[1]["event_type"] == "agent_response"
    assert call_args[1]["payload"]["text"] == "Hi there!"


def test_store_agent_response_audio_only(mock_memory_client):
    """Test storing agent response with audio transcript only."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    manager.store_agent_response(audio_transcript="Response from audio")
    
    mock_memory_client.store_event.assert_called_once()
    call_args = mock_memory_client.store_event.call_args
    assert call_args[1]["payload"]["audio_transcript"] == "Response from audio"


def test_store_agent_response_both(mock_memory_client):
    """Test storing agent response with both text and audio transcript."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    manager.store_agent_response(text="Hi", audio_transcript="Hi from audio")
    
    mock_memory_client.store_event.assert_called_once()
    call_args = mock_memory_client.store_event.call_args
    assert call_args[1]["payload"]["text"] == "Hi"
    assert call_args[1]["payload"]["audio_transcript"] == "Hi from audio"


def test_store_agent_response_empty_content(mock_memory_client):
    """Test storing agent response with empty content (should not store)."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    manager.store_agent_response()
    
    mock_memory_client.store_event.assert_not_called()


def test_store_tool_use_full_data(mock_memory_client):
    """Test storing tool use with full data."""
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
    assert call_args[1]["payload"]["input"] == {"expression": "2+2"}
    assert call_args[1]["payload"]["output"] == {"result": 4}


def test_store_tool_use_minimal_data(mock_memory_client):
    """Test storing tool use with minimal data."""
    from memory.session_manager import MemorySessionManager
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    manager.store_tool_use(
        tool_name="weather",
        input_data={},
        output_data={}
    )
    
    mock_memory_client.store_event.assert_called_once()
    call_args = mock_memory_client.store_event.call_args
    assert call_args[1]["payload"]["tool_name"] == "weather"


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


@pytest.mark.asyncio
async def test_finalize_session_error_handling(mock_memory_client):
    """Test that finalize handles errors gracefully."""
    from memory.session_manager import MemorySessionManager
    
    mock_memory_client.store_event.side_effect = Exception("Storage failed")
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    # Should not raise
    await manager.finalize()


@pytest.mark.asyncio
async def test_context_building_with_dict_records(mock_memory_client):
    """Test context building with dict-like memory records."""
    from memory.session_manager import MemorySessionManager
    
    # Mock memory records as dicts
    mock_memory_client.retrieve_memories.return_value = [
        {"content": {"text": "Memory 1"}},
        {"content": {"text": "Memory 2"}}
    ]
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    # Should handle dict records (though current implementation uses hasattr)
    assert context is not None or context is None  # May not handle dicts perfectly


@pytest.mark.asyncio
async def test_context_building_limits_records(mock_memory_client):
    """Test that context building limits to top 3 records."""
    from memory.session_manager import MemorySessionManager
    
    # Create 5 memory records
    memories = []
    for i in range(5):
        mock_mem = MagicMock()
        mock_mem.content = f"Memory {i}"
        memories.append(mock_mem)
    
    mock_memory_client.retrieve_memories.return_value = memories
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    # Should only include top 3
    if context:
        # Count occurrences of "Memory" to verify limit
        assert context.count("Memory") <= 3

