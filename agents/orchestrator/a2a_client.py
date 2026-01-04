"""Client for agent-to-agent communication using A2A protocol (JSON-RPC 2.0)."""

import os
import logging
import httpx
import json
from typing import Dict
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
            
            # Build JSON-RPC 2.0 request
            request = {
                "jsonrpc": "2.0",
                "method": "task",
                "params": {
                    "task": task,
                    **kwargs
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
                content = result["result"]
                # Handle different response formats
                if isinstance(content, str):
                    response_content = content
                elif isinstance(content, dict):
                    response_content = content.get("content", content.get("text", str(content)))
                else:
                    response_content = str(content)
            elif "error" in result:
                error = result["error"]
                raise Exception(f"A2A error from {agent_name}: {error.get('message', str(error))}")
            else:
                raise Exception(f"Invalid JSON-RPC response from {agent_name}: {result}")
            
            latency_ms = (time.time() - start_time) * 1000
            
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
