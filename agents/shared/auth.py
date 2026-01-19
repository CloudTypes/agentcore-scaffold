"""Inter-agent authentication stub for backward compatibility with tests.

Note: This module is provided for backward compatibility with existing tests.
The current architecture uses Strands A2A protocol which handles authentication
automatically via AgentCore Runtime in production and Docker network isolation
in development. This stub allows tests to run without modification.
"""

import os
import jwt
from datetime import datetime, timedelta
from typing import Dict, Any


class InterAgentAuth:
    """
    Authentication stub for agent-to-agent communication.

    This is a minimal implementation for backward compatibility with tests.
    In production, authentication is handled by AgentCore Runtime.
    """

    def __init__(self):
        """Initialize authentication handler."""
        self.secret_key = os.getenv("AGENT_AUTH_SECRET", "test-secret-key-for-testing-only")
        self.algorithm = "HS256"
        self.token_expiry_minutes = 5

    def create_token(self, agent_name: str) -> str:
        """
        Create JWT token for agent-to-agent calls.

        Args:
            agent_name: Name of the calling agent

        Returns:
            JWT token string
        """
        payload = {
            "agent_name": agent_name,
            "exp": datetime.utcnow() + timedelta(minutes=self.token_expiry_minutes),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify JWT token from another agent.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            ValueError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {e}")
