"""OAuth2 middleware for FastAPI.

This module provides OAuth2 authentication middleware for FastAPI applications,
specifically designed to work with Google OAuth2 authentication. It extracts
and verifies JWT tokens from HTTP requests, supporting both standard HTTP
requests (via Authorization header) and WebSocket connections (via query
parameters).

The module provides:
- OAuth2Middleware: A class that handles token extraction and verification
- get_current_user: A FastAPI dependency function for route protection

The middleware uses lazy initialization to defer OAuth2 handler creation
until first use, allowing the application to start even if OAuth2 credentials
are not immediately available (useful for testing or development).

Example:
    Using as a FastAPI dependency::

        from fastapi import Depends
        from auth.oauth2_middleware import get_current_user

        @app.get("/api/protected")
        async def protected_route(
            user: Dict[str, Any] = Depends(get_current_user)
        ):
            return {"message": f"Hello, {user['email']}"}

    The middleware automatically extracts tokens from:
    - Authorization header: "Bearer <token>"
    - Query parameter: "?token=<token>" (for WebSocket connections)
"""

import logging
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from .google_oauth2 import GoogleOAuth2Handler

logger = logging.getLogger(__name__)


class OAuth2Middleware:
    """Middleware for OAuth2 authentication.

    This class handles the extraction and verification of OAuth2 JWT tokens
    from incoming requests. It supports token extraction from both HTTP
    Authorization headers and query parameters (for WebSocket support).

    The middleware uses GoogleOAuth2Handler to verify tokens and extract
    user information from validated JWT tokens.
    """

    def __init__(self):
        """Initialize middleware with OAuth2 handler.

        Creates a new GoogleOAuth2Handler instance for token verification.
        The handler is initialized with configuration from environment
        variables (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, JWT_SECRET_KEY).

        Raises:
            ImportError: If Google OAuth2 dependencies are not installed
            ValueError: If required environment variables are missing:
                - GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET (both required)
                - JWT_SECRET_KEY (required)
        """
        self.oauth2_handler = GoogleOAuth2Handler()

    async def get_current_user(self, request: Request) -> Dict[str, Any]:
        """Extract and verify user from request.

        Attempts to extract a JWT token from the request using two methods:
        1. Authorization header: Looks for "Bearer <token>" in the
           Authorization header (standard HTTP requests)
        2. Query parameter: Falls back to "token" query parameter
           (for WebSocket connections that cannot use headers)

        Once a token is found, it is verified using the OAuth2 handler.
        If verification succeeds, the decoded token payload is returned.

        Args:
            request: FastAPI request object containing headers and/or
                query parameters with the authentication token.

        Returns:
            Dict[str, Any]: User information dictionary containing:
                - email (str): User's email address (required)
                - name (str, optional): User's full name
                - picture (str, optional): URL to user's profile picture
                - domain (str, optional): Google Workspace domain (hd claim)
                - iat (int): Token issued at timestamp (UTC)
                - exp (int): Token expiration timestamp (UTC)

        Raises:
            HTTPException: If authentication fails:
                - 401 UNAUTHORIZED: No token provided or token is invalid/expired
                - Includes WWW-Authenticate header for proper HTTP auth flow
        """
        # Try to get token from Authorization header (standard HTTP requests)
        authorization = request.headers.get("Authorization")
        token = None

        if authorization and authorization.startswith("Bearer "):
            # Use maxsplit=1 to handle cases where token might contain spaces
            # (though this shouldn't happen with valid tokens)
            parts = authorization.split(" ", 1)
            if len(parts) == 2:
                token = parts[1].strip()
                # Validate that token is not empty after stripping
                if not token:
                    token = None

        # Fallback to query parameter (for WebSocket connections)
        if not token:
            token = request.query_params.get("token")
            if token:
                token = token.strip()
                if not token:
                    token = None

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = self.oauth2_handler.verify_token(token)
            return payload
        except ValueError as e:
            # ValueError is raised for expired or invalid tokens
            logger.warning(f"Token verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            # Catch any other unexpected exceptions from token verification
            logger.error(f"Unexpected error during token verification: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token verification failed",
                headers={"WWW-Authenticate": "Bearer"},
            )


# Global middleware instance (lazy initialization)
# Note: This is not thread-safe, but FastAPI's dependency injection system
# ensures that dependencies are called within the request context, so this
# should be safe for typical FastAPI usage patterns.
_oauth2_middleware: Optional[OAuth2Middleware] = None


def _get_oauth2_middleware() -> OAuth2Middleware:
    """Get or create the OAuth2 middleware instance (lazy initialization).

    Implements a singleton pattern with lazy initialization. The middleware
    instance is created only when first needed, allowing the application to
    start even if OAuth2 credentials are not immediately available.

    If initialization fails (e.g., missing environment variables), an
    HTTPException is raised. This is appropriate since this function is
    only called from the get_current_user dependency, which is expected
    to raise HTTPException on errors.

    Returns:
        OAuth2Middleware: The singleton middleware instance.

    Raises:
        HTTPException: If OAuth2 middleware initialization fails:
            - 503 SERVICE_UNAVAILABLE: OAuth2 credentials are not configured
            - Includes a helpful error message indicating which environment
              variables need to be set
    """
    global _oauth2_middleware
    if _oauth2_middleware is None:
        try:
            _oauth2_middleware = OAuth2Middleware()
        except ValueError as e:
            logger.error(f"Failed to initialize OAuth2 middleware: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OAuth2 authentication is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
            )
        except Exception as e:
            # Catch any other initialization errors (e.g., ImportError)
            logger.error(f"Unexpected error initializing OAuth2 middleware: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OAuth2 authentication is not available. Please check your configuration.",
            )
    return _oauth2_middleware


async def get_current_user(request: Request) -> Dict[str, Any]:
    """Dependency function for FastAPI to get current authenticated user.

    This function is designed to be used as a FastAPI dependency with
    Depends(). It extracts and verifies the OAuth2 JWT token from the
    request and returns the decoded user information.

    The function uses lazy initialization of the OAuth2 middleware,
    so the middleware is only created when first needed. This allows
    the application to start even if OAuth2 credentials are not
    immediately configured.

    Args:
        request: FastAPI request object. The token can be provided via:
            - Authorization header: "Bearer <token>"
            - Query parameter: "?token=<token>" (for WebSocket)

    Returns:
        Dict[str, Any]: User information dictionary containing:
            - email (str): User's email address (required)
            - name (str, optional): User's full name
            - picture (str, optional): URL to user's profile picture
            - domain (str, optional): Google Workspace domain
            - iat (int): Token issued at timestamp
            - exp (int): Token expiration timestamp

    Raises:
        HTTPException: If authentication fails:
            - 401 UNAUTHORIZED: No token provided or token is invalid/expired
            - 503 SERVICE_UNAVAILABLE: OAuth2 is not configured

    Example:
        Using as a FastAPI dependency::

            from fastapi import Depends
            from auth.oauth2_middleware import get_current_user

            @app.get("/api/user/profile")
            async def get_profile(
                user: Dict[str, Any] = Depends(get_current_user)
            ):
                return {
                    "email": user["email"],
                    "name": user.get("name"),
                }

        The dependency will automatically:
        - Extract the token from the request
        - Verify the token signature and expiration
        - Return user information if valid
        - Raise HTTPException if authentication fails
    """
    middleware = _get_oauth2_middleware()
    return await middleware.get_current_user(request)
