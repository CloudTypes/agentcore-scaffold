"""Service discovery for agent endpoints."""

import os
from typing import Dict, Optional
from functools import lru_cache


class ServiceDiscovery:
    """Discover agent endpoints in AgentCore Runtime or local development."""
    
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self._endpoints: Dict[str, str] = {}
        self._load_endpoints()
    
    def _load_endpoints(self):
        """Load agent endpoints from environment or service discovery."""
        if self.environment == "development":
            # Local development - check if running in Docker or locally
            # If VISION_AGENT_URL is set, use it; otherwise try localhost first, then Docker service name
            self._endpoints = {
                "orchestrator": os.getenv("ORCHESTRATOR_URL", "http://localhost:9005"),  # A2A port from docker-compose
                "vision": os.getenv("VISION_AGENT_URL", "http://localhost:9001"),  # Port 9001 from docker-compose
                "document": os.getenv("DOCUMENT_AGENT_URL", "http://localhost:9002"),
                "data": os.getenv("DATA_AGENT_URL", "http://localhost:9003"),
                "tool": os.getenv("TOOL_AGENT_URL", "http://localhost:9004")
            }
        else:
            # Production - use environment variables set by CDK
            self._endpoints = {
                "orchestrator": os.getenv("ORCHESTRATOR_URL"),
                "vision": os.getenv("VISION_AGENT_URL"),
                "document": os.getenv("DOCUMENT_AGENT_URL"),
                "data": os.getenv("DATA_AGENT_URL"),
                "tool": os.getenv("TOOL_AGENT_URL")
            }
    
    def get_endpoint(self, agent_name: str) -> str:
        """Get endpoint URL for a specific agent."""
        endpoint = self._endpoints.get(agent_name)
        if not endpoint:
            raise ValueError(f"No endpoint found for agent: {agent_name}")
        return endpoint
    
    def get_all_endpoints(self) -> Dict[str, str]:
        """Get all agent endpoints."""
        return self._endpoints.copy()


@lru_cache()
def get_service_discovery() -> ServiceDiscovery:
    """Singleton service discovery instance."""
    return ServiceDiscovery()

