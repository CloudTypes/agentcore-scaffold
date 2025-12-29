"""
Shared pytest fixtures for integration tests.
"""

import pytest
import asyncio
import base64
import sys
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import uvicorn
from threading import Thread

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from agent import app
from strands.experimental.bidi.types.events import (
    BidiConnectionStartEvent,
    BidiResponseStartEvent,
    BidiTranscriptStreamEvent,
    BidiAudioStreamEvent,
    BidiResponseCompleteEvent,
    BidiErrorEvent
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
    pcm_data = b'\x00' * 3200
    return base64.b64encode(pcm_data).decode('utf-8')


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
                    delta=ContentBlockDelta(text=""),
                    text="Hello! How can I help you?",
                    role="assistant",
                    is_final=True
                ),
                BidiResponseCompleteEvent(response_id="test-response-1", stop_reason="complete")
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
        "connection_start": BidiConnectionStartEvent(
            connection_id="test-conn-1",
            model="amazon.nova-sonic-v1:0"
        ),
        "response_start": BidiResponseStartEvent(response_id="test-response-1"),
        "transcript": BidiTranscriptStreamEvent(
            delta=ContentBlockDelta(text=""),
            text="Test response",
            role="assistant",
            is_final=True
        ),
        "audio": BidiAudioStreamEvent(
            audio=base64.b64encode(b'\x00' * 3200).decode('utf-8'),
            format="pcm",
            sample_rate=24000,
            channels=1
        ),
        "response_complete": BidiResponseCompleteEvent(
            response_id="test-response-1",
            stop_reason="complete"
        )
    }


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up environment variables for integration tests."""
    env_vars = {
        "AWS_REGION": "us-east-1",
        "MODEL_ID": "amazon.nova-sonic-v1:0",
        "VOICE": "matthew",
        "INPUT_SAMPLE_RATE": "16000",
        "OUTPUT_SAMPLE_RATE": "24000",
        "WEATHER_API_KEY": "test_api_key_12345",
        "SYSTEM_PROMPT": "You are a helpful voice assistant."
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars

