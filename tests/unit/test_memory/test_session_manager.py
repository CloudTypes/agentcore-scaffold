"""Tests for memory session manager."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock


@pytest.fixture
def mock_memory_client():
    """Mock memory client."""
    client = MagicMock()
    client.list_sessions = MagicMock(return_value=[])
    client.get_session_summary = MagicMock(return_value=None)
    client.get_user_preferences = MagicMock(return_value=[])
    client.store_event = MagicMock()
    return client


@pytest.fixture
def mock_config():
    """Mock config system."""
    config = MagicMock()
    config.get_config_value = MagicMock(return_value="3")
    return config


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
@patch('memory.session_manager.get_config')
async def test_session_manager_initialize(mock_get_config, mock_memory_client, mock_config):
    """Test session initialization."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    
    assert manager._initialized is True
    mock_memory_client.list_sessions.assert_called_once()
    mock_memory_client.store_event.assert_called()
    # Check that session_start event was stored
    # store_event is called with keyword args: actor_id, session_id, event_type, payload
    calls = [call.kwargs.get("event_type") or call[1].get("event_type") for call in mock_memory_client.store_event.call_args_list]
    assert "session_start" in calls


@pytest.mark.asyncio
@patch('memory.session_manager.get_config')
async def test_session_manager_initialize_idempotency(mock_get_config, mock_memory_client, mock_config):
    """Test that initialize is idempotent (can be called multiple times)."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    assert manager._initialized is True
    
    # Reset call count
    mock_memory_client.store_event.reset_mock()
    mock_memory_client.list_sessions.reset_mock()
    
    # Call again
    await manager.initialize()
    
    # Should not call list_sessions or store_event again
    mock_memory_client.list_sessions.assert_not_called()
    calls = [call.kwargs.get("event_type") or call[1].get("event_type") for call in mock_memory_client.store_event.call_args_list]
    assert "session_start" not in calls


@pytest.mark.asyncio
@patch('memory.session_manager.get_config')
async def test_session_manager_initialize_with_past_sessions(mock_get_config, mock_memory_client, mock_config):
    """Test session initialization with past session summaries."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    
    # Mock past sessions
    past_sessions = [
        {"session_id": "session-1", "summary": "Summary 1"},
        {"session_id": "session-2", "summary": "Summary 2"}
    ]
    mock_memory_client.list_sessions.return_value = past_sessions
    
    # Mock session summaries
    mock_memory_client.get_session_summary.side_effect = [
        {"content": {"text": "Past conversation about weather"}, "createdAt": "2024-01-01"},
        {"content": {"text": "Past conversation about coding"}, "createdAt": "2024-01-02"}
    ]
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id="current-session"  # Different from past sessions
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    assert context is not None
    assert "Here is relevant information from previous conversations" in context
    assert "weather" in context or "coding" in context
    assert "[Memory 1]" in context
    assert "[Memory 2]" in context


@pytest.mark.asyncio
@patch('memory.session_manager.get_config')
async def test_session_manager_initialize_with_preferences(mock_get_config, mock_memory_client, mock_config):
    """Test session initialization with user preferences."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    
    # Mock preference record
    mock_pref = {"content": {"text": "User prefers dark mode"}}
    mock_memory_client.get_user_preferences.return_value = [mock_pref]
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    assert context is not None
    assert "User Preferences" in context
    assert "dark mode" in context


@pytest.mark.asyncio
@patch('memory.session_manager.get_config')
async def test_session_manager_initialize_with_both(mock_get_config, mock_memory_client, mock_config):
    """Test session initialization with both past sessions and preferences."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    
    # Mock past sessions
    past_sessions = [{"session_id": "session-1", "summary": "Summary 1"}]
    mock_memory_client.list_sessions.return_value = past_sessions
    mock_memory_client.get_session_summary.return_value = {
        "content": {"text": "Past conversation about weather"}
    }
    
    # Mock preferences
    mock_pref = {"content": {"text": "User preference"}}
    mock_memory_client.get_user_preferences.return_value = [mock_pref]
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id="current-session"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    assert context is not None
    assert "Here is relevant information from previous conversations" in context
    assert "weather" in context
    assert "User Preferences" in context
    assert "User preference" in context
    assert "Use this information to provide personalized responses" in context


@pytest.mark.asyncio
@patch('memory.session_manager.get_config')
async def test_session_manager_initialize_empty_memories(mock_get_config, mock_memory_client, mock_config):
    """Test session initialization with no past sessions or preferences."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    assert context is None


@pytest.mark.asyncio
@patch('memory.session_manager.get_config')
async def test_session_manager_initialize_error_handling(mock_get_config, mock_memory_client, mock_config):
    """Test that initialization continues even if memory operations fail."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    mock_memory_client.list_sessions.side_effect = Exception("Memory error")
    
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
    calls = [call.kwargs.get("event_type") or call[1].get("event_type") for call in mock_memory_client.store_event.call_args_list]
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
@patch('memory.session_manager.get_config')
async def test_context_building_filters_current_session(mock_get_config, mock_memory_client, mock_config):
    """Test that context building filters out the current session."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    
    current_session_id = "current-session-123"
    
    # Mock past sessions including current session
    past_sessions = [
        {"session_id": "session-1", "summary": "Summary 1"},
        {"session_id": current_session_id, "summary": "Current session"},  # Should be filtered
        {"session_id": "session-2", "summary": "Summary 2"}
    ]
    mock_memory_client.list_sessions.return_value = past_sessions
    
    # Mock session summaries
    mock_memory_client.get_session_summary.side_effect = [
        {"content": {"text": "Memory 1"}},
        {"content": {"text": "Memory 2"}}
    ]
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id=current_session_id
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    assert context is not None
    # Should not include current session
    assert current_session_id not in context or "Current session" not in context
    # Should include past sessions
    assert "Memory 1" in context or "Memory 2" in context


@pytest.mark.asyncio
@patch('memory.session_manager.get_config')
async def test_context_building_limits_to_past_sessions_count(mock_get_config, mock_memory_client, mock_config):
    """Test that context building limits to PAST_SESSIONS_COUNT (default 3)."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    mock_config.get_config_value.return_value = "3"  # Default is 3
    
    # Create 5 past sessions
    past_sessions = []
    for i in range(5):
        past_sessions.append({"session_id": f"session-{i}", "summary": f"Summary {i}"})
    
    mock_memory_client.list_sessions.return_value = past_sessions
    
    # Mock session summaries
    def mock_get_summary(actor_id, session_id):
        session_num = session_id.split("-")[1]
        return {"content": {"text": f"Memory {session_num}"}}
    
    mock_memory_client.get_session_summary.side_effect = mock_get_summary
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id="current-session"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    # Should only include top 3 (PAST_SESSIONS_COUNT)
    if context:
        # Count occurrences of "[Memory" to verify limit
        assert context.count("[Memory") <= 3


@pytest.mark.asyncio
@patch('memory.session_manager.get_config')
async def test_context_building_with_timestamps(mock_get_config, mock_memory_client, mock_config):
    """Test that context includes timestamps when available."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    
    past_sessions = [{"session_id": "session-1", "summary": "Summary 1"}]
    mock_memory_client.list_sessions.return_value = past_sessions
    
    # Mock session summary with timestamp
    mock_memory_client.get_session_summary.return_value = {
        "content": {"text": "Past conversation"},
        "createdAt": "2024-01-01T10:00:00Z",
        "updatedAt": "2024-01-01T11:00:00Z"
    }
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id="current-session"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    assert context is not None
    # Should include timestamp in format
    assert "Session: session-1" in context
    assert "2024-01-01" in context or "11:00:00" in context


@pytest.mark.asyncio
@patch('memory.session_manager.get_config')
async def test_context_building_handles_missing_summaries(mock_get_config, mock_memory_client, mock_config):
    """Test that context building handles sessions without summaries gracefully."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    
    past_sessions = [
        {"session_id": "session-1", "summary": "Summary 1"},
        {"session_id": "session-2", "summary": "Summary 2"}
    ]
    mock_memory_client.list_sessions.return_value = past_sessions
    
    # First session has summary, second doesn't
    mock_memory_client.get_session_summary.side_effect = [
        {"content": {"text": "Memory 1"}},
        None  # No summary available yet
    ]
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id="current-session"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    # Should still work with partial summaries
    assert context is not None
    assert "Memory 1" in context
    # Should only have one memory entry
    assert context.count("[Memory") == 1


@pytest.mark.asyncio
@patch('memory.session_manager.get_config')
async def test_context_building_handles_summary_retrieval_error(mock_get_config, mock_memory_client, mock_config):
    """Test that context building handles errors when retrieving individual summaries."""
    from memory.session_manager import MemorySessionManager
    
    mock_get_config.return_value = mock_config
    
    past_sessions = [
        {"session_id": "session-1", "summary": "Summary 1"},
        {"session_id": "session-2", "summary": "Summary 2"}
    ]
    mock_memory_client.list_sessions.return_value = past_sessions
    
    # First session succeeds, second fails
    mock_memory_client.get_session_summary.side_effect = [
        {"content": {"text": "Memory 1"}},
        Exception("Failed to retrieve summary")
    ]
    
    manager = MemorySessionManager(
        memory_client=mock_memory_client,
        actor_id="user@example.com",
        session_id="current-session"
    )
    
    await manager.initialize()
    
    context = manager.get_context()
    # Should still work with partial summaries
    assert context is not None
    assert "Memory 1" in context
    # Should only have one memory entry (second one failed)
    assert context.count("[Memory") == 1

