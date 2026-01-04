"""Document specialist agent for document processing."""

from typing import List, Dict
import time
import os
from strands import Agent
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.memory_client import MemoryClient
from agents.shared.observability import AgentLogger, track_latency


class DocumentAgent:
    """Specialist agent for document processing and text extraction."""
    
    def __init__(self):
        self.agent_name = "document"
        self.logger = AgentLogger(self.agent_name)
        self.memory = MemoryClient()
        
        # Initialize Strands agent with document model
        model_id = os.getenv("DOCUMENT_MODEL", "amazon.nova-pro-v1:0")
        self.strands_agent = Agent(
            model=model_id,
            system_prompt=self._get_system_prompt()
        )
    
    def _get_system_prompt(self) -> str:
        return """You are a document specialist agent focused on document processing and text extraction.

Your capabilities:
- Extract text from documents (PDF, Word, etc.)
- Analyze document structure and content
- Summarize documents
- Answer questions about document content
- Process and understand document formats

Be thorough and accurate in your document analysis."""
    
    @track_latency("document")
    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process document-related request."""
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

