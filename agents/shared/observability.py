"""Structured logging and observability for agents."""

import logging
import time
from typing import Optional, Dict, Any
from functools import wraps

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class AgentLogger:
    """Structured logging for agents."""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.logger = logging.getLogger(agent_name)
    
    def log_request(
        self,
        user_id: str,
        session_id: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log incoming request."""
        self.logger.info(
            "Request received",
            extra={
                "agent": self.agent_name,
                "user_id": user_id,
                "session_id": session_id,
                "message_length": len(message),
                "metadata": metadata or {}
            }
        )
    
    def log_response(
        self,
        user_id: str,
        session_id: str,
        processing_time_ms: float,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log response."""
        self.logger.info(
            "Response sent",
            extra={
                "agent": self.agent_name,
                "user_id": user_id,
                "session_id": session_id,
                "processing_time_ms": processing_time_ms,
                "success": success,
                "metadata": metadata or {}
            }
        )
    
    def log_a2a_call(
        self,
        target_agent: str,
        user_id: str,
        session_id: str,
        latency_ms: float,
        success: bool
    ):
        """Log agent-to-agent call."""
        self.logger.info(
            "A2A call",
            extra={
                "source_agent": self.agent_name,
                "target_agent": target_agent,
                "user_id": user_id,
                "session_id": session_id,
                "latency_ms": latency_ms,
                "success": success
            }
        )
    
    def log_error(
        self,
        error: Exception,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log error."""
        self.logger.error(
            f"Error: {str(error)}",
            extra={
                "agent": self.agent_name,
                "user_id": user_id,
                "session_id": session_id,
                "error_type": type(error).__name__,
                "context": context or {}
            },
            exc_info=True
        )


def track_latency(agent_name: str):
    """Decorator to track function latency."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                latency_ms = (time.time() - start_time) * 1000
                logger = AgentLogger(agent_name)
                logger.logger.info(
                    f"{func.__name__} completed",
                    extra={
                        "function": func.__name__,
                        "latency_ms": latency_ms,
                        "success": True
                    }
                )
                return result
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                logger = AgentLogger(agent_name)
                logger.log_error(e, context={"function": func.__name__, "latency_ms": latency_ms})
                raise
        return wrapper
    return decorator

