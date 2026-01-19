"""
Unit tests for FastAPI endpoints.
"""

import pytest
import sys
import os
import json

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from fastapi.testclient import TestClient
from agent import app


class TestHealthCheck:
    """Test cases for /ping health check endpoint."""
    
    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        return TestClient(app)
    
    def test_health_check_status_code(self, client):
        """Test health check returns 200 status code."""
        response = client.get("/ping")
        assert response.status_code == 200
    
    def test_health_check_response_structure(self, client):
        """Test health check response structure."""
        response = client.get("/ping")
        data = response.json()
        
        assert "status" in data
        assert "service" in data
        assert "version" in data
    
    def test_health_check_content(self, client):
        """Test health check response content."""
        response = client.get("/ping")
        data = response.json()
        
        assert data["status"] == "healthy"
        assert data["service"] == "agentcore-scaffold"
        assert data["version"] == "1.0.0"
    
    def test_health_check_content_type(self, client):
        """Test health check returns JSON content type."""
        response = client.get("/ping")
        assert response.headers["content-type"] == "application/json"


class TestRootEndpoint:
    """Test cases for / root endpoint."""
    
    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        return TestClient(app)
    
    def test_root_status_code(self, client):
        """Test root endpoint returns 200 status code."""
        response = client.get("/")
        assert response.status_code == 200
    
    def test_root_response_structure(self, client):
        """Test root endpoint response structure."""
        # Root endpoint may serve HTML if index.html exists, so test /api instead
        response = client.get("/api")
        data = response.json()
        
        assert "service" in data
        assert "description" in data
        assert "endpoints" in data
        assert "model" in data
        assert "region" in data
    
    def test_root_service_info(self, client):
        """Test root endpoint service information."""
        # Root endpoint may serve HTML if index.html exists, so test /api instead
        response = client.get("/api")
        data = response.json()
        
        assert data["service"] == "AgentCore Voice Agent"
        assert "Bi-directional streaming" in data["description"]
    
    def test_root_endpoints_list(self, client):
        """Test root endpoint includes endpoints list."""
        # Root endpoint may serve HTML if index.html exists, so test /api instead
        response = client.get("/api")
        data = response.json()
        
        assert "websocket" in data["endpoints"]
        assert "health" in data["endpoints"]
        assert data["endpoints"]["websocket"] == "/ws"
        assert data["endpoints"]["health"] == "/ping"
    
    def test_root_model_info(self, client):
        """Test root endpoint includes model information."""
        # Root endpoint may serve HTML if index.html exists, so test /api instead
        response = client.get("/api")
        data = response.json()
        
        assert "model" in data
        assert "region" in data
        assert isinstance(data["model"], str)
        assert isinstance(data["region"], str)
    
    def test_root_content_type(self, client):
        """Test root endpoint returns JSON content type."""
        # Root endpoint may serve HTML if index.html exists, so test /api instead
        response = client.get("/api")
        assert response.headers["content-type"] == "application/json"

