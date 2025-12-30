"""Tests for memory client."""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import os
from botocore.exceptions import ClientError


@pytest.fixture
def mock_memory_available():
    """Mock memory availability."""
    with patch('memory.client.MEMORY_AVAILABLE', True):
        with patch('memory.client.AgentCoreMemoryClient') as mock_client_class:
            yield mock_client_class


@pytest.fixture
def mock_bedrock_client():
    """Mock boto3 bedrock-agentcore client."""
    with patch('memory.client.boto3.client') as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.return_value = mock_client
        yield mock_client


@pytest.fixture
def sample_memory_record():
    """Sample memory record."""
    return {
        "memoryRecordId": "record-123",
        "namespace": "/summaries/user_example_com/session-123",
        "content": {
            "text": "Test memory content"
        }
    }


@pytest.fixture
def memory_env_vars(monkeypatch):
    """
    Set up memory-related environment variables from .env file.
    
    Loads AGENTCORE_MEMORY_REGION and AWS_REGION from .env file if available,
    otherwise uses defaults. This ensures tests use the same region configuration
    as the application.
    """
    import os
    from pathlib import Path
    from dotenv import load_dotenv
    
    # Load .env file if it exists
    project_root = Path(__file__).parent.parent.parent
    env_file = project_root / '.env'
    if env_file.exists():
        load_dotenv(env_file, override=False)
    
    # Get values from environment (loaded from .env) or use defaults
    env_vars = {
        "AGENTCORE_MEMORY_REGION": os.getenv("AGENTCORE_MEMORY_REGION", "us-west-2"),
        "AWS_REGION": os.getenv("AWS_REGION", "us-west-2"),
    }
    
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


def test_memory_client_initialization(memory_env_vars):
    """Test memory client initialization with explicit region overrides env."""
    from memory.client import MemoryClient
    
    # Test with explicit region (overrides env)
    client = MemoryClient(region="us-west-2", memory_id="test-memory-id")
    assert client.region == "us-west-2"
    assert client.memory_id == "test-memory-id"
    
    # Test without explicit region (uses env)
    client2 = MemoryClient(memory_id="test-memory-id-2")
    assert client2.region == "us-west-2"  # From AGENTCORE_MEMORY_REGION env var
    assert client2.memory_id == "test-memory-id-2"


def test_memory_client_initialization_from_env(memory_env_vars):
    """Test memory client initialization from environment variables."""
    from memory.client import MemoryClient
    
    with patch.dict(os.environ, {"AGENTCORE_MEMORY_ID": "env-memory-id"}):
        client = MemoryClient()
        assert client.region == "us-west-2"  # From AGENTCORE_MEMORY_REGION
        assert client.memory_id == "env-memory-id"


def test_memory_client_initialization_fallback_to_aws_region(monkeypatch):
    """Test memory client falls back to AWS_REGION when AGENTCORE_MEMORY_REGION not set."""
    from memory.client import MemoryClient
    
    # Clear AGENTCORE_MEMORY_REGION, set AWS_REGION
    monkeypatch.delenv("AGENTCORE_MEMORY_REGION", raising=False)
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    
    client = MemoryClient()
    assert client.region == "eu-west-1"


@patch('memory.client.MEMORY_AVAILABLE', False)
def test_memory_client_without_memory(monkeypatch):
    """Test memory client when memory is not available."""
    from memory.client import MemoryClient
    
    # Clear environment variables to ensure memory_id is None
    monkeypatch.delenv("AGENTCORE_MEMORY_ID", raising=False)
    monkeypatch.delenv("AGENTCORE_MEMORY_ARN", raising=False)
    
    client = MemoryClient()
    # Should not raise error, but operations will fail gracefully
    assert client.memory_id is None


# Actor ID Sanitization Tests
def test_sanitize_actor_id_email(memory_env_vars):
    """Test actor ID sanitization with email address."""
    from memory.client import MemoryClient
    
    client = MemoryClient()
    assert client._sanitize_actor_id("user@example.com") == "user_example_com"
    assert client.region == "us-west-2"  # From env


def test_sanitize_actor_id_with_dots(memory_env_vars):
    """Test actor ID sanitization with dots."""
    from memory.client import MemoryClient
    
    client = MemoryClient()
    assert client._sanitize_actor_id("user.name@example.com") == "user_name_example_com"
    assert client.region == "us-west-2"  # From env


def test_sanitize_actor_id_starts_with_non_alnum(memory_env_vars):
    """Test actor ID sanitization starting with non-alphanumeric."""
    from memory.client import MemoryClient
    
    client = MemoryClient()
    assert client._sanitize_actor_id("_user@example.com") == "user__user_example_com"
    assert client.region == "us-west-2"  # From env


def test_sanitize_actor_id_already_valid(memory_env_vars):
    """Test actor ID that's already valid."""
    from memory.client import MemoryClient
    
    client = MemoryClient()
    assert client._sanitize_actor_id("valid_user_123") == "valid_user_123"
    assert client.region == "us-west-2"  # From env


# Memory Resource Creation Tests
@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.MemoryControlPlaneClient')
@patch('memory.client.AgentCoreMemoryClient')
def test_create_memory_resource_existing(mock_client_class, mock_control_plane_class, mock_env_vars):
    """Test memory resource creation with existing memory ID."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_control_plane = MagicMock()
    mock_control_plane.get_memory.return_value = {
        "memoryId": "existing-id",
        "strategies": [
            {"type": "summaryMemoryStrategy"},
            {"type": "userPreferenceMemoryStrategy"}
        ]
    }
    mock_client_class.return_value = mock_client
    mock_control_plane_class.return_value = mock_control_plane
    
    client = MemoryClient(memory_id="existing-id")
    result = client.create_memory_resource()
    
    assert result is not None
    assert result["memoryId"] == "existing-id"
    mock_control_plane.get_memory.assert_called_once_with(memory_id="existing-id")


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.MemoryControlPlaneClient')
@patch('memory.client.AgentCoreMemoryClient')
def test_create_memory_resource_no_strategies(mock_client_class, mock_control_plane_class, mock_env_vars):
    """Test memory resource with no strategies (warning case)."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_control_plane = MagicMock()
    mock_control_plane.get_memory.return_value = {
        "memoryId": "existing-id",
        "strategies": []
    }
    mock_client_class.return_value = mock_client
    mock_control_plane_class.return_value = mock_control_plane
    
    client = MemoryClient(memory_id="existing-id")
    result = client.create_memory_resource()
    
    assert result is not None
    # Warning should be logged but function should continue


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.MemoryControlPlaneClient')
@patch('memory.client.AgentCoreMemoryClient')
def test_create_memory_resource_new(mock_client_class, mock_control_plane_class, mock_env_vars):
    """Test creating new memory resource."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_control_plane = MagicMock()
    mock_control_plane.get_memory.side_effect = Exception("Not found")
    mock_client.create_memory.return_value = {"memoryId": "new-id"}
    mock_client_class.return_value = mock_client
    mock_control_plane_class.return_value = mock_control_plane
    
    client = MemoryClient()
    result = client.create_memory_resource()
    
    assert result is not None
    assert result["memoryId"] == "new-id"
    assert client.memory_id == "new-id"
    mock_client.create_memory.assert_called_once()


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.MemoryControlPlaneClient')
@patch('memory.client.AgentCoreMemoryClient')
def test_create_memory_resource_error(mock_client_class, mock_control_plane_class, mock_env_vars):
    """Test memory resource creation error handling."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_control_plane = MagicMock()
    mock_control_plane.get_memory.side_effect = Exception("Not found")
    mock_client.create_memory.side_effect = Exception("Creation failed")
    mock_client_class.return_value = mock_client
    mock_control_plane_class.return_value = mock_control_plane
    
    client = MemoryClient()
    
    with pytest.raises(Exception, match="Creation failed"):
        client.create_memory_resource()


# Event Storage Tests
@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.AgentCoreMemoryClient')
def test_store_event_user_input(mock_client_class, mock_env_vars):
    """Test storing user input event."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    client = MemoryClient(memory_id="test-id")
    client._client = mock_client
    
    client.store_event(
        actor_id="user@example.com",
        session_id="session-123",
        event_type="user_input",
        payload={"text": "Hello"}
    )
    
    mock_client.create_event.assert_called_once()
    call_args = mock_client.create_event.call_args
    assert call_args[1]["actor_id"] == "user_example_com"
    assert call_args[1]["session_id"] == "session-123"
    assert call_args[1]["messages"] == [("Hello", "USER")]


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.AgentCoreMemoryClient')
def test_store_event_agent_response(mock_client_class, mock_env_vars):
    """Test storing agent response event."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    client = MemoryClient(memory_id="test-id")
    client._client = mock_client
    
    client.store_event(
        actor_id="user@example.com",
        session_id="session-123",
        event_type="agent_response",
        payload={"text": "Hi there!"}
    )
    
    call_args = mock_client.create_event.call_args
    assert call_args[1]["messages"] == [("Hi there!", "ASSISTANT")]


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.AgentCoreMemoryClient')
def test_store_event_tool_use(mock_client_class, mock_env_vars):
    """Test storing tool use event."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    client = MemoryClient(memory_id="test-id")
    client._client = mock_client
    
    client.store_event(
        actor_id="user@example.com",
        session_id="session-123",
        event_type="tool_use",
        payload={"text": "Calculator result: 4"}
    )
    
    call_args = mock_client.create_event.call_args
    assert call_args[1]["messages"] == [("Calculator result: 4", "TOOL")]


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.AgentCoreMemoryClient')
def test_store_event_payload_extraction(mock_client_class, mock_env_vars):
    """Test event storage with different payload formats."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    client = MemoryClient(memory_id="test-id")
    client._client = mock_client
    
    # Test with content field
    client.store_event(
        actor_id="user@example.com",
        session_id="session-123",
        event_type="user_input",
        payload={"content": "Hello from content"}
    )
    
    call_args = mock_client.create_event.call_args
    assert call_args[1]["messages"] == [("Hello from content", "USER")]
    
    # Test with audio_transcript
    client.store_event(
        actor_id="user@example.com",
        session_id="session-123",
        event_type="user_input",
        payload={"audio_transcript": "Hello from audio"}
    )
    
    call_args = mock_client.create_event.call_args
    assert call_args[1]["messages"] == [("Hello from audio", "USER")]


@patch('memory.client.MEMORY_AVAILABLE', True)
def test_store_event_empty_text(mock_env_vars):
    """Test storing event with empty text content (should skip)."""
    from memory.client import MemoryClient
    
    client = MemoryClient(memory_id="test-id")
    
    # Mock the client properly
    mock_client = MagicMock()
    client._client = mock_client
    
    # Test with whitespace-only text - should be stripped to empty and skipped
    client.store_event(
        actor_id="user@example.com",
        session_id="session-123",
        event_type="user_input",
        payload={"text": "   "}  # Whitespace only - should be stripped to empty and skipped
    )
    
    # Should not call create_event because text is empty after strip
    mock_client.create_event.assert_not_called()


@patch('memory.client.MEMORY_AVAILABLE', True)
def test_store_event_no_memory_id(monkeypatch):
    """Test storing event without memory ID."""
    from memory.client import MemoryClient
    
    # Clear environment variables to ensure memory_id is None
    monkeypatch.delenv("AGENTCORE_MEMORY_ID", raising=False)
    monkeypatch.delenv("AGENTCORE_MEMORY_ARN", raising=False)
    
    client = MemoryClient()
    
    # Mock the client (though it shouldn't be called)
    mock_client = MagicMock()
    client._client = mock_client
    
    client.store_event(
        actor_id="user@example.com",
        session_id="session-123",
        event_type="user_input",
        payload={"text": "Hello"}
    )
    
    # Should not call create_event because memory_id is None
    mock_client.create_event.assert_not_called()


@patch('memory.client.MEMORY_AVAILABLE', False)
def test_store_event_memory_not_available():
    """Test storing event when memory is not available."""
    from memory.client import MemoryClient
    
    client = MemoryClient(memory_id="test-id")
    
    with patch.object(client, '_get_client') as mock_get_client:
        client.store_event(
            actor_id="user@example.com",
            session_id="session-123",
            event_type="user_input",
            payload={"text": "Hello"}
        )
        
        mock_get_client.assert_not_called()


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.AgentCoreMemoryClient')
def test_store_event_error_handling(mock_client_class, mock_env_vars):
    """Test error handling during event storage."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_client.create_event.side_effect = Exception("Storage failed")
    mock_client_class.return_value = mock_client
    
    client = MemoryClient(memory_id="test-id")
    client._client = mock_client
    
    # Should not raise, just log error
    client.store_event(
        actor_id="user@example.com",
        session_id="session-123",
        event_type="user_input",
        payload={"text": "Hello"}
    )


# Memory Retrieval Tests
@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.AgentCoreMemoryClient')
def test_retrieve_memories_semantic(mock_client_class, mock_env_vars):
    """Test retrieving memories using semantic search."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_client.retrieve_memory_records.return_value = {
        "memoryRecords": [{"content": {"text": "Test memory"}}]
    }
    mock_client_class.return_value = mock_client
    
    client = MemoryClient(memory_id="test-id")
    client._client = mock_client
    
    memories = client.retrieve_memories(
        actor_id="user@example.com",
        query="test query",
        top_k=5
    )
    
    assert len(memories) == 1
    mock_client.retrieve_memory_records.assert_called_once()


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.boto3.client')
def test_retrieve_memories_summaries(mock_boto3, mock_env_vars):
    """Test retrieving summaries using ListMemoryRecords."""
    from memory.client import MemoryClient
    
    mock_bedrock = MagicMock()
    mock_bedrock.list_memory_records.return_value = {
        "memoryRecordSummaries": [
            {"content": {"text": "Summary 1"}},
            {"content": {"text": "Summary 2"}}
        ]
    }
    mock_boto3.return_value = mock_bedrock
    
    client = MemoryClient(memory_id="test-id")
    
    memories = client.retrieve_memories(
        actor_id="user@example.com",
        memory_type="summaries",
        top_k=5
    )
    
    assert len(memories) == 2
    mock_bedrock.list_memory_records.assert_called()


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.boto3.client')
def test_retrieve_memories_summaries_pagination(mock_boto3, mock_env_vars):
    """Test retrieving summaries with pagination."""
    from memory.client import MemoryClient
    
    mock_bedrock = MagicMock()
    # First page
    mock_bedrock.list_memory_records.side_effect = [
        {
            "memoryRecordSummaries": [{"content": {"text": "Summary 1"}}],
            "nextToken": "token-123"
        },
        {
            "memoryRecordSummaries": [{"content": {"text": "Summary 2"}}]
        }
    ]
    mock_boto3.return_value = mock_bedrock
    
    client = MemoryClient(memory_id="test-id")
    
    memories = client.retrieve_memories(
        actor_id="user@example.com",
        memory_type="summaries",
        top_k=5
    )
    
    assert len(memories) == 2
    assert mock_bedrock.list_memory_records.call_count == 2


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.boto3.client')
def test_retrieve_memories_preferences(mock_boto3, mock_env_vars):
    """Test retrieving preferences."""
    from memory.client import MemoryClient
    
    mock_bedrock = MagicMock()
    mock_bedrock.list_memory_records.return_value = {
        "memoryRecordSummaries": [{"content": {"text": "Preference 1"}}]
    }
    mock_boto3.return_value = mock_bedrock
    
    client = MemoryClient(memory_id="test-id")
    
    memories = client.retrieve_memories(
        actor_id="user@example.com",
        memory_type="preferences",
        top_k=5
    )
    
    assert len(memories) == 1


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.AgentCoreMemoryClient')
def test_retrieve_memories_no_query(mock_client_class, mock_env_vars):
    """Test retrieving memories without query (should return empty for semantic)."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    client = MemoryClient(memory_id="test-id")
    client._client = mock_client
    
    memories = client.retrieve_memories(
        actor_id="user@example.com",
        query=None,
        top_k=5
    )
    
    assert memories == []
    mock_client.retrieve_memory_records.assert_not_called()


def test_retrieve_memories_no_memory_id():
    """Test retrieving memories without memory ID."""
    from memory.client import MemoryClient
    
    client = MemoryClient()
    
    memories = client.retrieve_memories(
        actor_id="user@example.com",
        query="test",
        top_k=5
    )
    
    assert memories == []


@patch('memory.client.MEMORY_AVAILABLE', False)
def test_retrieve_memories_not_available():
    """Test retrieving memories when memory is not available."""
    from memory.client import MemoryClient
    
    client = MemoryClient(memory_id="test-id")
    
    memories = client.retrieve_memories(
        actor_id="user@example.com",
        query="test",
        top_k=5
    )
    
    assert memories == []


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.boto3.client')
def test_retrieve_summaries_list_error(mock_boto3, mock_env_vars):
    """Test error handling in _retrieve_summaries_list."""
    from memory.client import MemoryClient
    
    mock_bedrock = MagicMock()
    mock_bedrock.list_memory_records.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
        "ListMemoryRecords"
    )
    mock_boto3.return_value = mock_bedrock
    
    client = MemoryClient(memory_id="test-id")
    
    memories = client._retrieve_summaries_list(
        actor_id="user@example.com",
        sanitized_actor_id="user_example_com",
        namespace_prefix=None,
        top_k=5
    )
    
    assert memories == []


# Session Summary Tests
@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.boto3.client')
def test_get_session_summary_exact_namespace(mock_boto3, mock_env_vars):
    """Test getting session summary from exact namespace."""
    from memory.client import MemoryClient
    
    mock_bedrock = MagicMock()
    mock_bedrock.list_memory_records.return_value = {
        "memoryRecordSummaries": [{
            "memoryRecordId": "record-123",
            "content": {"text": "Session summary"}
        }]
    }
    mock_boto3.return_value = mock_bedrock
    
    client = MemoryClient(memory_id="test-id")
    
    summary = client.get_session_summary("user@example.com", "session-123")
    
    assert summary is not None
    assert summary["content"]["text"] == "Session summary"


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.boto3.client')
def test_get_session_summary_parent_namespace_fallback(mock_boto3, mock_env_vars):
    """Test getting session summary from parent namespace fallback."""
    from memory.client import MemoryClient
    
    mock_bedrock = MagicMock()
    # Exact namespace returns empty
    mock_bedrock.list_memory_records.side_effect = [
        {"memoryRecordSummaries": []},  # Exact namespace
        {  # Parent namespace
            "memoryRecordSummaries": [{
                "memoryRecordId": "record-123",
                "namespace": "/summaries/user_example_com/session-123",
                "content": {"text": "Session summary"}
            }]
        }
    ]
    mock_boto3.return_value = mock_bedrock
    
    client = MemoryClient(memory_id="test-id")
    
    summary = client.get_session_summary("user@example.com", "session-123")
    
    assert summary is not None
    assert "session-123" in summary.get("namespace", "")


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.boto3.client')
@patch('memory.client.AgentCoreMemoryClient')
def test_get_session_summary_semantic_fallback(mock_client_class, mock_boto3, mock_env_vars):
    """Test getting session summary via semantic search fallback."""
    from memory.client import MemoryClient
    
    mock_bedrock = MagicMock()
    mock_bedrock.list_memory_records.side_effect = Exception("List failed")
    
    mock_client = MagicMock()
    mock_client.retrieve_memory_records.return_value = {
        "memoryRecords": [{
            "content": {"text": "Session summary from search"}
        }]
    }
    mock_client_class.return_value = mock_client
    mock_boto3.return_value = mock_bedrock
    
    client = MemoryClient(memory_id="test-id")
    client._client = mock_client
    
    summary = client.get_session_summary("user@example.com", "session-123")
    
    assert summary is not None
    assert summary["content"]["text"] == "Session summary from search"


def test_get_session_summary_no_memory_id():
    """Test getting session summary without memory ID."""
    from memory.client import MemoryClient
    
    client = MemoryClient()
    
    summary = client.get_session_summary("user@example.com", "session-123")
    
    assert summary is None


# User Preferences Tests
@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.boto3.client')
def test_get_user_preferences_list(mock_boto3, mock_env_vars):
    """Test getting user preferences using ListMemoryRecords."""
    from memory.client import MemoryClient
    
    mock_bedrock = MagicMock()
    mock_bedrock.list_memory_records.return_value = {
        "memoryRecordSummaries": [{
            "content": {"text": "User prefers dark mode"}
        }]
    }
    mock_boto3.return_value = mock_bedrock
    
    client = MemoryClient(memory_id="test-id")
    
    preferences = client.get_user_preferences("user@example.com")
    
    assert len(preferences) == 1


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.boto3.client')
@patch('memory.client.AgentCoreMemoryClient')
def test_get_user_preferences_semantic_fallback(mock_client_class, mock_boto3, mock_env_vars):
    """Test getting user preferences with semantic search fallback."""
    from memory.client import MemoryClient
    
    mock_bedrock = MagicMock()
    mock_bedrock.list_memory_records.return_value = {
        "memoryRecordSummaries": []
    }
    
    mock_client = MagicMock()
    mock_client.retrieve_memory_records.return_value = {
        "memoryRecords": [{
            "content": {"text": "User preference from search"}
        }]
    }
    mock_client_class.return_value = mock_client
    mock_boto3.return_value = mock_bedrock
    
    client = MemoryClient(memory_id="test-id")
    client._client = mock_client
    
    preferences = client.get_user_preferences("user@example.com")
    
    assert len(preferences) == 1


# List Sessions Tests
@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.boto3.client')
def test_list_sessions(mock_boto3, mock_env_vars):
    """Test listing sessions."""
    from memory.client import MemoryClient
    
    mock_bedrock = MagicMock()
    # First call: list_memory_records
    mock_bedrock.list_memory_records.return_value = {
        "memoryRecordSummaries": [{
            "memoryRecordId": "record-123"
        }]
    }
    # Second call: get_memory_record
    mock_bedrock.get_memory_record.return_value = {
        "memoryRecord": {
            "namespaces": ["/summaries/user_example_com/session-123"],
            "content": {"text": "Session summary"}
        }
    }
    mock_boto3.return_value = mock_bedrock
    
    client = MemoryClient(memory_id="test-id")
    
    sessions = client.list_sessions("user@example.com", top_k=10)
    
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "session-123"


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.boto3.client')
@patch('memory.client.AgentCoreMemoryClient')
def test_list_sessions_semantic_fallback(mock_client_class, mock_boto3, mock_env_vars):
    """Test listing sessions with semantic search fallback."""
    from memory.client import MemoryClient
    
    mock_bedrock = MagicMock()
    mock_bedrock.list_memory_records.side_effect = Exception("List failed")
    
    mock_client = MagicMock()
    mock_client.retrieve_memory_records.return_value = {
        "memoryRecords": [{
            "namespace": "/summaries/user_example_com/session-456",
            "content": {"text": "Another session"}
        }]
    }
    mock_client_class.return_value = mock_client
    mock_boto3.return_value = mock_bedrock
    
    client = MemoryClient(memory_id="test-id")
    client._client = mock_client
    
    sessions = client.list_sessions("user@example.com", top_k=10)
    
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "session-456"


def test_list_sessions_no_memory_id():
    """Test listing sessions without memory ID."""
    from memory.client import MemoryClient
    
    client = MemoryClient()
    
    sessions = client.list_sessions("user@example.com")
    
    assert sessions == []


@patch('memory.client.MEMORY_AVAILABLE', False)
def test_list_sessions_not_available():
    """Test listing sessions when memory is not available."""
    from memory.client import MemoryClient
    
    client = MemoryClient(memory_id="test-id")
    
    sessions = client.list_sessions("user@example.com")
    
    assert sessions == []


# Error Handling Tests
@patch('memory.client.MEMORY_AVAILABLE', True)
def test_get_client_not_available():
    """Test _get_client when memory is not available."""
    from memory.client import MemoryClient
    
    with patch('memory.client.MEMORY_AVAILABLE', False):
        client = MemoryClient(memory_id="test-id")
        
        with pytest.raises(RuntimeError, match="AgentCore Memory is not available"):
            client._get_client()


@patch('memory.client.MEMORY_AVAILABLE', True)
def test_get_control_plane_client_not_available():
    """Test _get_control_plane_client when memory is not available."""
    from memory.client import MemoryClient
    
    with patch('memory.client.MEMORY_AVAILABLE', False):
        client = MemoryClient(memory_id="test-id")
        
        with pytest.raises(RuntimeError, match="AgentCore Memory is not available"):
            client._get_control_plane_client()


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.AgentCoreMemoryClient')
def test_retrieve_memories_error_handling(mock_client_class, mock_env_vars):
    """Test error handling in retrieve_memories."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_client.retrieve_memory_records.side_effect = Exception("Retrieval failed")
    mock_client_class.return_value = mock_client
    
    client = MemoryClient(memory_id="test-id")
    client._client = mock_client
    
    memories = client.retrieve_memories(
        actor_id="user@example.com",
        query="test",
        top_k=5
    )
    
    assert memories == []

