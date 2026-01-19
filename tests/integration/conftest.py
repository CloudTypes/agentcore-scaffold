"""
Shared pytest fixtures for integration tests.
"""

import pytest
import asyncio
import base64
import sys
import os
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import uvicorn
from threading import Thread

# Load .env file from project root if it exists
# This ensures integration tests use the same configuration as the application
project_root = Path(__file__).parent.parent.parent
env_file = project_root / ".env"
if env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(env_file, override=False)  # Don't override existing env vars

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from agent import app
from strands.experimental.bidi.types.events import (
    BidiConnectionStartEvent,
    BidiResponseStartEvent,
    BidiTranscriptStreamEvent,
    BidiAudioStreamEvent,
    BidiResponseCompleteEvent,
    BidiErrorEvent,
)
from strands.types._events import ToolUseStreamEvent, ContentBlockDelta


@pytest.fixture
def test_client():
    """Create a FastAPI test client for WebSocket testing."""
    return TestClient(app)


@pytest.fixture
def sample_pcm_audio():
    """Sample base64-encoded PCM audio data for testing."""
    # Generate a small PCM audio chunk (silence)
    # 16-bit PCM, mono, 16000 Hz, 0.1 seconds = 1600 samples = 3200 bytes
    pcm_data = b"\x00" * 3200
    return base64.b64encode(pcm_data).decode("utf-8")


@pytest.fixture
def mock_agent_run():
    """
    Create a mock agent.run() function that simulates agent behavior.

    This fixture returns a function that can be configured to send different
    event sequences to the output handler.
    """

    async def _mock_agent_run(inputs=None, outputs=None, event_sequence=None):
        """
        Mock implementation of agent.run().

        Args:
            inputs: List of input handlers (not used in mock)
            outputs: List of output handlers (where events are sent)
            event_sequence: List of events to send, or None for default sequence
        """
        if outputs is None or len(outputs) == 0:
            return

        output = outputs[0]  # Use first output handler

        # Default event sequence if none provided
        if event_sequence is None:
            event_sequence = [
                BidiConnectionStartEvent(connection_id="test-conn-1", model="test-model"),
                BidiResponseStartEvent(response_id="test-response-1"),
                BidiTranscriptStreamEvent(
                    delta=ContentBlockDelta(text=""), text="Hello! How can I help you?", role="assistant", is_final=True
                ),
                BidiResponseCompleteEvent(response_id="test-response-1", stop_reason="complete"),
            ]

        # Send events to output handler
        for event in event_sequence:
            try:
                await output(event)
            except Exception as e:
                # If output handler is stopped, break
                if "stopped" in str(e).lower() or isinstance(e, (StopAsyncIteration, RuntimeError)):
                    break
                raise

        # Simulate normal completion
        await asyncio.sleep(0.01)  # Small delay to simulate processing

    return _mock_agent_run


@pytest.fixture
def mock_nova_sonic_responses():
    """Mock responses from Nova Sonic model for testing."""
    return {
        "connection_start": BidiConnectionStartEvent(connection_id="test-conn-1", model="amazon.nova-sonic-v1:0"),
        "response_start": BidiResponseStartEvent(response_id="test-response-1"),
        "transcript": BidiTranscriptStreamEvent(
            delta=ContentBlockDelta(text=""), text="Test response", role="assistant", is_final=True
        ),
        "audio": BidiAudioStreamEvent(
            audio=base64.b64encode(b"\x00" * 3200).decode("utf-8"), format="pcm", sample_rate=24000, channels=1
        ),
        "response_complete": BidiResponseCompleteEvent(response_id="test-response-1", stop_reason="complete"),
    }


@pytest.fixture
def mock_env_vars(monkeypatch):
    """
    Load environment variables from .env file for integration tests, with test-specific overrides.

    This fixture loads values from .env file (if it exists) and applies
    test-specific overrides. This ensures integration tests use the same configuration
    as the application while allowing test-specific values where needed.
    """
    # Test-specific overrides (values that should always be test values)
    test_overrides = {
        "WEATHER_API_KEY": "test_api_key_12345",  # Always use test API key
        "AGENTCORE_MEMORY_ID": "test-memory-id",  # Use test memory ID
        "MEMORY_ENABLED": "true",  # Enable memory for integration tests
    }

    # Environment variables to load from .env or use defaults
    env_vars = {}

    # Keys that should come from .env if available
    env_keys = [
        "AWS_REGION",
        "AGENTCORE_MEMORY_REGION",
        "MODEL_ID",
        "VOICE",
        "INPUT_SAMPLE_RATE",
        "OUTPUT_SAMPLE_RATE",
        "SYSTEM_PROMPT",
    ]

    # Default values (used if not in .env and not in test_overrides)
    defaults = {
        "AWS_REGION": "us-west-2",
        "AGENTCORE_MEMORY_REGION": "us-west-2",
        "MODEL_ID": "amazon.nova-sonic-v1:0",
        "VOICE": "matthew",
        "INPUT_SAMPLE_RATE": "16000",
        "OUTPUT_SAMPLE_RATE": "24000",
        "SYSTEM_PROMPT": "You are a helpful voice assistant.",
    }

    # Load values: .env > test_overrides > defaults
    for key in env_keys:
        value = os.getenv(key) or test_overrides.get(key) or defaults.get(key)
        if value:
            env_vars[key] = value
            monkeypatch.setenv(key, value)

    # Apply test overrides (these always override .env values)
    for key, value in test_overrides.items():
        env_vars[key] = value
        monkeypatch.setenv(key, value)

    return env_vars


@pytest.fixture
def mock_memory_client_integration():
    """Mock MemoryClient for integration tests."""
    from memory.client import MemoryClient

    client = MagicMock(spec=MemoryClient)
    client.memory_id = "test-memory-id"
    # Use region from .env file or default
    client.region = os.getenv("AGENTCORE_MEMORY_REGION") or os.getenv("AWS_REGION", "us-west-2")
    client.retrieve_memories = MagicMock(return_value=[])
    client.get_user_preferences = MagicMock(return_value=[])
    client.store_event = MagicMock()
    client.get_session_summary = MagicMock(return_value=None)
    client.list_sessions = MagicMock(return_value=[])
    return client


@pytest.fixture
def sample_memory_records_integration():
    """Sample memory records for integration tests."""
    mock_record1 = MagicMock()
    mock_record1.content = "Past conversation about weather in Denver"
    mock_record2 = MagicMock()
    mock_record2.content = "User asked about calculations"
    return [mock_record1, mock_record2]


@pytest.fixture
def sample_preferences_integration():
    """Sample user preferences for integration tests."""
    mock_pref = MagicMock()
    mock_pref.content = "User prefers concise responses"
    return [mock_pref]
