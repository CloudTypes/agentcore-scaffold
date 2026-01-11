"""Orchestrator Agent using Strands framework with A2A protocol."""

import os
import logging
import sys
import re
from pathlib import Path
from typing import Dict, Optional, Any
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from strands import Agent
from strands.multiagent.a2a import A2AServer
from strands.tools import tool
from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.a2a_client import A2AClient

# Import memory and auth modules (from src/)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
from memory.client import MemoryClient
from memory.session_manager import MemorySessionManager
from auth.google_oauth2 import GoogleOAuth2Handler
from auth.oauth2_middleware import get_current_user
from config.runtime import get_config

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
        
        # Create a new system prompt that instructs the agent to USE the routing tools
        # instead of just returning specialist names
        self.system_prompt = """You are an orchestrator agent that routes user requests to specialist agents.

You have access to routing tools that connect to specialist agents:
- route_to_vision: For image analysis, visual content understanding
- route_to_document: For document processing, text extraction, PDF analysis
- route_to_data: For data analysis, SQL queries, chart generation
- route_to_tool: For calculator, weather, general utilities

When a user asks a question or makes a request:
1. Determine which specialist agent should handle it
2. USE the appropriate routing tool (route_to_vision, route_to_document, route_to_data, or route_to_tool)
3. Pass the user's complete question/task to the routing tool
4. The tool will return the specialist agent's response
5. Present that response directly to the user - do NOT mention that you used a tool or show the tool call

IMPORTANT: After calling a routing tool, you will receive the specialist's response. Simply present that response to the user in a natural, conversational way. Do NOT say "Action: route_to_tool(...)" or mention the tool call.

For general greetings or questions that don't fit a specialist, you can respond directly in a friendly manner.
Always use the routing tools when appropriate - the tools will handle calling the specialists and return their responses."""
        
        # Create Strands Agent with routing tools (create once, reuse in run())
        self.agent_with_tools = Agent(
            model=self.model,
            tools=self.tools,
            system_prompt=self.system_prompt
        )
    
    def _create_routing_tool(self, agent_name: str, description: str):
        """Create a routing tool for a specialist agent."""
        # Create a closure to capture self and agent_name
        orchestrator_instance = self
        
        # Define the async function first
        async def route_to_specialist_impl(task: str) -> str:
            """Route task to {agent_name} agent and return the response.
            
            Use this tool when the user's request requires {description}.
            Pass the user's complete question or request as the task parameter.
            The tool will call the specialist agent and return their response.
            You should then present this response to the user in a natural way.
            
            Args:
                task: The task or question to send to the {agent_name} agent. This should be the user's full question or request.
                
            Returns:
                The response from the {agent_name} agent. Present this directly to the user.
            """
            # Get user_id and session_id from the current invocation context
            user_id = getattr(orchestrator_instance, '_current_user_id', 'default')
            session_id = getattr(orchestrator_instance, '_current_session_id', 'default')
            
            logger.info(f"[ROUTING] → Calling specialist agent '{agent_name}' with task: {task[:100]}")
            logger.info(f"[ROUTING]   user_id={user_id}, session_id={session_id}")
            try:
                result = await orchestrator_instance.a2a_client.call_agent(
                    agent_name=agent_name,
                    task=task,
                    user_id=user_id,
                    session_id=session_id
                )
                logger.info(f"[ROUTING] ← Received response from '{agent_name}': {result[:200] if result else 'empty'}")
                return result
            except Exception as e:
                logger.error(f"[ROUTING] ✗ Error calling {agent_name} agent: {e}", exc_info=True)
                return f"I encountered an error while trying to get help from the {agent_name} specialist: {str(e)}"
        
        # Set function name before decoration
        route_to_specialist_impl.__name__ = f"route_to_{agent_name}"
        
        # Decorate with @tool to register it with Strands
        decorated_tool = tool(route_to_specialist_impl)
        
        return decorated_tool
    
    async def run(self, messages, **kwargs):
        """Run orchestrator with memory integration."""
        # Extract user_id and session_id from kwargs for use in routing tools
        user_id = kwargs.get("user_id", "default")
        session_id = kwargs.get("session_id", "default")
        
        # Store user_id and session_id so routing tools can access them
        # We'll update the tools to use these values
        self._current_user_id = user_id
        self._current_session_id = session_id
        
        # Extract user message and context
        user_message = None
        context_messages = []
        
        # Log the incoming request
        logger.info(f"[ORCHESTRATOR] Processing request (user_id={user_id}, session_id={session_id})")
        
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
        
        # Normalize messages to ensure they're in the correct format for Strands
        # Strands expects messages with content as ContentBlock (dict with 'text' key) or list of ContentBlocks
        # Content cannot be a plain string - it must be {"text": "..."} or [{"text": "..."}]
        normalized_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "user").lower()
                content = msg.get("content", "")
                
                # Convert content to list of ContentBlocks format
                # Strands expects content to be a list of ContentBlock dicts: [{"text": "..."}]
                if isinstance(content, str):
                    # Convert string to list with single ContentBlock
                    content = [{"text": content}]
                elif isinstance(content, dict):
                    # Single ContentBlock dict - wrap in list
                    if "text" in content:
                        content = [content]
                    else:
                        # If it's a dict but not a ContentBlock, try to extract text
                        text = content.get("content", content.get("text", str(content)))
                        content = [{"text": text}]
                elif isinstance(content, list):
                    # List of ContentBlocks - ensure each is properly formatted
                    formatted_blocks = []
                    for block in content:
                        if isinstance(block, str):
                            formatted_blocks.append({"text": block})
                        elif isinstance(block, dict):
                            if "text" in block:
                                formatted_blocks.append(block)
                            else:
                                # Try to extract text from dict
                                text = block.get("content", block.get("text", str(block)))
                                formatted_blocks.append({"text": text})
                        else:
                            formatted_blocks.append({"text": str(block)})
                    content = formatted_blocks
                else:
                    # Convert other types to list with single ContentBlock
                    content = [{"text": str(content) if content else ""}]
                
                normalized_messages.append({"role": role, "content": content})
            elif hasattr(msg, "role") and hasattr(msg, "content"):
                # Handle Message objects - convert to dict format
                role = getattr(msg, "role", "user").lower()
                content = getattr(msg, "content", "")
                # Convert to list of ContentBlocks
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
                # Skip invalid message formats
                logger.warning(f"Skipping invalid message format: {type(msg)}")
        
        # Run the Strands agent with tools (reuse the agent created in __init__)
        # Agent is callable - call it directly with messages
        # The Agent class doesn't have a run() method, so we use invoke_async
        logger.info(f"[ORCHESTRATOR] Invoking agent with {len(normalized_messages)} message(s)")
        if user_message:
            logger.info(f"[ORCHESTRATOR] User message: {user_message[:100]}")
        response = await self.agent_with_tools.invoke_async(prompt=normalized_messages)
        
        # Extract content from AgentResult
        # AgentResult has a 'message' field which is a Message object
        # The Message object has 'content' which is a list of ContentBlocks
        response_content = ""
        if hasattr(response, 'message'):
            message = response.message
            # Message is dict-like, get content
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
            # Fallback: try to get text from the result
            response_content = str(response) if response else ""
        
        # Clean up the response - remove tool call mentions if present
        # Sometimes the agent includes "Action: route_to_tool(...)" in the response
        # Remove patterns like "Action: route_to_tool(...)" or "route_to_tool(...)"
        original_content = response_content
        response_content = re.sub(r'Action:\s*route_to_\w+\([^)]*\)', '', response_content, flags=re.IGNORECASE)
        response_content = re.sub(r'route_to_\w+\([^)]*\)', '', response_content, flags=re.IGNORECASE)
        response_content = response_content.strip()
        
        # Log the response
        if response_content != original_content:
            logger.info(f"[ORCHESTRATOR] Cleaned response (removed tool call mentions)")
        logger.info(f"[ORCHESTRATOR] Final response: {response_content[:200]}")
        
        # Check if a tool was used by examining the stop_reason
        if hasattr(response, 'stop_reason'):
            if response.stop_reason == 'tool_use':
                logger.info(f"[ORCHESTRATOR] ✓ Request was routed to a specialist agent (stop_reason=tool_use)")
            else:
                logger.info(f"[ORCHESTRATOR] → Request handled directly by orchestrator (stop_reason={response.stop_reason})")
        
        # If we got an empty response but the agent used a tool, the tool result should be in the message
        # The agent should have incorporated the tool result into its final response
        if not response_content or response_content.strip() == "":
            logger.warning(f"[ORCHESTRATOR] Empty response from agent. Response object: {response}")
            response_content = "I apologize, but I couldn't generate a response. Please try again."
        
        # Store interaction in memory if we have user info
        if user_message and "user_id" in kwargs and "session_id" in kwargs:
            try:
                await self.orchestrator_wrapper.memory.store_interaction(
                    user_id=kwargs["user_id"],
                    session_id=kwargs["session_id"],
                    user_message=user_message,
                    agent_response=response_content,
                    agent_name=self.orchestrator_wrapper.agent_name,
                    metadata={"routed_via": "orchestrator"}
                )
            except Exception as e:
                logger.warning(f"Failed to store interaction in memory: {e}")
        
        # Return a response object with content attribute for compatibility
        class Response:
            def __init__(self, content):
                self.content = content
        
        return Response(response_content)


def create_orchestrator_agent():
    """Create orchestrator agent with Strands and memory integration."""
    # Initialize A2A client
    a2a_client = A2AClient("orchestrator")
    
    # Create the orchestrator wrapper (handles memory integration)
    orchestrator_wrapper = OrchestratorAgent(a2a_client)
    
    # Create memory-integrated orchestrator
    return MemoryIntegratedOrchestrator(orchestrator_wrapper, a2a_client)


# Initialize FastAPI app
app = FastAPI(
    title="Orchestrator Agent",
    description="Orchestrator agent that routes tasks to specialist agents",
    version="1.0.0"
)

# Add CORS middleware for CloudFront/API Gateway compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
config = get_config()
MEMORY_ENABLED = config.get_config_value("MEMORY_ENABLED", "false").lower() == "true"
AWS_REGION = config.get_config_value("AWS_REGION", "us-east-1")

# Initialize memory client if enabled
memory_client: Optional[MemoryClient] = None
if MEMORY_ENABLED:
    try:
        memory_region = config.get_config_value("AGENTCORE_MEMORY_REGION", AWS_REGION)
        memory_id = config.get_config_value("AGENTCORE_MEMORY_ID")
        memory_client = MemoryClient(region=memory_region, memory_id=memory_id)
        # Create memory resource if needed
        memory_client.create_memory_resource()
        logger.info("Memory client initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize memory client: {e}. Orchestrator will continue without memory features.")
        memory_client = None

# Initialize OAuth2 handler
oauth2_handler: Optional[GoogleOAuth2Handler] = None
try:
    oauth2_handler = GoogleOAuth2Handler()
    logger.info("OAuth2 handler initialized")
except Exception as e:
    logger.warning(f"OAuth2 handler not initialized: {e}")

# Global orchestrator agent instance (will be created in main)
orchestrator_agent: Optional[MemoryIntegratedOrchestrator] = None


@app.get("/health")
async def health() -> Dict[str, str]:
    """
    Health check endpoint for load balancers and monitoring.
    
    Returns:
        Dict containing service status and name.
        
    Example:
        >>> response = await health()
        >>> response
        {"status": "healthy", "service": "orchestrator"}
    """
    return {"status": "healthy", "service": "orchestrator"}


@app.post("/api/sessions")
async def create_session(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
    session_id: Optional[str] = None
) -> Dict[str, str]:
    """
    Create a new session or reuse an existing session.
    
    This endpoint creates a new memory session for the authenticated user.
    If a session_id is provided in the request body, it will reuse that session
    instead of creating a new one. This allows session continuity when switching
    between voice and text modes.
    
    Args:
        request: FastAPI request object (may contain session_id in body)
        user: Authenticated user information from OAuth2 middleware.
        session_id: Optional session ID from query parameter to reuse. If not provided,
                   a new session will be created.
    
    Returns:
        Dict containing the session_id.
        
    Raises:
        HTTPException: If authentication fails or memory client is unavailable.
        
    Example:
        >>> response = await create_session(user={"email": "user@example.com"})
        >>> response
        {"session_id": "abc123-def456-..."}
    """
    if not memory_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory not enabled"
        )
    
    # Try to get session_id from request body if not in query param
    if not session_id:
        try:
            body = await request.json()
            session_id = body.get("session_id")
        except Exception:
            pass  # No body or not JSON
    
    actor_id = user.get("email", "anonymous")
    session_manager = MemorySessionManager(memory_client, actor_id=actor_id, session_id=session_id)
    await session_manager.initialize()
    return {"session_id": session_manager.session_id}


@app.get("/api/sessions/{session_id}")
async def get_session(
    session_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get session details.
    
    Args:
        session_id: Session ID to retrieve
        user: Authenticated user information from OAuth2 middleware.
    
    Returns:
        Dict containing session details.
        
    Raises:
        HTTPException: If authentication fails, session not found, or memory client unavailable.
    """
    if not memory_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory not enabled"
        )
    
    actor_id = user.get("email", "anonymous")
    
    try:
        # Get session summary
        summary_record = memory_client.get_session_summary(
            actor_id=actor_id,
            session_id=session_id
        )
        
        if not summary_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Extract summary text
        content = summary_record.get("content", {})
        if isinstance(content, dict):
            summary_text = content.get("text", "")
        else:
            summary_text = str(content) if content else ""
        
        return {
            "session_id": session_id,
            "summary": summary_text,
            "namespace": summary_record.get("namespace", ""),
            "created_at": summary_record.get("createdAt"),
            "updated_at": summary_record.get("updatedAt")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving session: {str(e)}"
        )


@app.post("/api/chat")
async def chat(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Send a text message to the orchestrator agent and get a response.
    
    The orchestrator agent will process the message, potentially routing to
    specialist agents via A2A protocol, and return a text response. The
    session_id from the request is used to maintain conversation context.
    
    Args:
        request: FastAPI request object containing message and session_id in body.
        user: Authenticated user information from OAuth2 middleware.
    
    Returns:
        Dict containing the agent's text response.
        
    Raises:
        HTTPException: If authentication fails, session is invalid, or agent
                      processing fails.
        
    Example:
        >>> request_body = {"message": "What is 2+2?", "session_id": "abc123"}
        >>> response = await chat(request, user={"email": "user@example.com"})
        >>> response
        {"response": "2+2 equals 4."}
    """
    # Initialize orchestrator agent if not already initialized
    global orchestrator_agent
    if not orchestrator_agent:
        orchestrator_agent = create_orchestrator_agent()
    
    try:
        body = await request.json()
        message = body.get("message")
        session_id = body.get("session_id")
        
        if not message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message is required"
            )
        
        if not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session ID is required"
            )
        
        actor_id = user.get("email", "anonymous")
        
        # Prepare messages for orchestrator
        messages = [{"role": "user", "content": message}]
        
        # Run orchestrator agent
        response = await orchestrator_agent.run(
            messages=messages,
            user_id=actor_id,
            session_id=session_id
        )
        
        return {"response": response.content}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing chat message: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}"
        )


def main():
    """
    Start orchestrator A2A server and FastAPI HTTP server.
    
    The A2A server runs on port 9000 (default) for agent-to-agent communication.
    The FastAPI HTTP server runs on a configurable port (default 9000, but can be
    set via ORCHESTRATOR_HTTP_PORT environment variable). In production, these
    can be routed through API Gateway/CloudFront.
    """
    global orchestrator_agent
    
    logger.info("Starting Orchestrator Agent...")
    
    # Create agent
    orchestrator_agent = create_orchestrator_agent()
    
    # Get A2A port (default 9001 to avoid conflict with FastAPI on 9000)
    # Can be configured via A2A_PORT environment variable
    a2a_port = int(os.getenv("A2A_PORT", "9001"))
    
    # Get HTTP port (default 9000 for FastAPI REST API)
    # Can be configured via ORCHESTRATOR_HTTP_PORT environment variable
    http_port = int(os.getenv("ORCHESTRATOR_HTTP_PORT", "9000"))
    
    # Create A2A server (agent card is auto-generated from the agent)
    a2a_server = A2AServer(
        agent=orchestrator_agent,
        port=a2a_port,
        host="0.0.0.0"
    )
    
    logger.info("Orchestrator Agent ready")
    logger.info(f"FastAPI HTTP server on port {http_port}")
    logger.info(f"A2A server on port {a2a_port}")
    logger.info(f"Agent Card: http://0.0.0.0:{a2a_port}/.well-known/agent-card.json")
    
    # Start A2A server in background thread
    import threading
    a2a_thread = threading.Thread(target=a2a_server.serve, daemon=True)
    a2a_thread.start()
    
    # Start FastAPI server (BLOCKING - runs forever)
    # Note: If both use port 9000, A2A server will handle A2A requests,
    # and FastAPI will handle HTTP REST requests (they use different protocols)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=http_port)


if __name__ == "__main__":
    main()
