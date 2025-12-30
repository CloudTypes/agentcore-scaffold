"""Tests for memory client."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import os


@pytest.fixture
def mock_memory_available():
    """Mock memory availability."""
    with patch('memory.client.MEMORY_AVAILABLE', True):
        with patch('memory.client.AgentCoreMemoryClient') as mock_client_class:
            yield mock_client_class


def test_memory_client_initialization():
    """Test memory client initialization."""
    from memory.client import MemoryClient
    
    client = MemoryClient(region="us-east-1", memory_id="test-memory-id")
    assert client.region == "us-east-1"
    assert client.memory_id == "test-memory-id"


@patch('memory.client.MEMORY_AVAILABLE', False)
def test_memory_client_without_memory():
    """Test memory client when memory is not available."""
    from memory.client import MemoryClient
    
    client = MemoryClient()
    # Should not raise error, but operations will fail gracefully
    assert client.memory_id is None


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.AgentCoreMemoryClient')
def test_create_memory_resource(mock_client_class, mock_env_vars):
    """Test memory resource creation."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_client.get_memory.return_value = {"memoryId": "existing-id"}
    mock_client.create_memory.return_value = {"memoryId": "new-id"}
    mock_client_class.return_value = mock_client
    
    client = MemoryClient(region="us-east-1", memory_id="existing-id")
    result = client.create_memory_resource()
    
    assert result is not None


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.AgentCoreMemoryClient')
@patch('memory.client.Event')
def test_store_event(mock_event, mock_client_class, mock_env_vars):
    """Test storing events."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_event_instance = MagicMock()
    mock_event.return_value = mock_event_instance
    
    client = MemoryClient(region="us-east-1", memory_id="test-id")
    client._client = mock_client
    
    client.store_event(
        actor_id="user@example.com",
        session_id="session-123",
        event_type="user_input",
        payload={"text": "Hello"}
    )
    
    mock_client.create_event.assert_called_once()


@patch('memory.client.MEMORY_AVAILABLE', True)
@patch('memory.client.AgentCoreMemoryClient')
def test_retrieve_memories(mock_client_class, mock_env_vars):
    """Test retrieving memories."""
    from memory.client import MemoryClient
    
    mock_client = MagicMock()
    mock_record = MagicMock()
    mock_record.content = "Test memory"
    mock_client.retrieve_memory_records.return_value = [mock_record]
    mock_client_class.return_value = mock_client
    
    client = MemoryClient(region="us-east-1", memory_id="test-id")
    client._client = mock_client
    
    memories = client.retrieve_memories(
        actor_id="user@example.com",
        query="test query",
        top_k=5
    )
    
    assert len(memories) == 1
    mock_client.retrieve_memory_records.assert_called_once()

