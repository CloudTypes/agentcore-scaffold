"""Shared AgentCore Memory client for multi-agent use."""

import os
import logging
from typing import Optional, Dict, Any, List
from agents.shared.models import AgentRequest

logger = logging.getLogger(__name__)

# Try to import AgentCore Memory client
try:
    from bedrock_agentcore.memory import MemoryClient as AgentCoreMemoryClient
    from bedrock_agentcore.memory import MemoryControlPlaneClient
    from bedrock_agentcore.memory.models import Event, MemoryRecord
    MEMORY_AVAILABLE = True
except ImportError:
    logger.warning("bedrock_agentcore.memory not available - memory features disabled")
    MEMORY_AVAILABLE = False
    AgentCoreMemoryClient = None
    MemoryControlPlaneClient = None
    Event = None
    MemoryRecord = None


class MemoryClient:
    """Shared AgentCore Memory client for all agents."""
    
    def __init__(self, region: Optional[str] = None, memory_id: Optional[str] = None):
        """
        Initialize the memory client.
        
        Args:
            region: AWS region for memory resource
            memory_id: Optional memory resource ID (will be created if not provided)
        """
        self.region = region or os.getenv("AGENTCORE_MEMORY_REGION") or os.getenv("AWS_REGION", "us-east-1")
        self.memory_id = memory_id or os.getenv("AGENTCORE_MEMORY_ID")
        self._client = None
        self._control_plane_client = None
        self._memory_resource = None
        logger.info(f"Memory client initialized with region: {self.region}, memory_id: {self.memory_id}")
        
    def _get_client(self) -> AgentCoreMemoryClient:
        """Get or create the AgentCore Memory client."""
        if not MEMORY_AVAILABLE:
            raise RuntimeError("AgentCore Memory is not available")
        if self._client is None:
            self._client = AgentCoreMemoryClient(region_name=self.region)
        return self._client
    
    def _sanitize_actor_id(self, actor_id: str) -> str:
        """Sanitize actor_id to match AgentCore Memory requirements."""
        sanitized = actor_id.replace("@", "_").replace(".", "_")
        if not sanitized[0].isalnum():
            sanitized = "user_" + sanitized
        return sanitized
    
    async def get_recent_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int = 10
    ) -> List[Dict[str, str]]:
        """
        Retrieve recent conversation history.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of message dictionaries with 'role' and 'content' keys
        """
        if not self.memory_id or not MEMORY_AVAILABLE:
            return []
        
        try:
            client = self._get_client()
            sanitized_actor_id = self._sanitize_actor_id(user_id)
            
            # Use list_events to get recent events (sync method, but we're in async context)
            # Note: This is a simplified version - in production you might want
            # to use a more sophisticated approach
            import asyncio
            loop = asyncio.get_event_loop()
            events = await loop.run_in_executor(
                None,
                lambda: client.list_events(
                    memory_id=self.memory_id,
                    actor_id=sanitized_actor_id,
                    session_id=session_id,
                    max_results=limit
                )
            )
            
            messages = []
            for event in events.get("events", [])[:limit]:
                # Extract role and content from event
                event_data = event.get("event", {})
                messages_data = event_data.get("messages", [])
                
                for msg in messages_data:
                    if isinstance(msg, tuple) and len(msg) == 2:
                        text, role = msg
                        messages.append({
                            "role": role.lower(),
                            "content": text
                        })
                    elif isinstance(msg, dict):
                        messages.append({
                            "role": msg.get("role", "user").lower(),
                            "content": msg.get("content", msg.get("text", ""))
                        })
            
            return messages[-limit:] if len(messages) > limit else messages
        except Exception as e:
            logger.error(f"Failed to get recent messages: {e}")
            return []
    
    async def semantic_search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant past context using semantic search.
        
        Args:
            user_id: User identifier
            query: Search query
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold (not used by AgentCore Memory API)
            
        Returns:
            List of relevant memory records
        """
        if not self.memory_id or not MEMORY_AVAILABLE:
            return []
        
        try:
            client = self._get_client()
            sanitized_actor_id = self._sanitize_actor_id(user_id)
            namespace = f"/semantic/{sanitized_actor_id}"
            
            # Run sync method in executor
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.retrieve_memory_records(
                    memoryId=self.memory_id,
                    namespace=namespace,
                    searchCriteria={
                        "searchQuery": query,
                        "topK": limit
                    }
                )
            )
            
            records = response.get("memoryRecords", [])
            # Convert to list of dicts with role/content format
            messages = []
            for record in records:
                content = record.get("content", {})
                if isinstance(content, dict):
                    text = content.get("text", "")
                else:
                    text = str(content) if content else ""
                
                if text:
                    messages.append({
                        "role": "assistant",  # Semantic memories are typically from past conversations
                        "content": text
                    })
            
            return messages
        except Exception as e:
            logger.error(f"Failed to perform semantic search: {e}")
            return []
    
    async def store_interaction(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        agent_response: str,
        agent_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Store interaction in memory with agent attribution.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            user_message: User's message
            agent_response: Agent's response
            agent_name: Name of the agent that handled the request
            metadata: Optional metadata to store
        """
        if not self.memory_id or not MEMORY_AVAILABLE:
            return
        
        try:
            client = self._get_client()
            sanitized_actor_id = self._sanitize_actor_id(user_id)
            
            # Run sync methods in executor
            import asyncio
            loop = asyncio.get_event_loop()
            
            # Store user message
            await loop.run_in_executor(
                None,
                lambda: client.create_event(
                    memory_id=self.memory_id,
                    actor_id=sanitized_actor_id,
                    session_id=session_id,
                    messages=[(user_message, "USER")]
                )
            )
            
            # Store agent response with attribution
            agent_response_with_metadata = agent_response
            if metadata or agent_name:
                # Add agent attribution to response
                attribution = f"[Handled by {agent_name}]"
                if metadata:
                    attribution += f" {metadata}"
                agent_response_with_metadata = f"{agent_response}\n{attribution}"
            
            await loop.run_in_executor(
                None,
                lambda: client.create_event(
                    memory_id=self.memory_id,
                    actor_id=sanitized_actor_id,
                    session_id=session_id,
                    messages=[(agent_response_with_metadata, "ASSISTANT")]
                )
            )
            
            logger.debug(f"Stored interaction for {sanitized_actor_id}, session {session_id}, agent {agent_name}")
        except Exception as e:
            logger.error(f"Failed to store interaction: {e}")
    
    async def close(self):
        """Close the memory client (no-op for AgentCore Memory client)."""
        pass

