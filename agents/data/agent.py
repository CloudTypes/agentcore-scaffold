"""Data specialist agent for data analysis."""

from typing import List, Dict
import time
import os
from strands import Agent
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.memory_client import MemoryClient
from agents.shared.observability import AgentLogger, track_latency


class DataAgent:
    """Specialist agent for data analysis and SQL queries."""
    
    def __init__(self):
        self.agent_name = "data"
        self.logger = AgentLogger(self.agent_name)
        self.memory = MemoryClient()
        
        # Initialize Strands agent with data model
        model_id = os.getenv("DATA_MODEL", "amazon.nova-lite-v1:0")
        self.strands_agent = Agent(
            model=model_id,
            system_prompt=self._get_system_prompt()
        )
    
    def _get_system_prompt(self) -> str:
        return """You are a data specialist agent focused on data analysis and SQL queries.

Your capabilities:
- Analyze data and generate insights
- Write and execute SQL queries
- Generate charts and visualizations
- Answer questions about data
- Perform statistical analysis

Be precise and analytical in your data work."""
    
    @track_latency("data")
    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process data-related request."""
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
            
            # Process with Strands agent
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

