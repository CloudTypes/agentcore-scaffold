"""Session manager for integrating memory with BidiAgent."""

import uuid
import logging
from typing import Optional, Dict, Any, List
from .client import MemoryClient

# Import config with fallback for direct execution
try:
    from ..config.runtime import get_config
except ImportError:
    # Fallback for direct execution
    from config.runtime import get_config

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
        """Initialize the session and load relevant memories from past sessions."""
        if self._initialized:
            return
        
        try:
            # Get configuration for number of past sessions to retrieve
            config = get_config()
            past_sessions_count = int(config.get_config_value("PAST_SESSIONS_COUNT", "3"))
            
            # Get list of all past sessions (retrieve extra to account for filtering out current session)
            logger.info(f"Retrieving past sessions for actor {self.actor_id} (requesting {past_sessions_count + 5} to filter)")
            all_sessions = self.memory_client.list_sessions(
                actor_id=self.actor_id,
                top_k=past_sessions_count + 5
            )
            
            # Filter out current session and take the most recent N sessions
            past_sessions = [
                session for session in all_sessions
                if session.get("session_id") != self.session_id
            ][:past_sessions_count]
            
            logger.info(f"Found {len(past_sessions)} past sessions (excluding current session {self.session_id})")
            
            # Retrieve full summaries for each past session
            session_summaries: List[Dict[str, Any]] = []
            for session in past_sessions:
                session_id = session.get("session_id")
                if not session_id:
                    continue
                
                try:
                    summary_record = self.memory_client.get_session_summary(
                        actor_id=self.actor_id,
                        session_id=session_id
                    )
                    
                    if summary_record:
                        # Extract summary text and metadata
                        content = summary_record.get("content", {})
                        if isinstance(content, dict):
                            summary_text = content.get("text", "")
                        else:
                            summary_text = str(content) if content else ""
                        
                        # Extract metadata
                        metadata = {
                            "session_id": session_id,
                            "created_at": summary_record.get("createdAt"),
                            "updated_at": summary_record.get("updatedAt"),
                        }
                        
                        if summary_text:
                            session_summaries.append({
                                "summary": summary_text,
                                "metadata": metadata
                            })
                            logger.debug(f"Retrieved summary for session {session_id}")
                        else:
                            logger.debug(f"Session {session_id} summary record found but has no text content")
                    else:
                        logger.debug(f"No summary record found for session {session_id} (may not be indexed yet)")
                except Exception as e:
                    logger.warning(f"Failed to retrieve summary for session {session_id}: {e}")
                    continue
            
            logger.info(f"Successfully retrieved {len(session_summaries)} session summaries out of {len(past_sessions)} past sessions")
            
            # Get user preferences
            preferences = self.memory_client.get_user_preferences(self.actor_id)
            
            # Build context string using structured format with conversational framing
            context_parts = []
            
            # Add past session summaries if available
            if session_summaries:
                context_parts.append("Here is relevant information from previous conversations with this user:\n")
                
                for idx, session_data in enumerate(session_summaries, 1):
                    summary_text = session_data["summary"]
                    metadata = session_data["metadata"]
                    session_id = metadata.get("session_id", "unknown")
                    
                    # Format with optional metadata
                    timestamp_info = ""
                    if metadata.get("created_at") or metadata.get("updated_at"):
                        timestamp = metadata.get("updated_at") or metadata.get("created_at")
                        if timestamp:
                            timestamp_info = f", {timestamp}"
                    
                    if timestamp_info:
                        context_parts.append(f"[Memory {idx}] (Session: {session_id}{timestamp_info}): {summary_text}")
                    else:
                        context_parts.append(f"[Memory {idx}] (Session: {session_id}): {summary_text}")
                
                context_parts.append("")  # Empty line for spacing
            
            # Add user preferences if available
            if preferences:
                context_parts.append("User Preferences:")
                for pref in preferences[:3]:  # Top 3 preferences
                    # Extract preference text
                    if isinstance(pref, dict):
                        content = pref.get("content", {})
                        if isinstance(content, dict):
                            pref_text = content.get("text", "")
                        else:
                            pref_text = str(content) if content else ""
                    elif hasattr(pref, 'content'):
                        content = pref.content
                        if isinstance(content, dict):
                            pref_text = content.get("text", "")
                        else:
                            pref_text = str(content) if content else ""
                    else:
                        pref_text = str(pref)
                    
                    if pref_text:
                        context_parts.append(f"- {pref_text}")
                
                context_parts.append("")  # Empty line for spacing
            
            # Add closing instruction
            if session_summaries or preferences:
                context_parts.append("Use this information to provide personalized responses.")
            
            self._context_memories = "\n".join(context_parts) if context_parts else None
            
            # Store session start event
            self.memory_client.store_event(
                actor_id=self.actor_id,
                session_id=self.session_id,
                event_type="session_start",
                payload={"session_id": self.session_id}
            )
            
            self._initialized = True
            logger.info(f"Initialized session {self.session_id} for actor {self.actor_id} with {len(session_summaries)} past session summaries")
        except Exception as e:
            logger.error(f"Failed to initialize session: {e}", exc_info=True)
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
        
        try:
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
        except Exception as e:
            logger.error(f"Failed to store user input: {e}")
    
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
        
        try:
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
        except Exception as e:
            logger.error(f"Failed to store agent response: {e}")
    
    def store_tool_use(self, tool_name: str, input_data: Dict[str, Any], output_data: Dict[str, Any]) -> None:
        """
        Store tool use event.
        
        Args:
            tool_name: Name of the tool used
            input_data: Tool input parameters
            output_data: Tool output/result
        """
        try:
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
        except Exception as e:
            logger.error(f"Failed to store tool use: {e}")
    
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

