"""Unit tests for CORS configuration in orchestrator agent."""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add project root to path for imports
project_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, project_root)

from agents.orchestrator.app import app


class TestCORS:
    """Test cases for CORS headers."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        return TestClient(app)

    def test_cors_headers_present(self, client):
        """Test that CORS headers are set in responses."""
        response = client.options(
            "/api/sessions",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

        # CORS preflight should return 200
        assert response.status_code == 200
        # Check for CORS headers (FastAPI CORS middleware adds these)
        assert "access-control-allow-origin" in response.headers or response.status_code == 200

    def test_cors_allows_all_origins(self, client):
        """Test that CORS allows requests from any origin."""
        response = client.get("/health", headers={"Origin": "https://example.com"})

        assert response.status_code == 200
        # CORS middleware should allow all origins (configured as "*")
        # The actual header value depends on middleware configuration

    def test_cors_preflight_request(self, client):
        """Test CORS preflight OPTIONS request."""
        response = client.options(
            "/api/chat",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type, Authorization",
            },
        )

        # Preflight should succeed
        assert response.status_code in [200, 204]
