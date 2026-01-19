"""Service discovery for agent endpoints.

This module provides service discovery functionality for locating agent endpoints
in both development and production environments. In development, it uses localhost
URLs with default ports, while in production it relies on environment variables
set by the CDK infrastructure.
"""

import os
from typing import Dict
from functools import lru_cache


# Agent names supported by service discovery
AGENT_NAMES = ("orchestrator", "vision", "document", "data", "tool")

# Default endpoint URLs for development environment
DEFAULT_DEV_ENDPOINTS = {
    "orchestrator": "http://localhost:9005",  # A2A port from docker-compose
    "vision": "http://localhost:9001",  # Port 9001 from docker-compose
    "document": "http://localhost:9002",
    "data": "http://localhost:9003",
    "tool": "http://localhost:9004",
}

# Environment variable names for each agent endpoint
ENV_VAR_NAMES = {
    "orchestrator": "ORCHESTRATOR_URL",
    "vision": "VISION_AGENT_URL",
    "document": "DOCUMENT_AGENT_URL",
    "data": "DATA_AGENT_URL",
    "tool": "TOOL_AGENT_URL",
}


class ServiceDiscovery:
    """Discover agent endpoints in AgentCore Runtime or local development.

    This class handles endpoint discovery for agent-to-agent communication.
    In development mode, it provides default localhost URLs that can be
    overridden by environment variables. In production mode, it requires
    all endpoint URLs to be set via environment variables.

    The class uses a singleton pattern via the `get_service_discovery()`
    function to ensure consistent endpoint configuration across the application.
    """

    def __init__(self):
        """Initialize service discovery instance.

        Detects the current environment (development or production) and loads
        the appropriate endpoint configuration. In development, defaults are
        provided for all endpoints. In production, all endpoints must be set
        via environment variables.

        Raises:
            ValueError: If in production mode and any required environment
                variable is missing or empty.
        """
        self.environment = os.getenv("ENVIRONMENT", "development")
        self._endpoints: Dict[str, str] = {}
        self._load_endpoints()

    def _load_endpoints(self):
        """Load agent endpoints from environment or service discovery.

        In development mode, loads endpoints from environment variables with
        fallback to default localhost URLs. In production mode, requires all
        endpoints to be set via environment variables and validates that none
        are missing.

        Raises:
            ValueError: If in production mode and any required environment
                variable is missing or empty.
        """
        is_development = self.environment == "development"
        self._endpoints = {}

        for agent_name in AGENT_NAMES:
            env_var_name = ENV_VAR_NAMES[agent_name]
            endpoint = os.getenv(env_var_name)

            if endpoint:
                # Environment variable is set, use it
                self._endpoints[agent_name] = endpoint
            elif is_development:
                # Development mode: use default localhost URL
                self._endpoints[agent_name] = DEFAULT_DEV_ENDPOINTS[agent_name]
            else:
                # Production mode: environment variable is required
                raise ValueError(
                    f"Missing required environment variable '{env_var_name}' "
                    f"for agent '{agent_name}' in production environment. "
                    f"All agent endpoints must be configured via environment variables."
                )

    def get_endpoint(self, agent_name: str) -> str:
        """Get endpoint URL for a specific agent.

        Args:
            agent_name: Name of the agent (must be one of: orchestrator, vision,
                document, data, tool).

        Returns:
            The endpoint URL for the specified agent.

        Raises:
            ValueError: If the agent name is not recognized or no endpoint
                is configured for the agent.
        """
        if agent_name not in AGENT_NAMES:
            available = ", ".join(AGENT_NAMES)
            raise ValueError(f"Unknown agent name: '{agent_name}'. " f"Available agents: {available}")

        endpoint = self._endpoints.get(agent_name)
        if not endpoint:
            available = ", ".join(self._endpoints.keys())
            raise ValueError(f"No endpoint found for agent: '{agent_name}'. " f"Available agents: {available}")

        return endpoint

    def get_all_endpoints(self) -> Dict[str, str]:
        """Get all agent endpoints.

        Returns:
            A dictionary mapping agent names to their endpoint URLs. The
            returned dictionary is a copy to prevent external modification
            of the internal endpoint configuration.
        """
        return self._endpoints.copy()


@lru_cache()
def get_service_discovery() -> ServiceDiscovery:
    """Get singleton service discovery instance.

    Uses LRU cache to ensure only one ServiceDiscovery instance is created
    and reused across the application lifecycle. This ensures consistent
    endpoint configuration throughout the application.

    Returns:
        The singleton ServiceDiscovery instance.
    """
    return ServiceDiscovery()
