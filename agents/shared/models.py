"""Shared Pydantic models for A2A communication."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class AgentRequest(BaseModel):
    """Standard request format for A2A communication."""

    message: str
    context: List[Dict[str, str]] = []
    user_id: str
    session_id: str
    metadata: Optional[Dict[str, Any]] = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentResponse(BaseModel):
    """Standard response format for A2A communication."""

    content: str
    agent_name: str
    processing_time_ms: float
    metadata: Optional[Dict[str, Any]] = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str
    agent_name: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
