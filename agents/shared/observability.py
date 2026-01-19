"""Structured logging and observability for agents."""

import logging
import time
import re
from typing import Optional, Dict, Any, Union
from functools import wraps

# Module-level constants
_BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/=]+$")

# Configure structured logging only if not already configured
if not logging.root.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Cache for AgentLogger instances to avoid recreating them
_logger_cache: Dict[str, "AgentLogger"] = {}


class AgentLogger:
    """
    Structured logging for agents.

    Provides methods to log requests, responses, agent-to-agent calls, and errors
    with consistent structured data for observability.

    Example:
        >>> logger = AgentLogger("orchestrator")
        >>> logger.log_request(
        ...     user_id="user123",
        ...     session_id="session456",
        ...     message="Hello, world"
        ... )
    """

    def __init__(self, agent_name: str):
        """
        Initialize an AgentLogger instance.

        Args:
            agent_name: Name of the agent using this logger (e.g., "orchestrator", "vision")
        """
        self.agent_name = agent_name
        self.logger = logging.getLogger(agent_name)

    def log_request(self, user_id: str, session_id: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Log an incoming request.

        Args:
            user_id: Unique identifier for the user making the request
            session_id: Unique identifier for the session
            message: The request message content
            metadata: Optional dictionary of additional metadata to include in the log
        """
        self.logger.info(
            "Request received",
            extra={
                "agent": self.agent_name,
                "user_id": user_id,
                "session_id": session_id,
                "message_length": len(message),
                "metadata": metadata or {},
            },
        )

    def log_response(
        self,
        user_id: str,
        session_id: str,
        processing_time_ms: float,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log a response being sent.

        Args:
            user_id: Unique identifier for the user receiving the response
            session_id: Unique identifier for the session
            processing_time_ms: Time taken to process the request in milliseconds
            success: Whether the request was processed successfully
            metadata: Optional dictionary of additional metadata to include in the log
        """
        self.logger.info(
            "Response sent",
            extra={
                "agent": self.agent_name,
                "user_id": user_id,
                "session_id": session_id,
                "processing_time_ms": processing_time_ms,
                "success": success,
                "metadata": metadata or {},
            },
        )

    def log_a2a_call(self, target_agent: str, user_id: str, session_id: str, latency_ms: float, success: bool) -> None:
        """
        Log an agent-to-agent (A2A) call.

        Args:
            target_agent: Name of the target agent being called
            user_id: Unique identifier for the user associated with the call
            session_id: Unique identifier for the session
            latency_ms: Latency of the A2A call in milliseconds
            success: Whether the A2A call was successful
        """
        self.logger.info(
            "A2A call",
            extra={
                "source_agent": self.agent_name,
                "target_agent": target_agent,
                "user_id": user_id,
                "session_id": session_id,
                "latency_ms": latency_ms,
                "success": success,
            },
        )

    def log_error(
        self,
        error: Exception,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an error with full exception information.

        Args:
            error: The exception that was raised
            user_id: Optional unique identifier for the user (if available)
            session_id: Optional unique identifier for the session (if available)
            context: Optional dictionary of additional context information
        """
        self.logger.error(
            f"Error: {str(error)}",
            extra={
                "agent": self.agent_name,
                "user_id": user_id,
                "session_id": session_id,
                "error_type": type(error).__name__,
                "context": context or {},
            },
            exc_info=True,
        )


def sanitize_for_logging(obj: Any, max_base64_length: int = 100) -> Union[Dict[str, Any], list, str, bytes, Any]:
    """
    Recursively sanitize objects for logging by truncating base64 strings.

    This function traverses dictionaries, lists, and other structures to find
    long base64-encoded strings or binary data and replaces them with truncated
    placeholders to prevent log bloat.

    Args:
        obj: Object to sanitize (dict, list, str, bytes, or other)
        max_base64_length: Maximum length before truncating base64-like strings.
            Strings longer than this that match base64 pattern will be truncated.

    Returns:
        Sanitized copy of the object. Dictionaries and lists are recursively
        processed. Base64-like strings longer than max_base64_length are replaced
        with placeholders. Binary data longer than max_base64_length is replaced
        with a placeholder. Other types are returned unchanged.

    Example:
        >>> data = {"token": "very_long_base64_string_here..."}
        >>> sanitize_for_logging(data, max_base64_length=50)
        {'token': '<base64_data_123_chars>'}
    """
    if isinstance(obj, dict):
        return {k: sanitize_for_logging(v, max_base64_length) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_logging(item, max_base64_length) for item in obj]
    elif isinstance(obj, str):
        # Check if it looks like base64 and is long
        if len(obj) > max_base64_length and _BASE64_PATTERN.match(obj):
            return f"<base64_data_{len(obj)}_chars>"
        return obj
    elif isinstance(obj, bytes):
        if len(obj) > max_base64_length:
            return f"<binary_data_{len(obj)}_bytes>"
        return obj
    return obj


def track_latency(agent_name: str):
    """
    Decorator to track function execution latency and log results.

    This decorator measures the execution time of an async function and logs
    both successful completions and errors with latency information. Logger
    instances are cached by agent name for efficiency.

    Args:
        agent_name: Name of the agent using this decorator (e.g., "orchestrator", "vision")

    Returns:
        A decorator function that wraps the target function with latency tracking.

    Example:
        >>> @track_latency("orchestrator")
        ... async def process_request(request: AgentRequest) -> AgentResponse:
        ...     # Process the request
        ...     return response
        ...
        >>> # The decorator will automatically log:
        >>> # - Function completion with latency_ms
        >>> # - Errors with latency_ms and exception details

    Note:
        This decorator is designed for async functions. For synchronous functions,
        use a different approach or modify the wrapper accordingly.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get or create cached logger for this agent
            if agent_name not in _logger_cache:
                _logger_cache[agent_name] = AgentLogger(agent_name)
            logger = _logger_cache[agent_name]

            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                latency_ms = (time.time() - start_time) * 1000
                logger.logger.info(
                    f"{func.__name__} completed", extra={"function": func.__name__, "latency_ms": latency_ms, "success": True}
                )
                return result
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                logger.log_error(e, context={"function": func.__name__, "latency_ms": latency_ms, "success": False})
                raise

        return wrapper

    return decorator
