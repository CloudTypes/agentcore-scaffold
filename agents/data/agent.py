"""Data specialist agent for data analysis."""

import time
import os
from strands import Agent
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.memory_client import MemoryClient
from agents.shared.observability import AgentLogger, track_latency


class DataAgent:
    """
    Specialist agent for data analysis and SQL queries.

    This agent provides data analysis capabilities including SQL query generation
    and execution, data visualization, statistical analysis, and answering questions
    about data. It uses the Strands framework with memory integration for
    context-aware responses.
    """

    def __init__(self) -> None:
        """
        Initialize the DataAgent.

        Sets up the agent with:
        - Logger for observability
        - Memory client for context storage
        - Strands agent configured for data analysis

        The model ID can be configured via the DATA_MODEL environment variable,
        defaulting to "amazon.nova-lite-v1:0" if not set.
        """
        self.agent_name = "data"
        self.logger = AgentLogger(self.agent_name)
        self.memory = MemoryClient()

        # Initialize Strands agent with data model
        model_id = os.getenv("DATA_MODEL", "amazon.nova-lite-v1:0")
        self.strands_agent = Agent(model=model_id, system_prompt=self._get_system_prompt())

    def _get_system_prompt(self) -> str:
        """
        Generate the system prompt for the data agent.

        Returns:
            A string containing the system prompt that defines the agent's
            capabilities and behavior for data analysis tasks.
        """
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
        """
        Process a data-related request from a user.

        This method handles the full request lifecycle:
        1. Logs the incoming request
        2. Builds message context from the request
        3. Processes the request using the Strands agent
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

        self.logger.log_request(user_id=request.user_id, session_id=request.session_id, message=request.message)

        try:
            # Build messages with context
            messages = request.context + [{"role": "user", "content": request.message}]

            # Process with Strands agent
            response = await self.strands_agent.run(messages=messages)

            processing_time = (time.time() - start_time) * 1000

            # Store interaction in memory
            await self.memory.store_interaction(
                user_id=request.user_id,
                session_id=request.session_id,
                user_message=request.message,
                agent_response=response.content,
                agent_name=self.agent_name,
            )

            self.logger.log_response(
                user_id=request.user_id, session_id=request.session_id, processing_time_ms=processing_time, success=True
            )

            return AgentResponse(content=response.content, agent_name=self.agent_name, processing_time_ms=processing_time)

        except (RuntimeError, ValueError) as e:
            self.logger.log_error(e, request.user_id, request.session_id)
            raise
        except Exception as e:
            self.logger.log_error(e, request.user_id, request.session_id)
            raise RuntimeError(f"Unexpected error processing request: {e}") from e
