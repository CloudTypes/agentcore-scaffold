"""Document Agent using Strands framework with A2A protocol."""

import os
import logging
from strands import Agent
from strands.multiagent.a2a import A2AServer
from agents.document.agent import DocumentAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MemoryIntegratedAgent:
    """Wrapper that adds memory integration to Strands Agent for A2A protocol."""
    
    def __init__(self, document_agent_wrapper: DocumentAgent):
        """Initialize with document agent wrapper that has memory client."""
        self.document_agent_wrapper = document_agent_wrapper
        self.strands_agent = document_agent_wrapper.strands_agent
        # Set description on the underlying Strands agent for A2AServer
        if not hasattr(self.strands_agent, 'description') or not self.strands_agent.description:
            self.strands_agent.description = 'Document agent for processing documents, text extraction, and PDF analysis'
        # Copy agent attributes for A2AServer compatibility
        self.model = self.strands_agent.model
        self.tools = getattr(self.strands_agent, 'tools', [])
        self.system_prompt = getattr(self.strands_agent, 'system_prompt', '')
        self.name = getattr(self.strands_agent, 'name', 'document-agent')
        self.description = self.strands_agent.description
        # Delegate tool_registry to underlying Strands agent for A2AServer
        self.tool_registry = getattr(self.strands_agent, 'tool_registry', None)
    
    async def run(self, messages, **kwargs):
        """Run agent with memory integration."""
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
                recent = await self.document_agent_wrapper.memory.get_recent_messages(
                    user_id=kwargs["user_id"],
                    session_id=kwargs["session_id"],
                    limit=10
                )
                
                # Get relevant semantic context
                relevant = await self.document_agent_wrapper.memory.semantic_search(
                    user_id=kwargs["user_id"],
                    query=user_message,
                    limit=5
                )
                
                # Prepend loaded context to messages
                loaded_context = context_messages + relevant + recent
                messages = loaded_context
            except Exception as e:
                logger.warning(f"Failed to load context from memory: {e}")
        
        # Run the Strands agent
        response = await self.strands_agent.run(messages=messages, **kwargs)
        
        # Store interaction in memory if we have user info
        if user_message and "user_id" in kwargs and "session_id" in kwargs:
            try:
                await self.document_agent_wrapper.memory.store_interaction(
                    user_id=kwargs["user_id"],
                    session_id=kwargs["session_id"],
                    user_message=user_message,
                    agent_response=response.content,
                    agent_name=self.document_agent_wrapper.agent_name
                )
            except Exception as e:
                logger.warning(f"Failed to store interaction in memory: {e}")
        
        return response


def create_document_agent():
    """Create document agent with Strands and memory integration."""
    # Create the document agent wrapper (handles memory integration)
    document_agent_wrapper = DocumentAgent()
    
    # Create memory-integrated agent
    return MemoryIntegratedAgent(document_agent_wrapper)


def main():
    """Start document agent A2A server."""
    logger.info("Starting Document Agent A2A Server...")
    
    # Create agent
    agent = create_document_agent()
    
    # Create A2A server (agent card is auto-generated from the agent)
    server = A2AServer(
        agent=agent,
        port=9000,
        host="0.0.0.0"
    )
    
    logger.info("Document Agent ready on port 9000")
    logger.info("Agent Card: http://0.0.0.0:9000/.well-known/agent-card.json")
    
    # Start server (BLOCKING - runs forever)
    server.serve()


if __name__ == "__main__":
    main()
