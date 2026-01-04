"""Tool specialist agent for utilities."""

from typing import List, Dict
import time
import os
import sys
from pathlib import Path
from strands import Agent
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.memory_client import MemoryClient
from agents.shared.observability import AgentLogger, track_latency

# Import tools from local tools directory
tools_path = Path(__file__).parent / "tools"
sys.path.insert(0, str(tools_path))
# Import with absolute path to avoid conflicts
import importlib.util
spec_calc = importlib.util.spec_from_file_location("calculator", tools_path / "calculator.py")
calculator_module = importlib.util.module_from_spec(spec_calc)
spec_calc.loader.exec_module(calculator_module)
calculator = calculator_module.calculator

spec_weather = importlib.util.spec_from_file_location("weather", tools_path / "weather.py")
weather_module = importlib.util.module_from_spec(spec_weather)
spec_weather.loader.exec_module(weather_module)
weather_api = weather_module.weather_api

spec_db = importlib.util.spec_from_file_location("database", tools_path / "database.py")
database_module = importlib.util.module_from_spec(spec_db)
spec_db.loader.exec_module(database_module)
database_query = database_module.database_query


class ToolAgent:
    """Specialist agent for calculator, weather, and general utilities."""
    
    def __init__(self):
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
        return """You are a tool specialist agent with access to calculator, weather, and database utilities.

Your capabilities:
- Perform mathematical calculations
- Get weather information for locations
- Query databases
- Use tools when appropriate to answer user questions

Be helpful and use tools when they can provide accurate information."""
    
    @track_latency("tool")
    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process tool-related request."""
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
            
        except Exception as e:
            self.logger.log_error(e, request.user_id, request.session_id)
            raise

