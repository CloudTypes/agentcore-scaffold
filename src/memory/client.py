"""AgentCore Memory client for storing and retrieving memories."""

import os
import logging
from typing import Optional, Dict, Any, List
import boto3

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
    """Client for interacting with AgentCore Memory."""
    
    def __init__(self, region: Optional[str] = None, memory_id: Optional[str] = None):
        """
        Initialize the memory client.
        
        Args:
            region: AWS region for memory resource
            memory_id: Optional memory resource ID (will be created if not provided)
        """
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.memory_id = memory_id or os.getenv("AGENTCORE_MEMORY_ID")
        self._client = None
        self._control_plane_client = None
        self._memory_resource = None
        
    def _get_client(self) -> AgentCoreMemoryClient:
        """Get or create the AgentCore Memory client."""
        if not MEMORY_AVAILABLE:
            raise RuntimeError("AgentCore Memory is not available")
        if self._client is None:
            self._client = AgentCoreMemoryClient(region_name=self.region)
        return self._client
    
    def _get_control_plane_client(self) -> MemoryControlPlaneClient:
        """Get or create the Memory Control Plane client for management operations."""
        if not MEMORY_AVAILABLE:
            raise RuntimeError("AgentCore Memory is not available")
        if self._control_plane_client is None:
            self._control_plane_client = MemoryControlPlaneClient(region_name=self.region)
        return self._control_plane_client
    
    def create_memory_resource(self, name: str = "voice-agent-memory") -> Dict[str, Any]:
        """
        Create or get existing memory resource.
        
        Args:
            name: Name for the memory resource
            
        Returns:
            Memory resource information including memory_id
        """
        client = self._get_client()
        control_plane_client = self._get_control_plane_client()
        
        # If memory_id is provided, try to get existing resource
        if self.memory_id:
            try:
                memory = control_plane_client.get_memory(memory_id=self.memory_id)
                logger.info(f"Using existing memory resource: {self.memory_id}")
                
                # Check if memory has strategies configured
                strategies = memory.get("strategies", [])
                if not strategies:
                    logger.warning(
                        f"⚠️  Memory resource {self.memory_id} has NO strategies configured! "
                        "Events will be stored in short-term memory but will NOT be processed into long-term memory. "
                        "To fix this:\n"
                        "1. Delete the existing memory resource (via CDK: cdk destroy, or AWS Console)\n"
                        "2. Remove AGENTCORE_MEMORY_ID from your environment\n"
                        "3. Restart the application - it will create a new memory with strategies\n"
                        "OR manually add strategies via AWS Console/CLI"
                    )
                else:
                    strategy_types = [s.get("type", "unknown") for s in strategies]
                    logger.info(f"Memory has {len(strategies)} strategy(ies) configured: {', '.join(strategy_types)}")
                
                self._memory_resource = memory
                return memory
            except Exception as e:
                logger.warning(f"Could not get existing memory {self.memory_id}: {e}")
                logger.info("Creating new memory resource...")
        
        # Create new memory resource with all three strategies
        # Note: Strategies should not include "name" field - only "type" and "namespaces"
        try:
            memory = client.create_memory(
                name=name,
                description="Memory resource for voice agent with short-term and long-term memory",
                strategies=[
                    {
                        "type": "summaryMemoryStrategy",
                        "namespaces": ["/summaries/{actorId}/{sessionId}"]
                    },
                    {
                        "type": "userPreferenceMemoryStrategy",
                        "namespaces": ["/preferences/{actorId}"]
                    },
                    {
                        "type": "semanticMemoryStrategy",
                        "namespaces": ["/semantic/{actorId}"]
                    }
                ]
            )
            self.memory_id = memory.get("memoryId")
            self._memory_resource = memory
            logger.info(f"Created memory resource: {self.memory_id}")
            return memory
        except Exception as e:
            logger.error(f"Failed to create memory resource: {e}")
            raise
    
    def _sanitize_actor_id(self, actor_id: str) -> str:
        """
        Sanitize actor_id to match AgentCore Memory requirements.
        Pattern: [a-zA-Z0-9][a-zA-Z0-9-_/]*(?::[a-zA-Z0-9-_/]+)*[a-zA-Z0-9-_/]*
        Replaces @ with _ and ensures it starts with alphanumeric.
        """
        # Replace @ with _ and ensure it starts with alphanumeric
        sanitized = actor_id.replace("@", "_").replace(".", "_")
        # Ensure it starts with alphanumeric
        if not sanitized[0].isalnum():
            sanitized = "user_" + sanitized
        return sanitized
    
    def store_event(
        self,
        actor_id: str,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> None:
        """
        Store a conversation event in memory (STM).
        
        Args:
            actor_id: User identifier (email - will be sanitized)
            session_id: Session identifier
            event_type: Type of event (e.g., "user_input", "agent_response", "tool_use")
            payload: Event data
        """
        if not self.memory_id:
            logger.warning("Memory ID not set, cannot store event")
            return
        
        if not MEMORY_AVAILABLE:
            logger.warning("Memory not available, cannot store event")
            return
        
        try:
            client = self._get_client()
            # Sanitize actor_id to match AgentCore requirements (no @ symbols)
            sanitized_actor_id = self._sanitize_actor_id(actor_id)
            
            # create_event expects messages as list of (text, role) tuples
            # Convert event_type and payload to message format
            role = "USER" if event_type == "user_input" else "ASSISTANT" if event_type == "agent_response" else "TOOL"
            
            # Extract text from payload - try multiple fields
            text = None
            if isinstance(payload, dict):
                text = payload.get("text") or payload.get("content") or payload.get("audio_transcript")
            
            # If still no text, convert payload to string
            if not text:
                text = str(payload) if payload else ""
            
            # Ensure text is not empty
            if not text or not text.strip():
                logger.debug(f"Skipping event storage - no text content for {event_type}")
                return
            
            messages = [(text, role)]
            
            client.create_event(
                memory_id=self.memory_id,
                actor_id=sanitized_actor_id,
                session_id=session_id,
                messages=messages
            )
            logger.debug(f"Stored event: {event_type} for actor {sanitized_actor_id}, session {session_id}")
        except Exception as e:
            logger.error(f"Failed to store event: {e}")
    
    def retrieve_memories(
        self,
        actor_id: str,
        query: Optional[str] = None,
        namespace_prefix: Optional[str] = None,
        top_k: int = 5
    ) -> List[Any]:
        """
        Retrieve relevant memories (LTM) for a user.
        
        Args:
            actor_id: User identifier (email)
            query: Optional query string for semantic search
            namespace_prefix: Optional namespace prefix to filter memories
            top_k: Number of memories to retrieve
            
        Returns:
            List of memory records
        """
        if not self.memory_id:
            logger.warning("Memory ID not set, cannot retrieve memories")
            return []
        
        if not MEMORY_AVAILABLE:
            return []
        
        try:
            client = self._get_client()
            
            # searchQuery is required and must have min length 1
            # If no query provided, skip retrieval
            if not query or not query.strip():
                logger.debug("No query provided, skipping memory retrieval")
                return []
            
            # Sanitize actor_id for namespace
            sanitized_actor_id = self._sanitize_actor_id(actor_id)
            
            # Build namespace if not provided
            if namespace_prefix is None:
                namespace = f"/semantic/{sanitized_actor_id}"
            else:
                # Replace actorId placeholder in namespace
                namespace = namespace_prefix.replace("{actorId}", sanitized_actor_id)
            
            # Build searchCriteria dict
            search_criteria = {
                "searchQuery": query.strip(),
                "topK": top_k
            }
            
            # Retrieve memory records using correct API signature
            response = client.retrieve_memory_records(
                memoryId=self.memory_id,
                namespace=namespace,
                searchCriteria=search_criteria
            )
            
            # Extract records from response
            records = response.get("memoryRecords", [])
            logger.debug(f"Retrieved {len(records)} memories for actor {sanitized_actor_id}")
            return records
        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            return []
    
    def get_session_summary(self, actor_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get summary for a specific session using ListMemoryRecords (no semantic search required).
        
        Args:
            actor_id: User identifier (email)
            session_id: Session identifier
            
        Returns:
            Session summary or None if not found
        """
        if not self.memory_id:
            return None
        
        try:
            # Use boto3 client directly for ListMemoryRecords (doesn't require semantic search)
            bedrock_client = boto3.client('bedrock-agentcore', region_name=self.region)
            
            # Sanitize actor_id for namespace
            sanitized_actor_id = self._sanitize_actor_id(actor_id)
            namespace = f"/summaries/{sanitized_actor_id}/{session_id}"
            
            # Use ListMemoryRecords to get all records in this namespace
            # This doesn't require a semantic search query
            try:
                response = bedrock_client.list_memory_records(
                    memoryId=self.memory_id,
                    namespace=namespace,
                    maxResults=10
                )
                
                records = response.get("memoryRecords", [])
                
                if records:
                    # Return the first (and likely only) record
                    record = records[0]
                    # Convert to dict if needed
                    if isinstance(record, dict):
                        return record
                    elif hasattr(record, 'to_dict'):
                        return record.to_dict()
                    elif hasattr(record, '__dict__'):
                        return record.__dict__
                    else:
                        return {"content": str(record)}
                
                logger.debug(f"No records found in exact namespace: {namespace}")
                
                # Try parent namespace (without session ID) and filter
                parent_namespace = f"/summaries/{sanitized_actor_id}"
                try:
                    response = bedrock_client.list_memory_records(
                        memoryId=self.memory_id,
                        namespace=parent_namespace,
                        maxResults=100
                    )
                    all_records = response.get("memoryRecords", [])
                    # Filter for this specific session ID
                    for record in all_records:
                        record_ns = record.get("namespace", "")
                        if session_id in record_ns:
                            if isinstance(record, dict):
                                return record
                            elif hasattr(record, 'to_dict'):
                                return record.to_dict()
                            elif hasattr(record, '__dict__'):
                                return record.__dict__
                            else:
                                return {"content": str(record)}
                    
                    logger.debug(f"No records found for session {session_id} in parent namespace")
                except Exception as e2:
                    logger.debug(f"Parent namespace query failed: {e2}")
                
                return None
            except Exception as e:
                logger.debug(f"ListMemoryRecords failed for {namespace}: {e}")
                # Fallback to semantic search if ListMemoryRecords fails
                return self._get_session_summary_via_search(actor_id, session_id, sanitized_actor_id, namespace)
        except Exception as e:
            logger.error(f"Failed to get session summary: {e}", exc_info=True)
            return None
    
    def _get_session_summary_via_search(self, actor_id: str, session_id: str, sanitized_actor_id: str, namespace: str) -> Optional[Dict[str, Any]]:
        """Fallback method using semantic search."""
        try:
            client = self._get_client()
            query_terms = ["greeting", "conversation", "user", "assistant", "hello", "help", "topic"]
            
            for query_term in query_terms:
                try:
                    response = client.retrieve_memory_records(
                        memoryId=self.memory_id,
                        namespace=namespace,
                        searchCriteria={
                            "searchQuery": query_term,
                            "topK": 1
                        }
                    )
                    found_records = response.get("memoryRecords", [])
                    if found_records:
                        record = found_records[0]
                        if isinstance(record, dict):
                            return record
                        elif hasattr(record, 'to_dict'):
                            return record.to_dict()
                        elif hasattr(record, '__dict__'):
                            return record.__dict__
                        else:
                            return {"content": str(record)}
                except Exception:
                    continue
            return None
        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            return None
    
    def get_user_preferences(self, actor_id: str) -> List[Any]:
        """
        Get user preferences from memory.
        
        Args:
            actor_id: User identifier (email)
            
        Returns:
            List of preference memory records
        """
        # Use a query to retrieve preferences (searchQuery is required)
        return self.retrieve_memories(
            actor_id=actor_id,
            namespace_prefix=f"/preferences/{{actorId}}",
            query="user preferences",
            top_k=10
        )
    
    def list_sessions(self, actor_id: str, top_k: int = 50) -> List[Dict[str, Any]]:
        """
        List all sessions for an actor by using list_events to find sessions,
        then querying summaries for each session.
        
        Args:
            actor_id: User identifier (email)
            top_k: Maximum number of sessions to retrieve
            
        Returns:
            List of session dictionaries with session_id and summary
        """
        if not self.memory_id:
            return []
        
        if not MEMORY_AVAILABLE:
            return []
        
        try:
            client = self._get_client()
            sanitized_actor_id = self._sanitize_actor_id(actor_id)
            
            # Strategy: Use list_events with a known session to get events,
            # but we need to find sessions first. Since list_events requires session_id,
            # we'll try a different approach: query summaries with very broad terms
            # and extract session IDs from the namespaces of returned records.
            
            # Use ListMemoryRecords via boto3 to get all records without semantic search
            # This is more reliable than semantic search for listing all sessions
            bedrock_client = boto3.client('bedrock-agentcore', region_name=self.region)
            namespace = f"/summaries/{sanitized_actor_id}"
            
            try:
                # Try to list records in the actor's summaries namespace
                # Note: ListMemoryRecords might require exact namespace match
                response = bedrock_client.list_memory_records(
                    memoryId=self.memory_id,
                    namespace=namespace,
                    maxResults=top_k * 10  # Get more to find all sessions
                )
                
                records = response.get("memoryRecords", [])
                
                # Extract unique session IDs from namespaces
                seen_session_ids = set()
                sessions = []
                
                for record in records:
                    ns = record.get("namespace", "")
                    # Namespace format: /summaries/{actorId}/{sessionId}
                    parts = ns.split("/")
                    if len(parts) >= 4 and parts[1] == "summaries":
                        session_id = parts[-1]
                        if session_id and session_id not in seen_session_ids:
                            seen_session_ids.add(session_id)
                            
                            # Extract summary text
                            content = record.get("content", {})
                            if isinstance(content, dict):
                                text = content.get("text", "")
                            else:
                                text = str(content) if content else ""
                            
                            sessions.append({
                                "session_id": session_id,
                                "summary": text[:200] if text else "No summary available"
                            })
                            
                            if len(sessions) >= top_k:
                                break
                
                if sessions:
                    logger.info(f"Found {len(sessions)} sessions using ListMemoryRecords")
                    return sessions
            except Exception as e:
                logger.debug(f"ListMemoryRecords failed for namespace {namespace}: {e}")
                # Fallback: try querying individual session namespaces
                # We'd need to know session IDs first, which is a chicken-and-egg problem
                # So fall back to semantic search approach
                pass
            
            # Fallback to semantic search if ListMemoryRecords doesn't work
            query_terms = ["conversation", "greeting", "user", "assistant", "hello", "help"]
            all_records = []
            
            for query_term in query_terms:
                try:
                    response = client.retrieve_memory_records(
                        memoryId=self.memory_id,
                        namespace=namespace,
                        searchCriteria={
                            "searchQuery": query_term,
                            "topK": top_k * 2
                        }
                    )
                    found_records = response.get("memoryRecords", [])
                    if found_records:
                        all_records.extend(found_records)
                except Exception:
                    continue
            
            # Deduplicate by namespace and extract session IDs
            seen_namespaces = set()
            sessions = []
            seen_session_ids = set()
            
            for record in all_records:
                ns = record.get("namespace", "")
                if ns and ns not in seen_namespaces:
                    seen_namespaces.add(ns)
                    parts = ns.split("/")
                    if len(parts) >= 4 and parts[1] == "summaries":
                        session_id = parts[-1]
                        if session_id and session_id not in seen_session_ids:
                            seen_session_ids.add(session_id)
                            
                            content = record.get("content", {})
                            if isinstance(content, dict):
                                text = content.get("text", "")
                            else:
                                text = str(content) if content else ""
                            
                            sessions.append({
                                "session_id": session_id,
                                "summary": text[:200] if text else "No summary available"
                            })
                            
                            if len(sessions) >= top_k:
                                break
            
            # If we didn't find any summaries, try using list_events with a workaround
            # by getting events and extracting unique session IDs
            if not sessions:
                logger.debug("No summaries found via retrieve_memory_records, trying list_events approach")
                # Note: list_events requires session_id, so we can't use it to list all sessions
                # This is a limitation - we'd need to know session IDs first
            
            logger.info(f"Found {len(sessions)} sessions for actor {sanitized_actor_id}")
            return sessions
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}", exc_info=True)
            return []

