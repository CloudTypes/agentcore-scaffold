"""
AgentCore Bi-Directional Streaming Voice Agent

This module implements a FastAPI-based voice agent application that provides
bi-directional streaming voice conversations using Amazon Nova Sonic. The agent
supports real-time audio input/output through WebSocket connections, text-based
interactions, and integrates with memory and authentication systems.

Architecture:
    - WebSocket endpoint (/ws) for real-time voice streaming
    - REST API endpoints for session management, memory operations, and authentication
    - Integration with Strands BidiAgent for bi-directional streaming
    - Optional memory persistence using AgentCore Memory
    - Optional OAuth2 authentication via Google

Key Components:
    - WebSocketInput: Handles incoming WebSocket messages (audio/text)
    - WebSocketOutput: Handles outgoing WebSocket messages (audio/transcripts/events)
    - Memory integration for session continuity and context
    - Tool integration (calculator, weather, database)
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator, Dict, Any, Awaitable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from strands.experimental.bidi.agent import BidiAgent
from concurrent.futures import InvalidStateError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Vision routes are handled by the orchestrator agent, not the voice agent
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
    BidiConnectionCloseEvent,
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
    from .config.runtime import get_config

    # Optional OAuth imports - may fail if google-auth is not installed
    try:
        from .auth.google_oauth2 import GoogleOAuth2Handler
        from .auth.oauth2_middleware import get_current_user
    except ImportError:
        # OAuth dependencies not available (e.g., in test environment)
        GoogleOAuth2Handler = None
        get_current_user = None
except ImportError:
    # Fallback for direct execution
    from memory.client import MemoryClient
    from memory.session_manager import MemorySessionManager
    from config.runtime import get_config

    # Optional OAuth imports - may fail if google-auth is not installed
    try:
        from auth.google_oauth2 import GoogleOAuth2Handler
        from auth.oauth2_middleware import get_current_user
    except ImportError:
        # OAuth dependencies not available (e.g., in test environment)
        GoogleOAuth2Handler = None
        get_current_user = None

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Suppress noisy AWS CRT cleanup errors (harmless cancellation errors during WebSocket cleanup)
logging.getLogger("awscrt").setLevel(logging.WARNING)
# Also suppress errors from concurrent.futures that are raised during cleanup
logging.getLogger("concurrent.futures").setLevel(logging.WARNING)


# Custom exception handler to suppress AWS CRT cleanup errors from background tasks
def suppress_awscrt_cleanup_error(exc_type: type[BaseException], exc_value: BaseException, exc_traceback: Any) -> None:
    """
    Suppress harmless AWS CRT cleanup errors that occur during WebSocket cleanup.

    This custom exception handler filters out InvalidStateError exceptions that
    contain "CANCELLED" in their message, as these are harmless race conditions
    that occur during WebSocket connection cleanup. All other exceptions are
    passed through to the default exception handler.

    Args:
        exc_type: The exception type.
        exc_value: The exception instance.
        exc_traceback: The traceback object.

    Returns:
        None. Suppresses the exception if it's a harmless cleanup error,
        otherwise calls the default exception handler.
    """
    if exc_type == InvalidStateError:
        error_str = str(exc_value)
        if "CANCELLED" in error_str or "cancelled" in error_str.lower():
            # Suppress this error - it's a harmless cleanup race condition
            logger.debug(f"Suppressed AWS CRT cleanup error: {exc_value}")
            return

    # For all other exceptions, use default handler
    import sys

    sys.__excepthook__(exc_type, exc_value, exc_traceback)


# Set custom exception handler
import sys

sys.excepthook = suppress_awscrt_cleanup_error

# Initialize FastAPI app
app = FastAPI(
    title="AgentCore Voice Agent", description="Bi-directional streaming voice agent with Amazon Nova Sonic", version="1.0.0"
)

# Add CORS middleware for CloudFront/API Gateway compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

# Audio configuration constants
VALID_SAMPLE_RATES = [16000, 24000, 48000]  # Valid sample rates for Nova Sonic
VALID_AUDIO_FORMATS = ["pcm", "wav"]  # Valid audio formats supported by Nova Sonic


def serialize_record(record: Dict[str, Any] | Any) -> Dict[str, Any] | str:
    """
    Convert datetime objects in record to strings for JSON serialization.

    Recursively processes dictionaries, lists, and objects to convert datetime
    objects to ISO format strings. Handles nested structures and object-like
    records that can be converted to dictionaries.

    Args:
        record: Dictionary, object, or other value to serialize. If it's an object
                with __dict__, it will be converted to a dict first.

    Returns:
        Serialized dictionary with datetime objects converted to ISO format strings,
        or a string representation if the record cannot be serialized as a dict.
    """
    from datetime import datetime

    if not isinstance(record, dict):
        # If it's not a dict, try to convert it
        if hasattr(record, "__dict__"):
            record = record.__dict__
        else:
            return str(record)

    serialized = {}
    for key, value in record.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        elif isinstance(value, dict):
            serialized[key] = serialize_record(value)
        elif isinstance(value, list):
            serialized[key] = [
                (
                    serialize_record(item)
                    if isinstance(item, dict)
                    else (item.isoformat() if isinstance(item, datetime) else item)
                )
                for item in value
            ]
        else:
            serialized[key] = value
    return serialized


def _get_api_info() -> Dict[str, Any]:
    """
    Get API information dictionary.

    Returns:
        Dictionary containing service information, endpoints, and configuration.
    """
    return {
        "service": "AgentCore Voice Agent",
        "description": "Bi-directional streaming voice agent with Amazon Nova Sonic",
        "endpoints": {
            "websocket": "/ws",
            "health": "/ping",
            "auth": {
                "login": "/api/auth/login",
                "callback": "/api/auth/callback",
                "me": "/api/auth/me",
                "logout": "/api/auth/logout",
            },
            "memory": {
                "query": "/api/memory/query",
                "sessions": "/api/memory/sessions",
                "preferences": "/api/memory/preferences",
            },
        },
        "model": MODEL_ID,
        "region": AWS_REGION,
        "memory_enabled": MEMORY_ENABLED,
        "auth_enabled": oauth2_handler is not None,
    }


def _sanitize_actor_id(actor_id: str) -> str:
    """
    Sanitize actor ID for use in namespace paths.

    Replaces special characters (@ and .) with underscores and ensures
    the ID starts with an alphanumeric character for compatibility with
    namespace requirements.

    Args:
        actor_id: The original actor ID (typically an email address).

    Returns:
        Sanitized actor ID safe for use in namespace paths.
    """
    sanitized = actor_id.replace("@", "_").replace(".", "_")
    if not sanitized[0].isalnum():
        sanitized = "user_" + sanitized
    return sanitized


async def _run_agent(
    agent: Any,  # BidiAgent - using Any to avoid forward reference issues
    ws_input: Any,  # WebSocketInput - defined later in file
    ws_output: Any,  # WebSocketOutput - defined later in file
) -> None:
    """
    Run the agent with WebSocket input and output handlers.

    Handles the agent execution loop and gracefully handles various termination
    conditions including normal disconnects, AWS CRT cleanup errors, and Nova Sonic
    timeout errors.

    Args:
        agent: The BidiAgent instance to run.
        ws_input: WebSocketInput handler for receiving events.
        ws_output: WebSocketOutput handler for sending events.

    Raises:
        InvalidStateError: If an unexpected InvalidStateError occurs (non-cleanup errors).
        Exception: If an unexpected error occurs during agent execution.
    """
    try:
        await agent.run(inputs=[ws_input], outputs=[ws_output])
        logger.debug("agent.run() completed normally")
    except (StopAsyncIteration, WebSocketDisconnect):
        # Normal termination - client disconnected
        logger.debug("Agent session ended (client disconnected)")
        return
    except InvalidStateError as e:
        # Suppress AWS CRT cleanup errors (harmless cancellation errors during WebSocket cleanup)
        if "CANCELLED" in str(e) or "cancelled" in str(e).lower():
            logger.debug(f"AWS CRT cleanup error (harmless): {e}")
            return
        else:
            logger.error(f"InvalidStateError inside agent.run(): {e}", exc_info=True)
            raise
    except Exception as e:
        # Check if it's a timeout error from Nova Sonic (expected when no audio input)
        error_str = str(e)
        if "Timed out waiting for audio bytes" in error_str:
            logger.info("Nova Sonic timeout (expected when no audio input) - ending session gracefully")
            return
        logger.error(f"Error inside agent.run(): {e}", exc_info=True)
        raise


def _check_namespace(bedrock_client: Any, memory_id: str, namespace: str, max_records_to_serialize: int = 3) -> Dict[str, Any]:
    """
    Check a namespace for memory records and return diagnostic information.

    Args:
        bedrock_client: Boto3 Bedrock AgentCore client instance.
        memory_id: The memory ID to query.
        namespace: The namespace path to check.
        max_records_to_serialize: Maximum number of records to include in serialized output.

    Returns:
        Dictionary containing namespace check results with keys:
        - namespace: The namespace that was checked
        - success: Boolean indicating if the check succeeded
        - record_count: Number of records found (if successful)
        - records: List of serialized records (if successful, limited to max_records_to_serialize)
        - error: Error message (if failed)
        - error_code: AWS error code (if failed, ClientError only)
    """
    from botocore.exceptions import ClientError

    try:
        response = bedrock_client.list_memory_records(memoryId=memory_id, namespace=namespace, maxResults=10)
        records = response.get("memoryRecordSummaries", response.get("memoryRecords", []))
        for record in records:
            if isinstance(record, dict) and "namespace" not in record:
                record["namespace"] = namespace

        # Serialize records to handle datetime objects
        serialized_records = [serialize_record(r) for r in records[:max_records_to_serialize]] if records else []

        return {"namespace": namespace, "record_count": len(records), "records": serialized_records, "success": True}
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", "")
        return {"namespace": namespace, "error": error_msg, "error_code": error_code, "success": False}
    except Exception as e:
        return {"namespace": namespace, "error": str(e), "success": False}


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
    "Provide clear, concise responses and use tools when appropriate.",
)


def create_nova_sonic_model() -> BidiNovaSonicModel:
    """
    Create and configure Nova Sonic model for bi-directional streaming.

    Initializes a BidiNovaSonicModel instance with configuration from environment
    variables or defaults. Configures audio settings including sample rates and
    voice selection.

    Returns:
        Configured BidiNovaSonicModel instance ready for use with BidiAgent.
    """
    return BidiNovaSonicModel(
        region=AWS_REGION,
        model_id=MODEL_ID,
        provider_config={
            "audio": {
                "input_sample_rate": INPUT_SAMPLE_RATE,
                "output_sample_rate": OUTPUT_SAMPLE_RATE,
                "voice": VOICE,
            }
        },
    )


def create_agent(model: BidiNovaSonicModel, system_prompt: Optional[str] = None) -> BidiAgent:
    """
    Create Strands BidiAgent with tools and system prompt.

    Initializes a BidiAgent instance with the provided model, configured tools
    (calculator, weather, database), and system prompt. If no system prompt is
    provided, uses the default SYSTEM_PROMPT.

    Args:
        model: The BidiNovaSonicModel instance to use for the agent.
        system_prompt: Optional custom system prompt. If None, uses SYSTEM_PROMPT.

    Returns:
        Configured BidiAgent instance ready for bi-directional streaming.
    """
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
    into WebSocket messages that the client can process. Handles various
    event types including audio streams, transcripts, tool usage, and
    connection lifecycle events. Optionally integrates with memory session
    management to store conversation history.

    The class processes events from the BidiAgent and formats them as JSON
    messages sent over the WebSocket connection. It also handles graceful
    shutdown and error conditions.
    """

    def __init__(self, websocket: WebSocket, session_manager: Optional[MemorySessionManager] = None):
        """
        Initialize WebSocketOutput handler.

        Args:
            websocket: The WebSocket connection to send events to.
            session_manager: Optional memory session manager for storing
                           conversation history. If provided, transcripts
                           and tool usage will be stored in memory.
        """
        self.websocket = websocket
        self.session_manager = session_manager
        self._stopped = False
        self._event_count = 0
        self._current_transcript = ""

    async def start(self, agent: BidiAgent) -> None:
        """
        Start the output handler.

        Resets internal state to prepare for processing output events.
        Should be called before the agent starts running.

        Args:
            agent: The BidiAgent instance (unused but required by protocol).
        """
        self._stopped = False
        self._event_count = 0

    async def stop(self) -> None:
        """
        Stop the output handler.

        Signals that the handler should stop processing events. After
        calling this, the __call__ method will return early without
        processing events.
        """
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
            # Log all received events for debugging
            logger.debug(f"[OUTPUT] Received event type: {type(event).__name__}")

            # Handle different event types
            if isinstance(event, BidiAudioStreamEvent):
                # Audio stream event - send audio data
                await self.websocket.send_json(
                    {"type": "audio", "data": event.audio, "format": event.format, "sample_rate": event.sample_rate}
                )
                logger.debug(f"Sent audio stream: {len(event.audio)} chars, format={event.format}, rate={event.sample_rate}")

            elif isinstance(event, BidiTranscriptStreamEvent):
                # Transcript stream event - can be user or assistant transcript
                # Use the role to determine if it's user or agent speech
                # Only send final transcripts to avoid duplicates from incremental updates
                role = getattr(event, "role", "assistant")  # Default to assistant if role not present
                is_final = getattr(event, "is_final", False)

                logger.info(
                    f"[OUTPUT] Transcript event - role: {role}, final: {is_final}, text: {event.text[:100] if event.text else 'empty'}"
                )

                if is_final:
                    await self.websocket.send_json({"type": "transcript", "data": event.text, "role": role})
                    logger.info(f"[OUTPUT] Sent final transcript ({role}): {event.text}")

                    # Store in memory if session manager is available
                    if self.session_manager:
                        if role == "assistant":
                            self.session_manager.store_agent_response(audio_transcript=event.text)
                        elif role == "user":
                            self.session_manager.store_user_input(audio_transcript=event.text)
                else:
                    # Log incremental updates at debug level but don't send to client
                    logger.debug(f"Incremental transcript ({role}): {event.text}")

            elif isinstance(event, BidiResponseStartEvent):
                logger.info("Agent response started")
                await self.websocket.send_json({"type": "response_start"})

            elif isinstance(event, BidiResponseCompleteEvent):
                logger.info("Agent response completed")
                await self.websocket.send_json({"type": "response_complete"})

            elif isinstance(event, BidiErrorEvent):
                logger.error(f"Agent error: {event.error}")
                await self.websocket.send_json({"type": "error", "message": str(event.error)})
            elif isinstance(event, BidiConnectionStartEvent):
                logger.info("Agent connection started")
                await self.websocket.send_json({"type": "connection_start"})
            elif isinstance(event, BidiConnectionCloseEvent):
                logger.info("Agent connection closed")
                await self.websocket.send_json({"type": "connection_close"})
            elif isinstance(event, ToolUseStreamEvent):
                tool_name = getattr(event, "tool_name", "unknown")
                tool_content = str(getattr(event, "content", ""))[:200]
                logger.info(f"Tool use: {tool_name}")
                await self.websocket.send_json({"type": "tool_use", "tool": tool_name, "data": tool_content})

                # Store tool use in memory if session manager is available
                if self.session_manager:
                    # Try to extract input/output from event
                    input_data = getattr(event, "input", {})
                    output_data = {"content": tool_content}
                    self.session_manager.store_tool_use(tool_name=tool_name, input_data=input_data, output_data=output_data)
            else:
                # Log unhandled event types at debug level
                event_type = type(event).__name__
                logger.debug(f"Unhandled event type: {event_type}")

        except (WebSocketDisconnect, RuntimeError) as e:
            logger.debug(f"WebSocket closed while sending output: {e}")
            self._stopped = True
        except InvalidStateError as e:
            # Suppress AWS CRT cleanup errors (harmless cancellation errors during WebSocket cleanup)
            if "CANCELLED" in str(e) or "cancelled" in str(e).lower():
                logger.debug(f"AWS CRT cleanup error (harmless): {e}")
            else:
                logger.error(f"InvalidStateError sending output event: {e}", exc_info=True)
                raise
        except Exception as e:
            logger.error(f"Error sending output event: {e}", exc_info=True)


class WebSocketInput:
    """
    BidiInput implementation that reads from a WebSocket connection.

    Implements the BidiInput protocol to convert WebSocket messages
    into BidiInputEvent objects that the agent can process. Supports
    both audio and text input modes, with validation and error handling
    for audio format and sample rate requirements. Optionally integrates
    with memory session management to store user inputs.

    The class reads JSON messages from the WebSocket, validates audio
    format and sample rate constraints, and converts them to appropriate
    BidiInputEvent instances for the agent to process.
    """

    def __init__(self, websocket: WebSocket, session_manager: Optional[MemorySessionManager] = None):
        """
        Initialize WebSocketInput handler.

        Args:
            websocket: The WebSocket connection to read events from.
            session_manager: Optional memory session manager for storing
                           user inputs. If provided, text inputs will be
                           stored in memory.
        """
        self.websocket = websocket
        self.session_manager = session_manager
        self._stopped = False
        self._last_input_type = None  # Track 'audio' or 'text'
        self._text_pending = False  # Flag for pending text input

    async def start(self, agent: BidiAgent) -> None:
        """
        Start the input source.

        Resets internal state to prepare for reading input events.
        Should be called before the agent starts running.

        Args:
            agent: The BidiAgent instance (unused but required by protocol).
        """
        self._stopped = False

    async def stop(self) -> None:
        """
        Stop the input source.

        Signals that the handler should stop reading events. After
        calling this, _read_next will raise StopAsyncIteration.
        """
        self._stopped = True

    def __call__(self) -> Awaitable[BidiTextInputEvent | BidiAudioInputEvent]:
        """
        Read input data from the WebSocket.

        Returns:
            Coroutine that resolves to a BidiInputEvent (text or audio)
        """
        return self._read_next()

    async def _read_next(self) -> BidiTextInputEvent | BidiAudioInputEvent:
        """
        Read the next event from the WebSocket.

        Receives JSON data from the WebSocket connection and converts it
        to an appropriate BidiInputEvent. Supports both audio and text input
        formats. Validates audio format and sample rate, and handles errors
        gracefully.

        Returns:
            BidiTextInputEvent or BidiAudioInputEvent based on the received data.

        Raises:
            StopAsyncIteration: If the WebSocket is disconnected or stopped.
            Exception: If an error occurs while reading from the WebSocket.
        """
        if self._stopped:
            raise StopAsyncIteration

        try:
            # Receive data from client
            data = await self.websocket.receive_json()

            # Convert to appropriate event type
            if "audio" in data:
                # Audio input - base64 encoded audio data
                self._last_input_type = "audio"
                audio_data = data["audio"]
                sample_rate = data.get("sample_rate", INPUT_SAMPLE_RATE)
                # Ensure sample_rate is one of the valid values
                if sample_rate not in VALID_SAMPLE_RATES:
                    sample_rate = 16000  # Default to 16000 if invalid

                format_type = data.get("format", "pcm")  # Default to PCM (required by Nova Sonic)
                # Nova Sonic requires Linear PCM format
                if format_type not in VALID_AUDIO_FORMATS:
                    error_msg = (
                        f"Invalid audio format '{format_type}'. "
                        f"Supported formats: {', '.join(VALID_AUDIO_FORMATS)}. "
                        "Please convert audio to PCM on the client side before sending."
                    )
                    logger.warning(f"[AUDIO INPUT] {error_msg}")
                    # Skip this invalid chunk and read the next message
                    # Note: We can't send error back through input handler, so we log and continue
                    return await self._read_next()

                logger.debug(
                    f"[AUDIO INPUT] Received audio chunk: {len(audio_data)} chars, format={format_type}, sample_rate={sample_rate}"
                )

                # Create the audio input event
                audio_event = BidiAudioInputEvent(
                    audio=audio_data,
                    format=format_type,
                    sample_rate=sample_rate,
                    channels=data.get("channels", 1),  # Default to mono
                )

                return audio_event
            elif "text" in data:
                text = data["text"]
                logger.info(f"[TEXT INPUT] Received text message: {text}")
                logger.debug(
                    f"[TEXT INPUT] WebSocket state: {self.websocket.client_state if hasattr(self.websocket, 'client_state') else 'unknown'}"
                )
                logger.debug(f"[TEXT INPUT] Session manager: {self.session_manager is not None}")
                self._last_input_type = "text"

                # Store user input in memory if session manager is available
                if self.session_manager:
                    try:
                        self.session_manager.store_user_input(text=text)
                        logger.debug(f"[TEXT INPUT] Stored in memory")
                    except Exception as e:
                        logger.warning(f"[TEXT INPUT] Failed to store in memory: {e}")

                # Create text event
                try:
                    text_event = BidiTextInputEvent(text=text)
                    logger.info(f"[TEXT INPUT] Created BidiTextInputEvent successfully")
                    logger.debug(f"[TEXT INPUT] Event type: {type(text_event)}, text: {text_event.text}")
                    return text_event
                except Exception as e:
                    logger.error(f"[TEXT INPUT] Failed to create BidiTextInputEvent: {e}", exc_info=True)
                    raise
            else:
                # Unknown data format - log details and attempt to handle as text
                received_keys = list(data.keys()) if isinstance(data, dict) else "non-dict"
                logger.warning(
                    f"[INPUT] Received unknown data format with keys: {received_keys}. " "Attempting to process as text input."
                )
                # Default to text if format is unknown
                text_content = str(data) if not isinstance(data, dict) else data.get("text", str(data))
                return BidiTextInputEvent(text=text_content)

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

    This endpoint accepts WebSocket connections for real-time voice interactions.
    If a session_id is provided as a query parameter, it will reuse that session
    instead of creating a new one. This allows session continuity when switching
    from text mode to voice mode.

    Args:
        websocket: WebSocket connection instance.

    Note:
        Query parameters are standard for WebSocket handshakes and are supported
        by API Gateway v2 WebSocket API. The token and session_id are passed as
        query parameters for authentication and session management.

    Raises:
        WebSocketDisconnect: If the connection is closed unexpectedly.
    """
    # Get token and session_id from query parameters
    token = websocket.query_params.get("token")
    session_id = websocket.query_params.get("session_id")
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
        # Use provided session_id (from query param) or create new one
        # This allows reusing sessions when switching from text to voice mode
        session_manager = MemorySessionManager(memory_client, actor_id=actor_id, session_id=session_id)
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
            await _run_agent(agent, ws_input, ws_output)

        except (StopAsyncIteration, WebSocketDisconnect):
            # Normal termination - already handled in run_agent
            pass
        except InvalidStateError as e:
            # Suppress AWS CRT cleanup errors (harmless cancellation errors during WebSocket cleanup)
            if "CANCELLED" in str(e) or "cancelled" in str(e).lower():
                logger.debug(f"AWS CRT cleanup error (harmless): {e}")
            else:
                logger.error(f"InvalidStateError in agent.run(): {e}", exc_info=True)
                raise
        except Exception as e:
            logger.error(f"Error in agent.run(): {e}", exc_info=True)
            # Try to send error to client
            try:
                await websocket.send_json({"type": "error", "message": f"Agent error: {str(e)}"})
            except:
                pass
            raise

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except (StopAsyncIteration, asyncio.CancelledError):
        # Normal termination - client disconnected or agent stopped
        logger.debug("Agent session ended normally")
    except InvalidStateError as e:
        # Suppress AWS CRT cleanup errors (harmless cancellation errors during WebSocket cleanup)
        if "CANCELLED" in str(e) or "cancelled" in str(e).lower():
            logger.debug(f"AWS CRT cleanup error (harmless): {e}")
        else:
            logger.error(f"InvalidStateError in websocket_endpoint: {e}", exc_info=True)
            raise
    except Exception as e:
        # Check if it's a timeout error from Nova Sonic (expected when no audio input for a while)
        error_str = str(e)
        if "Timed out waiting for audio bytes" in error_str:
            logger.info("Nova Sonic timeout (expected when no audio input) - session ended normally")
        else:
            logger.error(f"Error in websocket_endpoint: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except (WebSocketDisconnect, RuntimeError):
            # WebSocket already closed, ignore
            pass
    finally:
        # Finalize memory session
        if session_manager:
            await session_manager.finalize()
        logger.info("WebSocket session ended")


@app.get("/health")
async def health() -> Dict[str, str]:
    """
    Health check endpoint for load balancers and monitoring.

    Returns:
        Dictionary with keys:
        - status: Always "healthy"
        - service: Service name "voice"
    """
    return {"status": "healthy", "service": "voice"}


@app.get("/ping")
async def health_check() -> JSONResponse:
    """
    Health check endpoint required by AgentCore Runtime.

    Returns:
        JSONResponse containing:
        - status: "healthy"
        - service: "agentcore-scaffold"
        - version: "1.0.0"
    """
    return JSONResponse(content={"status": "healthy", "service": "agentcore-scaffold", "version": "1.0.0"})


# Vision routes are handled by the orchestrator agent (port 9000), not the voice agent


@app.post("/api/sessions")
async def create_session(
    request: Request, user: Dict[str, Any] = Depends(get_current_user), session_id: Optional[str] = None
) -> Dict[str, str]:
    """
    Create a new session or reuse an existing session.

    This endpoint creates a new memory session for the authenticated user.
    If a session_id is provided in the request body or query parameter, it will
    reuse that session instead of creating a new one. This allows session continuity
    when switching between voice and text modes.

    Args:
        request: FastAPI request object (may contain session_id in body)
        user: Authenticated user information from OAuth2 middleware.
        session_id: Optional session ID from query parameter to reuse. If not provided,
                   a new session will be created.

    Returns:
        Dict containing the session_id.

    Raises:
        HTTPException: If authentication fails or memory client is unavailable.
    """
    if not memory_client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Memory not enabled")

    # Try to get session_id from request body if not in query param
    if not session_id:
        try:
            body = await request.json()
            session_id = body.get("session_id")
        except Exception:
            pass  # No body or not JSON

    actor_id = user.get("email", "anonymous")
    # If session_id provided, reuse it; otherwise create new
    session_manager = MemorySessionManager(memory_client, actor_id=actor_id, session_id=session_id)
    await session_manager.initialize()
    return {"session_id": session_manager.session_id}


# Authentication endpoints
@app.get("/api/auth/login")
async def login(request: Request) -> RedirectResponse:
    """
    Initiate Google OAuth2 login.

    Redirects the user to Google's OAuth2 authorization page. If a state
    parameter is provided in the query string, it will be preserved through
    the OAuth flow.

    Args:
        request: FastAPI request object. May contain optional "state" query parameter.

    Returns:
        RedirectResponse to Google OAuth2 authorization URL.

    Raises:
        HTTPException: 503 if OAuth2 is not configured.
    """
    if not oauth2_handler:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OAuth2 not configured")

    state = request.query_params.get("state")
    auth_url, state_value = oauth2_handler.get_authorization_url(state=state)
    return RedirectResponse(url=auth_url)


@app.get("/api/auth/callback")
async def auth_callback(request: Request, code: str, state: Optional[str] = None) -> RedirectResponse:
    """
    Handle OAuth2 callback from Google.

    Processes the authorization code returned by Google after user
    authentication and exchanges it for an access token. Redirects
    the user back to the frontend with the token in the query string.

    Args:
        request: FastAPI request object.
        code: Authorization code from Google OAuth2 callback.
        state: Optional state parameter for CSRF protection.

    Returns:
        RedirectResponse to frontend with token in query string.

    Raises:
        HTTPException: 503 if OAuth2 is not configured, 401 if callback fails.
    """
    if not oauth2_handler:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OAuth2 not configured")

    try:
        result = await oauth2_handler.handle_callback(code=code, state=state)
        # Redirect to frontend with token
        # In production, use httpOnly cookie instead
        redirect_url = f"/?token={result['token']}"
        return RedirectResponse(url=redirect_url)
    except ValueError as e:
        logger.error(f"OAuth2 callback error: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@app.get("/api/auth/me")
async def get_me(request: Request, user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    """
    Get current authenticated user information.

    Returns the user information extracted from the authentication token.
    Requires valid authentication via OAuth2.

    Args:
        request: FastAPI request object.
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing user information dictionary.
    """
    return JSONResponse(content=user)


@app.post("/api/auth/logout")
async def logout() -> JSONResponse:
    """
    Logout endpoint.

    Note: This endpoint does not invalidate server-side tokens. The client
    should clear the token from local storage or cookies.

    Returns:
        JSONResponse with logout confirmation message.
    """
    return JSONResponse(content={"message": "Logged out"})


# Memory API endpoints
@app.post("/api/memory/query")
async def query_memories(
    request: Request, query: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)
) -> JSONResponse:
    """
    Query memories for current user.

    Searches the user's memory records using semantic search or namespace
    filtering. Supports querying summaries, preferences, and semantic memories.

    Args:
        request: FastAPI request object.
        query: Dictionary containing:
            - query: Optional search query text for semantic search
            - namespace: Optional namespace prefix to filter by
            - memory_type: Optional type filter ("summaries", "preferences", "semantic")
            - top_k: Optional number of results to return (default: 5)
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing:
        - memories: List of memory records with content and namespace

    Raises:
        HTTPException: 503 if memory is not enabled.
    """
    if not memory_client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Memory not enabled")

    actor_id = user.get("email")
    query_text = query.get("query", "")
    namespace_prefix = query.get("namespace")
    memory_type = query.get("memory_type")  # "summaries", "preferences", or "semantic"

    memories = memory_client.retrieve_memories(
        actor_id=actor_id,
        query=query_text if query_text else None,
        namespace_prefix=namespace_prefix,
        top_k=query.get("top_k", 5),
        memory_type=memory_type,
    )

    # Format memories for frontend
    formatted_memories = []
    for m in memories:
        if isinstance(m, dict):
            content = m.get("content", {})
            if isinstance(content, dict):
                text = content.get("text", "")
            else:
                text = str(content) if content else ""

            formatted_memories.append({"content": text, "namespace": m.get("namespace", "")})
        else:
            # Fallback for object-like records
            content_attr = getattr(m, "content", None)
            if content_attr and isinstance(content_attr, dict):
                text = content_attr.get("text", "")
            elif content_attr:
                text = str(content_attr)
            else:
                text = str(m)

            formatted_memories.append({"content": text, "namespace": getattr(m, "namespace", "")})

    return JSONResponse(content={"memories": formatted_memories})


@app.get("/api/memory/sessions")
async def list_sessions(user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    """
    List user's memory sessions.

    Retrieves all memory sessions for the authenticated user, including
    session IDs and summaries.

    Args:
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing:
        - sessions: List of session dictionaries with session_id and summary

    Raises:
        HTTPException: 503 if memory is not enabled.
    """
    if not memory_client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Memory not enabled")

    actor_id = user.get("email")
    sessions = memory_client.list_sessions(actor_id=actor_id)

    # Ensure sessions are properly formatted
    formatted_sessions = []
    for session in sessions:
        if isinstance(session, dict):
            formatted_sessions.append(
                {"session_id": session.get("session_id", ""), "summary": session.get("summary", "No summary available")}
            )
        else:
            formatted_sessions.append(
                {
                    "session_id": getattr(session, "session_id", ""),
                    "summary": getattr(session, "summary", "No summary available"),
                }
            )

    return JSONResponse(content={"sessions": formatted_sessions})


@app.get("/api/memory/sessions/{session_id}")
async def get_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    """
    Get session details and summary.

    Retrieves detailed information about a specific memory session, including
    the session summary and full record data.

    Args:
        session_id: The session ID to retrieve.
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing:
        - session_id: The session ID
        - namespace: The session namespace
        - summary: The session summary text
        - full_record: The complete serialized session record

    Raises:
        HTTPException: 503 if memory is not enabled, 404 if session not found.
    """
    if not memory_client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Memory not enabled")

    actor_id = user.get("email")
    summary_record = memory_client.get_session_summary(actor_id=actor_id, session_id=session_id)

    if not summary_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Format summary for frontend
    if isinstance(summary_record, dict):
        content = summary_record.get("content", {})
        if isinstance(content, dict):
            text = content.get("text", "")
        else:
            text = str(content) if content else ""

        # Serialize the full record to handle datetime objects
        serialized_record = serialize_record(summary_record)

        return JSONResponse(
            content={
                "session_id": session_id,
                "namespace": summary_record.get("namespace", ""),
                "summary": text,
                "full_record": serialized_record,
            }
        )
    else:
        # Fallback for object-like records
        content_attr = getattr(summary_record, "content", None)
        if content_attr and isinstance(content_attr, dict):
            text = content_attr.get("text", "")
        elif content_attr:
            text = str(content_attr)
        else:
            text = str(summary_record)

        return JSONResponse(
            content={
                "session_id": session_id,
                "namespace": getattr(summary_record, "namespace", ""),
                "summary": text,
                "full_record": str(summary_record),
            }
        )


@app.delete("/api/memory/sessions/{session_id}")
async def delete_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    """Delete a session's memories."""
    # This would require additional implementation
    return JSONResponse(content={"message": "Session deleted"})


@app.get("/api/memory/preferences")
async def get_preferences(user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    """
    Get user preferences from memory.

    Retrieves all preference records stored in memory for the authenticated user.

    Args:
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing:
        - preferences: List of preference records with content and namespace

    Raises:
        HTTPException: 503 if memory is not enabled.
    """
    if not memory_client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Memory not enabled")

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

            formatted_prefs.append({"content": text, "namespace": p.get("namespace", "")})
        else:
            # Fallback for object-like records
            content_attr = getattr(p, "content", None)
            if content_attr and hasattr(content_attr, "get"):
                text = content_attr.get("text", "")
            elif content_attr:
                text = str(content_attr)
            else:
                text = str(p)

            formatted_prefs.append({"content": text, "namespace": getattr(p, "namespace", "")})

    return JSONResponse(content={"preferences": formatted_prefs})


@app.post("/api/memory/diagnose")
async def diagnose_memory(
    request: Request, query: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)
) -> JSONResponse:
    """
    Run comprehensive memory diagnostics.

    Performs diagnostic checks on various memory namespaces to help debug
    memory-related issues. Checks parent namespace, exact session namespace
    (if provided), semantic namespace, and preferences namespace.

    Args:
        request: FastAPI request object.
        query: Dictionary containing:
            - session_id: Optional session ID for exact namespace check
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing diagnostic information:
        - user_id: Original user ID
        - sanitized_user_id: Sanitized user ID used in namespaces
        - session_id: Session ID if provided
        - memory_id: Memory resource ID
        - region: AWS region
        - checks: Dictionary of namespace check results
        - total_records: Total number of records found across all namespaces

    Raises:
        HTTPException: 503 if memory is not enabled.
    """
    if not memory_client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Memory not enabled")

    import boto3
    from botocore.exceptions import ClientError

    actor_id = user.get("email")
    session_id = query.get("session_id")

    # Sanitize actor_id
    sanitized_actor_id = _sanitize_actor_id(actor_id)

    diagnostics = {
        "user_id": actor_id,
        "sanitized_user_id": sanitized_actor_id,
        "session_id": session_id,
        "memory_id": memory_client.memory_id,
        "region": memory_client.region,
        "checks": {},
    }

    bedrock_client = boto3.client("bedrock-agentcore", region_name=memory_client.region)

    # Check 1: Parent namespace (summaries/{actorId})
    parent_ns = f"/summaries/{sanitized_actor_id}"
    diagnostics["checks"]["parent_namespace"] = _check_namespace(bedrock_client, memory_client.memory_id, parent_ns)

    # Check 2: Exact session namespace (if session_id provided)
    if session_id:
        exact_ns = f"/summaries/{sanitized_actor_id}/{session_id}"
        diagnostics["checks"]["exact_namespace"] = _check_namespace(
            bedrock_client, memory_client.memory_id, exact_ns, max_records_to_serialize=10
        )

    # Check 3: Semantic namespace
    semantic_ns = f"/semantic/{sanitized_actor_id}"
    diagnostics["checks"]["semantic_namespace"] = _check_namespace(bedrock_client, memory_client.memory_id, semantic_ns)

    # Check 4: Preferences namespace
    prefs_ns = f"/preferences/{sanitized_actor_id}"
    diagnostics["checks"]["preferences_namespace"] = _check_namespace(bedrock_client, memory_client.memory_id, prefs_ns)

    # Calculate total records
    total_records = 0
    for check in diagnostics["checks"].values():
        if check.get("success") and "record_count" in check:
            total_records += check["record_count"]

    diagnostics["total_records"] = total_records

    return JSONResponse(content=diagnostics)


@app.get("/", response_model=None)
async def root():
    """
    Serve the frontend HTML file or return API information.

    If the frontend index.html file exists, serves it. Otherwise, returns
    API information as JSON.

    Returns:
        FileResponse if index.html exists, otherwise JSONResponse with API info.
    """
    index_path = client_web_path / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))

    # Fallback to API info if frontend not found
    return JSONResponse(content=_get_api_info())


@app.get("/api")
async def api_info() -> JSONResponse:
    """
    API information endpoint.

    Returns comprehensive information about the API including available
    endpoints, configuration, and service status.

    Returns:
        JSONResponse containing:
        - service: Service name
        - description: Service description
        - endpoints: Dictionary of available endpoints
        - model: Model ID in use
        - region: AWS region
        - memory_enabled: Whether memory is enabled
        - auth_enabled: Whether authentication is enabled
    """
    return JSONResponse(content=_get_api_info())


if __name__ == "__main__":
    import uvicorn

    # Run the application
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
