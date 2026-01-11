"""Orchestrator agent that routes requests to specialists."""

from typing import List, Dict, Any
import time
import os
from strands import Agent
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.memory_client import MemoryClient
from agents.shared.observability import AgentLogger, track_latency


class OrchestratorAgent:
    """Orchestrator agent that routes requests to specialists."""
    
    def __init__(self, a2a_client):
        self.agent_name = "orchestrator"
        self.logger = AgentLogger(self.agent_name)
        self.memory = MemoryClient()
        self.a2a_client = a2a_client
        
        # Initialize Strands agent for intent classification
        model_id = os.getenv("ORCHESTRATOR_MODEL", "amazon.nova-pro-v1:0")
        self.strands_agent = Agent(
            model=model_id,
            system_prompt=self._get_system_prompt()
        )
    
    def _get_system_prompt(self) -> str:
        return """You are an orchestrator agent that classifies user intents and routes to specialists.

Available specialists:
- vision: Image analysis, visual content understanding
- document: Document processing, text extraction, PDF analysis
- data: Data analysis, SQL queries, chart generation
- tool: Calculator, weather, general utilities

Respond with ONLY the specialist name (vision, document, data, or tool).
If unclear, respond with 'orchestrator' to handle directly."""
    
    @track_latency("orchestrator")
    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process request and route to appropriate specialist."""
        start_time = time.time()
        
        self.logger.log_request(
            user_id=request.user_id,
            session_id=request.session_id,
            message=request.message
        )
        
        try:
            # 1. Load context from memory
            context = await self._load_context(request)
            
            # 2. Classify intent
            specialist = await self._classify_intent(request.message, context)
            
            # 3. Route to specialist or handle directly
            if specialist == "orchestrator":
                response_content = await self._handle_directly(request, context)
            else:
                response_content = await self._route_to_specialist(
                    specialist, request, context
                )
            
            # 4. Store interaction in memory
            await self.memory.store_interaction(
                user_id=request.user_id,
                session_id=request.session_id,
                user_message=request.message,
                agent_response=response_content,
                agent_name=specialist,
                metadata={"routed_to": specialist}
            )
            
            processing_time = (time.time() - start_time) * 1000
            
            self.logger.log_response(
                user_id=request.user_id,
                session_id=request.session_id,
                processing_time_ms=processing_time,
                success=True,
                metadata={"specialist": specialist}
            )
            
            return AgentResponse(
                content=response_content,
                agent_name=self.agent_name,
                processing_time_ms=processing_time,
                metadata={"specialist": specialist}
            )
            
        except Exception as e:
            self.logger.log_error(e, request.user_id, request.session_id)
            raise
    
    async def _load_context(self, request: AgentRequest) -> List[Dict[str, str]]:
        """Load conversation context from memory."""
        # Get recent history
        recent = await self.memory.get_recent_messages(
            user_id=request.user_id,
            session_id=request.session_id,
            limit=10
        )
        
        # Get relevant semantic context
        relevant = await self.memory.semantic_search(
            user_id=request.user_id,
            query=request.message,
            limit=5
        )
        
        # Combine with request context
        return request.context + relevant + recent
    
    async def _classify_intent(
        self,
        message: str,
        context: List[Dict[str, str]]
    ) -> str:
        """Classify user intent to determine specialist."""
        classification_prompt = f"User message: {message}\n\nWhich specialist should handle this?"
        
        response = await self.strands_agent.run(
            messages=[{"role": "user", "content": classification_prompt}]
        )
        
        specialist = response.content.strip().lower()
        
        # Validate specialist
        valid_specialists = ["vision", "document", "data", "tool", "orchestrator"]
        if specialist not in valid_specialists:
            specialist = "orchestrator"
        
        return specialist
    
    async def _route_to_specialist(
        self,
        specialist: str,
        request: AgentRequest,
        context: List[Dict[str, str]]
    ) -> str:
        """Route request to specialist agent via A2A."""
        start_time = time.time()
        
        try:
            # Make A2A call
            response = await self.a2a_client.call_agent(
                agent_name=specialist,
                request=AgentRequest(
                    message=request.message,
                    context=context,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    metadata=request.metadata
                )
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            self.logger.log_a2a_call(
                target_agent=specialist,
                user_id=request.user_id,
                session_id=request.session_id,
                latency_ms=latency_ms,
                success=True
            )
            
            return response.content
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self.logger.log_a2a_call(
                target_agent=specialist,
                user_id=request.user_id,
                session_id=request.session_id,
                latency_ms=latency_ms,
                success=False
            )
            raise
    
    async def _handle_directly(
        self,
        request: AgentRequest,
        context: List[Dict[str, str]]
    ) -> str:
        """Handle request directly without routing."""
        messages = context + [{"role": "user", "content": request.message}]
        response = await self.strands_agent.run(messages=messages)
        return response.content

