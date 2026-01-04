"""Orchestrator Agent using Strands framework with A2A protocol."""

import os
import logging
from strands import Agent
from strands.multiagent.a2a import A2AServer
from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.a2a_client import A2AClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MemoryIntegratedOrchestrator:
    """Wrapper that adds memory integration to Orchestrator Agent for A2A protocol."""
    
    def __init__(self, orchestrator_wrapper: OrchestratorAgent, a2a_client: A2AClient):
        """Initialize with orchestrator wrapper that has memory client."""
        self.orchestrator_wrapper = orchestrator_wrapper
        self.a2a_client = a2a_client
        self.strands_agent = orchestrator_wrapper.strands_agent
        # Set description on the underlying Strands agent for A2AServer
        if not hasattr(self.strands_agent, 'description') or not self.strands_agent.description:
            self.strands_agent.description = 'Orchestrator agent that routes tasks to specialist agents'
        # Copy agent attributes for A2AServer compatibility
        self.model = self.strands_agent.model
        self.system_prompt = getattr(self.strands_agent, 'system_prompt', '')
        self.name = getattr(self.strands_agent, 'name', 'orchestrator-agent')
        self.description = self.strands_agent.description
        # Delegate tool_registry to underlying Strands agent for A2AServer
        self.tool_registry = getattr(self.strands_agent, 'tool_registry', None)
        
        # Create routing tools that use A2AClient
        self.tools = [
            self._create_routing_tool("vision", "Image analysis, visual content understanding"),
            self._create_routing_tool("document", "Document processing, text extraction, PDF analysis"),
            self._create_routing_tool("data", "Data analysis, SQL queries, chart generation"),
            self._create_routing_tool("tool", "Calculator, weather, general utilities"),
        ]
    
    def _create_routing_tool(self, agent_name: str, description: str):
        """Create a routing tool for a specialist agent."""
        async def route_to_specialist(task: str, user_id: str = "default", session_id: str = "default") -> str:
            """Route task to {agent_name} agent.
            
            Args:
                task: The task or question to send to the {agent_name} agent
                user_id: User identifier for memory context
                session_id: Session identifier for memory context
                
            Returns:
                Response from the {agent_name} agent
            """
            logger.info(f"Routing to {agent_name}: {task}")
            return await self.a2a_client.call_agent(
                agent_name=agent_name,
                task=task,
                user_id=user_id,
                session_id=session_id
            )
        
        # Set function metadata for Strands
        route_to_specialist.__name__ = f"route_to_{agent_name}"
        route_to_specialist.__doc__ = f"Route task to {agent_name} agent. {description}"
        
        return route_to_specialist
    
    async def run(self, messages, **kwargs):
        """Run orchestrator with memory integration."""
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
                recent = await self.orchestrator_wrapper.memory.get_recent_messages(
                    user_id=kwargs["user_id"],
                    session_id=kwargs["session_id"],
                    limit=10
                )
                
                # Get relevant semantic context
                relevant = await self.orchestrator_wrapper.memory.semantic_search(
                    user_id=kwargs["user_id"],
                    query=user_message,
                    limit=5
                )
                
                # Prepend loaded context to messages
                loaded_context = context_messages + relevant + recent
                messages = loaded_context
            except Exception as e:
                logger.warning(f"Failed to load context from memory: {e}")
        
        # Create a new Strands Agent with routing tools
        agent_with_tools = Agent(
            model=self.model,
            tools=self.tools,
            system_prompt=self.system_prompt
        )
        
        # Run the Strands agent with tools
        response = await agent_with_tools.run(messages=messages, **kwargs)
        
        # Store interaction in memory if we have user info
        if user_message and "user_id" in kwargs and "session_id" in kwargs:
            try:
                await self.orchestrator_wrapper.memory.store_interaction(
                    user_id=kwargs["user_id"],
                    session_id=kwargs["session_id"],
                    user_message=user_message,
                    agent_response=response.content,
                    agent_name=self.orchestrator_wrapper.agent_name,
                    metadata={"routed_via": "orchestrator"}
                )
            except Exception as e:
                logger.warning(f"Failed to store interaction in memory: {e}")
        
        return response


def create_orchestrator_agent():
    """Create orchestrator agent with Strands and memory integration."""
    # Initialize A2A client
    a2a_client = A2AClient("orchestrator")
    
    # Create the orchestrator wrapper (handles memory integration)
    orchestrator_wrapper = OrchestratorAgent(a2a_client)
    
    # Create memory-integrated orchestrator
    return MemoryIntegratedOrchestrator(orchestrator_wrapper, a2a_client)


def main():
    """Start orchestrator A2A server."""
    logger.info("Starting Orchestrator Agent A2A Server...")
    
    # Create agent
    agent = create_orchestrator_agent()
    
    # Create A2A server (agent card is auto-generated from the agent)
    server = A2AServer(
        agent=agent,
        port=9000,
        host="0.0.0.0"
    )
    
    logger.info("Orchestrator Agent ready on port 9000")
    logger.info("Agent Card: http://0.0.0.0:9000/.well-known/agent-card.json")
    
    # Start server (BLOCKING - runs forever)
    server.serve()


if __name__ == "__main__":
    main()
