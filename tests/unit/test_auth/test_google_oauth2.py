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


# Tests for handle_callback()
@pytest.mark.asyncio
@patch('auth.google_oauth2.id_token')
@patch('auth.google_oauth2.Request')
@patch('auth.google_oauth2.Flow')
async def test_handle_callback_success(mock_flow, mock_request, mock_id_token, mock_env_vars):
    """Test successful OAuth2 callback handling."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    # Clear workspace domain to avoid domain restriction
    with patch.dict(os.environ, {"GOOGLE_WORKSPACE_DOMAIN": ""}, clear=False):
        # Mock flow and credentials
        mock_flow_instance = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.id_token = "test-id-token"
        mock_flow_instance.credentials = mock_credentials
        mock_flow.from_client_config.return_value = mock_flow_instance
        
        # Mock ID token verification
        mock_id_token.verify_oauth2_token.return_value = {
            "email": "user@example.com",
            "name": "Test User",
            "picture": "https://example.com/pic.jpg",
            "hd": "example.com"
        }
        
        handler = GoogleOAuth2Handler()
        result = await handler.handle_callback("auth-code-123", "state-123")
        
        assert result["email"] == "user@example.com"
        assert result["name"] == "Test User"
        assert result["picture"] == "https://example.com/pic.jpg"
        assert result["domain"] == "example.com"
        assert "token" in result
        mock_flow_instance.fetch_token.assert_called_once_with(code="auth-code-123")


@pytest.mark.asyncio
@patch('auth.google_oauth2.Flow')
async def test_handle_callback_invalid_code(mock_flow, mock_env_vars):
    """Test handle_callback with invalid authorization code."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    mock_flow_instance = MagicMock()
    mock_flow_instance.fetch_token.side_effect = Exception("Invalid code")
    mock_flow.from_client_config.return_value = mock_flow_instance
    
    handler = GoogleOAuth2Handler()
    
    with pytest.raises(ValueError, match="Invalid authorization code"):
        await handler.handle_callback("invalid-code", "state-123")


@pytest.mark.asyncio
@patch('auth.google_oauth2.Flow')
async def test_handle_callback_missing_id_token(mock_flow, mock_env_vars):
    """Test handle_callback when ID token is missing."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    mock_flow_instance = MagicMock()
    mock_credentials = MagicMock()
    mock_credentials.id_token = None  # Missing ID token
    mock_flow_instance.credentials = mock_credentials
    mock_flow.from_client_config.return_value = mock_flow_instance
    
    handler = GoogleOAuth2Handler()
    
    with pytest.raises(ValueError, match="No ID token received"):
        await handler.handle_callback("auth-code-123", "state-123")


@pytest.mark.asyncio
@patch('auth.google_oauth2.id_token')
@patch('auth.google_oauth2.Request')
@patch('auth.google_oauth2.Flow')
async def test_handle_callback_id_token_verification_failure(mock_flow, mock_request, mock_id_token, mock_env_vars):
    """Test handle_callback when ID token verification fails."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    mock_flow_instance = MagicMock()
    mock_credentials = MagicMock()
    mock_credentials.id_token = "invalid-token"
    mock_flow_instance.credentials = mock_credentials
    mock_flow.from_client_config.return_value = mock_flow_instance
    
    mock_id_token.verify_oauth2_token.side_effect = ValueError("Invalid token")
    
    handler = GoogleOAuth2Handler()
    
    with pytest.raises(ValueError, match="Invalid ID token"):
        await handler.handle_callback("auth-code-123", "state-123")


@pytest.mark.asyncio
@patch('auth.google_oauth2.id_token')
@patch('auth.google_oauth2.Request')
@patch('auth.google_oauth2.Flow')
async def test_handle_callback_missing_email(mock_flow, mock_request, mock_id_token, mock_env_vars):
    """Test handle_callback when email is missing from ID token."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    mock_flow_instance = MagicMock()
    mock_credentials = MagicMock()
    mock_credentials.id_token = "test-id-token"
    mock_flow_instance.credentials = mock_credentials
    mock_flow.from_client_config.return_value = mock_flow_instance
    
    # ID token without email
    mock_id_token.verify_oauth2_token.return_value = {
        "name": "Test User",
        # Missing email
    }
    
    handler = GoogleOAuth2Handler()
    
    with pytest.raises(ValueError, match="Email is required"):
        await handler.handle_callback("auth-code-123", "state-123")


@pytest.mark.asyncio
@patch('auth.google_oauth2.id_token')
@patch('auth.google_oauth2.Request')
@patch('auth.google_oauth2.Flow')
async def test_handle_callback_domain_restriction(mock_flow, mock_request, mock_id_token, mock_env_vars):
    """Test handle_callback with domain restriction enforcement."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    # Set workspace domain
    with patch.dict(os.environ, {"GOOGLE_WORKSPACE_DOMAIN": "allowed.com"}):
        handler = GoogleOAuth2Handler()
        
        mock_flow_instance = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.id_token = "test-id-token"
        mock_flow_instance.credentials = mock_credentials
        mock_flow.from_client_config.return_value = mock_flow_instance
        
        # User from different domain
        mock_id_token.verify_oauth2_token.return_value = {
            "email": "user@different.com",
            "hd": "different.com"  # Different domain
        }
        
        with pytest.raises(ValueError, match="Access restricted"):
            await handler.handle_callback("auth-code-123", "state-123")


@pytest.mark.asyncio
@patch('auth.google_oauth2.id_token')
@patch('auth.google_oauth2.Request')
@patch('auth.google_oauth2.Flow')
async def test_handle_callback_domain_restriction_allowed(mock_flow, mock_request, mock_id_token, mock_env_vars):
    """Test handle_callback with domain restriction when domain matches."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    # Set workspace domain
    with patch.dict(os.environ, {"GOOGLE_WORKSPACE_DOMAIN": "allowed.com"}):
        handler = GoogleOAuth2Handler()
        
        mock_flow_instance = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.id_token = "test-id-token"
        mock_flow_instance.credentials = mock_credentials
        mock_flow.from_client_config.return_value = mock_flow_instance
        
        # User from allowed domain
        mock_id_token.verify_oauth2_token.return_value = {
            "email": "user@allowed.com",
            "hd": "allowed.com"  # Matching domain
        }
        
        result = await handler.handle_callback("auth-code-123", "state-123")
        
        assert result["email"] == "user@allowed.com"
        assert result["domain"] == "allowed.com"


# Edge Cases Tests
def test_jwt_secret_warning(mock_env_vars):
    """Test JWT secret warning for short secrets."""
    import logging
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    # Set short JWT secret
    with patch.dict(os.environ, {"JWT_SECRET_KEY": "short"}):
        with patch('auth.google_oauth2.logger') as mock_logger:
            handler = GoogleOAuth2Handler()
            # Check if warning was logged
            mock_logger.warning.assert_called()
            assert "shorter than 32 characters" in str(mock_logger.warning.call_args)


def test_custom_jwt_expiration():
    """Test JWT token with custom expiration."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    import jwt
    
    # Set custom expiration and all required env vars before creating handler
    # Use clear=True to ensure we start with a clean environment
    with patch.dict(os.environ, {
        "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:8080/api/auth/callback",
        "JWT_SECRET_KEY": "test-jwt-secret-key-for-testing-only-32-chars",
        "JWT_EXPIRATION_MINUTES": "120"
    }, clear=True):
        # Create handler after setting env vars
        handler = GoogleOAuth2Handler()
        assert handler.jwt_expiration_minutes == 120
        
        # Create token
        token = handler._create_jwt_token(email="test@example.com")
        
        # Decode token
        payload = jwt.decode(token, handler.jwt_secret, algorithms=[handler.jwt_algorithm])
        
        # Get timestamps from token
        iat_timestamp = payload.get("iat")
        exp_timestamp = payload["exp"]
        
        # Verify both iat and exp are present
        assert iat_timestamp is not None, "Token should have 'iat' claim"
        assert exp_timestamp is not None, "Token should have 'exp' claim"
        
        # Calculate expiration relative to iat (this avoids timezone/timing issues)
        # exp should be iat + 120 minutes
        expiration_minutes = (exp_timestamp - iat_timestamp) / 60
        
        # Should be approximately 120 minutes (allow small tolerance for rounding)
        assert 119.5 <= expiration_minutes <= 120.5, f"Token expiration {expiration_minutes} minutes from iat is not approximately 120 minutes"


def test_custom_jwt_algorithm(mock_env_vars):
    """Test JWT token with custom algorithm."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    with patch.dict(os.environ, {"JWT_ALGORITHM": "HS512"}):
        handler = GoogleOAuth2Handler()
        assert handler.jwt_algorithm == "HS512"
        
        token = handler._create_jwt_token(email="test@example.com")
        # Token should be valid with HS512
        payload = handler.verify_token(token)
        assert payload["email"] == "test@example.com"


def test_verify_token_empty(mock_env_vars):
    """Test verify_token with empty token."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    handler = GoogleOAuth2Handler()
    
    with pytest.raises(ValueError, match="Token cannot be empty"):
        handler.verify_token("")


def test_verify_token_malformed(mock_env_vars):
    """Test verify_token with malformed token."""
    from auth.google_oauth2 import GoogleOAuth2Handler
    
    handler = GoogleOAuth2Handler()
    
    with pytest.raises(ValueError, match="Invalid token"):
        handler.verify_token("not.a.valid.jwt.token")

