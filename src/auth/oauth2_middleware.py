"""OAuth2 middleware for FastAPI."""

import logging
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .google_oauth2 import GoogleOAuth2Handler

logger = logging.getLogger(__name__)
security = HTTPBearer()


class OAuth2Middleware:
    """Middleware for OAuth2 authentication."""
    
    def __init__(self):
        """Initialize middleware with OAuth2 handler."""
        self.oauth2_handler = GoogleOAuth2Handler()
    
    async def get_current_user(self, request: Request) -> Dict[str, Any]:
        """
        Extract and verify user from request.
        
        Args:
            request: FastAPI request object
            
        Returns:
            User information dictionary
            
        Raises:
            HTTPException: If authentication fails
        """
        # Try to get token from Authorization header
        authorization = request.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]
        else:
            # Try to get from query parameter (for WebSocket)
            token = request.query_params.get("token")
        
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
            logger.warning(f"Token verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )


# Global middleware instance (lazy initialization)
_oauth2_middleware: Optional[OAuth2Middleware] = None


def _get_oauth2_middleware() -> OAuth2Middleware:
    """
    Get or create the OAuth2 middleware instance (lazy initialization).
    
    Returns:
        OAuth2Middleware instance
        
    Raises:
        ValueError: If Google OAuth2 credentials are not configured
    """
    global _oauth2_middleware
    if _oauth2_middleware is None:
        try:
            _oauth2_middleware = OAuth2Middleware()
        except ValueError as e:
            logger.error(f"Failed to initialize OAuth2 middleware: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OAuth2 authentication is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
            )
    return _oauth2_middleware


async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Dependency function for FastAPI to get current user.
    
    Args:
        request: FastAPI request object
        
    Returns:
        User information dictionary
        
    Raises:
        HTTPException: If authentication fails or OAuth2 is not configured
    """
    middleware = _get_oauth2_middleware()
    return await middleware.get_current_user(request)

