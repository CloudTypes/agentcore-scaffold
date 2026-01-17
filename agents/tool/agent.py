"""Tool specialist agent for utilities."""

from typing import Any
import time
import os
from pathlib import Path
import importlib.util
from strands import Agent
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.memory_client import MemoryClient
from agents.shared.observability import AgentLogger, track_latency


def _load_tool_module(tool_name: str, tool_file: Path) -> Any:
    """
    Load a tool module dynamically from a file path.
    
    Args:
        tool_name: Name identifier for the tool module (e.g., "calculator")
        tool_file: Path to the tool module file
        
    Returns:
        The loaded module object
        
    Raises:
        FileNotFoundError: If the tool file does not exist
        ImportError: If the module cannot be loaded or executed
    """
    if not tool_file.exists():
        raise FileNotFoundError(f"Tool file not found: {tool_file}")
    
    spec = importlib.util.spec_from_file_location(tool_name, tool_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to create spec for tool: {tool_name}")
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Import tools from local tools directory
tools_path = Path(__file__).parent / "tools"
calculator_module = _load_tool_module("calculator", tools_path / "calculator.py")
calculator = calculator_module.calculator

weather_module = _load_tool_module("weather", tools_path / "weather.py")
weather_api = weather_module.weather_api

database_module = _load_tool_module("database", tools_path / "database.py")
database_query = database_module.database_query


class ToolAgent:
    """
    Specialist agent for calculator, weather, and general utilities.
    
    This agent provides access to various utility tools including mathematical
    calculations, weather information retrieval, and database queries. It uses
    the Strands framework with memory integration for context-aware responses.
    """
    
    def __init__(self) -> None:
        """
        Initialize the ToolAgent.
        
        Sets up the agent with:
        - Logger for observability
        - Memory client for context storage
        - Strands agent configured with calculator, weather, and database tools
        
        The model ID can be configured via the TOOL_MODEL environment variable,
        defaulting to "amazon.nova-lite-v1:0" if not set.
        """
        self.agent_name = "tool"
        self.logger = AgentLogger(self.agent_name)
        self.memory = MemoryClient()
        
        # Initialize Strands agent with tool model and tools
        model_id = os.getenv("TOOL_MODEL", "amazon.nova-lite-v1:0")
        self.strands_agent = Agent(
            model=model_id,
            tools=[calculator, weather_api, database_query],
            system_prompt=self._get_system_prompt()
        )
    
    def _get_system_prompt(self) -> str:
        """
        Generate the system prompt for the tool agent.
        
        Returns:
            A string containing the system prompt that defines the agent's
            capabilities and behavior.
        """
        return """You are a tool specialist agent with access to calculator, weather, and database utilities.

Your capabilities:
- Perform mathematical calculations
- Get weather information for locations
- Query databases
- Use tools when appropriate to answer user questions

Be helpful and use tools when they can provide accurate information."""
    
    @track_latency("tool")
    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process a tool-related request from a user.
        
        This method handles the full request lifecycle:
        1. Logs the incoming request
        2. Builds message context from the request
        3. Processes the request using the Strands agent (which may invoke tools)
        4. Stores the interaction in memory for future context
        5. Logs the response
        6. Returns the formatted response
        
        Args:
            request: The agent request containing user message, context, and metadata
            
        Returns:
            AgentResponse containing the agent's response, processing time, and metadata
            
        Raises:
            RuntimeError: If the Strands agent fails to process the request
            ValueError: If the request is invalid or missing required fields
            Exception: Re-raises any exceptions from underlying components after logging
        """
        start_time = time.time()
        
        self.logger.log_request(
            user_id=request.user_id,
            session_id=request.session_id,
            message=request.message
        )
        
        try:
            # Build messages with context
            messages = request.context + [
                {"role": "user", "content": request.message}
            ]
            
            # Process with Strands agent (will use tools as needed)
            response = await self.strands_agent.run(messages=messages)
            
            processing_time = (time.time() - start_time) * 1000
            
            # Store interaction in memory
            await self.memory.store_interaction(
                user_id=request.user_id,
                session_id=request.session_id,
                user_message=request.message,
                agent_response=response.content,
                agent_name=self.agent_name
            )
            
            self.logger.log_response(
                user_id=request.user_id,
                session_id=request.session_id,
                processing_time_ms=processing_time,
                success=True
            )
            
            return AgentResponse(
                content=response.content,
                agent_name=self.agent_name,
                processing_time_ms=processing_time
            )
            
        except (RuntimeError, ValueError) as e:
            self.logger.log_error(e, request.user_id, request.session_id)
            raise
        except Exception as e:
            self.logger.log_error(e, request.user_id, request.session_id)
            raise RuntimeError(f"Unexpected error processing request: {e}") from e

