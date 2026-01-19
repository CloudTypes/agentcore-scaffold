"""
Unit tests for WebSocketInput class.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocket, WebSocketDisconnect

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from agent import WebSocketInput, INPUT_SAMPLE_RATE


class TestWebSocketInput:
    """Test cases for WebSocketInput class."""

    @pytest.fixture
    def websocket(self):
        """Create a mock WebSocket."""
        ws = AsyncMock(spec=WebSocket)
        ws.receive_json = AsyncMock()
        return ws

    @pytest.fixture
    def ws_input(self, websocket):
        """Create WebSocketInput instance."""
        return WebSocketInput(websocket)

    def test_init(self, websocket):
        """Test WebSocketInput initialization."""
        ws_input = WebSocketInput(websocket)
        assert ws_input.websocket == websocket
        assert ws_input._stopped is False
        assert ws_input._last_input_type is None
        assert ws_input._text_pending is False

    @pytest.mark.asyncio
    async def test_start(self, ws_input):
        """Test start method."""
        mock_agent = MagicMock()
        await ws_input.start(mock_agent)
        assert ws_input._stopped is False

    @pytest.mark.asyncio
    async def test_stop(self, ws_input):
        """Test stop method."""
        await ws_input.stop()
        assert ws_input._stopped is True

    @pytest.mark.asyncio
    async def test_text_input(self, ws_input, websocket):
        """Test text input message."""
        websocket.receive_json.return_value = {"text": "Hello, world"}

        result = await ws_input()

        assert result.text == "Hello, world"
        assert ws_input._last_input_type == "text"
        websocket.receive_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_text_input_tracks_input_type(self, ws_input, websocket):
        """Test that text input sets _last_input_type correctly."""
        websocket.receive_json.return_value = {"text": "Test message"}

        await ws_input()

        assert ws_input._last_input_type == "text"

    @pytest.mark.asyncio
    async def test_audio_input_tracks_input_type(self, ws_input, websocket):
        """Test that audio input sets _last_input_type correctly."""
        websocket.receive_json.return_value = {"audio": "base64_audio_data", "format": "pcm", "sample_rate": 16000}

        await ws_input()

        assert ws_input._last_input_type == "audio"

    @pytest.mark.asyncio
    async def test_text_input_with_session_manager(self, websocket):
        """Test text input with session manager stores in memory."""
        mock_session_manager = MagicMock()
        ws_input = WebSocketInput(websocket, session_manager=mock_session_manager)
        websocket.receive_json.return_value = {"text": "Hello, world"}

        result = await ws_input()

        assert result.text == "Hello, world"
        mock_session_manager.store_user_input.assert_called_once_with(text="Hello, world")

    @pytest.mark.asyncio
    async def test_text_input_memory_storage_error_handled(self, websocket):
        """Test that text input handles memory storage errors gracefully."""
        mock_session_manager = MagicMock()
        mock_session_manager.store_user_input.side_effect = Exception("Memory error")
        ws_input = WebSocketInput(websocket, session_manager=mock_session_manager)
        websocket.receive_json.return_value = {"text": "Hello, world"}

        # Should not raise, should still return text event
        result = await ws_input()

        assert result.text == "Hello, world"
        mock_session_manager.store_user_input.assert_called_once()

    @pytest.mark.asyncio
    async def test_audio_input_pcm(self, ws_input, websocket):
        """Test audio input with PCM format."""
        websocket.receive_json.return_value = {
            "audio": "base64_audio_data",
            "format": "pcm",
            "sample_rate": 16000,
            "channels": 1,
        }

        result = await ws_input()

        assert result.audio == "base64_audio_data"
        assert result.format == "pcm"
        assert result.sample_rate == 16000
        assert result.channels == 1

    @pytest.mark.asyncio
    async def test_audio_input_wav(self, ws_input, websocket):
        """Test audio input with WAV format."""
        websocket.receive_json.return_value = {
            "audio": "base64_audio_data",
            "format": "wav",
            "sample_rate": 24000,
            "channels": 1,
        }

        result = await ws_input()

        assert result.format == "wav"
        assert result.sample_rate == 24000

    @pytest.mark.asyncio
    async def test_audio_input_default_sample_rate(self, ws_input, websocket):
        """Test audio input with default sample rate."""
        websocket.receive_json.return_value = {
            "audio": "base64_audio_data",
            "format": "pcm",
            # No sample_rate provided
        }

        result = await ws_input()

        assert result.sample_rate == INPUT_SAMPLE_RATE

    @pytest.mark.asyncio
    async def test_audio_input_invalid_sample_rate_normalized(self, ws_input, websocket):
        """Test audio input with invalid sample rate (should normalize to 16000)."""
        websocket.receive_json.return_value = {"audio": "base64_audio_data", "format": "pcm", "sample_rate": 99999}  # Invalid

        result = await ws_input()

        assert result.sample_rate == 16000

    @pytest.mark.asyncio
    async def test_audio_input_valid_sample_rates(self, ws_input, websocket):
        """Test audio input with valid sample rates."""
        for rate in [16000, 24000, 48000]:
            websocket.receive_json.return_value = {"audio": "base64_audio_data", "format": "pcm", "sample_rate": rate}

            result = await ws_input()
            assert result.sample_rate == rate

    @pytest.mark.asyncio
    async def test_audio_input_invalid_format_skipped(self, ws_input, websocket):
        """Test audio input with invalid format (should skip and read next)."""
        # First call returns invalid format
        websocket.receive_json.side_effect = [
            {"audio": "base64_audio_data", "format": "opus", "sample_rate": 16000},  # Invalid - not PCM or WAV
            {"text": "Hello"},  # Next message
        ]

        result = await ws_input()

        # Should have skipped the invalid audio and returned the text
        assert result.text == "Hello"
        assert websocket.receive_json.call_count == 2

    @pytest.mark.asyncio
    async def test_unknown_data_format_defaults_to_text(self, ws_input, websocket):
        """Test unknown data format defaults to text."""
        websocket.receive_json.return_value = {"unknown_field": "some_value"}

        result = await ws_input()

        assert result.text == "{'unknown_field': 'some_value'}"

    @pytest.mark.asyncio
    async def test_websocket_disconnect_raises_stop_async_iteration(self, ws_input, websocket):
        """Test WebSocket disconnect raises StopAsyncIteration."""
        websocket.receive_json.side_effect = WebSocketDisconnect()

        with pytest.raises(StopAsyncIteration):
            await ws_input()

        assert ws_input._stopped is True

    @pytest.mark.asyncio
    async def test_stopped_input_raises_stop_async_iteration(self, ws_input):
        """Test that stopped input raises StopAsyncIteration."""
        ws_input._stopped = True

        with pytest.raises(StopAsyncIteration):
            await ws_input()

    @pytest.mark.asyncio
    async def test_audio_input_default_channels(self, ws_input, websocket):
        """Test audio input with default channels (mono)."""
        websocket.receive_json.return_value = {
            "audio": "base64_audio_data",
            "format": "pcm",
            "sample_rate": 16000,
            # No channels provided
        }

        result = await ws_input()

        assert result.channels == 1

    @pytest.mark.asyncio
    async def test_exception_handling(self, ws_input, websocket):
        """Test exception handling in _read_next."""
        websocket.receive_json.side_effect = Exception("Test error")

        with pytest.raises(Exception, match="Test error"):
            await ws_input()

        assert ws_input._stopped is True
