"""Client for agent-to-agent communication using A2A protocol (JSON-RPC 2.0)."""

import os
import logging
import httpx
import json
import uuid
from typing import Dict, List, Optional
from agents.shared.service_discovery import get_service_discovery
from agents.shared.observability import AgentLogger

logger = logging.getLogger(__name__)


class A2AClient:
    """Client for agent-to-agent communication using A2A protocol (JSON-RPC 2.0)."""
    
    def __init__(self, source_agent_name: str):
        """Initialize A2A client."""
        self.source_agent_name = source_agent_name
        self.service_discovery = get_service_discovery()
        self.logger = AgentLogger(source_agent_name)
        self.client = httpx.AsyncClient(timeout=30.0)
        self._request_id = 0
    
    def _get_next_id(self) -> int:
        """Get next JSON-RPC request ID."""
        self._request_id += 1
        return self._request_id
    
    def _generate_message_id(self) -> str:
        """Generate unique message ID for A2A protocol."""
        return f"msg-{uuid.uuid4().hex[:16]}"
    
    async def call_agent(
        self,
        agent_name: str,
        task: str,
        **kwargs
    ) -> str:
        """
        Make A2A call to another agent using JSON-RPC 2.0 protocol.
        
        Args:
            agent_name: Name of the target agent
            task: Task description/message to send
            **kwargs: Additional parameters (user_id, session_id, etc.)
            
        Returns:
            Response content from the agent
        """
        import time
        start_time = time.time()
        
        try:
            endpoint = self.service_discovery.get_endpoint(agent_name)
            logger.info(f"[A2A] Calling '{agent_name}' agent at endpoint: {endpoint}")
            logger.info(f"[A2A] Task: {task[:150]}")
            
            # Build JSON-RPC 2.0 request
            # Strands A2AServer uses 'message/send' method with required fields:
            # - messageId: unique identifier (required)
            # - role: "user" or "agent" (required)
            # - parts: array of content parts (required, not "content")
            message = {
                "messageId": self._generate_message_id(),  # REQUIRED
                "role": "user",                            # REQUIRED
                "parts": [                                 # REQUIRED (not "content")
                    {
                        "type": "text",
                        "text": task
                    }
                ]
            }
            
            # Add optional fields if provided in kwargs
            if "context_id" in kwargs:
                message["contextId"] = kwargs["context_id"]
            if "task_id" in kwargs:
                message["taskId"] = kwargs["task_id"]
            if "metadata" in kwargs:
                message["metadata"] = kwargs["metadata"]
            
            request = {
                "jsonrpc": "2.0",
                "method": "message/send",  # Strands uses message-based approach
                "params": {
                    "message": message
                },
                "id": self._get_next_id()
            }
            
            # Make HTTP POST request
            response = await self.client.post(
                endpoint,
                json=request,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            # Parse JSON-RPC 2.0 response
            result = response.json()
            
            # Extract result or error
            if "result" in result:
                response_content = self._extract_response_content(result["result"])
            elif "error" in result:
                error = result["error"]
                raise Exception(f"A2A error from {agent_name}: {error.get('message', str(error))}")
            else:
                raise Exception(f"Invalid JSON-RPC response from {agent_name}: {result}")
            
            latency_ms = (time.time() - start_time) * 1000
            
            logger.info(f"[A2A] ✓ Successfully called '{agent_name}' agent (latency: {latency_ms:.1f}ms)")
            logger.info(f"[A2A]   Response length: {len(response_content)} chars")
            
            self.logger.log_a2a_call(
                target_agent=agent_name,
                user_id=kwargs.get("user_id", "unknown"),
                session_id=kwargs.get("session_id", "unknown"),
                latency_ms=latency_ms,
                success=True
            )
            
            return response_content
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self.logger.log_a2a_call(
                target_agent=agent_name,
                user_id=kwargs.get("user_id", "unknown"),
                session_id=kwargs.get("session_id", "unknown"),
                latency_ms=latency_ms,
                success=False
            )
            logger.error(f"Failed to call agent {agent_name}: {e}")
            raise
    
    def _extract_response_content(self, result) -> str:
        """
        Extract text content from A2A response.
        
        Response can be:
        - Direct string
        - Message object with parts
        - Dict with various formats
        """
        if isinstance(result, str):
            return result
        
        if isinstance(result, dict):
            # Check for message object with parts
            if "message" in result:
                msg = result["message"]
                if isinstance(msg, dict) and "parts" in msg:
                    return self._extract_text_from_parts(msg["parts"])
                return str(msg)
            
            # Check for direct parts array
            if "parts" in result:
                return self._extract_text_from_parts(result["parts"])
            
            # Fallback to common response fields
            return result.get("content", result.get("text", str(result)))
        
        return str(result)
    
    def _extract_text_from_parts(self, parts: List[Dict]) -> str:
        """Extract text from parts array."""
        text_parts = []
        for part in parts:
            if part.get("type") == "text" and "text" in part:
                text_parts.append(part["text"])
        return "\n".join(text_parts) if text_parts else str(parts)
    
    async def health_check(self, agent_name: str) -> Dict:
        """Check health of another agent via agent card."""
        try:
            endpoint = self.service_discovery.get_endpoint(agent_name)
            # Try to get agent card
            response = await self.client.get(f"{endpoint}/.well-known/agent-card.json")
            response.raise_for_status()
            card = response.json()
            return {
                "status": "healthy",
                "agent_name": card.get("name", agent_name),
                "capabilities": card.get("capabilities", [])
            }
        except Exception as e:
            logger.warning(f"Health check failed for {agent_name}: {e}")
            return {"status": "unhealthy", "error": str(e)}
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
