"""Orchestrator Agent using Strands framework with A2A protocol."""

import os
import logging
import sys
import re
import json
import time
import uuid
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
import boto3
import uvicorn
import logging as uvicorn_logging
from strands import Agent
from strands.tools import tool
from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.a2a_client import A2AClient
from agents.shared.observability import sanitize_for_logging

# Import memory and auth modules (from src/)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
from memory.client import MemoryClient
from memory.session_manager import MemorySessionManager
from auth.google_oauth2 import GoogleOAuth2Handler
from auth.oauth2_middleware import get_current_user
from config.runtime import get_config

# Constants
DEFAULT_USER_ID = "default"
DEFAULT_ACTOR_ID = "anonymous"
DEFAULT_AGENT_NAME = "orchestrator-agent"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _disable_noisy_loggers():
    """Disable FastAPI and uvicorn loggers to reduce logging noise.

    Note: This doesn't prevent Pydantic validation errors from being printed.
    Those appear to be printed before our code can intercept them.
    """
    for logger_name in ["fastapi", "uvicorn", "uvicorn.error", "uvicorn.access"]:
        logging.getLogger(logger_name).disabled = True
    # Also disable uvicorn loggers via uvicorn_logging module
    uvicorn_logger = uvicorn_logging.getLogger("uvicorn")
    uvicorn_logger.disabled = True
    uvicorn_logger = uvicorn_logging.getLogger("uvicorn.access")
    uvicorn_logger.disabled = True
    uvicorn_logger = uvicorn_logging.getLogger("uvicorn.error")
    uvicorn_logger.disabled = True


# Disable noisy loggers at startup
_disable_noisy_loggers()


def _normalize_message_content(content: Any) -> List[Dict[str, str]]:
    """Normalize message content to ContentBlocks format for Strands.

    Strands expects content to be a list of ContentBlock dicts: [{"text": "..."}]

    Args:
        content: Content in various formats (str, dict, list, etc.)

    Returns:
        List of ContentBlock dictionaries
    """
    if isinstance(content, str):
        return [{"text": content}]
    elif isinstance(content, dict):
        if "text" in content:
            return [content]
        else:
            # Try to extract text from dict
            text = content.get("content", content.get("text", str(content)))
            return [{"text": text}]
    elif isinstance(content, list):
        # List of ContentBlocks - ensure each is properly formatted
        formatted_blocks = []
        for block in content:
            if isinstance(block, str):
                formatted_blocks.append({"text": block})
            elif isinstance(block, dict):
                if "text" in block:
                    formatted_blocks.append(block)
                else:
                    # Try to extract text from dict
                    text = block.get("content", block.get("text", str(block)))
                    formatted_blocks.append({"text": text})
            else:
                formatted_blocks.append({"text": str(block)})
        return formatted_blocks
    else:
        return [{"text": str(content) if content else ""}]


def _normalize_messages(messages: List) -> List[Dict]:
    """Normalize messages to ensure they're in the correct format for Strands.

    Args:
        messages: List of messages in various formats

    Returns:
        List of normalized message dictionaries
    """
    normalized_messages = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user").lower()
            content = msg.get("content", "")
            normalized_content = _normalize_message_content(content)
            normalized_messages.append({"role": role, "content": normalized_content})
        elif hasattr(msg, "role") and hasattr(msg, "content"):
            # Handle Message objects - convert to dict format
            role = getattr(msg, "role", "user").lower()
            content = getattr(msg, "content", "")
            normalized_content = _normalize_message_content(content)
            normalized_messages.append({"role": role, "content": normalized_content})
        else:
            # Skip invalid message formats
            logger.warning(f"Skipping invalid message format: {type(msg)}")
    return normalized_messages


def _extract_response_content(response: Any) -> str:
    """Extract text content from various response formats.

    Args:
        response: Response object from Strands agent (AgentResult, Message, etc.)

    Returns:
        Extracted text content as string
    """
    response_content = ""
    if hasattr(response, "message"):
        message = response.message
        # Message is dict-like, get content
        if isinstance(message, dict):
            content = message.get("content", [])
        else:
            content = getattr(message, "content", [])

        # Extract text from content blocks
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if text:
                        text_parts.append(text)
                elif isinstance(block, str):
                    text_parts.append(block)
            response_content = " ".join(text_parts) if text_parts else ""
        elif isinstance(content, str):
            response_content = content
        else:
            response_content = str(content) if content else ""
    elif hasattr(response, "content"):
        response_content = response.content
    else:
        # Fallback: try to get text from the result
        response_content = str(response) if response else ""

    return response_content


def _get_actor_id(user: Dict[str, Any]) -> str:
    """Extract actor ID from user dictionary consistently.

    Args:
        user: User dictionary from OAuth2 middleware

    Returns:
        Actor ID string (email, sub, or default)
    """
    return user.get("email") or user.get("sub") or DEFAULT_ACTOR_ID


# Global orchestrator agent instance (will be created lazily)
_orchestrator_agent: Optional["MemoryIntegratedOrchestrator"] = None
# Public attribute for testing - can be patched by tests
orchestrator_agent: Optional["MemoryIntegratedOrchestrator"] = None


def _get_orchestrator_agent() -> "MemoryIntegratedOrchestrator":
    """Get or create the global orchestrator agent instance (lazy initialization).

    Checks for a patched orchestrator_agent first (for testing), then falls back
    to creating/returning the global _orchestrator_agent instance.

    Returns:
        MemoryIntegratedOrchestrator instance
    """
    global _orchestrator_agent
    # Check if orchestrator_agent was patched (for testing)
    # Use globals() to check if it's been set without triggering __getattr__
    module_globals = globals()
    if "orchestrator_agent" in module_globals and module_globals["orchestrator_agent"] is not None:
        return module_globals["orchestrator_agent"]

    # Otherwise, use the private global instance
    if not _orchestrator_agent:
        _orchestrator_agent = create_orchestrator_agent()
    return _orchestrator_agent


def __getattr__(name: str):
    """Allow access to orchestrator_agent as a module attribute when not explicitly set.

    This allows tests to patch orchestrator_agent directly, but when not patched,
    it will return the actual agent instance via _get_orchestrator_agent().
    """
    if name == "orchestrator_agent":
        return _get_orchestrator_agent()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def _build_media_content(media_type: str, media_format: str, base64_data: Optional[str], s3_uri: Optional[str]) -> Dict:
    """Build media content dictionary for A2A call.

    Args:
        media_type: Type of media ("image" or "video")
        media_format: Format string (e.g., "jpeg", "mp4")
        base64_data: Optional base64 encoded data
        s3_uri: Optional S3 URI

    Returns:
        Media content dictionary for A2A protocol

    Raises:
        HTTPException: If no data source provided or unsupported media type
    """
    if media_type not in ["image", "video"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported media type: {media_type}")

    media_content = {"type": media_type, media_type: {"format": media_format, "source": {}}}

    if base64_data:
        media_content[media_type]["source"]["base64"] = base64_data
    elif s3_uri:
        media_content[media_type]["source"]["s3Location"] = {"uri": s3_uri}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"No {media_type} data provided (base64 or S3 URI required)"
        )

    return media_content


def _parse_vision_result(result: Any) -> Dict[str, Any]:
    """Parse vision agent response into standardized format.

    Args:
        result: Result from vision agent (string, dict, or other)

    Returns:
        Dictionary with "text" and optional "usage" keys
    """
    # If result is already a string (from _extract_response_content)
    if isinstance(result, str):
        # Try to parse as JSON in case it's a JSON string
        try:
            parsed = json.loads(result)
            logger.debug(f"Parsed JSON result type: {type(parsed)}")
            # If it's a dict, extract text field
            if isinstance(parsed, dict):
                text = parsed.get("text", str(parsed))
                logger.debug(f"Extracted text length: {len(text)}")
                return {"text": text, "usage": parsed.get("usage")}
            else:
                # If parsed is not a dict, use it as text
                return {"text": str(parsed), "usage": None}
        except (json.JSONDecodeError, TypeError) as e:
            # Not JSON, treat as plain text
            logger.debug(f"Result is not JSON, treating as plain text: {e}")
            return {"text": result, "usage": None}
    elif isinstance(result, dict):
        # Already a dict, extract text field
        text = result.get("text", str(result))
        logger.debug(f"Result is dict, extracted text length: {len(text)}")
        return {"text": text, "usage": result.get("usage")}
    else:
        # Other types, convert to text
        logger.debug(f"Result is other type, converting to string")
        return {"text": str(result), "usage": None}


# Override Pydantic ValidationError string representation to sanitize base64 data
try:
    from pydantic_core import ValidationError as PydanticValidationError

    # Store original method
    original_str = PydanticValidationError.__str__

    def sanitized_str(self):
        """Override Pydantic's __str__ to sanitize base64 data in error messages.

        Replaces long base64-like strings in Pydantic validation error messages
        with a truncated placeholder to prevent log pollution and potential
        security issues from exposing large base64 payloads.

        Returns:
            Sanitized string representation of the validation error with
            base64 data truncated to '<base64_data_truncated>'
        """
        original = original_str(self)
        # Truncate long base64-like strings in the output
        return re.sub(r"[A-Za-z0-9+/=]{200,}", "<base64_data_truncated>", original)

    # Apply the override
    PydanticValidationError.__str__ = sanitized_str
except ImportError:
    # pydantic_core may not be available in all environments
    logger.warning("Could not import pydantic_core.ValidationError - base64 sanitization in error messages may not work.")


class MemoryIntegratedOrchestrator:
    """Wrapper that adds memory integration to Orchestrator Agent for A2A protocol."""

    def __init__(self, orchestrator_wrapper: OrchestratorAgent, a2a_client: A2AClient):
        """Initialize with orchestrator wrapper that has memory client.

        Sets up the memory-integrated orchestrator by wrapping an OrchestratorAgent
        instance and configuring it with routing tools for specialist agents.
        Creates a Strands Agent with routing tools that can be called during
        conversation to delegate tasks to specialist agents via A2A protocol.

        Args:
            orchestrator_wrapper: OrchestratorAgent instance that provides memory
                                 integration and base agent functionality
            a2a_client: A2AClient instance for making agent-to-agent calls to
                      specialist agents
        """
        self.orchestrator_wrapper = orchestrator_wrapper
        self.a2a_client = a2a_client
        self.strands_agent = orchestrator_wrapper.strands_agent
        # Set description on the underlying Strands agent for A2AServer
        if not hasattr(self.strands_agent, "description") or not self.strands_agent.description:
            self.strands_agent.description = "Orchestrator agent that routes tasks to specialist agents"
        # Copy agent attributes for A2AServer compatibility
        self.model = self.strands_agent.model
        self.name = getattr(self.strands_agent, "name", DEFAULT_AGENT_NAME)
        self.description = self.strands_agent.description
        # Delegate tool_registry to underlying Strands agent for A2AServer
        self.tool_registry = getattr(self.strands_agent, "tool_registry", None)

        # Create routing tools that use A2AClient
        self.tools = [
            self._create_routing_tool("vision", "Image analysis, visual content understanding"),
            self._create_routing_tool("document", "Document processing, text extraction, PDF analysis"),
            self._create_routing_tool("data", "Data analysis, SQL queries, chart generation"),
            self._create_routing_tool("tool", "Calculator, weather, general utilities"),
        ]

        # Create a new system prompt that instructs the agent to USE the routing tools
        # instead of just returning specialist names
        self.system_prompt = """You are an orchestrator agent that routes user requests to specialist agents.

You have access to routing tools that connect to specialist agents:
- route_to_vision: For image analysis, visual content understanding
- route_to_document: For document processing, text extraction, PDF analysis
- route_to_data: For data analysis, SQL queries, chart generation
- route_to_tool: For calculator, weather, general utilities

When a user asks a question or makes a request:
1. Determine which specialist agent should handle it
2. USE the appropriate routing tool (route_to_vision, route_to_document, route_to_data, or route_to_tool)
3. Pass the user's complete question/task to the routing tool
4. The tool will return the specialist agent's response
5. Present that response directly to the user - do NOT mention that you used a tool or show the tool call

IMPORTANT: After calling a routing tool, you will receive the specialist's response. Simply present that response to the user in a natural, conversational way. Do NOT say "Action: route_to_tool(...)" or mention the tool call.

For general greetings or questions that don't fit a specialist, you can respond directly in a friendly manner.
Always use the routing tools when appropriate - the tools will handle calling the specialists and return their responses."""

        # Create Strands Agent with routing tools (create once, reuse in run())
        self.agent_with_tools = Agent(model=self.model, tools=self.tools, system_prompt=self.system_prompt)

    def _create_routing_tool(self, agent_name: str, description: str):
        """Create a routing tool for a specialist agent.

        This method creates a dynamically named tool function that routes tasks
        to a specific specialist agent via the A2A client. The tool is registered
        with Strands and can be called by the orchestrator agent during conversation.

        Args:
            agent_name: Name of the specialist agent (e.g., "vision", "document", "data", "tool")
            description: Human-readable description of what the agent handles

        Returns:
            A decorated tool function that can be used by the Strands agent
        """
        # Create a closure to capture self and agent_name
        orchestrator_instance = self

        # Define the async function first
        async def route_to_specialist_impl(task: str) -> str:
            """Route task to {agent_name} agent and return the response.

            Use this tool when the user's request requires {description}.
            Pass the user's complete question or request as the task parameter.
            The tool will call the specialist agent and return their response.
            You should then present this response to the user in a natural way.

            Args:
                task: The task or question to send to the {agent_name} agent. This should be the user's full question or request.

            Returns:
                The response from the {agent_name} agent. Present this directly to the user.
            """
            # Get user_id and session_id from the current invocation context
            user_id = getattr(orchestrator_instance, "_current_user_id", DEFAULT_USER_ID)
            session_id = getattr(orchestrator_instance, "_current_session_id", DEFAULT_USER_ID)

            logger.info(f"[ROUTING] → Calling specialist agent '{agent_name}' with task: {task[:100]}")
            logger.info(f"[ROUTING]   user_id={user_id}, session_id={session_id}")
            try:
                result = await orchestrator_instance.a2a_client.call_agent(
                    agent_name=agent_name, task=task, user_id=user_id, session_id=session_id
                )
                logger.info(f"[ROUTING] ← Received response from '{agent_name}': {result[:200] if result else 'empty'}")
                return result
            except Exception as e:
                logger.error(f"[ROUTING] ✗ Error calling {agent_name} agent: {e}", exc_info=True)
                return f"I encountered an error while trying to get help from the {agent_name} specialist: {str(e)}"

        # Set function name before decoration
        route_to_specialist_impl.__name__ = f"route_to_{agent_name}"

        # Decorate with @tool to register it with Strands
        decorated_tool = tool(route_to_specialist_impl)

        return decorated_tool

    async def run(self, messages, **kwargs):
        """Run orchestrator with memory integration.

        Processes user messages through the orchestrator agent, which may route
        to specialist agents via A2A protocol. Loads conversation context from
        memory, normalizes messages for Strands format, invokes the agent with
        routing tools, and stores the interaction back to memory.

        Args:
            messages: List of message dictionaries or objects in various formats.
                     Should include at least one user message.
            **kwargs: Additional keyword arguments including:
                - user_id: User identifier for memory context
                - session_id: Session identifier for conversation continuity

        Returns:
            Response object with a 'content' attribute containing the agent's
            text response. The response may come directly from the orchestrator
            or from a specialist agent via routing tools.
        """
        # Extract user_id and session_id from kwargs for use in routing tools
        user_id = kwargs.get("user_id", DEFAULT_USER_ID)
        session_id = kwargs.get("session_id", DEFAULT_USER_ID)

        # Store user_id and session_id so routing tools can access them
        # We'll update the tools to use these values
        self._current_user_id = user_id
        self._current_session_id = session_id

        # Extract user message and context
        user_message = None
        context_messages = []

        # Log the incoming request
        logger.info(f"[ORCHESTRATOR] Processing request (user_id={user_id}, session_id={session_id})")

        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "").lower()
                content = msg.get("content", "")
                if role == "user":
                    user_message = content
                context_messages.append(msg)
            else:
                context_messages.append(msg)

        # Load context from memory if we have user info
        if user_message and "user_id" in kwargs and "session_id" in kwargs:
            try:
                # Get recent messages from memory
                recent = await self.orchestrator_wrapper.memory.get_recent_messages(
                    user_id=kwargs["user_id"], session_id=kwargs["session_id"], limit=10
                )

                # Get relevant semantic context
                relevant = await self.orchestrator_wrapper.memory.semantic_search(
                    user_id=kwargs["user_id"], query=user_message, limit=5
                )

                # Prepend loaded context to messages
                loaded_context = context_messages + relevant + recent
                messages = loaded_context
            except Exception as e:
                logger.warning(f"Failed to load context from memory: {e}")

        # Normalize messages to ensure they're in the correct format for Strands
        normalized_messages = _normalize_messages(messages)

        # Run the Strands agent with tools (reuse the agent created in __init__)
        # Agent is callable - call it directly with messages
        # The Agent class doesn't have a run() method, so we use invoke_async
        logger.info(f"[ORCHESTRATOR] Invoking agent with {len(normalized_messages)} message(s)")
        if user_message:
            logger.info(f"[ORCHESTRATOR] User message: {user_message[:100]}")
        response = await self.agent_with_tools.invoke_async(prompt=normalized_messages)

        # Extract content from AgentResult
        response_content = _extract_response_content(response)

        # Clean up the response - remove tool call mentions if present
        # Sometimes the agent includes "Action: route_to_tool(...)" in the response
        # Remove patterns like "Action: route_to_tool(...)" or "route_to_tool(...)"
        original_content = response_content
        response_content = re.sub(r"Action:\s*route_to_\w+\([^)]*\)", "", response_content, flags=re.IGNORECASE)
        response_content = re.sub(r"route_to_\w+\([^)]*\)", "", response_content, flags=re.IGNORECASE)
        response_content = response_content.strip()

        # Log the response
        if response_content != original_content:
            logger.info(f"[ORCHESTRATOR] Cleaned response (removed tool call mentions)")
        logger.info(f"[ORCHESTRATOR] Final response: {response_content[:200]}")

        # Check if a tool was used by examining the stop_reason
        if hasattr(response, "stop_reason"):
            if response.stop_reason == "tool_use":
                logger.info(f"[ORCHESTRATOR] ✓ Request was routed to a specialist agent (stop_reason=tool_use)")
            else:
                logger.info(f"[ORCHESTRATOR] → Request handled directly by orchestrator (stop_reason={response.stop_reason})")

        # If we got an empty response but the agent used a tool, the tool result should be in the message
        # The agent should have incorporated the tool result into its final response
        if not response_content or response_content.strip() == "":
            logger.warning(f"[ORCHESTRATOR] Empty response from agent. Response object: {response}")
            response_content = "I apologize, but I couldn't generate a response. Please try again."

        # Store interaction in memory if we have user info
        if user_message and "user_id" in kwargs and "session_id" in kwargs:
            try:
                await self.orchestrator_wrapper.memory.store_interaction(
                    user_id=kwargs["user_id"],
                    session_id=kwargs["session_id"],
                    user_message=user_message,
                    agent_response=response_content,
                    agent_name=self.orchestrator_wrapper.agent_name,
                    metadata={"routed_via": "orchestrator"},
                )
            except Exception as e:
                logger.warning(f"Failed to store interaction in memory: {e}")

        # Return a response object with content attribute for compatibility
        class Response:
            """Simple response wrapper for compatibility with A2A protocol.

            This class provides a consistent interface for returning agent responses
            with a 'content' attribute, matching the expected format for A2A
            protocol and other parts of the system.

            Args:
                content: The text content of the agent's response
            """

            def __init__(self, content):
                self.content = content

        return Response(response_content)


def create_orchestrator_agent():
    """Create orchestrator agent with Strands and memory integration.

    Initializes and returns a fully configured MemoryIntegratedOrchestrator
    instance. This includes setting up the A2A client, orchestrator wrapper,
    and all routing tools for specialist agents.

    Returns:
        MemoryIntegratedOrchestrator: Configured orchestrator agent instance
        ready to process requests and route to specialist agents
    """
    # Initialize A2A client
    a2a_client = A2AClient("orchestrator")

    # Create the orchestrator wrapper (handles memory integration)
    orchestrator_wrapper = OrchestratorAgent(a2a_client)

    # Create memory-integrated orchestrator
    return MemoryIntegratedOrchestrator(orchestrator_wrapper, a2a_client)


# Initialize FastAPI app
app = FastAPI(
    title="Orchestrator Agent", description="Orchestrator agent that routes tasks to specialist agents", version="1.0.0"
)

# Add CORS middleware for CloudFront/API Gateway compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Custom handler that sanitizes validation errors before logging.

    Intercepts FastAPI request validation errors and sanitizes any base64
    data in the error details before logging. This prevents large base64
    payloads from polluting logs and potentially exposing sensitive data.

    Args:
        request: FastAPI request object that triggered the validation error
        exc: RequestValidationError exception containing validation details

    Returns:
        JSONResponse with HTTP 422 status and a generic error message that
        doesn't expose base64 data or detailed validation information
    """
    # Sanitize the errors before they get logged
    sanitized_errors = [sanitize_for_logging(error) for error in exc.errors()]

    # Log the sanitized version
    logger.error(f"Validation error on {request.url.path}: {sanitized_errors}")

    # Return clean response without exposing base64 data
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": "Validation error - check request format"}
    )


# Configuration
config = get_config()
MEMORY_ENABLED = config.get_config_value("MEMORY_ENABLED", "false").lower() == "true"
AWS_REGION = config.get_config_value("AWS_REGION", "us-east-1")

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
        logger.warning(f"Failed to initialize memory client: {e}. Orchestrator will continue without memory features.")
        memory_client = None

# Initialize OAuth2 handler
oauth2_handler: Optional[GoogleOAuth2Handler] = None
try:
    oauth2_handler = GoogleOAuth2Handler()
    logger.info("OAuth2 handler initialized")
except Exception as e:
    logger.warning(f"OAuth2 handler not initialized: {e}")


@app.get("/health")
async def health() -> Dict[str, str]:
    """
    Health check endpoint for load balancers and monitoring.

    Returns:
        Dict containing service status and name.

    Example:
        >>> response = await health()
        >>> response
        {"status": "healthy", "service": "orchestrator"}
    """
    return {"status": "healthy", "service": "orchestrator"}


@app.post("/api/sessions")
async def create_session(
    request: Request, user: Dict[str, Any] = Depends(get_current_user), session_id: Optional[str] = None
) -> Dict[str, str]:
    """
    Create a new session or reuse an existing session.

    This endpoint creates a new memory session for the authenticated user.
    If a session_id is provided in the request body, it will reuse that session
    instead of creating a new one. This allows session continuity when switching
    between voice and text modes.

    Args:
        request: FastAPI request object (may contain session_id in body)
        user: Authenticated user information from OAuth2 middleware.
        session_id: Optional session ID from query parameter to reuse. If not provided,
                   a new session will be created.

    Returns:
        Dict containing the session_id.

    Raises:
        HTTPException: If authentication fails or memory client is unavailable.

    Example:
        >>> response = await create_session(user={"email": "user@example.com"})
        >>> response
        {"session_id": "abc123-def456-..."}
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

    actor_id = _get_actor_id(user)
    session_manager = MemorySessionManager(memory_client, actor_id=actor_id, session_id=session_id)
    await session_manager.initialize()
    return {"session_id": session_manager.session_id}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Get session details.

    Args:
        session_id: Session ID to retrieve
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        Dict containing session details.

    Raises:
        HTTPException: If authentication fails, session not found, or memory client unavailable.
    """
    if not memory_client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Memory not enabled")

    actor_id = _get_actor_id(user)

    try:
        # Get session summary
        summary_record = memory_client.get_session_summary(actor_id=actor_id, session_id=session_id)

        if not summary_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        # Extract summary text
        content = summary_record.get("content", {})
        if isinstance(content, dict):
            summary_text = content.get("text", "")
        else:
            summary_text = str(content) if content else ""

        return {
            "session_id": session_id,
            "summary": summary_text,
            "namespace": summary_record.get("namespace", ""),
            "created_at": summary_record.get("createdAt"),
            "updated_at": summary_record.get("updatedAt"),
        }
    except HTTPException:
        # Re-raise HTTPExceptions (e.g., validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Error retrieving session: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error retrieving session: {str(e)}")


@app.post("/api/chat")
async def chat(request: Request, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, str]:
    """
    Send a text message to the orchestrator agent and get a response.

    The orchestrator agent will process the message, potentially routing to
    specialist agents via A2A protocol, and return a text response. The
    session_id from the request is used to maintain conversation context.

    Args:
        request: FastAPI request object containing message and session_id in body.
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        Dict containing the agent's text response.

    Raises:
        HTTPException: If authentication fails, session is invalid, or agent
                      processing fails.

    Example:
        >>> request_body = {"message": "What is 2+2?", "session_id": "abc123"}
        >>> response = await chat(request, user={"email": "user@example.com"})
        >>> response
        {"response": "2+2 equals 4."}
    """
    # Get orchestrator agent (lazy initialization)
    orchestrator_agent = _get_orchestrator_agent()

    try:
        body = await request.json()
        message = body.get("message")
        session_id = body.get("session_id")

        if not message:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required")

        if not session_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session ID is required")

        actor_id = _get_actor_id(user)

        # Prepare messages for orchestrator
        messages = [{"role": "user", "content": message}]

        # Run orchestrator agent
        response = await orchestrator_agent.run(messages=messages, user_id=actor_id, session_id=session_id)

        return {"response": response.content}
    except HTTPException:
        # Re-raise HTTPExceptions (e.g., validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Error processing chat message: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error processing message: {str(e)}")


@app.post("/api/vision/presigned-url")
async def get_presigned_url(request: Request, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, str]:
    """Generate S3 presigned URL for file upload.

    Creates a presigned S3 URL that allows clients to upload image or video
    files directly to S3 without exposing AWS credentials. The URL is valid
    for a configurable expiration time (default 1 hour).

    Args:
        request: FastAPI request object containing fileName and fileType in body.
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        Dictionary containing:
            - uploadUrl: Presigned S3 URL for PUT operation
            - s3Uri: Full S3 URI (s3://bucket/key)
            - key: S3 object key for the uploaded file

    Raises:
        HTTPException: If fileName/fileType are missing, file type is unsupported,
                      or S3 URL generation fails.

    Example:
        >>> request_body = {"fileName": "image.jpg", "fileType": "image/jpeg"}
        >>> response = await get_presigned_url(request, user={...})
        >>> response
        {
            "uploadUrl": "https://s3.amazonaws.com/...",
            "s3Uri": "s3://bucket/uploads/20240101-120000-abc123.jpg",
            "key": "uploads/20240101-120000-abc123.jpg"
        }
    """
    try:
        body = await request.json()
        file_name = body.get("fileName")
        file_type = body.get("fileType")

        if not file_name or not file_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fileName and fileType are required")

        # Validate file type
        accepted_types = [
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "video/mp4",
            "video/quicktime",
            "video/x-matroska",
            "video/webm",
            "video/x-flv",
            "video/mpeg",
            "video/x-ms-wmv",
            "video/3gpp",
        ]
        if file_type not in accepted_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type: {file_type}")

        s3_bucket = os.getenv("S3_VISION_BUCKET", "agentcore-vision-uploads")
        s3_prefix = os.getenv("S3_UPLOAD_PREFIX", "uploads/")
        expiry = int(os.getenv("VISION_PRESIGNED_URL_EXPIRY", "3600"))

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        file_ext = file_name.split(".")[-1] if "." in file_name else ""
        s3_key = f"{s3_prefix}{timestamp}-{unique_id}.{file_ext}" if file_ext else f"{s3_prefix}{timestamp}-{unique_id}"
        s3_uri = f"s3://{s3_bucket}/{s3_key}"

        s3_client = boto3.client("s3")
        upload_url = s3_client.generate_presigned_url(
            "put_object", Params={"Bucket": s3_bucket, "Key": s3_key, "ContentType": file_type}, ExpiresIn=expiry
        )

        return {"uploadUrl": upload_url, "s3Uri": s3_uri, "key": s3_key}
    except HTTPException:
        # Re-raise HTTPExceptions (e.g., validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error generating presigned URL: {str(e)}"
        )


@app.post("/api/vision")
async def vision_analysis(request: Request, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Analyze image or video via orchestrator routing to vision agent.

    Accepts multimodal content (image/video) either as base64-encoded data or
    as an S3 URI. Routes the request to the vision specialist agent via A2A
    protocol and returns the analysis results.

    Args:
        request: FastAPI request object containing:
            - prompt: Text prompt/question about the media
            - mediaType: "image" or "video" (default: "image")
            - base64Data: Optional base64-encoded media data
            - s3Uri: Optional S3 URI pointing to uploaded media
            - mimeType: MIME type of the media (default: "image/jpeg")
            - session_id: Optional session ID for conversation context
        user: Authenticated user information from OAuth2 middleware.

    Returns:
        Dictionary containing:
            - text: The vision agent's analysis response
            - usage: Optional usage metadata (if provided by vision agent)

    Raises:
        HTTPException: If prompt is missing, no media data provided, media type
                      is unsupported, or vision agent processing fails.

    Example:
        >>> request_body = {
        ...     "prompt": "What's in this image?",
        ...     "base64Data": "iVBORw0KGgoAAAANSUhEUgAA...",
        ...     "mimeType": "image/png"
        ... }
        >>> response = await vision_analysis(request, user={...})
        >>> response
        {"text": "This image shows...", "usage": None}
    """
    orchestrator_agent = _get_orchestrator_agent()

    try:
        body = await request.json()
        prompt = body.get("prompt") or body.get("message")
        media_type = body.get("mediaType") or body.get("media_type", "image")
        base64_data = body.get("base64Data")
        mime_type = body.get("mimeType", "image/jpeg")
        s3_uri = body.get("s3Uri")
        session_id = body.get("session_id")

        if not prompt:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing prompt")

        # Extract format from mime type
        media_format = "jpeg"
        if mime_type:
            media_format = mime_type.split("/")[-1]
            if media_format == "jpg":
                media_format = "jpeg"

        # Clean base64 data: strip data URI prefix if present
        if base64_data:
            if base64_data.startswith("data:"):
                # Strip data URI prefix if present
                base64_data = base64_data.split(",", 1)[1]

        # Build media_content for A2A call
        media_content = _build_media_content(media_type, media_format, base64_data, s3_uri)

        # Get user context
        actor_id = _get_actor_id(user)
        if not session_id:
            session_id = f"vision-{actor_id}-{int(time.time())}"

        # Log sanitized request
        logger.info(
            f"Vision request: prompt='{prompt[:50]}...', format={media_format}, has_base64={bool(base64_data)}, has_s3={bool(s3_uri)}"
        )

        # Call vision agent directly via A2A with multimodal content
        # The orchestrator_agent is a MemoryIntegratedOrchestrator which has a2a_client
        a2a_client = orchestrator_agent.a2a_client

        result = await a2a_client.call_agent_with_media(
            agent_name="vision", task=prompt, media_content=media_content, user_id=actor_id, session_id=session_id
        )

        # Parse result - extract text content
        logger.debug(f"Vision analysis result type: {type(result)}, value preview: {str(result)[:200]}")
        return _parse_vision_result(result)
    except HTTPException:
        # Re-raise HTTPExceptions (e.g., validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Error processing vision request: {str(e)}", exc_info=False)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error processing vision request: {str(e)}"
        )


def main():
    """
    Start orchestrator A2A server and FastAPI HTTP server.

    The A2A server runs on port 9000 (default) for agent-to-agent communication.
    The FastAPI HTTP server runs on a configurable port (default 9000, but can be
    set via ORCHESTRATOR_HTTP_PORT environment variable). In production, these
    can be routed through API Gateway/CloudFront.
    """
    # Import A2AServer only when needed (lazy import to avoid dependency issues in tests)
    try:
        from strands.multiagent.a2a import A2AServer
    except ImportError as e:
        logger.error(f"Failed to import A2AServer: {e}")
        logger.error("A2A functionality requires the 'a2a' package. Install it with: pip install a2a")
        raise

    logger.info("Starting Orchestrator Agent...")

    # Create agent (this will also set the global _orchestrator_agent)
    orchestrator_agent = _get_orchestrator_agent()

    # Get A2A port (default 9001 to avoid conflict with FastAPI on 9000)
    # Can be configured via A2A_PORT environment variable
    a2a_port = int(os.getenv("A2A_PORT", "9001"))

    # Get HTTP port (default 9000 for FastAPI REST API)
    # Can be configured via ORCHESTRATOR_HTTP_PORT environment variable
    http_port = int(os.getenv("ORCHESTRATOR_HTTP_PORT", "9000"))

    # Create A2A server (agent card is auto-generated from the agent)
    a2a_server = A2AServer(agent=orchestrator_agent, port=a2a_port, host="0.0.0.0")

    logger.info("Orchestrator Agent ready")
    logger.info(f"FastAPI HTTP server on port {http_port}")
    logger.info(f"A2A server on port {a2a_port}")
    logger.info(f"Agent Card: http://0.0.0.0:{a2a_port}/.well-known/agent-card.json")

    # Start A2A server in background thread
    a2a_thread = threading.Thread(target=a2a_server.serve, daemon=True)
    a2a_thread.start()

    # Start FastAPI server (BLOCKING - runs forever)
    # Note: If both use port 9000, A2A server will handle A2A requests,
    # and FastAPI will handle HTTP REST requests (they use different protocols)
    # Uvicorn loggers are already disabled by _disable_noisy_loggers()
    uvicorn.run(app, host="0.0.0.0", port=http_port, log_config=None)  # Disable uvicorn's default logging config


if __name__ == "__main__":
    main()
