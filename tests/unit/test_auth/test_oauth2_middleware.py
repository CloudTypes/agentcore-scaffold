"""Tests for OAuth2 middleware."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from fastapi import Request, HTTPException
from auth.oauth2_middleware import OAuth2Middleware, get_current_user, _get_oauth2_middleware


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for OAuth2."""
    with patch.dict(
        os.environ,
        {
            "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
            "GOOGLE_CLIENT_SECRET": "test-client-secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:8080/api/auth/callback",
            "JWT_SECRET_KEY": "test-jwt-secret-key-for-testing-only-32-chars",
        },
    ):
        yield


@pytest.fixture
def mock_request():
    """Mock FastAPI request."""
    request = MagicMock(spec=Request)
    request.headers = {}
    request.query_params = {}
    return request


class TestOAuth2Middleware:
    """Tests for OAuth2Middleware class."""

    def test_middleware_initialization(self, mock_env_vars):
        """Test OAuth2Middleware initialization."""
        middleware = OAuth2Middleware()
        assert middleware.oauth2_handler is not None

    def test_middleware_initialization_failure(self):
        """Test OAuth2Middleware initialization failure."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                OAuth2Middleware()

    @pytest.mark.asyncio
    async def test_get_current_user_from_authorization_header(self, mock_env_vars, mock_request):
        """Test get_current_user with token from Authorization header."""
        middleware = OAuth2Middleware()

        # Create a valid token
        token = middleware.oauth2_handler._create_jwt_token(email="user@example.com", name="Test User")

        mock_request.headers = {"Authorization": f"Bearer {token}"}

        user = await middleware.get_current_user(mock_request)

        assert user["email"] == "user@example.com"
        assert user["name"] == "Test User"

    @pytest.mark.asyncio
    async def test_get_current_user_from_query_parameter(self, mock_env_vars, mock_request):
        """Test get_current_user with token from query parameter."""
        middleware = OAuth2Middleware()

        # Create a valid token
        token = middleware.oauth2_handler._create_jwt_token(email="user@example.com")

        mock_request.query_params = {"token": token}

        user = await middleware.get_current_user(mock_request)

        assert user["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_get_current_user_missing_token(self, mock_env_vars, mock_request):
        """Test get_current_user when no token is provided."""
        middleware = OAuth2Middleware()

        with pytest.raises(HTTPException) as exc_info:
            await middleware.get_current_user(mock_request)

        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token_format(self, mock_env_vars, mock_request):
        """Test get_current_user with invalid token format in header."""
        middleware = OAuth2Middleware()

        mock_request.headers = {"Authorization": "InvalidFormat token"}

        with pytest.raises(HTTPException) as exc_info:
            await middleware.get_current_user(mock_request)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_empty_bearer_token(self, mock_env_vars, mock_request):
        """Test get_current_user with empty Bearer token."""
        middleware = OAuth2Middleware()

        mock_request.headers = {"Authorization": "Bearer "}

        with pytest.raises(HTTPException) as exc_info:
            await middleware.get_current_user(mock_request)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_expired_token(self, mock_env_vars, mock_request):
        """Test get_current_user with expired token."""
        from auth.google_oauth2 import GoogleOAuth2Handler
        import jwt
        from datetime import datetime, timedelta

        middleware = OAuth2Middleware()

        # Create expired token
        handler = GoogleOAuth2Handler()
        payload = {"email": "user@example.com", "exp": datetime.utcnow() - timedelta(hours=1)}
        expired_token = jwt.encode(payload, handler.jwt_secret, algorithm=handler.jwt_algorithm)

        mock_request.headers = {"Authorization": f"Bearer {expired_token}"}

        with pytest.raises(HTTPException) as exc_info:
            await middleware.get_current_user(mock_request)

        assert exc_info.value.status_code == 401
        assert "Invalid token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_env_vars, mock_request):
        """Test get_current_user with invalid token."""
        middleware = OAuth2Middleware()

        mock_request.headers = {"Authorization": "Bearer invalid.token.here"}

        with pytest.raises(HTTPException) as exc_info:
            await middleware.get_current_user(mock_request)

        assert exc_info.value.status_code == 401
        assert "Invalid token" in exc_info.value.detail


class TestGetCurrentUser:
    """Tests for get_current_user dependency function."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_env_vars, mock_request):
        """Test get_current_user dependency function success."""
        # Reset global middleware
        import auth.oauth2_middleware

        auth.oauth2_middleware._oauth2_middleware = None

        # Create valid token
        handler = OAuth2Middleware().oauth2_handler
        token = handler._create_jwt_token(email="user@example.com")

        mock_request.headers = {"Authorization": f"Bearer {token}"}

        user = await get_current_user(mock_request)

        assert user["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_get_current_user_middleware_initialization_failure(self, mock_request):
        """Test get_current_user when middleware initialization fails."""
        # Reset global middleware
        import auth.oauth2_middleware

        auth.oauth2_middleware._oauth2_middleware = None

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request)

            assert exc_info.value.status_code == 503
            assert "OAuth2 authentication is not configured" in exc_info.value.detail


class TestMiddlewareInitialization:
    """Tests for middleware lazy initialization."""

    def test_get_oauth2_middleware_lazy_initialization(self, mock_env_vars):
        """Test that middleware is initialized lazily."""
        # Reset global middleware
        import auth.oauth2_middleware

        auth.oauth2_middleware._oauth2_middleware = None

        middleware1 = _get_oauth2_middleware()
        middleware2 = _get_oauth2_middleware()

        # Should be the same instance (singleton)
        assert middleware1 is middleware2

    def test_get_oauth2_middleware_initialization_failure_valueerror(self):
        """Test middleware initialization failure with ValueError."""
        # Reset global middleware
        import auth.oauth2_middleware

        auth.oauth2_middleware._oauth2_middleware = None

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                _get_oauth2_middleware()

            assert exc_info.value.status_code == 503
            assert "OAuth2 authentication is not configured" in exc_info.value.detail

    def test_get_oauth2_middleware_initialization_failure_importerror(self, mock_env_vars):
        """Test middleware initialization failure with ImportError."""
        # Reset global middleware
        import auth.oauth2_middleware

        auth.oauth2_middleware._oauth2_middleware = None

        with patch("auth.oauth2_middleware.GoogleOAuth2Handler", side_effect=ImportError("Module not found")):
            with pytest.raises(HTTPException) as exc_info:
                _get_oauth2_middleware()

            assert exc_info.value.status_code == 503
            assert "OAuth2 authentication is not available" in exc_info.value.detail
