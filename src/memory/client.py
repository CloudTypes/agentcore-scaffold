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
    from bedrock_agentcore.memory.constants import StrategyType

    MEMORY_AVAILABLE = True
except ImportError:
    logger.warning("bedrock_agentcore.memory not available - memory features disabled")
    MEMORY_AVAILABLE = False
    AgentCoreMemoryClient = None
    MemoryControlPlaneClient = None
    Event = None
    MemoryRecord = None
    StrategyType = None


class MemoryClient:
    """Client for interacting with AgentCore Memory."""

    def __init__(self, region: Optional[str] = None, memory_id: Optional[str] = None):
        """
        Initialize the memory client.

        Args:
            region: AWS region for memory resource
            memory_id: Optional memory resource ID (will be created if not provided)
        """
        # Check AGENTCORE_MEMORY_REGION first, then AWS_REGION, then default
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
        # Format strategies using StrategyType constants (matches scripts/manage_memory.py)
        if not MEMORY_AVAILABLE or StrategyType is None:
            raise RuntimeError("AgentCore Memory is not available")

        try:
            strategies = [
                {
                    StrategyType.SUMMARY.value: {
                        "name": "SessionSummarizer",
                        "description": "Captures summaries of conversations",
                        "namespaces": ["/summaries/{actorId}/{sessionId}"],
                    }
                },
                {
                    StrategyType.USER_PREFERENCE.value: {
                        "name": "UserPreferences",
                        "description": "Captures user preferences and behavior",
                        "namespaces": ["/preferences/{actorId}"],
                    }
                },
                {
                    StrategyType.SEMANTIC.value: {
                        "name": "SemanticMemory",
                        "description": "Stores factual information using vector embeddings",
                        "namespaces": ["/semantic/{actorId}"],
                    }
                },
            ]

            memory = client.create_memory(
                name=name,
                description="Memory resource for voice agent with short-term and long-term memory",
                strategies=strategies,
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

    def store_event(self, actor_id: str, session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
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
                memory_id=self.memory_id, actor_id=sanitized_actor_id, session_id=session_id, messages=messages
            )
            logger.debug(f"Stored event: {event_type} for actor {sanitized_actor_id}, session {session_id}")
        except Exception as e:
            logger.error(f"Failed to store event: {e}")

    def retrieve_memories(
        self,
        actor_id: str,
        query: Optional[str] = None,
        namespace_prefix: Optional[str] = None,
        top_k: int = 5,
        memory_type: Optional[str] = None,
    ) -> List[Any]:
        """
        Retrieve relevant memories (LTM) for a user.

        Args:
            actor_id: User identifier (email)
            query: Optional query string for semantic search (required for semantic/preferences)
            namespace_prefix: Optional namespace prefix to filter memories
            top_k: Number of memories to retrieve
            memory_type: Type of memory to retrieve - "summaries", "preferences", or "semantic" (default: semantic)

        Returns:
            List of memory records
        """
        if not self.memory_id:
            logger.warning("Memory ID not set, cannot retrieve memories")
            return []

        if not MEMORY_AVAILABLE:
            return []

        try:
            # Sanitize actor_id for namespace
            sanitized_actor_id = self._sanitize_actor_id(actor_id)

            # Determine memory type and namespace
            if memory_type == "summaries" or (namespace_prefix and "summaries" in namespace_prefix):
                # For summaries, use ListMemoryRecords (no semantic search needed)
                return self._retrieve_summaries_list(actor_id, sanitized_actor_id, namespace_prefix, top_k)
            elif memory_type == "preferences" or (namespace_prefix and "preferences" in namespace_prefix):
                # For preferences, try ListMemoryRecords first, fall back to semantic search
                return self._retrieve_preferences_list(
                    actor_id, sanitized_actor_id, top_k
                ) or self._retrieve_memories_semantic(actor_id, sanitized_actor_id, query, namespace_prefix, top_k)
            else:
                # For semantic memory, use semantic search (requires query)
                return self._retrieve_memories_semantic(actor_id, sanitized_actor_id, query, namespace_prefix, top_k)
        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}", exc_info=True)
            return []

    def _retrieve_memories_semantic(
        self, actor_id: str, sanitized_actor_id: str, query: Optional[str], namespace_prefix: Optional[str], top_k: int
    ) -> List[Any]:
        """Retrieve memories using semantic search (for semantic memory type)."""
        client = self._get_client()

        # searchQuery is required and must have min length 1
        # If no query provided, skip retrieval
        if not query or not query.strip():
            logger.debug("No query provided for semantic search, skipping memory retrieval")
            return []

        # Build namespace if not provided
        if namespace_prefix is None:
            namespace = f"/semantic/{sanitized_actor_id}"
        else:
            # Replace actorId placeholder in namespace
            namespace = namespace_prefix.replace("{actorId}", sanitized_actor_id)

        # Build searchCriteria dict
        search_criteria = {"searchQuery": query.strip(), "topK": top_k}

        # Retrieve memory records using correct API signature
        response = client.retrieve_memory_records(memoryId=self.memory_id, namespace=namespace, searchCriteria=search_criteria)

        # Extract records from response
        records = response.get("memoryRecords", [])
        logger.debug(f"Retrieved {len(records)} semantic memories for actor {sanitized_actor_id}")
        return records

    def _retrieve_summaries_list(
        self, actor_id: str, sanitized_actor_id: str, namespace_prefix: Optional[str], top_k: int
    ) -> List[Any]:
        """Retrieve summaries using ListMemoryRecords (no semantic search required)."""
        bedrock_client = boto3.client("bedrock-agentcore", region_name=self.region)

        # Build namespace
        if namespace_prefix:
            namespace = namespace_prefix.replace("{actorId}", sanitized_actor_id)
        else:
            namespace = f"/summaries/{sanitized_actor_id}"

        all_records = []
        next_token = None

        try:
            while len(all_records) < top_k:
                params = {"memoryId": self.memory_id, "namespace": namespace, "maxResults": min(100, top_k - len(all_records))}
                if next_token:
                    params["nextToken"] = next_token

                response = bedrock_client.list_memory_records(**params)
                records = response.get("memoryRecordSummaries", response.get("memoryRecords", []))
                # Add namespace to each record (since it's not in the response)
                for record in records:
                    if isinstance(record, dict) and "namespace" not in record:
                        record["namespace"] = namespace
                all_records.extend(records)

                next_token = response.get("nextToken")
                if not next_token or len(records) == 0:
                    break

            logger.debug(f"Retrieved {len(all_records)} summaries using ListMemoryRecords for actor {sanitized_actor_id}")
            return all_records[:top_k]
        except Exception as e:
            logger.error(f"Failed to retrieve summaries using ListMemoryRecords: {e}")
            return []

    def _retrieve_preferences_list(self, actor_id: str, sanitized_actor_id: str, top_k: int) -> List[Any]:
        """Retrieve preferences using ListMemoryRecords (no semantic search required)."""
        bedrock_client = boto3.client("bedrock-agentcore", region_name=self.region)
        namespace = f"/preferences/{sanitized_actor_id}"

        all_records = []
        next_token = None

        try:
            while len(all_records) < top_k:
                params = {"memoryId": self.memory_id, "namespace": namespace, "maxResults": min(100, top_k - len(all_records))}
                if next_token:
                    params["nextToken"] = next_token

                response = bedrock_client.list_memory_records(**params)
                records = response.get("memoryRecordSummaries", response.get("memoryRecords", []))
                # Add namespace to each record (since it's not in the response)
                for record in records:
                    if isinstance(record, dict) and "namespace" not in record:
                        record["namespace"] = namespace
                all_records.extend(records)

                next_token = response.get("nextToken")
                if not next_token or len(records) == 0:
                    break

            logger.debug(f"Retrieved {len(all_records)} preferences using ListMemoryRecords for actor {sanitized_actor_id}")
            return all_records[:top_k]
        except Exception as e:
            logger.debug(f"Failed to retrieve preferences using ListMemoryRecords: {e}")
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
            bedrock_client = boto3.client("bedrock-agentcore", region_name=self.region)

            # Sanitize actor_id for namespace
            sanitized_actor_id = self._sanitize_actor_id(actor_id)
            namespace = f"/summaries/{sanitized_actor_id}/{session_id}"

            # Use ListMemoryRecords to get all records in this namespace with pagination
            # This doesn't require a semantic search query
            try:
                all_records = []
                next_token = None

                while True:
                    params = {"memoryId": self.memory_id, "namespace": namespace, "maxResults": 100}
                    if next_token:
                        params["nextToken"] = next_token

                    response = bedrock_client.list_memory_records(**params)
                    records = response.get("memoryRecordSummaries", response.get("memoryRecords", []))
                    # Add namespace to each record (since it's not in the response)
                    for record in records:
                        if isinstance(record, dict) and "namespace" not in record:
                            record["namespace"] = namespace
                    all_records.extend(records)

                    next_token = response.get("nextToken")
                    if not next_token or len(records) == 0:
                        break

                if all_records:
                    # Return the first (and likely only) record
                    record = all_records[0]
                    # Convert to dict if needed
                    if isinstance(record, dict):
                        return record
                    elif hasattr(record, "to_dict"):
                        return record.to_dict()
                    elif hasattr(record, "__dict__"):
                        return record.__dict__
                    else:
                        return {"content": str(record)}

                logger.debug(f"No records found in exact namespace: {namespace}")

                # Try parent namespace (without session ID) and filter with pagination
                parent_namespace = f"/summaries/{sanitized_actor_id}"
                try:
                    all_parent_records = []
                    next_token = None

                    while True:
                        params = {"memoryId": self.memory_id, "namespace": parent_namespace, "maxResults": 100}
                        if next_token:
                            params["nextToken"] = next_token

                        response = bedrock_client.list_memory_records(**params)
                        records = response.get("memoryRecordSummaries", response.get("memoryRecords", []))
                        # Add namespace to each record (since it's not in the response)
                        for record in records:
                            if isinstance(record, dict) and "namespace" not in record:
                                record["namespace"] = parent_namespace
                        all_parent_records.extend(records)

                        next_token = response.get("nextToken")
                        if not next_token or len(records) == 0:
                            break

                    # Filter for this specific session ID
                    for record in all_parent_records:
                        record_ns = record.get("namespace", "")
                        if session_id in record_ns:
                            if isinstance(record, dict):
                                return record
                            elif hasattr(record, "to_dict"):
                                return record.to_dict()
                            elif hasattr(record, "__dict__"):
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

    def _get_session_summary_via_search(
        self, actor_id: str, session_id: str, sanitized_actor_id: str, namespace: str
    ) -> Optional[Dict[str, Any]]:
        """Fallback method using semantic search."""
        try:
            client = self._get_client()
            query_terms = ["greeting", "conversation", "user", "assistant", "hello", "help", "topic"]

            for query_term in query_terms:
                try:
                    response = client.retrieve_memory_records(
                        memoryId=self.memory_id, namespace=namespace, searchCriteria={"searchQuery": query_term, "topK": 1}
                    )
                    found_records = response.get("memoryRecordSummaries", response.get("memoryRecords", []))
                    if found_records:
                        record = found_records[0]
                        if isinstance(record, dict):
                            return record
                        elif hasattr(record, "to_dict"):
                            return record.to_dict()
                        elif hasattr(record, "__dict__"):
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
        Get user preferences from memory using ListMemoryRecords.

        Args:
            actor_id: User identifier (email)

        Returns:
            List of preference memory records
        """
        # Try ListMemoryRecords first (no query needed)
        preferences = self._retrieve_preferences_list(actor_id, self._sanitize_actor_id(actor_id), 10)
        if preferences:
            return preferences

        # Fall back to semantic search if ListMemoryRecords returns nothing
        return self.retrieve_memories(
            actor_id=actor_id,
            namespace_prefix=f"/preferences/{{actorId}}",
            query="user preferences",
            top_k=10,
            memory_type="preferences",
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
            bedrock_client = boto3.client("bedrock-agentcore", region_name=self.region)
            namespace = f"/summaries/{sanitized_actor_id}"

            try:
                # Try to list records in the actor's summaries namespace with pagination
                all_records = []
                next_token = None

                while len(all_records) < top_k * 10:
                    params = {"memoryId": self.memory_id, "namespace": namespace, "maxResults": 100}
                    if next_token:
                        params["nextToken"] = next_token

                    response = bedrock_client.list_memory_records(**params)
                    records = response.get("memoryRecordSummaries", response.get("memoryRecords", []))
                    # IMPORTANT: Don't overwrite namespace - list_memory_records might return the actual namespace
                    # Only set parent namespace if the field is completely missing
                    for record in records:
                        if isinstance(record, dict):
                            # Preserve any existing namespace - don't overwrite it
                            if "namespace" not in record or not record.get("namespace"):
                                # Only set parent namespace if truly missing
                                record["namespace"] = namespace
                            else:
                                # Log if we found a namespace in the response
                                logger.debug(
                                    f"Record {record.get('memoryRecordId', 'unknown')} has namespace: {record.get('namespace')}"
                                )
                    all_records.extend(records)

                    next_token = response.get("nextToken")
                    if not next_token or len(records) == 0:
                        break

                # Extract unique session IDs from records
                # When querying parent namespace, the API doesn't return the full namespace path
                # We MUST use GetMemoryRecord to get the actual namespace for each record
                seen_session_ids = set()
                sessions = []

                logger.info(
                    f"Found {len(all_records)} records in parent namespace, using GetMemoryRecord to extract session IDs"
                )
                # Temporarily enable debug logging for namespace extraction
                original_level = logger.level
                logger.setLevel(logging.DEBUG)

                # Use GetMemoryRecord to get the full namespace for each record
                # This is necessary because list_memory_records doesn't return full namespace paths
                # when querying a parent namespace
                processed = 0
                for record in all_records[: min(50, top_k * 5)]:  # Limit to avoid too many API calls
                    record_id = record.get("memoryRecordId") or record.get("recordId")
                    if not record_id:
                        logger.debug(f"Record missing memoryRecordId, skipping")
                        continue

                    processed += 1
                    try:
                        get_response = bedrock_client.get_memory_record(memoryId=self.memory_id, memoryRecordId=record_id)

                        full_record = get_response.get("memoryRecord", {})

                        # GetMemoryRecord returns 'namespaces' (plural, array) not 'namespace' (singular)
                        namespaces_list = full_record.get("namespaces", [])
                        # Get the original namespace from list_memory_records (before we might have overwritten it)
                        original_ns = record.get("namespace", "")

                        logger.debug(
                            f"Record {record_id}: namespaces array={namespaces_list}, original_ns={original_ns}, parent_ns={namespace}"
                        )

                        # Try to get namespace from multiple sources, in order of preference:
                        # 1. namespaces array from GetMemoryRecord (most reliable - contains full path)
                        # 2. original namespace from list_memory_records (if it's a full path, not parent)
                        # 3. other possible locations
                        full_ns = ""
                        if namespaces_list and len(namespaces_list) > 0:
                            # Use the first namespace from the array
                            full_ns = namespaces_list[0] if isinstance(namespaces_list[0], str) else str(namespaces_list[0])
                            logger.info(f"Record {record_id}: Using namespace from 'namespaces' array: {full_ns}")
                        elif original_ns and original_ns != namespace:
                            # Use original namespace if it's different from parent (means it's a full path)
                            full_ns = original_ns
                            logger.info(f"Record {record_id}: Using original record namespace: {full_ns}")
                        else:
                            # Try other possible locations
                            full_ns = (
                                full_record.get("namespace")
                                or full_record.get("namespacePath")
                                or get_response.get("namespace")
                                or ""
                            )

                        logger.debug(f"Record {record_id}: Final namespace='{full_ns}'")

                        if not full_ns:
                            logger.warning(
                                f"Record {record_id} has no namespace. namespaces={namespaces_list}, original_ns={original_ns}, parent_ns={namespace}"
                            )
                            continue

                        parts = full_ns.split("/")
                        logger.debug(f"Record {record_id}: namespace parts={parts}, len={len(parts)}")

                        if len(parts) >= 4 and parts[1] == "summaries":
                            session_id = parts[-1]
                            logger.debug(
                                f"Record {record_id}: extracted session_id='{session_id}', sanitized_actor_id='{sanitized_actor_id}'"
                            )

                            # Make sure it's actually a session ID (not the actor ID)
                            # Session IDs are typically UUIDs, so check format
                            if session_id == sanitized_actor_id:
                                logger.debug(f"Record {record_id}: session_id matches actor_id, skipping")
                                continue

                            if session_id in seen_session_ids:
                                logger.debug(f"Record {record_id}: session_id already seen, skipping")
                                continue

                            if len(session_id) <= 10:
                                logger.debug(
                                    f"Record {record_id}: session_id too short ({len(session_id)}), likely not a UUID, skipping"
                                )
                                continue

                            # All checks passed, add the session
                            seen_session_ids.add(session_id)

                            # Extract summary text
                            content = full_record.get("content", {})
                            if isinstance(content, dict):
                                text = content.get("text", "")
                            else:
                                text = str(content) if content else ""

                            sessions.append(
                                {"session_id": session_id, "summary": text[:200] if text else "No summary available"}
                            )

                            logger.info(f"Extracted session {session_id} from namespace {full_ns}")

                            if len(sessions) >= top_k:
                                break
                        else:
                            logger.warning(
                                f"Record {record_id} namespace '{full_ns}' doesn't match expected pattern. Expected: /summaries/{{actorId}}/{{sessionId}}, got {len(parts)} parts: {parts}"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to get full record for {record_id}: {e}")
                        continue

                # Restore original log level
                logger.setLevel(original_level)

                logger.info(f"Processed {processed} records, found {len(sessions)} unique sessions")

                if sessions:
                    logger.info(f"Found {len(sessions)} sessions using ListMemoryRecords + GetMemoryRecord")
                    return sessions
                else:
                    logger.warning(
                        f"No sessions extracted from {len(all_records)} records. This may indicate the records are not in session-specific namespaces."
                    )
                    # Log a sample record for debugging
                    if all_records:
                        sample = all_records[0]
                        sample_id = sample.get("memoryRecordId") or sample.get("recordId", "N/A")
                        logger.warning(f"Sample record ID: {sample_id}, keys: {list(sample.keys())}")
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
                        searchCriteria={"searchQuery": query_term, "topK": top_k * 2},
                    )
                    found_records = response.get("memoryRecordSummaries", response.get("memoryRecords", []))
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

                            sessions.append(
                                {"session_id": session_id, "summary": text[:200] if text else "No summary available"}
                            )

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
