"""
Unit tests for WebSocketInput class.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocket, WebSocketDisconnect

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

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
        websocket.receive_json.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_audio_input_pcm(self, ws_input, websocket):
        """Test audio input with PCM format."""
        websocket.receive_json.return_value = {
            "audio": "base64_audio_data",
            "format": "pcm",
            "sample_rate": 16000,
            "channels": 1
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
            "channels": 1
        }
        
        result = await ws_input()
        
        assert result.format == "wav"
        assert result.sample_rate == 24000
    
    @pytest.mark.asyncio
    async def test_audio_input_default_sample_rate(self, ws_input, websocket):
        """Test audio input with default sample rate."""
        websocket.receive_json.return_value = {
            "audio": "base64_audio_data",
            "format": "pcm"
            # No sample_rate provided
        }
        
        result = await ws_input()
        
        assert result.sample_rate == INPUT_SAMPLE_RATE
    
    @pytest.mark.asyncio
    async def test_audio_input_invalid_sample_rate_normalized(self, ws_input, websocket):
        """Test audio input with invalid sample rate (should normalize to 16000)."""
        websocket.receive_json.return_value = {
            "audio": "base64_audio_data",
            "format": "pcm",
            "sample_rate": 99999  # Invalid
        }
        
        result = await ws_input()
        
        assert result.sample_rate == 16000
    
    @pytest.mark.asyncio
    async def test_audio_input_valid_sample_rates(self, ws_input, websocket):
        """Test audio input with valid sample rates."""
        for rate in [16000, 24000, 48000]:
            websocket.receive_json.return_value = {
                "audio": "base64_audio_data",
                "format": "pcm",
                "sample_rate": rate
            }
            
            result = await ws_input()
            assert result.sample_rate == rate
    
    @pytest.mark.asyncio
    async def test_audio_input_invalid_format_skipped(self, ws_input, websocket):
        """Test audio input with invalid format (should skip and read next)."""
        # First call returns invalid format
        websocket.receive_json.side_effect = [
            {
                "audio": "base64_audio_data",
                "format": "opus",  # Invalid - not PCM or WAV
                "sample_rate": 16000
            },
            {
                "text": "Hello"  # Next message
            }
        ]
        
        result = await ws_input()
        
        # Should have skipped the invalid audio and returned the text
        assert result.text == "Hello"
        assert websocket.receive_json.call_count == 2
    
    @pytest.mark.asyncio
    async def test_unknown_data_format_defaults_to_text(self, ws_input, websocket):
        """Test unknown data format defaults to text."""
        websocket.receive_json.return_value = {
            "unknown_field": "some_value"
        }
        
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
            "sample_rate": 16000
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

