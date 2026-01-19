"""Runtime configuration loader for local and AgentCore Runtime environments."""

import os
import json
import logging
from typing import Optional, Dict, Any
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class RuntimeConfig:
    """Loads configuration from environment variables, Secrets Manager, or SSM."""

    def __init__(self):
        """Initialize configuration loader."""
        self._secrets_cache: Dict[str, Any] = {}
        self._is_agentcore_runtime = self._detect_runtime()

    def _detect_runtime(self) -> bool:
        """Detect if running in AgentCore Runtime."""
        # AgentCore Runtime typically sets specific environment variables
        # Check for common indicators
        return (
            os.getenv("AGENTCORE_RUNTIME") == "true"
            or os.getenv("AWS_EXECUTION_ENV") is not None
            or os.getenv("_HANDLER") is not None
        )

    def _get_secrets_client(self):
        """Get Secrets Manager client."""
        return boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))

    def _get_ssm_client(self):
        """Get SSM Parameter Store client."""
        return boto3.client("ssm", region_name=os.getenv("AWS_REGION", "us-east-1"))

    def get_secret(self, secret_name: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get secret from Secrets Manager.

        Args:
            secret_name: Name of the secret
            use_cache: Whether to use cached value

        Returns:
            Secret value as dictionary or None
        """
        if use_cache and secret_name in self._secrets_cache:
            return self._secrets_cache[secret_name]

        if not self._is_agentcore_runtime:
            return None

        try:
            client = self._get_secrets_client()
            response = client.get_secret_value(SecretId=secret_name)
            secret_value = json.loads(response["SecretString"])
            self._secrets_cache[secret_name] = secret_value
            return secret_value
        except ClientError as e:
            logger.warning(f"Could not retrieve secret {secret_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving secret {secret_name}: {e}")
            return None

    def get_ssm_parameter(self, parameter_name: str) -> Optional[str]:
        """
        Get parameter from SSM Parameter Store.

        Args:
            parameter_name: Name of the parameter

        Returns:
            Parameter value or None
        """
        if not self._is_agentcore_runtime:
            return None

        try:
            client = self._get_ssm_client()
            response = client.get_parameter(Name=parameter_name, WithDecryption=True)
            return response["Parameter"]["Value"]
        except ClientError as e:
            logger.warning(f"Could not retrieve SSM parameter {parameter_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving SSM parameter {parameter_name}: {e}")
            return None

    def get_config_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get configuration value with fallback chain.

        Fallback order:
        1. Environment variable
        2. Secrets Manager (if in AgentCore Runtime)
        3. SSM Parameter Store (if in AgentCore Runtime)
        4. Default value

        Args:
            key: Configuration key
            default: Default value if not found

        Returns:
            Configuration value or default
        """
        # First try environment variable
        value = os.getenv(key)
        if value:
            return value

        # Try Secrets Manager (for secrets like OAuth credentials)
        if self._is_agentcore_runtime:
            # Try common secret names
            secret_name = f"agentcore/scaffold/{key.lower().replace('_', '-')}"
            secret = self.get_secret(secret_name)
            if secret:
                # If secret is a dict, try to get the key value
                if isinstance(secret, dict):
                    return secret.get(key, secret.get(key.lower()))
                return str(secret)

            # Try SSM Parameter Store
            ssm_name = f"/agentcore/scaffold/{key}"
            ssm_value = self.get_ssm_parameter(ssm_name)
            if ssm_value:
                return ssm_value

        return default

    def get_google_oauth_config(self) -> Dict[str, Optional[str]]:
        """Get Google OAuth2 configuration."""
        # Try to get from Secrets Manager first
        oauth_secret = self.get_secret("agentcore/scaffold/google-oauth2")
        if oauth_secret and isinstance(oauth_secret, dict):
            return {
                "client_id": oauth_secret.get("client_id") or oauth_secret.get("GOOGLE_CLIENT_ID"),
                "client_secret": oauth_secret.get("client_secret") or oauth_secret.get("GOOGLE_CLIENT_SECRET"),
                "redirect_uri": oauth_secret.get("redirect_uri") or oauth_secret.get("GOOGLE_REDIRECT_URI"),
                "workspace_domain": oauth_secret.get("workspace_domain") or oauth_secret.get("GOOGLE_WORKSPACE_DOMAIN"),
            }

        # Fall back to environment variables
        return {
            "client_id": self.get_config_value("GOOGLE_CLIENT_ID"),
            "client_secret": self.get_config_value("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": self.get_config_value("GOOGLE_REDIRECT_URI", "http://localhost:8080/api/auth/callback"),
            "workspace_domain": self.get_config_value("GOOGLE_WORKSPACE_DOMAIN"),
        }

    def get_jwt_config(self) -> Dict[str, Optional[str]]:
        """Get JWT configuration."""
        # Try to get JWT secret from Secrets Manager
        jwt_secret = self.get_secret("agentcore/scaffold/jwt-secret")
        if jwt_secret:
            if isinstance(jwt_secret, dict):
                secret_key = jwt_secret.get("secret_key") or jwt_secret.get("JWT_SECRET_KEY")
            else:
                secret_key = str(jwt_secret)
        else:
            secret_key = self.get_config_value("JWT_SECRET_KEY")

        return {
            "secret_key": secret_key,
            "algorithm": self.get_config_value("JWT_ALGORITHM", "HS256"),
            "expiration_minutes": self.get_config_value("JWT_EXPIRATION_MINUTES", "60"),
        }


# Global config instance
_config = RuntimeConfig()


def get_config() -> RuntimeConfig:
    """Get global configuration instance."""
    return _config
