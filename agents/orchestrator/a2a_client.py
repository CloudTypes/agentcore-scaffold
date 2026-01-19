"""
Client for agent-to-agent communication using A2A protocol (JSON-RPC 2.0).

This module provides the A2AClient class for making agent-to-agent calls using
the A2A (Agent-to-Agent) protocol, which is based on JSON-RPC 2.0. The client
handles service discovery, message formatting, response parsing, and error handling
for both text-only and multimodal (image/video) agent communications.
"""

import logging
import time
import httpx
import json
import uuid
from typing import Dict, List
from agents.shared.service_discovery import get_service_discovery
from agents.shared.observability import AgentLogger, sanitize_for_logging

logger = logging.getLogger(__name__)

# Disable httpx request/response body logging to avoid logging base64 encoded media
# httpx logs at INFO level by default, which can include request bodies
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)  # Only log warnings and errors, not request/response bodies

# Constants
DEFAULT_TIMEOUT = 30.0  # Default HTTP request timeout in seconds
MEDIA_TIMEOUT = 120.0  # Timeout for media requests (images/videos) in seconds
JSONRPC_VERSION = "2.0"  # JSON-RPC protocol version
METHOD_MESSAGE_SEND = "message/send"  # A2A method name for sending messages
ROLE_USER = "user"  # Default role for A2A messages


class A2AClient:
    """Client for agent-to-agent communication using A2A protocol (JSON-RPC 2.0)."""
    
    def __init__(self, source_agent_name: str):
        """
        Initialize A2A client.
        
        Args:
            source_agent_name: Name of the agent making the A2A calls (used for logging)
        """
        self.source_agent_name = source_agent_name
        self.service_discovery = get_service_discovery()
        self.logger = AgentLogger(source_agent_name)
        self.client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        self._request_id = 0
    
    def _get_next_id(self) -> int:
        """
        Get next JSON-RPC request ID.
        
        Returns:
            Incrementing integer ID for JSON-RPC requests
        """
        self._request_id += 1
        return self._request_id
    
    def _generate_message_id(self) -> str:
        """
        Generate unique message ID for A2A protocol.
        
        Returns:
            Unique message ID string in format "msg-{16-char-hex}"
        """
        return f"msg-{uuid.uuid4().hex[:16]}"
    
    def _build_message(self, parts: List[Dict], **kwargs) -> Dict:
        """
        Build A2A message object with optional fields.
        
        Args:
            parts: List of message parts (text, file, or data parts)
            **kwargs: Optional fields that may be added to message:
                - context_id: Context identifier for the message
                - task_id: Task identifier for the message
                - metadata: Additional metadata dictionary
        
        Returns:
            Dictionary containing the A2A message with required and optional fields
        """
        message = {
            "messageId": self._generate_message_id(),
            "role": ROLE_USER,
            "parts": parts
        }
        
        # Add optional fields if provided in kwargs
        if "context_id" in kwargs:
            message["contextId"] = kwargs["context_id"]
        if "task_id" in kwargs:
            message["taskId"] = kwargs["task_id"]
        if "metadata" in kwargs:
            message["metadata"] = kwargs["metadata"]
        
        return message
    
    def _build_jsonrpc_request(self, message: Dict, **kwargs) -> Dict:
        """
        Build JSON-RPC 2.0 request.
        
        Args:
            message: A2A message dictionary to include in params
            **kwargs: Optional parameters that may be added to request:
                - user_id: User identifier
                - session_id: Session identifier
        
        Returns:
            Dictionary containing the complete JSON-RPC 2.0 request
        """
        params = {"message": message}
        
        # Add user_id and session_id to params if provided (A2AServer may need these)
        if "user_id" in kwargs:
            params["user_id"] = kwargs["user_id"]
        if "session_id" in kwargs:
            params["session_id"] = kwargs["session_id"]
        
        return {
            "jsonrpc": JSONRPC_VERSION,
            "method": METHOD_MESSAGE_SEND,
            "params": params,
            "id": self._get_next_id()
        }
    
    def _handle_response(self, result: Dict, agent_name: str) -> str:
        """
        Handle JSON-RPC response and extract content or raise error.
        
        Args:
            result: JSON-RPC response dictionary
            agent_name: Name of the agent that sent the response (for error messages)
        
        Returns:
            Extracted text content from the response
        
        Raises:
            Exception: If the response contains an error or is invalid
        """
        if "result" in result:
            return self._extract_response_content(result["result"])
        elif "error" in result:
            error = result["error"]
            raise Exception(f"A2A error from {agent_name}: {error.get('message', str(error))}")
        else:
            # Sanitize result before logging to avoid logging base64 data
            sanitized_result = sanitize_for_logging(result)
            raise Exception(f"Invalid JSON-RPC response from {agent_name}: {sanitized_result}")
    
    def _log_a2a_call(self, agent_name: str, kwargs: Dict, latency_ms: float, success: bool):
        """
        Log A2A call with consistent format.
        
        Args:
            agent_name: Name of the target agent that was called
            kwargs: Dictionary containing user_id and session_id (if provided)
            latency_ms: Request latency in milliseconds
            success: Whether the call was successful
        """
        self.logger.log_a2a_call(
            target_agent=agent_name,
            user_id=kwargs.get("user_id", "unknown"),
            session_id=kwargs.get("session_id", "unknown"),
            latency_ms=latency_ms,
            success=success
        )
    
    def _create_media_part(self, media_content: Dict) -> Dict:
        """
        Create media part (image or video) for A2A message.
        
        Supports both S3 file URIs (FilePart) and base64-encoded data (DataPart).
        
        Args:
            media_content: Dictionary containing media information with structure:
                - type: "image" or "video"
                - image/video: Dictionary with "source" and "format" fields
                    - source: Dictionary with either "s3Location" or "base64"
                    - format: Media format (e.g., "jpeg", "mp4")
        
        Returns:
            Dictionary representing the media part (FilePart or DataPart), or None
            if media_type is not supported
        
        Raises:
            ValueError: If base64 data is not a string
        """
        media_type = media_content.get("type")
        
        if media_type == "image":
            image_block = media_content.get("image", {})
            source = image_block.get("source", {})
            format_str = image_block.get('format', 'jpeg')
            
            if "s3Location" in source:
                # Use FilePart for S3 URIs
                s3_uri = source["s3Location"].get("uri")
                return {
                    "type": "file",
                    "fileUri": s3_uri,
                    "mimeType": f"image/{format_str}"
                }
            elif "base64" in source:
                # Use DataPart for base64 content
                base64_data = source["base64"]
                
                # Validate base64 string
                if not isinstance(base64_data, str):
                    raise ValueError(f"base64 data must be string, got {type(base64_data)}")
                
                logger.info(f"Added DataPart: mimeType=image/{format_str}, data_length={len(base64_data)} chars")
                
                # Create A2A DataPart - A2A server expects data to be a dict, not a string
                return {
                    "type": "data",
                    "mimeType": f"image/{format_str}",
                    "data": {
                        "base64": base64_data  # Wrap in dict as A2A server expects
                    }
                }
        
        elif media_type == "video":
            video_block = media_content.get("video", {})
            source = video_block.get("source", {})
            format_str = video_block.get('format', 'mp4')
            
            if "s3Location" in source:
                # Use FilePart for S3 URIs
                s3_uri = source["s3Location"].get("uri")
                return {
                    "type": "file",
                    "fileUri": s3_uri,
                    "mimeType": f"video/{format_str}"
                }
            elif "base64" in source:
                # Use DataPart for base64 content
                base64_data = source["base64"]
                
                # Validate base64 string
                if not isinstance(base64_data, str):
                    raise ValueError(f"base64 data must be string, got {type(base64_data)}")
                
                logger.info(f"Added DataPart: mimeType=video/{format_str}, data_length={len(base64_data)} chars")
                
                # Create A2A DataPart - A2A server expects data to be a dict
                return {
                    "type": "data",
                    "mimeType": f"video/{format_str}",
                    "data": {
                        "base64": base64_data  # Wrap in dict as A2A server expects
                    }
                }
        
        return None
    
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
            **kwargs: Additional parameters:
                - user_id: User identifier
                - session_id: Session identifier
                - context_id: Context identifier
                - task_id: Task identifier
                - metadata: Additional metadata dictionary
            
        Returns:
            Response content from the agent as a string
        
        Raises:
            Exception: If the agent is not found (404), HTTP error occurs,
                or the response is invalid
        """
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
            parts = [{"type": "text", "text": task}]
            message = self._build_message(parts, **kwargs)
            request = self._build_jsonrpc_request(message, **kwargs)
            
            # Make HTTP POST request
            response = await self.client.post(
                endpoint,
                json=request,
                headers={"Content-Type": "application/json"}
            )
            
            # Check for 404 or other errors
            if response.status_code == 404:
                raise Exception(f"Agent '{agent_name}' not found at endpoint: {endpoint}. Please ensure the agent is running.")
            
            response.raise_for_status()
            
            # Parse JSON-RPC 2.0 response
            result = response.json()
            
            # Extract result or error
            response_content = self._handle_response(result, agent_name)
            
            latency_ms = (time.time() - start_time) * 1000
            
            logger.info(f"[A2A] ✓ Successfully called '{agent_name}' agent (latency: {latency_ms:.1f}ms)")
            logger.info(f"[A2A]   Response length: {len(response_content)} chars")
            
            self._log_a2a_call(agent_name, kwargs, latency_ms, success=True)
            
            return response_content
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._log_a2a_call(agent_name, kwargs, latency_ms, success=False)
            logger.error(f"Failed to call agent {agent_name}: {e}")
            raise
    
    def _extract_response_content(self, result) -> str:
        """
        Extract text content from A2A response.
        
        Handles multiple response formats:
        - Direct string
        - Message object with parts
        - Dict with artifacts, parts, content, or text fields
        - Streaming response aggregated by A2AServer
        
        Args:
            result: Response data (string, dict, or other) to extract text from
        
        Returns:
            Extracted text content as a string, joined with newlines if multiple parts
        """
        if isinstance(result, str):
            return result
        
        if isinstance(result, dict):
            # Check for artifacts field (A2AServer streaming response format)
            # Structure: result.artifacts[].parts[] where parts with kind="text" or type="text" have text field
            if "artifacts" in result:
                artifacts = result["artifacts"]
                if isinstance(artifacts, list):
                    # Extract text from artifacts - iterate through artifacts, then parts
                    text_parts = []
                    for artifact in artifacts:
                        if isinstance(artifact, dict):
                            parts = artifact.get("parts", [])
                            for part in parts:
                                if isinstance(part, dict):
                                    # A2A server uses "kind" field, but we also check "type" for compatibility
                                    part_type = part.get("kind") or part.get("type")
                                    if part_type == "text":
                                        text = part.get("text", "")
                                        if text:
                                            # Check if text is a JSON string that needs parsing
                                            # (e.g., vision agent returns JSON string)
                                            try:
                                                parsed = json.loads(text)
                                                if isinstance(parsed, dict) and "text" in parsed:
                                                    # Extract text from parsed JSON
                                                    text_parts.append(parsed["text"])
                                                else:
                                                    text_parts.append(text)
                                            except (json.JSONDecodeError, TypeError):
                                                # Not JSON, use as-is
                                                text_parts.append(text)
                    if text_parts:
                        # Join with newlines to preserve formatting
                        return "\n".join(text_parts)
            
            # Check for message object with parts
            if "message" in result:
                msg = result["message"]
                if isinstance(msg, dict) and "parts" in msg:
                    return self._extract_text_from_parts(msg["parts"])
                return str(msg)
            
            # Check for direct parts array
            if "parts" in result:
                return self._extract_text_from_parts(result["parts"])
            
            # Check for streaming response format (A2AServer aggregates events)
            # Streaming responses might have "content" as a list of content blocks
            if "content" in result:
                content = result["content"]
                if isinstance(content, list):
                    # Extract text from content blocks
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if "text" in block:
                                text_parts.append(block["text"])
                            elif "content" in block:
                                # Nested content
                                if isinstance(block["content"], str):
                                    text_parts.append(block["content"])
                                elif isinstance(block["content"], list):
                                    for sub_block in block["content"]:
                                        if isinstance(sub_block, dict) and "text" in sub_block:
                                            text_parts.append(sub_block["text"])
                    if text_parts:
                        return "\n".join(text_parts)
            
            # Fallback to common response fields
            text = result.get("content", result.get("text", None))
            if text:
                if isinstance(text, list):
                    # Extract text from list
                    text_parts = []
                    for item in text:
                        if isinstance(item, dict) and "text" in item:
                            text_parts.append(item["text"])
                        elif isinstance(item, str):
                            text_parts.append(item)
                    return "\n".join(text_parts) if text_parts else str(result)
                return str(text)
            
            # Last resort: convert entire dict to string (but log it)
            logger.warning(f"Could not extract text from A2A response, returning string representation. Keys: {list(result.keys())}")
            return str(result)
        
        return str(result)
    
    def _extract_text_from_parts(self, parts: List[Dict]) -> str:
        """
        Extract text from parts array.
        
        Handles parts with "kind" or "type" field set to "text", and may parse
        JSON strings within text parts if they contain nested text content.
        
        Args:
            parts: List of part dictionaries, each potentially containing text content
        
        Returns:
            Extracted text joined with newlines, or string representation of parts
            if no text is found
        """
        text_parts = []
        for part in parts:
            # A2A server uses "kind" field, but we also check "type" for compatibility
            part_type = part.get("kind") or part.get("type")
            if part_type == "text" and "text" in part:
                text = part["text"]
                # Check if text is a JSON string that needs parsing
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict) and "text" in parsed:
                        text_parts.append(parsed["text"])
                    else:
                        text_parts.append(text)
                except (json.JSONDecodeError, TypeError):
                    # Not JSON, use as-is
                    text_parts.append(text)
        # Join with newlines to preserve formatting
        return "\n".join(text_parts) if text_parts else str(parts)
    
    async def health_check(self, agent_name: str) -> Dict:
        """
        Check health of another agent via agent card.
        
        Attempts to retrieve the agent's card from the /.well-known/agent-card.json
        endpoint to verify the agent is running and accessible.
        
        Args:
            agent_name: Name of the agent to check
        
        Returns:
            Dictionary with health status:
                - status: "healthy" or "unhealthy"
                - agent_name: Name of the agent (if healthy)
                - capabilities: List of agent capabilities (if healthy)
                - error: Error message (if unhealthy)
        """
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
    
    async def call_agent_with_media(
        self,
        agent_name: str,
        task: str,
        media_content: Dict,
        **kwargs
    ) -> str:
        """
        Make A2A call with multimodal content (image/video).
        
        Args:
            agent_name: Name of the target agent
            task: Task description/message to send
            media_content: Dictionary with media content block containing:
                - type: "image" or "video"
                - image/video: Dictionary with "source" and "format" fields
            **kwargs: Additional parameters:
                - user_id: User identifier
                - session_id: Session identifier
                - context_id: Context identifier
                - task_id: Task identifier
                - metadata: Additional metadata dictionary
            
        Returns:
            Response content from the agent as a string
        
        Raises:
            ValueError: If base64 data in media_content is not a string
            Exception: If the agent is not found (404), HTTP error occurs,
                timeout occurs, or the response is invalid
        """
        start_time = time.time()
        
        try:
            endpoint = self.service_discovery.get_endpoint(agent_name)
            logger.info(f"[A2A] Calling '{agent_name}' agent with media at endpoint: {endpoint}")
            logger.info(f"[A2A] Task: {task[:150]}")
            
            # Build parts array with multimodal content
            # A2AServer expects TextPart, FilePart, or DataPart
            parts = []
            
            # Add media content block first
            if media_content:
                media_part = self._create_media_part(media_content)
                if media_part:
                    parts.append(media_part)
            
            # Add text prompt
            parts.append({
                "type": "text",
                "text": task
            })
            
            # Build JSON-RPC 2.0 request with multimodal parts
            message = self._build_message(parts, **kwargs)
            request = self._build_jsonrpc_request(message, **kwargs)
            
            # Log sanitized request (without base64)
            sanitized_request = sanitize_for_logging(request)
            logger.info(f"Sending A2A request to {agent_name}: {json.dumps(sanitized_request, indent=2)}")
            
            # Make HTTP POST request with increased timeout for large images
            response = await self.client.post(
                endpoint,
                json=request,
                headers={"Content-Type": "application/json"},
                timeout=MEDIA_TIMEOUT
            )
            
            # Check for 404 or other errors
            if response.status_code == 404:
                raise Exception(f"Agent '{agent_name}' not found at endpoint: {endpoint}. Please ensure the agent is running.")
            
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Received A2A response from {agent_name}")
            
            # Extract response according to A2A spec
            response_content = self._handle_response(result, agent_name)
            
            latency_ms = (time.time() - start_time) * 1000
            
            self._log_a2a_call(agent_name, kwargs, latency_ms, success=True)
            
            return response_content
            
        except httpx.HTTPStatusError as e:
            latency_ms = (time.time() - start_time) * 1000
            self._log_a2a_call(agent_name, kwargs, latency_ms, success=False)
            logger.error(f"HTTP error calling {agent_name}: {e.response.status_code} - {e.response.text}")
            raise Exception(f"HTTP {e.response.status_code} from {agent_name}")
        except httpx.TimeoutException:
            latency_ms = (time.time() - start_time) * 1000
            self._log_a2a_call(agent_name, kwargs, latency_ms, success=False)
            logger.error(f"Timeout calling {agent_name}")
            raise Exception(f"Timeout calling {agent_name}")
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._log_a2a_call(agent_name, kwargs, latency_ms, success=False)
            logger.error(f"Failed to call agent {agent_name} with media: {e}")
            raise
    
    async def close(self):
        """
        Close HTTP client.
        
        Cleans up the underlying httpx.AsyncClient connection. Should be called
        when the A2AClient is no longer needed to properly release resources.
        """
        await self.client.aclose()
