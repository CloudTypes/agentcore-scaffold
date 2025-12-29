"""
AgentCore Bi-Directional Streaming Voice Agent
Main application with WebSocket endpoint for real-time voice conversations
"""

import os
import asyncio
import logging
from typing import AsyncIterator, Dict, Any, Awaitable
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from strands.experimental.bidi.agent import BidiAgent
from strands.experimental.bidi.models.nova_sonic import BidiNovaSonicModel
from strands.experimental.bidi.types.io import BidiInput, BidiOutput
from strands.experimental.bidi.types.events import (
    BidiTextInputEvent, 
    BidiAudioInputEvent,
    BidiAudioStreamEvent,
    BidiTranscriptStreamEvent,
    BidiResponseStartEvent,
    BidiResponseCompleteEvent,
    BidiErrorEvent,
    BidiConnectionStartEvent,
    BidiConnectionCloseEvent
)
from strands.types._events import ToolUseStreamEvent
from dotenv import load_dotenv

# Import custom tools
from tools.calculator import calculator
from tools.weather import weather_api
from tools.database import database_query

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress noisy AWS CRT cleanup errors (harmless cancellation errors during WebSocket cleanup)
logging.getLogger('awscrt').setLevel(logging.WARNING)

# Initialize FastAPI app
app = FastAPI(
    title="AgentCore Voice Agent",
    description="Bi-directional streaming voice agent with Amazon Nova Sonic",
    version="1.0.0"
)

# Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID = os.getenv("MODEL_ID", "amazon.nova-sonic-v1:0")
VOICE = os.getenv("VOICE", "matthew")
INPUT_SAMPLE_RATE = int(os.getenv("INPUT_SAMPLE_RATE", "16000"))
OUTPUT_SAMPLE_RATE = int(os.getenv("OUTPUT_SAMPLE_RATE", "24000"))
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful voice assistant with access to calculator, weather, and database tools. "
    "Provide clear, concise responses and use tools when appropriate."
)


def create_nova_sonic_model() -> BidiNovaSonicModel:
    """Create and configure Nova Sonic model for bi-directional streaming."""
    return BidiNovaSonicModel(
        region=AWS_REGION,
        model_id=MODEL_ID,
        provider_config={
            "audio": {
                "input_sample_rate": INPUT_SAMPLE_RATE,
                "output_sample_rate": OUTPUT_SAMPLE_RATE,
                "voice": VOICE,
            }
        }
    )


def create_agent(model: BidiNovaSonicModel) -> BidiAgent:
    """Create Strands BidiAgent with tools and system prompt."""
    return BidiAgent(
        model=model,
        tools=[calculator, weather_api, database_query],
        system_prompt=SYSTEM_PROMPT,
    )


class WebSocketOutput:
    """
    BidiOutput implementation that sends events to a WebSocket connection.
    
    Implements the BidiOutput protocol to convert agent output events
    into WebSocket messages that the client can process.
    """
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self._stopped = False
        self._event_count = 0
    
    async def start(self, agent: BidiAgent) -> None:
        """Start the output handler."""
        self._stopped = False
        self._event_count = 0
    
    async def stop(self) -> None:
        """Stop the output handler."""
        self._stopped = True
    
    async def __call__(self, event) -> None:
        """
        Process output events from the agent.
        
        Args:
            event: Output event from the agent (audio, text, tool calls, etc.)
        """
        self._event_count += 1
        
        if self._stopped:
            return
        
        try:
            # Handle different event types
            if isinstance(event, BidiAudioStreamEvent):
                # Audio stream event - send audio data
                await self.websocket.send_json({
                    "type": "audio",
                    "data": event.audio,
                    "format": event.format,
                    "sample_rate": event.sample_rate
                })
                logger.debug(f"Sent audio stream: {len(event.audio)} chars, format={event.format}, rate={event.sample_rate}")
                
            elif isinstance(event, BidiTranscriptStreamEvent):
                # Transcript stream event - can be user or assistant transcript
                # Use the role to determine if it's user or agent speech
                # Only send final transcripts to avoid duplicates from incremental updates
                role = getattr(event, 'role', 'assistant')  # Default to assistant if role not present
                is_final = getattr(event, 'is_final', False)
                
                if is_final:
                    await self.websocket.send_json({
                        "type": "transcript",
                        "data": event.text,
                        "role": role
                    })
                    logger.info(f"Sent final transcript ({role}): {event.text}")
                else:
                    # Log incremental updates at debug level but don't send to client
                    logger.debug(f"Incremental transcript ({role}): {event.text}")
                
            elif isinstance(event, BidiResponseStartEvent):
                logger.info("Agent response started")
                await self.websocket.send_json({
                    "type": "response_start"
                })
                
            elif isinstance(event, BidiResponseCompleteEvent):
                logger.info("Agent response completed")
                await self.websocket.send_json({
                    "type": "response_complete"
                })
                
            elif isinstance(event, BidiErrorEvent):
                logger.error(f"Agent error: {event.error}")
                await self.websocket.send_json({
                    "type": "error",
                    "message": str(event.error)
                })
            elif isinstance(event, BidiConnectionStartEvent):
                logger.info("Agent connection started")
                await self.websocket.send_json({
                    "type": "connection_start"
                })
            elif isinstance(event, BidiConnectionCloseEvent):
                logger.info("Agent connection closed")
                await self.websocket.send_json({
                    "type": "connection_close"
                })
            elif isinstance(event, ToolUseStreamEvent):
                logger.info(f"Tool use: {getattr(event, 'tool_name', 'unknown')}")
                await self.websocket.send_json({
                    "type": "tool_use",
                    "tool": getattr(event, 'tool_name', 'unknown'),
                    "data": str(getattr(event, 'content', ''))[:200]  # Limit size
                })
            else:
                # Log unhandled event types at debug level
                event_type = type(event).__name__
                logger.debug(f"Unhandled event type: {event_type}")
                
        except (WebSocketDisconnect, RuntimeError) as e:
            logger.debug(f"WebSocket closed while sending output: {e}")
            self._stopped = True
        except Exception as e:
            logger.error(f"Error sending output event: {e}", exc_info=True)


class WebSocketInput:
    """
    BidiInput implementation that reads from a WebSocket connection.
    
    Implements the BidiInput protocol to convert WebSocket messages
    into BidiInputEvent objects that the agent can process.
    """
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self._stopped = False
    
    async def start(self, agent: BidiAgent) -> None:
        """Start the input source."""
        self._stopped = False
    
    async def stop(self) -> None:
        """Stop the input source."""
        self._stopped = True
    
    def __call__(self) -> Awaitable[BidiTextInputEvent | BidiAudioInputEvent]:
        """
        Read input data from the WebSocket.
        
        Returns:
            Coroutine that resolves to a BidiInputEvent (text or audio)
        """
        return self._read_next()
    
    async def _read_next(self) -> BidiTextInputEvent | BidiAudioInputEvent:
        """Read the next event from the WebSocket."""
        if self._stopped:
            raise StopAsyncIteration
        
        try:
            # Receive data from client
            data = await self.websocket.receive_json()
            
            # Convert to appropriate event type
            if "audio" in data:
                # Audio input - base64 encoded audio data
                audio_data = data["audio"]
                sample_rate = data.get("sample_rate", INPUT_SAMPLE_RATE)
                # Ensure sample_rate is one of the valid values
                if sample_rate not in [16000, 24000, 48000]:
                    sample_rate = 16000  # Default to 16000 if invalid
                
                format_type = data.get("format", "pcm")  # Default to PCM (required by Nova Sonic)
                # Nova Sonic requires Linear PCM format
                if format_type not in ["pcm", "wav"]:
                    logger.error(f"Received {format_type} format - Nova Sonic requires PCM format!")
                    logger.error("Please convert audio to PCM on the client side before sending")
                    # Skip this invalid chunk and read the next message
                    return await self._read_next()
                
                logger.debug(f"Received audio chunk: {len(audio_data)} chars, format={format_type}, sample_rate={sample_rate}")
                
                # Create the audio input event
                audio_event = BidiAudioInputEvent(
                    audio=audio_data,
                    format=format_type,
                    sample_rate=sample_rate,
                    channels=data.get("channels", 1)  # Default to mono
                )
                
                
                return audio_event
            elif "text" in data:
                logger.info(f"Received text: {data['text']}")
                return BidiTextInputEvent(text=data["text"])
            else:
                logger.warning(f"Received unknown data format: {data.keys()}")
                # Default to text if format is unknown
                return BidiTextInputEvent(text=str(data))
                
        except WebSocketDisconnect:
            # Normal disconnect - signal end of input
            logger.debug("WebSocket disconnected, ending input stream")
            self._stopped = True
            raise StopAsyncIteration
        except Exception as e:
            logger.error(f"Error reading from WebSocket: {e}")
            self._stopped = True
            raise


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for bi-directional streaming voice conversations.
    
    This endpoint:
    - Accepts WebSocket connections on port 8080 at /ws
    - Creates a Nova Sonic model and BidiAgent
    - Streams audio input/output in real-time
    - Handles interruptions and context changes
    """
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    try:
        # Create model and agent for this session
        model = create_nova_sonic_model()
        agent = create_agent(model)
        
        logger.info("Starting bi-directional streaming session")
        
        # Create BidiInput and BidiOutput implementations for WebSocket
        ws_input = WebSocketInput(websocket)
        ws_output = WebSocketOutput(websocket)
        
        # Start the input and output handlers
        await ws_input.start(agent)
        await ws_output.start(agent)
        logger.info("Bi-directional streaming session started")
        
        # Log configuration at debug level
        logger.debug(f"Agent model: {MODEL_ID}, region: {AWS_REGION}")
        logger.debug(f"Input sample rate: {INPUT_SAMPLE_RATE}, Output sample rate: {OUTPUT_SAMPLE_RATE}")
        
        try:
            # Start the agent - this will block until the connection ends
            async def run_agent():
                try:
                    await agent.run(
                        inputs=[ws_input],
                        outputs=[ws_output]
                    )
                    logger.debug("agent.run() completed normally")
                except (StopAsyncIteration, WebSocketDisconnect):
                    # Normal termination - client disconnected
                    logger.debug("Agent session ended (client disconnected)")
                    return
                except Exception as e:
                    # Check if it's a timeout error from Nova Sonic (expected when no audio input)
                    error_str = str(e)
                    if "Timed out waiting for audio bytes" in error_str:
                        logger.info("Nova Sonic timeout (expected when no audio input) - ending session gracefully")
                        return
                    logger.error(f"Error inside agent.run(): {e}", exc_info=True)
                    raise
            
            # Run the agent
            await run_agent()
            
        except (StopAsyncIteration, WebSocketDisconnect):
            # Normal termination - already handled in run_agent
            pass
        except Exception as e:
            logger.error(f"Error in agent.run(): {e}", exc_info=True)
            # Try to send error to client
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Agent error: {str(e)}"
                })
            except:
                pass
            raise
        
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except (StopAsyncIteration, asyncio.CancelledError):
        # Normal termination - client disconnected or agent stopped
        logger.debug("Agent session ended normally")
    except Exception as e:
        # Check if it's a timeout error from Nova Sonic (expected when no audio input for a while)
        error_str = str(e)
        if "Timed out waiting for audio bytes" in error_str:
            logger.info("Nova Sonic timeout (expected when no audio input) - session ended normally")
        else:
            logger.error(f"Error in websocket_endpoint: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except (WebSocketDisconnect, RuntimeError):
            # WebSocket already closed, ignore
            pass
    finally:
        logger.info("WebSocket session ended")


@app.get("/ping")
async def health_check():
    """
    Health check endpoint required by AgentCore Runtime.
    
    Returns:
        JSON response indicating service health
    """
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "agentcore-voice-agent",
            "version": "1.0.0"
        }
    )


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return JSONResponse(
        content={
            "service": "AgentCore Voice Agent",
            "description": "Bi-directional streaming voice agent with Amazon Nova Sonic",
            "endpoints": {
                "websocket": "/ws",
                "health": "/ping"
            },
            "model": MODEL_ID,
            "region": AWS_REGION
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    # Run the application
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )
