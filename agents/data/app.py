"""Data Agent using Strands framework with A2A protocol.

This module provides a data agent that integrates with the Strands framework
and A2A (agent-to-agent) protocol for data analysis, SQL queries, and chart generation.
The agent wraps the underlying Strands agent to add memory integration and
proper handling of A2A protocol messages.
"""

import os
import logging
from typing import List, Dict, Any, AsyncIterator, Optional
from strands import Agent
from strands.multiagent.a2a import A2AServer
from agents.data.agent import DataAgent

# Module-level constants
DEFAULT_PORT = 9000
DEFAULT_HOST = "0.0.0.0"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MemoryIntegratedAgent:
    """
    Wrapper that adds memory integration to Strands Agent for A2A protocol.
    
    This class bridges the DataAgent (which has memory integration) with the
    A2AServer requirements. It provides the necessary interface methods that
    A2AServer expects while maintaining access to memory for context-aware responses.
    
    The wrapper ensures that:
    - A2A protocol messages are properly converted to Strands format
    - Memory integration is maintained for conversation continuity
    - Data analysis capabilities are correctly exposed
    - Streaming responses work correctly with the A2A protocol
    
    Attributes:
        data_agent_wrapper (DataAgent): The underlying data agent with memory.
        strands_agent (Agent): The Strands agent instance.
        model: Model identifier from the underlying Strands agent.
        tools: Tools available to the agent.
        system_prompt: System prompt for the agent.
        name: Agent name identifier.
        description: Agent description for A2A protocol.
        tool_registry: Tool registry from the underlying agent.
    """
    
    def __init__(self, data_agent_wrapper: DataAgent) -> None:
        """
        Initialize with data agent wrapper that has memory client.
        
        Args:
            data_agent_wrapper: The DataAgent instance that provides the underlying
                Strands agent and memory client integration.
                
        Sets up all required attributes for A2AServer compatibility, including
        model, tools, system_prompt, name, description, and tool_registry.
        """
        self.data_agent_wrapper = data_agent_wrapper
        self.strands_agent = data_agent_wrapper.strands_agent
        # Set description on the underlying Strands agent for A2AServer
        if not hasattr(self.strands_agent, 'description') or not self.strands_agent.description:
            self.strands_agent.description = 'Data agent for data analysis, SQL queries, and chart generation'
        # Copy agent attributes for A2AServer compatibility
        self.model = self.strands_agent.model
        self.tools = getattr(self.strands_agent, 'tools', [])
        self.system_prompt = getattr(self.strands_agent, 'system_prompt', '')
        self.name = getattr(self.strands_agent, 'name', 'data-agent')
        self.description = self.strands_agent.description
        # Delegate tool_registry to underlying Strands agent for A2AServer
        self.tool_registry = getattr(self.strands_agent, 'tool_registry', None)
    
    def __getattr__(self, name: str) -> Any:
        """
        Delegate attribute access to underlying Strands agent for A2AServer compatibility.
        
        Args:
            name: The attribute name being accessed
            
        Returns:
            The attribute value from the underlying Strands agent
            
        Raises:
            AttributeError: If the attribute doesn't exist on either this object
                or the underlying Strands agent
        """
        # If A2AServer is looking for methods on the Strands agent, delegate to it
        if hasattr(self.strands_agent, name):
            return getattr(self.strands_agent, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
    
    async def __call__(self, task_input: Optional[str] = None, **kwargs: Any) -> str:
        """
        Handle A2A task request - called by A2AServer when it receives JSON-RPC 'message/send' method.
        
        Args:
            task_input: The task/message string. If None, will attempt to extract
                from kwargs using 'input', 'task', or 'task_input' keys.
            **kwargs: Additional parameters including:
                - user_id: User identifier for memory context
                - session_id: Session identifier for memory context
                - Other A2A protocol parameters
            
        Returns:
            Response content as string (A2AServer expects string return)
            
        Raises:
            ValueError: If no task input can be found in task_input or kwargs
        """
        # Extract task from kwargs if not provided as positional
        if task_input is None:
            task_input = kwargs.pop('input', kwargs.pop('task', kwargs.pop('task_input', None)))
        
        if task_input is None:
            raise ValueError("'task_input', 'input', or 'task' parameter is required")
        
        # Convert task_input string to messages format
        messages = [{"role": "user", "content": task_input}]
        response = await self.run(messages, **kwargs)
        
        # Return content as string (A2AServer expects string return)
        if hasattr(response, 'content'):
            return response.content
        elif isinstance(response, str):
            return response
        else:
            return str(response)
    
    async def stream_async(self, content_blocks: List[Dict[str, Any]]) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream agent response - called by A2AServer for streaming responses.
        
        Extracts text content from A2A content blocks, converts to normalized
        message format, and streams the agent's response as events.
        
        Args:
            content_blocks: List of content blocks from the A2A message.
                Each block should be a dictionary, typically with 'type' and 'text' keys.
            
        Yields:
            Streaming events from the agent. Events are dictionaries with 'type'
            and 'delta' keys for content delta events, or other event types as
            provided by the underlying Strands agent.
        """
        # Extract text from content blocks and convert to normalized messages format
        text_parts = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        
        user_message = " ".join(text_parts) if text_parts else str(content_blocks)
        
        # Convert to normalized messages format (ContentBlock format)
        normalized_messages = [{"role": "user", "content": [{"text": user_message}]}]
        
        # If Strands agent has stream_async, delegate to it
        if hasattr(self.strands_agent, 'stream_async'):
            async for event in self.strands_agent.stream_async(prompt=normalized_messages):
                yield event
        else:
            # Fallback: use invoke_async and yield the result as a single event
            response = await self.strands_agent.invoke_async(prompt=normalized_messages)
            # Yield the response as a content delta event
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                content = response.message.content
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and "text" in block:
                            yield {"type": "content_delta", "delta": {"text": block["text"]}}
                elif isinstance(content, str):
                    yield {"type": "content_delta", "delta": {"text": content}}
    
    def _normalize_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize messages to Strands ContentBlock format.
        
        Converts various message formats (strings, dicts, lists) into the
        standardized ContentBlock format expected by Strands agents.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys.
                Content can be a string, dict, or list of content blocks.
                
        Returns:
            List of normalized message dictionaries in ContentBlock format,
            where each message has 'role' and 'content' keys, with 'content'
            being a list of ContentBlock dictionaries with 'text' keys.
        """
        normalized_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "user").lower()
                content = msg.get("content", "")
                # Convert to list of ContentBlocks format
                if isinstance(content, str):
                    content = [{"text": content}]
                elif isinstance(content, dict):
                    if "text" in content:
                        content = [content]
                    else:
                        content = [{"text": str(content)}]
                elif isinstance(content, list):
                    # Ensure each element is a ContentBlock dict
                    formatted_blocks = []
                    for block in content:
                        if isinstance(block, str):
                            formatted_blocks.append({"text": block})
                        elif isinstance(block, dict) and "text" in block:
                            formatted_blocks.append(block)
                        else:
                            formatted_blocks.append({"text": str(block)})
                    content = formatted_blocks
                else:
                    content = [{"text": str(content) if content else ""}]
                normalized_messages.append({"role": role, "content": content})
            else:
                normalized_messages.append(msg)
        return normalized_messages
    
    def _extract_response_content(self, response: Any) -> str:
        """
        Extract text content from Strands AgentResult.
        
        Handles various response formats from Strands agents, extracting
        text content from nested structures like AgentResult.message.content.
        
        Args:
            response: The response object from a Strands agent, which may be
                an AgentResult with nested message/content structures, or a
                simpler object with a direct 'content' attribute.
                
        Returns:
            Extracted text content as a string, or empty string if no content
            can be extracted.
        """
        response_content = ""
        if hasattr(response, 'message'):
            message = response.message
            if isinstance(message, dict):
                content = message.get("content", [])
            else:
                content = getattr(message, "content", [])
            
            # Extract text from content blocks
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        if text:
                            text_parts.append(text)
                    elif isinstance(block, str):
                        text_parts.append(block)
                response_content = " ".join(text_parts) if text_parts else ""
            elif isinstance(content, str):
                response_content = content
            else:
                response_content = str(content) if content else ""
        elif hasattr(response, 'content'):
            response_content = response.content
        else:
            response_content = str(response) if response else ""
        return response_content
    
    async def run(self, messages: List[Dict[str, Any]], **kwargs: Any) -> Any:
        """
        Run agent with memory integration.
        
        Processes messages through the Strands agent with memory context loading
        and storage. Loads recent messages and semantic context from memory if
        user_id and session_id are provided, then processes the request and
        stores the interaction back to memory.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys.
                The first user message is used for semantic search and memory storage.
            **kwargs: Additional parameters including:
                - user_id: User identifier for memory context (optional)
                - session_id: Session identifier for memory context (optional)
                - Other parameters passed to the Strands agent
                
        Returns:
            Response object with a 'content' attribute containing the agent's
            response text. The response is a simple object wrapper for compatibility.
            
        Note:
            Memory operations (loading context and storing interactions) are
            performed asynchronously and failures are logged as warnings without
            interrupting the main request flow.
        """
        # Extract user message and context
        user_message = None
        context_messages = []
        
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "").lower()
                content = msg.get("content", "")
                if role == "user":
                    user_message = content
                context_messages.append(msg)
            else:
                context_messages.append(msg)
        
        # Load context from memory if we have user info
        if user_message and "user_id" in kwargs and "session_id" in kwargs:
            try:
                # Get recent messages from memory
                recent = await self.data_agent_wrapper.memory.get_recent_messages(
                    user_id=kwargs["user_id"],
                    session_id=kwargs["session_id"],
                    limit=10
                )
                
                # Get relevant semantic context
                relevant = await self.data_agent_wrapper.memory.semantic_search(
                    user_id=kwargs["user_id"],
                    query=user_message,
                    limit=5
                )
                
                # Prepend loaded context to messages
                loaded_context = context_messages + relevant + recent
                messages = loaded_context
            except Exception as e:
                logger.warning(f"Failed to load context from memory: {e}")
        
        # Run the Strands agent - use invoke_async since Agent doesn't have run() method
        # Normalize messages to ContentBlock format for Strands
        normalized_messages = self._normalize_messages(messages)
        
        response = await self.strands_agent.invoke_async(prompt=normalized_messages)
        
        # Extract content from AgentResult
        response_content = self._extract_response_content(response)
        
        # Create a response object with content attribute for compatibility
        class Response:
            def __init__(self, content):
                self.content = content
        
        response = Response(response_content)
        
        # Store interaction in memory if we have user info
        if user_message and "user_id" in kwargs and "session_id" in kwargs:
            try:
                await self.data_agent_wrapper.memory.store_interaction(
                    user_id=kwargs["user_id"],
                    session_id=kwargs["session_id"],
                    user_message=user_message,
                    agent_response=response.content,
                    agent_name=self.data_agent_wrapper.agent_name
                )
            except Exception as e:
                logger.warning(f"Failed to store interaction in memory: {e}")
        
        return response


def create_data_agent() -> MemoryIntegratedAgent:
    """
    Create data agent with Strands and memory integration.
    
    Factory function that creates a DataAgent instance and wraps it in a
    MemoryIntegratedAgent for A2A protocol compatibility.
    
    Returns:
        MemoryIntegratedAgent instance configured for data analysis tasks
        with memory integration enabled.
    """
    # Create the data agent wrapper (handles memory integration)
    data_agent_wrapper = DataAgent()
    
    # Create memory-integrated agent
    return MemoryIntegratedAgent(data_agent_wrapper)


def main() -> None:
    """
    Start data agent A2A server.
    
    Initializes the data agent, creates an A2A server instance, and starts
    the server to listen for agent-to-agent protocol requests. The server
    runs indefinitely until interrupted.
    
    The server exposes:
    - A2A protocol endpoints for agent communication
    - Agent card at /.well-known/agent-card.json
    """
    logger.info("Starting Data Agent A2A Server...")
    
    # Create agent
    agent = create_data_agent()
    
    # Create A2A server (agent card is auto-generated from the agent)
    server = A2AServer(
        agent=agent,
        port=DEFAULT_PORT,
        host=DEFAULT_HOST
    )
    
    logger.info(f"Data Agent ready on port {DEFAULT_PORT}")
    logger.info(f"Agent Card: http://{DEFAULT_HOST}:{DEFAULT_PORT}/.well-known/agent-card.json")
    
    # Start server (BLOCKING - runs forever)
    server.serve()


if __name__ == "__main__":
    main()
