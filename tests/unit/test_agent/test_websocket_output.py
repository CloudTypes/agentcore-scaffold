"""
Unit tests for WebSocketOutput class.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocket, WebSocketDisconnect

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from agent import WebSocketOutput

# Try to import actual event classes for testing
try:
    from strands.experimental.bidi.types.events import (
        BidiAudioStreamEvent,
        BidiTranscriptStreamEvent,
        BidiResponseStartEvent,
        BidiResponseCompleteEvent,
        BidiErrorEvent,
        BidiConnectionStartEvent,
        BidiConnectionCloseEvent
    )
    from strands.types._events import ToolUseStreamEvent
    from strands.types.streaming import ContentBlockDelta
    EVENT_CLASSES_AVAILABLE = True
except ImportError:
    EVENT_CLASSES_AVAILABLE = False
    ContentBlockDelta = None


class TestWebSocketOutput:
    """Test cases for WebSocketOutput class."""
    
    @pytest.fixture
    def websocket(self):
        """Create a mock WebSocket."""
        ws = AsyncMock(spec=WebSocket)
        ws.send_json = AsyncMock()
        return ws
    
    @pytest.fixture
    def output(self, websocket):
        """Create WebSocketOutput instance."""
        return WebSocketOutput(websocket)
    
    def test_init(self, websocket):
        """Test WebSocketOutput initialization."""
        output = WebSocketOutput(websocket)
        assert output.websocket == websocket
        assert output._stopped is False
        assert output._event_count == 0
    
    @pytest.mark.asyncio
    async def test_start(self, output, websocket):
        """Test start method."""
        mock_agent = MagicMock()
        await output.start(mock_agent)
        assert output._stopped is False
        assert output._event_count == 0
    
    @pytest.mark.asyncio
    async def test_stop(self, output):
        """Test stop method."""
        await output.stop()
        assert output._stopped is True
    
    @pytest.mark.asyncio
    async def test_audio_stream_event(self, output, websocket):
        """Test handling BidiAudioStreamEvent."""
        if EVENT_CLASSES_AVAILABLE:
            # Use actual event class
            event = BidiAudioStreamEvent(
                audio="base64_audio_data",
                format="pcm",
                sample_rate=16000,
                channels=1
            )
        else:
            # Fallback: skip test if event classes not available
            pytest.skip("Event classes not available for testing")
        
        await output(event)
        
        # Verify send_json was called
        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "audio"
        assert call_args["data"] == "base64_audio_data"
        assert call_args["format"] == "pcm"
        assert call_args["sample_rate"] == 16000
    
    @pytest.mark.asyncio
    async def test_transcript_stream_event_final(self, output, websocket):
        """Test handling BidiTranscriptStreamEvent with is_final=True."""
        if not EVENT_CLASSES_AVAILABLE:
            pytest.skip("Event classes not available for testing")
        
        # Create actual event with mock delta
        mock_delta = MagicMock(spec=ContentBlockDelta)
        event = BidiTranscriptStreamEvent(
            delta=mock_delta,
            text="Hello, world",
            role="user",
            is_final=True
        )
        
        await output(event)
        
        # Verify send_json was called for final transcript
        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "transcript"
        assert call_args["data"] == "Hello, world"
        assert call_args["role"] == "user"
    
    @pytest.mark.asyncio
    async def test_transcript_stream_event_not_final(self, output, websocket):
        """Test handling BidiTranscriptStreamEvent with is_final=False (should be skipped)."""
        if not EVENT_CLASSES_AVAILABLE:
            pytest.skip("Event classes not available for testing")
        
        # Create actual event with is_final=False
        mock_delta = MagicMock(spec=ContentBlockDelta)
        event = BidiTranscriptStreamEvent(
            delta=mock_delta,
            text="Hello, wo",
            role="user",
            is_final=False
        )
        
        await output(event)
        
        # Verify send_json was NOT called (non-final transcripts are skipped)
        websocket.send_json.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_response_start_event(self, output, websocket):
        """Test handling BidiResponseStartEvent."""
        if not EVENT_CLASSES_AVAILABLE:
            pytest.skip("Event classes not available for testing")
        
        event = BidiResponseStartEvent(response_id="test-response-123")
        
        await output(event)
        
        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "response_start"
    
    @pytest.mark.asyncio
    async def test_response_complete_event(self, output, websocket):
        """Test handling BidiResponseCompleteEvent."""
        if not EVENT_CLASSES_AVAILABLE:
            pytest.skip("Event classes not available for testing")
        
        event = BidiResponseCompleteEvent(
            response_id="test-response-123",
            stop_reason="complete"
        )
        
        await output(event)
        
        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "response_complete"
    
    @pytest.mark.asyncio
    async def test_error_event(self, output, websocket):
        """Test handling BidiErrorEvent."""
        if not EVENT_CLASSES_AVAILABLE:
            pytest.skip("Event classes not available for testing")
        
        test_error = Exception("Test error message")
        event = BidiErrorEvent(error=test_error)
        
        await output(event)
        
        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "error"
        assert call_args["message"] == "Test error message"
    
    @pytest.mark.asyncio
    async def test_connection_start_event(self, output, websocket):
        """Test handling BidiConnectionStartEvent."""
        if not EVENT_CLASSES_AVAILABLE:
            pytest.skip("Event classes not available for testing")
        
        event = BidiConnectionStartEvent(
            connection_id="test-connection-123",
            model="amazon.nova-sonic-v1:0"
        )
        
        await output(event)
        
        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "connection_start"
    
    @pytest.mark.asyncio
    async def test_connection_close_event(self, output, websocket):
        """Test handling BidiConnectionCloseEvent."""
        if not EVENT_CLASSES_AVAILABLE:
            pytest.skip("Event classes not available for testing")
        
        event = BidiConnectionCloseEvent(
            connection_id="test-connection-123",
            reason="client_disconnect"
        )
        
        await output(event)
        
        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "connection_close"
    
    @pytest.mark.asyncio
    async def test_tool_use_event(self, output, websocket):
        """Test handling ToolUseStreamEvent."""
        if not EVENT_CLASSES_AVAILABLE:
            pytest.skip("Event classes not available for testing")
        
        mock_delta = MagicMock(spec=ContentBlockDelta)
        # Create event and set tool_name attribute (code uses getattr)
        event = ToolUseStreamEvent(
            delta=mock_delta,
            current_tool_use={
                "tool_name": "calculator",
                "content": "Some tool content"
            }
        )
        # Set tool_name as attribute since code uses getattr(event, 'tool_name', 'unknown')
        event.tool_name = "calculator"
        event.content = "Some tool content"
        
        await output(event)
        
        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "tool_use"
        assert call_args["tool"] == "calculator"
    
    @pytest.mark.asyncio
    async def test_unknown_event_type(self, output, websocket):
        """Test handling unknown event type."""
        event = MagicMock()
        event.__class__.__name__ = "UnknownEvent"
        
        await output(event)
        
        # Unknown events should not send anything
        websocket.send_json.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_websocket_disconnect_handling(self, output, websocket):
        """Test handling WebSocket disconnect."""
        if not EVENT_CLASSES_AVAILABLE:
            pytest.skip("Event classes not available for testing")
        
        websocket.send_json.side_effect = WebSocketDisconnect()
        
        event = BidiResponseStartEvent(response_id="test-response-123")
        
        await output(event)
        
        # Should have marked as stopped
        assert output._stopped is True
    
    @pytest.mark.asyncio
    async def test_stopped_output_ignores_events(self, output, websocket):
        """Test that stopped output ignores new events."""
        if not EVENT_CLASSES_AVAILABLE:
            pytest.skip("Event classes not available for testing")
        
        output._stopped = True
        
        event = BidiResponseStartEvent(response_id="test-response-123")
        
        await output(event)
        
        # Should not send anything when stopped
        websocket.send_json.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_event_count_increment(self, output, websocket):
        """Test that event count increments."""
        initial_count = output._event_count
        
        event = MagicMock()
        event.__class__.__name__ = "UnknownEvent"
        
        await output(event)
        
        assert output._event_count == initial_count + 1

