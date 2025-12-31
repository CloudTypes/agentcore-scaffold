"""Tests for Google OAuth2 authentication."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import os


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for OAuth2."""
    with patch.dict(os.environ, {
        "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:8080/api/auth/callback",
        "JWT_SECRET_KEY": "test-jwt-secret-key-for-testing-only"
    }):
        yield


def test_oauth2_handler_initialization(mock_env_vars):
    """Test OAuth2 handler initialization."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    handler = GoogleOAuth2Handler()
    assert handler.client_id == "test-client-id.apps.googleusercontent.com"
    assert handler.client_secret == "test-client-secret"
    assert handler.redirect_uri == "http://localhost:8080/api/auth/callback"


def test_oauth2_handler_missing_config():
    """Test OAuth2 handler fails without required config."""
    with patch.dict(os.environ, {}, clear=True):
        from auth.google_oauth2 import GoogleOAuth2Handler
        
        with pytest.raises(ValueError):
            GoogleOAuth2Handler()


@patch('auth.google_oauth2.Flow')
def test_get_authorization_url(mock_flow, mock_env_vars):
    """Test authorization URL generation."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    mock_flow_instance = MagicMock()
    mock_flow_instance.authorization_url.return_value = (
        "https://accounts.google.com/o/oauth2/auth?state=test",
        "test"
    )
    mock_flow.from_client_config.return_value = mock_flow_instance
    
    handler = GoogleOAuth2Handler()
    auth_url, state = handler.get_authorization_url()
    
    assert auth_url.startswith("https://accounts.google.com")
    assert state is not None
    mock_flow.from_client_config.assert_called_once()


def test_create_jwt_token(mock_env_vars):
    """Test JWT token creation."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    handler = GoogleOAuth2Handler()
    token = handler._create_jwt_token(
        email="test@example.com",
        name="Test User",
        picture="https://example.com/pic.jpg"
    )
    
    assert token is not None
    assert isinstance(token, str)


def test_verify_token(mock_env_vars):
    """Test JWT token verification."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    handler = GoogleOAuth2Handler()
    token = handler._create_jwt_token(
        email="test@example.com",
        name="Test User"
    )
    
    payload = handler.verify_token(token)
    assert payload["email"] == "test@example.com"
    assert payload["name"] == "Test User"


def test_verify_token_expired(mock_env_vars):
    """Test expired token verification."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    import jwt
    from datetime import datetime, timedelta
    
    handler = GoogleOAuth2Handler()
    
    # Create expired token
    payload = {
        "email": "test@example.com",
        "exp": datetime.utcnow() - timedelta(hours=1)
    }
    expired_token = jwt.encode(payload, handler.jwt_secret, algorithm=handler.jwt_algorithm)
    
    with pytest.raises(ValueError, match="expired"):
        handler.verify_token(expired_token)

