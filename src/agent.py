"""
AgentCore Bi-Directional Streaming Voice Agent
Main application with WebSocket endpoint for real-time voice conversations
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator, Dict, Any, Awaitable, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
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

# Import memory and auth modules
try:
    from .memory.client import MemoryClient
    from .memory.session_manager import MemorySessionManager
    from .auth.google_oauth2 import GoogleOAuth2Handler
    from .auth.oauth2_middleware import get_current_user
    from .config.runtime import get_config
except ImportError:
    # Fallback for direct execution
    from memory.client import MemoryClient
    from memory.session_manager import MemorySessionManager
    from auth.google_oauth2 import GoogleOAuth2Handler
    from auth.oauth2_middleware import get_current_user
    from config.runtime import get_config

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

# Get the project root directory (assuming src/agent.py is in src/)
project_root = Path(__file__).parent.parent
client_web_path = project_root / "client" / "web"

# Serve static files (JS, CSS) from client/web directory
if client_web_path.exists():
    app.mount("/static", StaticFiles(directory=str(client_web_path)), name="static")
    logger.info(f"Serving static files from: {client_web_path}")
else:
    logger.warning(f"Frontend directory not found at: {client_web_path}")

# Configuration
config = get_config()
AWS_REGION = config.get_config_value("AWS_REGION", "us-east-1")
MODEL_ID = config.get_config_value("MODEL_ID", "amazon.nova-sonic-v1:0")
VOICE = config.get_config_value("VOICE", "matthew")
INPUT_SAMPLE_RATE = int(config.get_config_value("INPUT_SAMPLE_RATE", "16000"))
OUTPUT_SAMPLE_RATE = int(config.get_config_value("OUTPUT_SAMPLE_RATE", "24000"))
MEMORY_ENABLED = config.get_config_value("MEMORY_ENABLED", "false").lower() == "true"

# Initialize memory client if enabled
memory_client: Optional[MemoryClient] = None
if MEMORY_ENABLED:
    try:
        memory_region = config.get_config_value("AGENTCORE_MEMORY_REGION", AWS_REGION)
        memory_id = config.get_config_value("AGENTCORE_MEMORY_ID")
        memory_client = MemoryClient(region=memory_region, memory_id=memory_id)
        # Create memory resource if needed
        memory_client.create_memory_resource()
        logger.info("Memory client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize memory client: {e}")
        memory_client = None

# Initialize OAuth2 handler
oauth2_handler: Optional[GoogleOAuth2Handler] = None
try:
    oauth2_handler = GoogleOAuth2Handler()
    logger.info("OAuth2 handler initialized")
except Exception as e:
    logger.warning(f"OAuth2 handler not initialized: {e}")

SYSTEM_PROMPT = config.get_config_value(
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


def create_agent(model: BidiNovaSonicModel, system_prompt: Optional[str] = None) -> BidiAgent:
    """Create Strands BidiAgent with tools and system prompt."""
    prompt = system_prompt or SYSTEM_PROMPT
    return BidiAgent(
        model=model,
        tools=[calculator, weather_api, database_query],
        system_prompt=prompt,
    )


class WebSocketOutput:
    """
    BidiOutput implementation that sends events to a WebSocket connection.
    
    Implements the BidiOutput protocol to convert agent output events
    into WebSocket messages that the client can process.
    """
    
    def __init__(self, websocket: WebSocket, session_manager: Optional[MemorySessionManager] = None):
        self.websocket = websocket
        self.session_manager = session_manager
        self._stopped = False
        self._event_count = 0
        self._current_transcript = ""
    
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
                    
                    # Store in memory if session manager is available
                    if self.session_manager:
                        if role == 'assistant':
                            self.session_manager.store_agent_response(audio_transcript=event.text)
                        elif role == 'user':
                            self.session_manager.store_user_input(audio_transcript=event.text)
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
                tool_name = getattr(event, 'tool_name', 'unknown')
                tool_content = str(getattr(event, 'content', ''))[:200]
                logger.info(f"Tool use: {tool_name}")
                await self.websocket.send_json({
                    "type": "tool_use",
                    "tool": tool_name,
                    "data": tool_content
                })
                
                # Store tool use in memory if session manager is available
                if self.session_manager:
                    # Try to extract input/output from event
                    input_data = getattr(event, 'input', {})
                    output_data = {"content": tool_content}
                    self.session_manager.store_tool_use(
                        tool_name=tool_name,
                        input_data=input_data,
                        output_data=output_data
                    )
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
    
    def __init__(self, websocket: WebSocket, session_manager: Optional[MemorySessionManager] = None):
        self.websocket = websocket
        self.session_manager = session_manager
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
                text = data["text"]
                logger.info(f"Received text: {text}")
                
                # Store user input in memory if session manager is available
                if self.session_manager:
                    self.session_manager.store_user_input(text=text)
                
                return BidiTextInputEvent(text=text)
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
    - Requires authentication via JWT token in query parameter
    - Creates a Nova Sonic model and BidiAgent
    - Streams audio input/output in real-time
    - Handles interruptions and context changes
    - Integrates with memory for context-aware responses
    """
    # Get token from query parameters
    token = websocket.query_params.get("token")
    user_info = None
    
    # Authenticate if OAuth2 is enabled
    if oauth2_handler:
        if not token:
            await websocket.close(code=1008, reason="Authentication required")
            return
        
        try:
            user_info = oauth2_handler.verify_token(token)
        except ValueError as e:
            logger.warning(f"Invalid token: {e}")
            await websocket.close(code=1008, reason="Invalid token")
            return
    
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    # Initialize memory session manager if memory is enabled
    session_manager: Optional[MemorySessionManager] = None
    if memory_client and user_info:
        actor_id = user_info.get("email", "anonymous")
        session_manager = MemorySessionManager(memory_client, actor_id=actor_id)
        await session_manager.initialize()
        
        # Get memory context and update system prompt
        memory_context = session_manager.get_context()
        if memory_context:
            system_prompt = f"{SYSTEM_PROMPT}\n\n{memory_context}"
        else:
            system_prompt = SYSTEM_PROMPT
    else:
        system_prompt = SYSTEM_PROMPT
    
    try:
        # Create model and agent for this session
        model = create_nova_sonic_model()
        agent = create_agent(model, system_prompt=system_prompt)
        
        logger.info("Starting bi-directional streaming session")
        
        # Create BidiInput and BidiOutput implementations for WebSocket
        ws_input = WebSocketInput(websocket, session_manager=session_manager)
        ws_output = WebSocketOutput(websocket, session_manager=session_manager)
        
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
        # Finalize memory session
        if session_manager:
            await session_manager.finalize()
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


# Authentication endpoints
@app.get("/api/auth/login")
async def login(request: Request):
    """Initiate Google OAuth2 login."""
    if not oauth2_handler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth2 not configured"
        )
    
    state = request.query_params.get("state")
    auth_url, state_value = oauth2_handler.get_authorization_url(state=state)
    return RedirectResponse(url=auth_url)


@app.get("/api/auth/callback")
async def auth_callback(request: Request, code: str, state: Optional[str] = None):
    """Handle OAuth2 callback."""
    if not oauth2_handler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth2 not configured"
        )
    
    try:
        result = await oauth2_handler.handle_callback(code=code, state=state)
        # Redirect to frontend with token
        # In production, use httpOnly cookie instead
        redirect_url = f"/?token={result['token']}"
        return RedirectResponse(url=redirect_url)
    except ValueError as e:
        logger.error(f"OAuth2 callback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@app.get("/api/auth/me")
async def get_me(request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    """Get current user information."""
    return JSONResponse(content=user)


@app.post("/api/auth/logout")
async def logout():
    """Logout endpoint (client should clear token)."""
    return JSONResponse(content={"message": "Logged out"})


# Memory API endpoints
@app.post("/api/memory/query")
async def query_memories(
    request: Request,
    query: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Query memories for current user."""
    if not memory_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory not enabled"
        )
    
    actor_id = user.get("email")
    query_text = query.get("query", "")
    
    memories = memory_client.retrieve_memories(
        actor_id=actor_id,
        query=query_text if query_text else None,
        top_k=query.get("top_k", 5)
    )
    
    return JSONResponse(content={
        "memories": [
            {
                "content": getattr(m, "content", str(m)),
                "namespace": getattr(m, "namespace", ""),
            }
            for m in memories
        ]
    })


@app.get("/api/memory/sessions")
async def list_sessions(user: Dict[str, Any] = Depends(get_current_user)):
    """List user's sessions."""
    if not memory_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory not enabled"
        )
    
    actor_id = user.get("email")
    sessions = memory_client.list_sessions(actor_id=actor_id)
    
    return JSONResponse(content={"sessions": sessions})


@app.get("/api/memory/sessions/{session_id}")
async def get_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Get session details and summary."""
    if not memory_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory not enabled"
        )
    
    actor_id = user.get("email")
    summary = memory_client.get_session_summary(actor_id=actor_id, session_id=session_id)
    
    return JSONResponse(content={
        "session_id": session_id,
        "summary": summary
    })


@app.delete("/api/memory/sessions/{session_id}")
async def delete_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Delete a session's memories."""
    # This would require additional implementation
    return JSONResponse(content={"message": "Session deleted"})


@app.get("/api/memory/preferences")
async def get_preferences(user: Dict[str, Any] = Depends(get_current_user)):
    """Get user preferences."""
    if not memory_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory not enabled"
        )
    
    actor_id = user.get("email")
    preferences = memory_client.get_user_preferences(actor_id=actor_id)
    
    # Format preferences for frontend
    formatted_prefs = []
    for p in preferences:
        if isinstance(p, dict):
            # Memory record is a dictionary
            content = p.get("content", {})
            if isinstance(content, dict):
                text = content.get("text", "")
            else:
                text = str(content) if content else ""
            
            formatted_prefs.append({
                "content": text,
                "namespace": p.get("namespace", "")
            })
        else:
            # Fallback for object-like records
            content_attr = getattr(p, "content", None)
            if content_attr and hasattr(content_attr, "get"):
                text = content_attr.get("text", "")
            elif content_attr:
                text = str(content_attr)
            else:
                text = str(p)
            
            formatted_prefs.append({
                "content": text,
                "namespace": getattr(p, "namespace", "")
            })
    
    return JSONResponse(content={"preferences": formatted_prefs})


@app.get("/")
async def root():
    """Serve the frontend HTML file or return API information."""
    index_path = client_web_path / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    
    # Fallback to API info if frontend not found
    return JSONResponse(
        content={
            "service": "AgentCore Voice Agent",
            "description": "Bi-directional streaming voice agent with Amazon Nova Sonic",
            "endpoints": {
                "websocket": "/ws",
                "health": "/ping",
                "auth": {
                    "login": "/api/auth/login",
                    "callback": "/api/auth/callback",
                    "me": "/api/auth/me",
                    "logout": "/api/auth/logout"
                },
                "memory": {
                    "query": "/api/memory/query",
                    "sessions": "/api/memory/sessions",
                    "preferences": "/api/memory/preferences"
                }
            },
            "model": MODEL_ID,
            "region": AWS_REGION,
            "memory_enabled": MEMORY_ENABLED,
            "auth_enabled": oauth2_handler is not None
        }
    )


@app.get("/api")
async def api_info():
    """API information endpoint."""
    return JSONResponse(
        content={
            "service": "AgentCore Voice Agent",
            "description": "Bi-directional streaming voice agent with Amazon Nova Sonic",
            "endpoints": {
                "websocket": "/ws",
                "health": "/ping",
                "auth": {
                    "login": "/api/auth/login",
                    "callback": "/api/auth/callback",
                    "me": "/api/auth/me",
                    "logout": "/api/auth/logout"
                },
                "memory": {
                    "query": "/api/memory/query",
                    "sessions": "/api/memory/sessions",
                    "preferences": "/api/memory/preferences"
                }
            },
            "model": MODEL_ID,
            "region": AWS_REGION,
            "memory_enabled": MEMORY_ENABLED,
            "auth_enabled": oauth2_handler is not None
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
