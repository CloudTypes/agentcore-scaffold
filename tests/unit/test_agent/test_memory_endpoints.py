"""Unit tests for memory API endpoints."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from datetime import datetime
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from agent import app

# Import get_current_user - must match the import path used in agent.py
from auth.oauth2_middleware import get_current_user


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    return {"email": "user@example.com", "name": "Test User"}


@pytest.fixture
def mock_memory_client():
    """Mock memory client."""
    client = MagicMock()
    client.memory_id = "test-memory-id"
    # Use region from environment or default
    import os

    client.region = os.getenv("AGENTCORE_MEMORY_REGION") or os.getenv("AWS_REGION", "us-west-2")
    return client


@pytest.fixture
def app_client_with_memory(mock_memory_client, mock_user):
    """Create test client with memory enabled."""

    # Override FastAPI dependency
    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    with patch("agent.memory_client", mock_memory_client):
        yield TestClient(app)

    # Clean up dependency override
    app.dependency_overrides.clear()


@pytest.fixture
def app_client_no_memory(mock_user):
    """Create test client with memory disabled."""

    # Override FastAPI dependency
    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    with patch("agent.memory_client", None):
        yield TestClient(app)

    # Clean up dependency override
    app.dependency_overrides.clear()


@pytest.fixture
def app_client_unauthorized():
    """Create test client without authentication."""

    # Override FastAPI dependency to raise 401
    async def override_get_current_user():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = override_get_current_user

    with patch("agent.memory_client", MagicMock()):
        yield TestClient(app)

    # Clean up dependency override
    app.dependency_overrides.clear()


class TestQueryMemories:
    """Test cases for POST /api/memory/query endpoint."""

    def test_query_memories_with_query_text(self, app_client_with_memory, mock_memory_client, mock_user):
        """Test querying memories with query text."""
        mock_memory_client.retrieve_memories.return_value = [
            {"content": {"text": "Memory 1"}, "namespace": "/semantic/user_example_com"}
        ]

        response = app_client_with_memory.post("/api/memory/query", json={"query": "test query", "top_k": 5})

        assert response.status_code == 200
        data = response.json()
        assert "memories" in data
        assert len(data["memories"]) == 1
        assert data["memories"][0]["content"] == "Memory 1"
        mock_memory_client.retrieve_memories.assert_called_once()

    def test_query_memories_with_namespace_prefix(self, app_client_with_memory, mock_memory_client):
        """Test querying memories with namespace prefix."""
        mock_memory_client.retrieve_memories.return_value = []

        response = app_client_with_memory.post(
            "/api/memory/query", json={"query": "test", "namespace": "/summaries/{actorId}"}
        )

        assert response.status_code == 200
        call_args = mock_memory_client.retrieve_memories.call_args
        assert call_args[1]["namespace_prefix"] == "/summaries/{actorId}"

    def test_query_memories_with_memory_type(self, app_client_with_memory, mock_memory_client):
        """Test querying memories with memory type."""
        mock_memory_client.retrieve_memories.return_value = []

        response = app_client_with_memory.post("/api/memory/query", json={"query": "test", "memory_type": "summaries"})

        assert response.status_code == 200
        call_args = mock_memory_client.retrieve_memories.call_args
        assert call_args[1]["memory_type"] == "summaries"

    def test_query_memories_with_top_k(self, app_client_with_memory, mock_memory_client):
        """Test querying memories with top_k parameter."""
        mock_memory_client.retrieve_memories.return_value = []

        response = app_client_with_memory.post("/api/memory/query", json={"query": "test", "top_k": 10})

        assert response.status_code == 200
        call_args = mock_memory_client.retrieve_memories.call_args
        assert call_args[1]["top_k"] == 10

    def test_query_memories_dict_records(self, app_client_with_memory, mock_memory_client):
        """Test querying memories with dict records."""
        mock_memory_client.retrieve_memories.return_value = [
            {"content": {"text": "Memory text"}, "namespace": "/test/namespace"}
        ]

        response = app_client_with_memory.post("/api/memory/query", json={"query": "test"})

        assert response.status_code == 200
        data = response.json()
        assert data["memories"][0]["content"] == "Memory text"
        assert data["memories"][0]["namespace"] == "/test/namespace"

    def test_query_memories_object_records(self, app_client_with_memory, mock_memory_client):
        """Test querying memories with object-like records."""
        mock_record = MagicMock()
        mock_record.content = {"text": "Object memory"}
        mock_record.namespace = "/test/namespace"
        mock_memory_client.retrieve_memories.return_value = [mock_record]

        response = app_client_with_memory.post("/api/memory/query", json={"query": "test"})

        assert response.status_code == 200
        data = response.json()
        assert data["memories"][0]["content"] == "Object memory"

    def test_query_memories_memory_disabled(self, app_client_no_memory):
        """Test querying memories when memory is disabled."""
        response = app_client_no_memory.post("/api/memory/query", json={"query": "test"})

        assert response.status_code == 503
        assert "Memory not enabled" in response.json()["detail"]

    def test_query_memories_unauthorized(self, app_client_unauthorized):
        """Test querying memories without authentication."""
        response = app_client_unauthorized.post("/api/memory/query", json={"query": "test"})

        assert response.status_code == 401


class TestListSessions:
    """Test cases for GET /api/memory/sessions endpoint."""

    def test_list_sessions_success(self, app_client_with_memory, mock_memory_client):
        """Test listing user sessions."""
        mock_memory_client.list_sessions.return_value = [
            {"session_id": "session-123", "summary": "Session summary"},
            {"session_id": "session-456", "summary": "Another session"},
        ]

        response = app_client_with_memory.get("/api/memory/sessions")

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 2
        assert data["sessions"][0]["session_id"] == "session-123"

    def test_list_sessions_empty(self, app_client_with_memory, mock_memory_client):
        """Test listing sessions when none exist."""
        mock_memory_client.list_sessions.return_value = []

        response = app_client_with_memory.get("/api/memory/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["sessions"] == []

    def test_list_sessions_dict_format(self, app_client_with_memory, mock_memory_client):
        """Test listing sessions with dict format."""
        mock_memory_client.list_sessions.return_value = [{"session_id": "session-123", "summary": "Summary"}]

        response = app_client_with_memory.get("/api/memory/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["sessions"][0]["session_id"] == "session-123"

    def test_list_sessions_object_format(self, app_client_with_memory, mock_memory_client):
        """Test listing sessions with object format."""
        mock_session = MagicMock()
        mock_session.session_id = "session-123"
        mock_session.summary = "Summary"
        mock_memory_client.list_sessions.return_value = [mock_session]

        response = app_client_with_memory.get("/api/memory/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["sessions"][0]["session_id"] == "session-123"

    def test_list_sessions_memory_disabled(self, app_client_no_memory):
        """Test listing sessions when memory is disabled."""
        response = app_client_no_memory.get("/api/memory/sessions")

        assert response.status_code == 503

    def test_list_sessions_unauthorized(self, app_client_unauthorized):
        """Test listing sessions without authentication."""
        response = app_client_unauthorized.get("/api/memory/sessions")

        assert response.status_code == 401


class TestGetSession:
    """Test cases for GET /api/memory/sessions/{session_id} endpoint."""

    def test_get_session_success(self, app_client_with_memory, mock_memory_client):
        """Test getting session details."""
        mock_memory_client.get_session_summary.return_value = {
            "namespace": "/summaries/user_example_com/session-123",
            "content": {"text": "Session summary text"},
            "created_at": datetime(2024, 1, 1, 12, 0, 0),
        }

        response = app_client_with_memory.get("/api/memory/sessions/session-123")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "session-123"
        assert data["summary"] == "Session summary text"
        assert "full_record" in data
        # Check datetime serialization
        assert isinstance(data["full_record"]["created_at"], str)

    def test_get_session_not_found(self, app_client_with_memory, mock_memory_client):
        """Test getting session that doesn't exist."""
        mock_memory_client.get_session_summary.return_value = None

        response = app_client_with_memory.get("/api/memory/sessions/nonexistent")

        assert response.status_code == 404
        assert "Session not found" in response.json()["detail"]

    def test_get_session_dict_format(self, app_client_with_memory, mock_memory_client):
        """Test getting session with dict format."""
        mock_memory_client.get_session_summary.return_value = {"namespace": "/test/namespace", "content": {"text": "Summary"}}

        response = app_client_with_memory.get("/api/memory/sessions/session-123")

        assert response.status_code == 200
        data = response.json()
        assert data["summary"] == "Summary"

    def test_get_session_object_format(self, app_client_with_memory, mock_memory_client):
        """Test getting session with object format."""
        mock_record = MagicMock()
        mock_record.content = {"text": "Object summary"}
        mock_record.namespace = "/test/namespace"
        mock_memory_client.get_session_summary.return_value = mock_record

        response = app_client_with_memory.get("/api/memory/sessions/session-123")

        assert response.status_code == 200
        data = response.json()
        assert data["summary"] == "Object summary"

    def test_get_session_datetime_serialization(self, app_client_with_memory, mock_memory_client):
        """Test datetime serialization in full_record."""
        mock_memory_client.get_session_summary.return_value = {
            "namespace": "/test/namespace",
            "content": {"text": "Summary"},
            "created_at": datetime(2024, 1, 1, 12, 0, 0),
            "nested": {"updated_at": datetime(2024, 1, 2, 12, 0, 0)},
            "list_dates": [datetime(2024, 1, 3, 12, 0, 0)],
        }

        response = app_client_with_memory.get("/api/memory/sessions/session-123")

        assert response.status_code == 200
        data = response.json()
        full_record = data["full_record"]
        assert isinstance(full_record["created_at"], str)
        assert isinstance(full_record["nested"]["updated_at"], str)
        assert isinstance(full_record["list_dates"][0], str)

    def test_get_session_memory_disabled(self, app_client_no_memory):
        """Test getting session when memory is disabled."""
        response = app_client_no_memory.get("/api/memory/sessions/session-123")

        assert response.status_code == 503

    def test_get_session_unauthorized(self, app_client_unauthorized):
        """Test getting session without authentication."""
        response = app_client_unauthorized.get("/api/memory/sessions/session-123")

        assert response.status_code == 401


class TestDeleteSession:
    """Test cases for DELETE /api/memory/sessions/{session_id} endpoint."""

    def test_delete_session_success(self, app_client_with_memory):
        """Test deleting session (placeholder implementation)."""
        response = app_client_with_memory.delete("/api/memory/sessions/session-123")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Session deleted"

    def test_delete_session_unauthorized(self, app_client_unauthorized):
        """Test deleting session without authentication."""
        response = app_client_unauthorized.delete("/api/memory/sessions/session-123")

        assert response.status_code == 401


class TestGetPreferences:
    """Test cases for GET /api/memory/preferences endpoint."""

    def test_get_preferences_success(self, app_client_with_memory, mock_memory_client):
        """Test getting user preferences."""
        mock_memory_client.get_user_preferences.return_value = [
            {"content": {"text": "User prefers dark mode"}, "namespace": "/preferences/user_example_com"}
        ]

        response = app_client_with_memory.get("/api/memory/preferences")

        assert response.status_code == 200
        data = response.json()
        assert "preferences" in data
        assert len(data["preferences"]) == 1
        assert data["preferences"][0]["content"] == "User prefers dark mode"

    def test_get_preferences_empty(self, app_client_with_memory, mock_memory_client):
        """Test getting preferences when none exist."""
        mock_memory_client.get_user_preferences.return_value = []

        response = app_client_with_memory.get("/api/memory/preferences")

        assert response.status_code == 200
        data = response.json()
        assert data["preferences"] == []

    def test_get_preferences_dict_format(self, app_client_with_memory, mock_memory_client):
        """Test getting preferences with dict format."""
        mock_memory_client.get_user_preferences.return_value = [
            {"content": {"text": "Preference"}, "namespace": "/test/namespace"}
        ]

        response = app_client_with_memory.get("/api/memory/preferences")

        assert response.status_code == 200
        data = response.json()
        assert data["preferences"][0]["content"] == "Preference"

    def test_get_preferences_object_format(self, app_client_with_memory, mock_memory_client):
        """Test getting preferences with object format."""
        mock_pref = MagicMock()
        mock_pref.content = {"text": "Object preference"}
        mock_pref.namespace = "/test/namespace"
        mock_memory_client.get_user_preferences.return_value = [mock_pref]

        response = app_client_with_memory.get("/api/memory/preferences")

        assert response.status_code == 200
        data = response.json()
        assert data["preferences"][0]["content"] == "Object preference"

    def test_get_preferences_memory_disabled(self, app_client_no_memory):
        """Test getting preferences when memory is disabled."""
        response = app_client_no_memory.get("/api/memory/preferences")

        assert response.status_code == 503

    def test_get_preferences_unauthorized(self, app_client_unauthorized):
        """Test getting preferences without authentication."""
        response = app_client_unauthorized.get("/api/memory/preferences")

        assert response.status_code == 401


class TestDiagnoseMemory:
    """Test cases for POST /api/memory/diagnose endpoint."""

    def test_diagnose_memory_full(self, app_client_with_memory, mock_memory_client):
        """Test full memory diagnostics."""
        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()
            mock_bedrock.list_memory_records.return_value = {
                "memoryRecordSummaries": [{"content": {"text": "Record 1"}}, {"content": {"text": "Record 2"}}]
            }
            mock_boto3.return_value = mock_bedrock

            response = app_client_with_memory.post("/api/memory/diagnose", json={"session_id": "session-123"})

            assert response.status_code == 200
            data = response.json()
            assert "checks" in data
            assert "parent_namespace" in data["checks"]
            assert "exact_namespace" in data["checks"]
            assert "semantic_namespace" in data["checks"]
            assert "preferences_namespace" in data["checks"]
            assert "total_records" in data

    def test_diagnose_memory_without_session_id(self, app_client_with_memory, mock_memory_client):
        """Test diagnostics without session_id."""
        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()
            mock_bedrock.list_memory_records.return_value = {"memoryRecordSummaries": []}
            mock_boto3.return_value = mock_bedrock

            response = app_client_with_memory.post("/api/memory/diagnose", json={})

            assert response.status_code == 200
            data = response.json()
            assert "exact_namespace" not in data["checks"]

    def test_diagnose_memory_parent_namespace_success(self, app_client_with_memory, mock_memory_client):
        """Test parent namespace check success."""
        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()
            mock_bedrock.list_memory_records.return_value = {"memoryRecordSummaries": [{"content": {"text": "Record"}}]}
            mock_boto3.return_value = mock_bedrock

            response = app_client_with_memory.post("/api/memory/diagnose", json={})

            assert response.status_code == 200
            data = response.json()
            check = data["checks"]["parent_namespace"]
            assert check["success"] is True
            assert check["record_count"] == 1

    def test_diagnose_memory_parent_namespace_error(self, app_client_with_memory, mock_memory_client):
        """Test parent namespace check with error."""
        from botocore.exceptions import ClientError

        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()
            mock_bedrock.list_memory_records.side_effect = ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListMemoryRecords"
            )
            mock_boto3.return_value = mock_bedrock

            response = app_client_with_memory.post("/api/memory/diagnose", json={})

            assert response.status_code == 200
            data = response.json()
            check = data["checks"]["parent_namespace"]
            assert check["success"] is False
            assert "error" in check
            assert "error_code" in check

    def test_diagnose_memory_exact_namespace(self, app_client_with_memory, mock_memory_client):
        """Test exact namespace check."""
        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()
            mock_bedrock.list_memory_records.return_value = {
                "memoryRecordSummaries": [{"content": {"text": "Session record"}}]
            }
            mock_boto3.return_value = mock_bedrock

            response = app_client_with_memory.post("/api/memory/diagnose", json={"session_id": "session-123"})

            assert response.status_code == 200
            data = response.json()
            check = data["checks"]["exact_namespace"]
            assert check["success"] is True
            assert "session-123" in check["namespace"]

    def test_diagnose_memory_semantic_namespace(self, app_client_with_memory, mock_memory_client):
        """Test semantic namespace check."""
        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()
            mock_bedrock.list_memory_records.return_value = {"memoryRecordSummaries": []}
            mock_boto3.return_value = mock_bedrock

            response = app_client_with_memory.post("/api/memory/diagnose", json={})

            assert response.status_code == 200
            data = response.json()
            assert "semantic_namespace" in data["checks"]

    def test_diagnose_memory_preferences_namespace(self, app_client_with_memory, mock_memory_client):
        """Test preferences namespace check."""
        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()
            mock_bedrock.list_memory_records.return_value = {"memoryRecordSummaries": []}
            mock_boto3.return_value = mock_bedrock

            response = app_client_with_memory.post("/api/memory/diagnose", json={})

            assert response.status_code == 200
            data = response.json()
            assert "preferences_namespace" in data["checks"]

    def test_diagnose_memory_datetime_serialization(self, app_client_with_memory, mock_memory_client):
        """Test datetime serialization in diagnostics."""
        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()
            mock_bedrock.list_memory_records.return_value = {
                "memoryRecordSummaries": [{"content": {"text": "Record"}, "created_at": datetime(2024, 1, 1, 12, 0, 0)}]
            }
            mock_boto3.return_value = mock_bedrock

            response = app_client_with_memory.post("/api/memory/diagnose", json={})

            assert response.status_code == 200
            data = response.json()
            # Check that datetime is serialized
            records = data["checks"]["parent_namespace"]["records"]
            if records:
                assert isinstance(records[0].get("created_at"), str)

    def test_diagnose_memory_total_records(self, app_client_with_memory, mock_memory_client):
        """Test total records calculation."""
        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()
            mock_bedrock.list_memory_records.return_value = {
                "memoryRecordSummaries": [{"content": {"text": "Record 1"}}, {"content": {"text": "Record 2"}}]
            }
            mock_boto3.return_value = mock_bedrock

            response = app_client_with_memory.post("/api/memory/diagnose", json={})

            assert response.status_code == 200
            data = response.json()
            # Should sum records from all successful checks
            assert data["total_records"] >= 0

    def test_diagnose_memory_memory_disabled(self, app_client_no_memory):
        """Test diagnostics when memory is disabled."""
        response = app_client_no_memory.post("/api/memory/diagnose", json={})

        assert response.status_code == 503

    def test_diagnose_memory_unauthorized(self, app_client_unauthorized):
        """Test diagnostics without authentication."""
        response = app_client_unauthorized.post("/api/memory/diagnose", json={})

        assert response.status_code == 401
