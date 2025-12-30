"""Session manager for integrating memory with BidiAgent."""

import uuid
import logging
from typing import Optional, Dict, Any
from .client import MemoryClient

logger = logging.getLogger(__name__)


class MemorySessionManager:
    """Manages session lifecycle and memory integration with BidiAgent."""
    
    def __init__(self, memory_client: MemoryClient, actor_id: str, session_id: Optional[str] = None):
        """
        Initialize session manager.
        
        Args:
            memory_client: Memory client instance
            actor_id: User identifier (email)
            session_id: Optional session ID (will be generated if not provided)
        """
        self.memory_client = memory_client
        self.actor_id = actor_id
        self.session_id = session_id or str(uuid.uuid4())
        self._context_memories: Optional[str] = None
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize the session and load relevant memories."""
        if self._initialized:
            return
        
        try:
            # Retrieve relevant memories for context
            memories = self.memory_client.retrieve_memories(
                actor_id=self.actor_id,
                top_k=5
            )
            
            # Get user preferences
            preferences = self.memory_client.get_user_preferences(self.actor_id)
            
            # Build context string from memories
            context_parts = []
            
            if preferences:
                context_parts.append("User Preferences:")
                for pref in preferences[:3]:  # Top 3 preferences
                    if hasattr(pref, 'content'):
                        context_parts.append(f"- {pref.content}")
            
            if memories:
                context_parts.append("\nRelevant Past Conversations:")
                for mem in memories[:3]:  # Top 3 memories
                    if hasattr(mem, 'content'):
                        context_parts.append(f"- {mem.content}")
            
            self._context_memories = "\n".join(context_parts) if context_parts else None
            
            # Store session start event
            self.memory_client.store_event(
                actor_id=self.actor_id,
                session_id=self.session_id,
                event_type="session_start",
                payload={"session_id": self.session_id}
            )
            
            self._initialized = True
            logger.info(f"Initialized session {self.session_id} for actor {self.actor_id}")
        except Exception as e:
            logger.error(f"Failed to initialize session: {e}")
            self._initialized = True  # Continue even if memory fails
    
    def get_context(self) -> Optional[str]:
        """Get memory context to inject into system prompt."""
        return self._context_memories
    
    def store_user_input(self, text: Optional[str] = None, audio_transcript: Optional[str] = None) -> None:
        """
        Store user input event.
        
        Args:
            text: Text input (if any)
            audio_transcript: Audio transcript (if any)
        """
        content = text or audio_transcript
        if not content:
            return
        
        self.memory_client.store_event(
            actor_id=self.actor_id,
            session_id=self.session_id,
            event_type="user_input",
            payload={
                "text": text,
                "audio_transcript": audio_transcript,
                "content": content
            }
        )
    
    def store_agent_response(self, text: Optional[str] = None, audio_transcript: Optional[str] = None) -> None:
        """
        Store agent response event.
        
        Args:
            text: Text response (if any)
            audio_transcript: Audio transcript (if any)
        """
        content = text or audio_transcript
        if not content:
            return
        
        self.memory_client.store_event(
            actor_id=self.actor_id,
            session_id=self.session_id,
            event_type="agent_response",
            payload={
                "text": text,
                "audio_transcript": audio_transcript,
                "content": content
            }
        )
    
    def store_tool_use(self, tool_name: str, input_data: Dict[str, Any], output_data: Dict[str, Any]) -> None:
        """
        Store tool use event.
        
        Args:
            tool_name: Name of the tool used
            input_data: Tool input parameters
            output_data: Tool output/result
        """
        self.memory_client.store_event(
            actor_id=self.actor_id,
            session_id=self.session_id,
            event_type="tool_use",
            payload={
                "tool_name": tool_name,
                "input": input_data,
                "output": output_data
            }
        )
    
    async def finalize(self) -> None:
        """Finalize the session and store session end event."""
        try:
            self.memory_client.store_event(
                actor_id=self.actor_id,
                session_id=self.session_id,
                event_type="session_end",
                payload={"session_id": self.session_id}
            )
            logger.info(f"Finalized session {self.session_id} for actor {self.actor_id}")
        except Exception as e:
            logger.error(f"Failed to finalize session: {e}")

