"""Google OAuth2 authentication handler."""

import os
import json
import logging
import secrets
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import jwt
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class GoogleOAuth2Handler:
    """Handles Google OAuth2 authentication flow."""
    
    # OAuth2 scopes
    SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ]
    
    def __init__(self):
        """Initialize OAuth2 handler with configuration from environment."""
        self.client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/api/auth/callback")
        self.workspace_domain = os.getenv("GOOGLE_WORKSPACE_DOMAIN")
        self.jwt_secret = os.getenv("JWT_SECRET_KEY")
        self.jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.jwt_expiration_minutes = int(os.getenv("JWT_EXPIRATION_MINUTES", "60"))
        
        if not self.client_id or not self.client_secret:
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set")
        
        if not self.jwt_secret:
            raise ValueError("JWT_SECRET_KEY must be set")
    
    def get_authorization_url(self, state: Optional[str] = None) -> tuple[str, str]:
        """
        Generate Google OAuth2 authorization URL.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Tuple of (authorization_url, state)
        """
        if state is None:
            state = secrets.token_urlsafe(32)
        
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri]
                }
            },
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri
        )
        
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=state,
            prompt="consent"
        )
        
        return authorization_url, state
    
    async def handle_callback(self, code: str, state: Optional[str] = None) -> Dict[str, Any]:
        """
        Handle OAuth2 callback and exchange code for tokens.
        
        Args:
            code: Authorization code from Google
            state: State parameter (for CSRF protection)
            
        Returns:
            Dictionary with user info and JWT token
        """
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri]
                }
            },
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri
        )
        
        # Exchange code for tokens
        flow.fetch_token(code=code)
        
        # Get ID token
        credentials = flow.credentials
        id_token_str = credentials.id_token
        
        # Verify ID token
        try:
            idinfo = id_token.verify_oauth2_token(
                id_token_str,
                Request(),
                self.client_id
            )
        except ValueError as e:
            logger.error(f"Invalid ID token: {e}")
            raise ValueError("Invalid ID token")
        
        # Extract user information
        email = idinfo.get("email")
        name = idinfo.get("name")
        picture = idinfo.get("picture")
        hosted_domain = idinfo.get("hd")  # Google Workspace domain
        
        # Verify domain restriction if configured
        if self.workspace_domain and hosted_domain != self.workspace_domain:
            logger.warning(f"Domain mismatch: {hosted_domain} != {self.workspace_domain}")
            raise ValueError(f"Access restricted to {self.workspace_domain} domain")
        
        # Create JWT token
        jwt_token = self._create_jwt_token(
            email=email,
            name=name,
            picture=picture,
            domain=hosted_domain
        )
        
        return {
            "email": email,
            "name": name,
            "picture": picture,
            "domain": hosted_domain,
            "token": jwt_token
        }
    
    def _create_jwt_token(
        self,
        email: str,
        name: Optional[str] = None,
        picture: Optional[str] = None,
        domain: Optional[str] = None
    ) -> str:
        """
        Create JWT token for user session.
        
        Args:
            email: User email (used as actor_id)
            name: User name
            picture: User profile picture URL
            domain: Google Workspace domain
            
        Returns:
            JWT token string
        """
        payload = {
            "email": email,
            "name": name,
            "picture": picture,
            "domain": domain,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(minutes=self.jwt_expiration_minutes)
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token payload
            
        Raises:
            jwt.InvalidTokenError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {e}")

