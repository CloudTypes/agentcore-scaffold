"""
AgentCore Bi-Directional Streaming Voice Agent
Main application with WebSocket endpoint for real-time voice conversations
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator, Dict, Any, Awaitable, Optional, Union
from datetime import datetime
from concurrent.futures._base import InvalidStateError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
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
import boto3
from botocore.exceptions import ClientError

# Import custom tools (from src/tools)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
from tools.calculator import calculator
from tools.weather import weather_api
from tools.database import database_query

# Import memory and auth modules (from src/)
from memory.client import MemoryClient
from memory.session_manager import MemorySessionManager
from auth.google_oauth2 import GoogleOAuth2Handler
from auth.oauth2_middleware import get_current_user
from config.runtime import get_config

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Suppress noisy AWS CRT cleanup errors (harmless cancellation errors during WebSocket cleanup)
logging.getLogger("awscrt").setLevel(logging.WARNING)
# Also suppress errors from concurrent.futures that are raised during cleanup
logging.getLogger("concurrent.futures").setLevel(logging.WARNING)

# WebSocket message type constants
WS_MSG_TYPE_AUDIO = "audio"
WS_MSG_TYPE_TEXT = "text"
WS_MSG_TYPE_TRANSCRIPT = "transcript"
WS_MSG_TYPE_RESPONSE_START = "response_start"
WS_MSG_TYPE_RESPONSE_COMPLETE = "response_complete"
WS_MSG_TYPE_ERROR = "error"
WS_MSG_TYPE_CONNECTION_START = "connection_start"
WS_MSG_TYPE_CONNECTION_CLOSE = "connection_close"
WS_MSG_TYPE_TOOL_USE = "tool_use"

# Audio configuration constants
VALID_SAMPLE_RATES = [16000, 24000, 48000]
VALID_AUDIO_FORMATS = ["pcm", "wav"]
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_AUDIO_FORMAT = "pcm"
DEFAULT_CHANNELS = 1

# Role constants
ROLE_ASSISTANT = "assistant"
ROLE_USER = "user"


# Custom exception handler to suppress AWS CRT cleanup errors from background tasks
def suppress_awscrt_cleanup_error(exc_type, exc_value, exc_traceback):
    """
    Suppress harmless AWS CRT cleanup errors that occur during WebSocket cleanup.

    This custom exception handler filters out InvalidStateError exceptions that
    contain "CANCELLED" or "cancelled" in their message, as these are harmless
    race conditions that occur during WebSocket connection cleanup.

    Args:
        exc_type: Exception type.
        exc_value: Exception value.
        exc_traceback: Exception traceback.
    """
    if exc_type == InvalidStateError:
        error_str = str(exc_value)
        if "CANCELLED" in error_str or "cancelled" in error_str.lower():
            # Suppress this error - it's a harmless cleanup race condition
            logger.debug(f"Suppressed AWS CRT cleanup error: {exc_value}")
            return

    # For all other exceptions, use default handler
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


# Set custom exception handler
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

# Get the project root directory (agents/voice/app.py -> agents/voice -> agents -> project root)
# Note: project_root was already calculated above for sys.path, reuse it
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
        logger.warning(f"Failed to initialize memory client: {e}. Voice agent will continue without memory features.")
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


# ============================================================================
# Helper Functions
# ============================================================================


def serialize_record(record: Union[Dict[str, Any], Any]) -> Union[Dict[str, Any], str]:
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


def format_memory_record(record: Union[Dict[str, Any], Any]) -> Dict[str, str]:
    """
    Format a memory record for frontend consumption.

    Extracts content text and namespace from a memory record, handling both
    dictionary and object-like records.

    Args:
        record: Memory record (dict or object with content/namespace attributes).

    Returns:
        Dictionary with 'content' and 'namespace' keys.
    """
    if isinstance(record, dict):
        content = record.get("content", {})
        if isinstance(content, dict):
            text = content.get("text", "")
        else:
            text = str(content) if content else ""

        return {"content": text, "namespace": record.get("namespace", "")}
    else:
        # Fallback for object-like records
        content_attr = getattr(record, "content", None)
        if content_attr and isinstance(content_attr, dict):
            text = content_attr.get("text", "")
        elif content_attr:
            text = str(content_attr)
        else:
            text = str(record)

        return {"content": text, "namespace": getattr(record, "namespace", "")}


def format_preference_record(record: Union[Dict[str, Any], Any]) -> Dict[str, str]:
    """
    Format a preference record for frontend consumption.

    Extracts content text and namespace from a preference record, handling both
    dictionary and object-like records.

    Args:
        record: Preference record (dict or object with content/namespace attributes).

    Returns:
        Dictionary with 'content' and 'namespace' keys.
    """
    if isinstance(record, dict):
        content = record.get("content", {})
        if isinstance(content, dict):
            text = content.get("text", "")
        else:
            text = str(content) if content else ""

        return {"content": text, "namespace": record.get("namespace", "")}
    else:
        # Fallback for object-like records
        content_attr = getattr(record, "content", None)
        if content_attr and hasattr(content_attr, "get"):
            text = content_attr.get("text", "")
        elif content_attr:
            text = str(content_attr)
        else:
            text = str(record)

        return {"content": text, "namespace": getattr(record, "namespace", "")}


def _sanitize_actor_id(actor_id: str) -> str:
    """
    Sanitize actor ID for use in namespace paths.

    Replaces special characters (@, .) with underscores and ensures the
    ID starts with an alphanumeric character.

    Args:
        actor_id: Original actor ID (typically an email address).

    Returns:
        Sanitized actor ID safe for use in namespace paths.
    """
    sanitized = actor_id.replace("@", "_").replace(".", "_")
    if not sanitized[0].isalnum():
        sanitized = "user_" + sanitized
    return sanitized


def _check_namespace(
    bedrock_client: Any, memory_id: str, namespace: str, max_results: int = 10, sample_size: Optional[int] = None
) -> Dict[str, Any]:
    """
    Check a namespace for memory records.

    Queries the Bedrock AgentCore client for records in the specified namespace
    and returns diagnostic information including record count and sample records.

    Args:
        bedrock_client: Boto3 Bedrock AgentCore client instance.
        memory_id: Memory ID to query.
        namespace: Namespace path to check.
        max_results: Maximum number of records to retrieve (default: 10).
        sample_size: Number of records to include in sample (default: 3, or all if None).

    Returns:
        Dictionary containing:
            - namespace: The namespace that was checked.
            - record_count: Number of records found.
            - records: Sample of serialized records (if any).
            - success: Boolean indicating if the check succeeded.
            - error: Error message (if check failed).
            - error_code: AWS error code (if check failed).
    """
    try:
        response = bedrock_client.list_memory_records(memoryId=memory_id, namespace=namespace, maxResults=max_results)
        records = response.get("memoryRecordSummaries", response.get("memoryRecords", []))
        for record in records:
            if isinstance(record, dict) and "namespace" not in record:
                record["namespace"] = namespace

        # Serialize records to handle datetime objects
        if sample_size is None:
            sample_size = len(records) if records else 0
        serialized_records = [serialize_record(r) for r in records[:sample_size]] if records else []

        return {"namespace": namespace, "record_count": len(records), "records": serialized_records, "success": True}
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", "")
        return {"namespace": namespace, "error": error_msg, "error_code": error_code, "success": False}
    except Exception as e:
        return {"namespace": namespace, "error": str(e), "success": False}


# ============================================================================
# Model and Agent Creation
# ============================================================================


def create_nova_sonic_model() -> BidiNovaSonicModel:
    """
    Create and configure Nova Sonic model for bi-directional streaming.

    Returns:
        Configured BidiNovaSonicModel instance with audio settings.
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

    Args:
        model: BidiNovaSonicModel instance to use for the agent.
        system_prompt: Optional system prompt. If not provided, uses the default
                     SYSTEM_PROMPT from configuration.

    Returns:
        Configured BidiAgent instance with calculator, weather, and database tools.
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
    into WebSocket messages that the client can process.
    """

    def __init__(self, websocket: WebSocket, session_manager: Optional[MemorySessionManager] = None):
        """
        Initialize WebSocket output handler.

        Args:
            websocket: WebSocket connection to send messages to.
            session_manager: Optional memory session manager for storing interactions.
        """
        self.websocket = websocket
        self.session_manager = session_manager
        self._stopped = False
        self._event_count = 0
        self._current_transcript = ""

    async def start(self, agent: BidiAgent) -> None:
        """
        Start the output handler.

        Args:
            agent: BidiAgent instance (required by protocol, not used here).
        """
        self._stopped = False
        self._event_count = 0

    async def stop(self) -> None:
        """
        Stop the output handler.

        Marks the handler as stopped, preventing further event processing.
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
                    {"type": WS_MSG_TYPE_AUDIO, "data": event.audio, "format": event.format, "sample_rate": event.sample_rate}
                )
                logger.debug(f"Sent audio stream: {len(event.audio)} chars, format={event.format}, rate={event.sample_rate}")

            elif isinstance(event, BidiTranscriptStreamEvent):
                # Transcript stream event - can be user or assistant transcript
                # Use the role to determine if it's user or agent speech
                # Only send final transcripts to avoid duplicates from incremental updates
                role = getattr(event, "role", ROLE_ASSISTANT)  # Default to assistant if role not present
                is_final = getattr(event, "is_final", False)

                logger.info(
                    f"[OUTPUT] Transcript event - role: {role}, final: {is_final}, text: {event.text[:100] if event.text else 'empty'}"
                )

                if is_final:
                    await self.websocket.send_json({"type": WS_MSG_TYPE_TRANSCRIPT, "data": event.text, "role": role})
                    logger.info(f"[OUTPUT] Sent final transcript ({role}): {event.text}")

                    # Store in memory if session manager is available
                    if self.session_manager:
                        if role == ROLE_ASSISTANT:
                            self.session_manager.store_agent_response(audio_transcript=event.text)
                        elif role == ROLE_USER:
                            self.session_manager.store_user_input(audio_transcript=event.text)
                else:
                    # Log incremental updates at debug level but don't send to client
                    logger.debug(f"Incremental transcript ({role}): {event.text}")

            elif isinstance(event, BidiResponseStartEvent):
                logger.info("Agent response started")
                await self.websocket.send_json({"type": WS_MSG_TYPE_RESPONSE_START})

            elif isinstance(event, BidiResponseCompleteEvent):
                logger.info("Agent response completed")
                await self.websocket.send_json({"type": WS_MSG_TYPE_RESPONSE_COMPLETE})

            elif isinstance(event, BidiErrorEvent):
                logger.error(f"Agent error: {event.error}")
                await self.websocket.send_json({"type": WS_MSG_TYPE_ERROR, "message": str(event.error)})
            elif isinstance(event, BidiConnectionStartEvent):
                logger.info("Agent connection started")
                await self.websocket.send_json({"type": WS_MSG_TYPE_CONNECTION_START})
            elif isinstance(event, BidiConnectionCloseEvent):
                logger.info("Agent connection closed")
                await self.websocket.send_json({"type": WS_MSG_TYPE_CONNECTION_CLOSE})
            elif isinstance(event, ToolUseStreamEvent):
                tool_name = getattr(event, "tool_name", "unknown")
                tool_content = str(getattr(event, "content", ""))[:200]
                logger.info(f"Tool use: {tool_name}")
                await self.websocket.send_json({"type": WS_MSG_TYPE_TOOL_USE, "tool": tool_name, "data": tool_content})

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
    into BidiInputEvent objects that the agent can process.
    """

    def __init__(self, websocket: WebSocket, session_manager: Optional[MemorySessionManager] = None):
        """
        Initialize WebSocket input handler.

        Args:
            websocket: WebSocket connection to read messages from.
            session_manager: Optional memory session manager for storing user inputs.
        """
        self.websocket = websocket
        self.session_manager = session_manager
        self._stopped = False
        self._last_input_type = None  # Track 'audio' or 'text'
        self._text_pending = False  # Flag for pending text input

    async def start(self, agent: BidiAgent) -> None:
        """
        Start the input source.

        Args:
            agent: BidiAgent instance (required by protocol, not used here).
        """
        self._stopped = False

    async def stop(self) -> None:
        """
        Stop the input source.

        Marks the handler as stopped, preventing further input reading.
        """
        self._stopped = True

    def __call__(self) -> Awaitable[BidiTextInputEvent | BidiAudioInputEvent]:
        """
        Read input data from the WebSocket.

        Returns:
            Coroutine that resolves to a BidiInputEvent (text or audio).
        """
        return self._read_next()

    async def _read_next(self) -> BidiTextInputEvent | BidiAudioInputEvent:
        """
        Read the next event from the WebSocket.

        Returns:
            BidiTextInputEvent or BidiAudioInputEvent based on received data.

        Raises:
            StopAsyncIteration: When the WebSocket is disconnected or stopped.
        """
        if self._stopped:
            raise StopAsyncIteration

        try:
            # Receive data from client
            data = await self.websocket.receive_json()

            # Convert to appropriate event type
            if WS_MSG_TYPE_AUDIO in data:
                # Audio input - base64 encoded audio data
                self._last_input_type = WS_MSG_TYPE_AUDIO
                audio_data = data[WS_MSG_TYPE_AUDIO]
                sample_rate = data.get("sample_rate", INPUT_SAMPLE_RATE)
                # Ensure sample_rate is one of the valid values
                if sample_rate not in VALID_SAMPLE_RATES:
                    sample_rate = DEFAULT_SAMPLE_RATE

                format_type = data.get("format", DEFAULT_AUDIO_FORMAT)
                # Nova Sonic requires Linear PCM format
                if format_type not in VALID_AUDIO_FORMATS:
                    logger.error(f"Received {format_type} format - Nova Sonic requires PCM format!")
                    logger.error("Please convert audio to PCM on the client side before sending")
                    # Skip this invalid chunk and read the next message
                    return await self._read_next()

                logger.debug(
                    f"[AUDIO INPUT] Received audio chunk: {len(audio_data)} chars, format={format_type}, sample_rate={sample_rate}"
                )

                # Create the audio input event
                audio_event = BidiAudioInputEvent(
                    audio=audio_data,
                    format=format_type,
                    sample_rate=sample_rate,
                    channels=data.get("channels", DEFAULT_CHANNELS),
                )

                return audio_event
            elif WS_MSG_TYPE_TEXT in data:
                text = data[WS_MSG_TYPE_TEXT]
                logger.info(f"[TEXT INPUT] Received text message: {text}")
                logger.debug(
                    f"[TEXT INPUT] WebSocket state: {self.websocket.client_state if hasattr(self.websocket, 'client_state') else 'unknown'}"
                )
                logger.debug(f"[TEXT INPUT] Session manager: {self.session_manager is not None}")
                self._last_input_type = WS_MSG_TYPE_TEXT

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
            async def run_agent():
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

            # Run the agent
            await run_agent()

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
                await websocket.send_json({"type": WS_MSG_TYPE_ERROR, "message": f"Agent error: {str(e)}"})
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
            await websocket.send_json({"type": WS_MSG_TYPE_ERROR, "message": str(e)})
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
    return JSONResponse(content={"status": "healthy", "service": "agentcore-scaffold", "version": "1.0.0"})


# Authentication endpoints
@app.get("/api/auth/login")
async def login(request: Request) -> RedirectResponse:
    """
    Initiate Google OAuth2 login.

    Redirects the user to Google's OAuth2 authorization page.

    Args:
        request: FastAPI request object containing optional 'state' query parameter.

    Returns:
        RedirectResponse to Google OAuth2 authorization URL.

    Raises:
        HTTPException: If OAuth2 handler is not configured.
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

    Processes the OAuth2 authorization code and redirects to the frontend
    with an authentication token.

    Args:
        request: FastAPI request object.
        code: Authorization code from Google OAuth2.
        state: Optional state parameter for CSRF protection.

    Returns:
        RedirectResponse to frontend with authentication token in query parameter.

    Raises:
        HTTPException: If OAuth2 handler is not configured or callback processing fails.
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
    Get current user information.

    Args:
        request: FastAPI request object.
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing user information.
    """
    return JSONResponse(content=user)


@app.post("/api/auth/logout")
async def logout() -> JSONResponse:
    """
    Logout endpoint (client should clear token).

    Note: This endpoint does not invalidate the token server-side.
    The client is responsible for clearing the token from storage.

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

    Retrieves memories from the memory client based on the provided query parameters.
    Supports filtering by namespace, memory type, and semantic search.

    Args:
        request: FastAPI request object.
        query: Dictionary containing query parameters:
            - query: Optional text query for semantic search.
            - namespace: Optional namespace prefix to filter memories.
            - memory_type: Optional memory type ("summaries", "preferences", or "semantic").
            - top_k: Optional number of results to return (default: 5).
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing a list of formatted memory records.

    Raises:
        HTTPException: If memory client is not enabled or unavailable.
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

    # Format memories for frontend using helper function
    formatted_memories = [format_memory_record(m) for m in memories]

    return JSONResponse(content={"memories": formatted_memories})


@app.get("/health")
async def health() -> Dict[str, str]:
    """
    Health check endpoint for load balancers and monitoring.

    Returns:
        Dict containing service status and name.
    """
    return {"status": "healthy", "service": "voice"}


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


@app.get("/api/memory/sessions")
async def list_sessions(user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    """
    List user's sessions.

    Retrieves all memory sessions for the authenticated user.

    Args:
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing a list of session records with session_id and summary.

    Raises:
        HTTPException: If memory client is not enabled or unavailable.
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

    Retrieves the full session record including summary and metadata for a
    specific session ID.

    Args:
        session_id: Unique identifier for the session.
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing session_id, namespace, summary, and full_record.

    Raises:
        HTTPException: If memory client is not enabled, unavailable, or session not found.
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
    """
    Delete a session's memories.

    Note: This endpoint currently returns a success message but does not
    actually delete the session. Full implementation would require additional
    memory client methods.

    Args:
        session_id: Unique identifier for the session to delete.
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse with deletion confirmation message.
    """
    # This would require additional implementation
    return JSONResponse(content={"message": "Session deleted"})


@app.get("/api/memory/preferences")
async def get_preferences(user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    """
    Get user preferences.

    Retrieves all preference records for the authenticated user.

    Args:
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing a list of formatted preference records.

    Raises:
        HTTPException: If memory client is not enabled or unavailable.
    """
    if not memory_client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Memory not enabled")

    actor_id = user.get("email")
    preferences = memory_client.get_user_preferences(actor_id=actor_id)

    # Format preferences for frontend using helper function
    formatted_prefs = [format_preference_record(p) for p in preferences]

    return JSONResponse(content={"preferences": formatted_prefs})


@app.post("/api/memory/diagnose")
async def diagnose_memory(
    request: Request, query: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)
) -> JSONResponse:
    """
    Run comprehensive memory diagnostics.

    Performs diagnostic checks on multiple memory namespaces to verify
    memory system health and retrieve sample records. Checks include:
    - Parent summaries namespace
    - Exact session namespace (if session_id provided)
    - Semantic memory namespace
    - Preferences namespace

    Args:
        request: FastAPI request object.
        query: Dictionary containing optional 'session_id' parameter.
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        JSONResponse containing diagnostic information including:
            - user_id: Original actor ID.
            - sanitized_user_id: Sanitized actor ID for namespaces.
            - session_id: Session ID if provided.
            - memory_id: Memory resource ID.
            - region: AWS region.
            - checks: Dictionary of namespace check results.
            - total_records: Total number of records across all namespaces.

    Raises:
        HTTPException: If memory client is not enabled or unavailable.
    """
    if not memory_client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Memory not enabled")

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
    diagnostics["checks"]["parent_namespace"] = _check_namespace(
        bedrock_client, memory_client.memory_id, parent_ns, sample_size=3
    )

    # Check 2: Exact session namespace (if session_id provided)
    if session_id:
        exact_ns = f"/summaries/{sanitized_actor_id}/{session_id}"
        diagnostics["checks"]["exact_namespace"] = _check_namespace(bedrock_client, memory_client.memory_id, exact_ns)

    # Check 3: Semantic namespace
    semantic_ns = f"/semantic/{sanitized_actor_id}"
    diagnostics["checks"]["semantic_namespace"] = _check_namespace(
        bedrock_client, memory_client.memory_id, semantic_ns, sample_size=3
    )

    # Check 4: Preferences namespace
    prefs_ns = f"/preferences/{sanitized_actor_id}"
    diagnostics["checks"]["preferences_namespace"] = _check_namespace(
        bedrock_client, memory_client.memory_id, prefs_ns, sample_size=3
    )

    # Calculate total records
    total_records = 0
    for check in diagnostics["checks"].values():
        if check.get("success") and "record_count" in check:
            total_records += check["record_count"]

    diagnostics["total_records"] = total_records

    return JSONResponse(content=diagnostics)


@app.get("/", response_model=None)
async def root() -> Union[FileResponse, JSONResponse]:
    """
    Serve the frontend HTML file or return API information.

    If the frontend index.html file exists, it is served. Otherwise,
    returns API information as JSON.

    Returns:
        FileResponse if index.html exists, otherwise JSONResponse with API information.
    """
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
    )


@app.get("/api")
async def api_info() -> JSONResponse:
    """
    API information endpoint.

    Returns:
        JSONResponse containing service information, available endpoints,
        model configuration, and feature flags (memory/auth enabled).
    """
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
    )


if __name__ == "__main__":
    import uvicorn

    # Run the application
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
