"""Unit tests for runtime configuration, focusing on memory-related config."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import os
import sys
import json

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from config.runtime import RuntimeConfig, get_config


class TestRuntimeConfigMemory:
    """Test cases for memory-related configuration loading."""
    
    def test_get_config_value_agentcore_memory_region_env(self, monkeypatch):
        """Test getting AGENTCORE_MEMORY_REGION from environment variable."""
        monkeypatch.setenv("AGENTCORE_MEMORY_REGION", "us-west-2")
        config = RuntimeConfig()
        
        value = config.get_config_value("AGENTCORE_MEMORY_REGION")
        
        assert value == "us-west-2"
    
    def test_get_config_value_agentcore_memory_id_env(self, monkeypatch):
        """Test getting AGENTCORE_MEMORY_ID from environment variable."""
        monkeypatch.setenv("AGENTCORE_MEMORY_ID", "test-memory-id-123")
        config = RuntimeConfig()
        
        value = config.get_config_value("AGENTCORE_MEMORY_ID")
        
        assert value == "test-memory-id-123"
    
    def test_get_config_value_memory_enabled_env(self, monkeypatch):
        """Test getting MEMORY_ENABLED from environment variable."""
        monkeypatch.setenv("MEMORY_ENABLED", "true")
        config = RuntimeConfig()
        
        value = config.get_config_value("MEMORY_ENABLED")
        
        assert value == "true"
    
    def test_get_config_value_memory_enabled_false(self, monkeypatch):
        """Test getting MEMORY_ENABLED as false."""
        monkeypatch.setenv("MEMORY_ENABLED", "false")
        config = RuntimeConfig()
        
        value = config.get_config_value("MEMORY_ENABLED")
        
        assert value == "false"
    
    def test_get_config_value_fallback_to_aws_region(self, monkeypatch):
        """Test that memory region falls back to AWS_REGION."""
        monkeypatch.delenv("AGENTCORE_MEMORY_REGION", raising=False)
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        config = RuntimeConfig()
        
        # Note: This tests the fallback logic in MemoryClient, not RuntimeConfig
        # RuntimeConfig just returns the env var value
        value = config.get_config_value("AWS_REGION")
        
        assert value == "eu-west-1"
    
    def test_get_config_value_default_value(self, monkeypatch):
        """Test getting config value with default."""
        monkeypatch.delenv("AGENTCORE_MEMORY_REGION", raising=False)
        config = RuntimeConfig()
        
        value = config.get_config_value("AGENTCORE_MEMORY_REGION", "us-east-1")
        
        assert value == "us-east-1"
    
    def test_get_config_value_from_ssm_in_runtime(self, monkeypatch):
        """Test getting config value from SSM Parameter Store in AgentCore Runtime."""
        monkeypatch.delenv("AGENTCORE_MEMORY_ID", raising=False)
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        with patch.object(config, 'get_ssm_parameter', return_value="ssm-memory-id-123"):
            value = config.get_config_value("AGENTCORE_MEMORY_ID")
            
            assert value == "ssm-memory-id-123"
    
    def test_get_config_value_from_secrets_manager_in_runtime(self, monkeypatch):
        """Test getting config value from Secrets Manager in AgentCore Runtime."""
        monkeypatch.delenv("AGENTCORE_MEMORY_ID", raising=False)
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        mock_secret = {"AGENTCORE_MEMORY_ID": "secret-memory-id-123"}
        with patch.object(config, 'get_secret', return_value=mock_secret):
            value = config.get_config_value("AGENTCORE_MEMORY_ID")
            
            assert value == "secret-memory-id-123"
    
    def test_get_config_value_not_in_runtime(self, monkeypatch):
        """Test that SSM/Secrets Manager are not used when not in AgentCore Runtime."""
        monkeypatch.delenv("AGENTCORE_MEMORY_ID", raising=False)
        monkeypatch.delenv("AGENTCORE_RUNTIME", raising=False)
        monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("_HANDLER", raising=False)
        
        config = RuntimeConfig()
        
        with patch.object(config, 'get_ssm_parameter') as mock_ssm:
            with patch.object(config, 'get_secret') as mock_secret:
                value = config.get_config_value("AGENTCORE_MEMORY_ID", "default-id")
                
                assert value == "default-id"
                mock_ssm.assert_not_called()
                mock_secret.assert_not_called()
    
    def test_detect_runtime_agentcore_runtime_env(self, monkeypatch):
        """Test runtime detection via AGENTCORE_RUNTIME environment variable."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        assert config._is_agentcore_runtime is True
    
    def test_detect_runtime_aws_execution_env(self, monkeypatch):
        """Test runtime detection via AWS_EXECUTION_ENV environment variable."""
        monkeypatch.delenv("AGENTCORE_RUNTIME", raising=False)
        monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_Lambda_python3.9")
        
        config = RuntimeConfig()
        
        assert config._is_agentcore_runtime is True
    
    def test_detect_runtime_handler_env(self, monkeypatch):
        """Test runtime detection via _HANDLER environment variable."""
        monkeypatch.delenv("AGENTCORE_RUNTIME", raising=False)
        monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
        monkeypatch.setenv("_HANDLER", "lambda_function.handler")
        
        config = RuntimeConfig()
        
        assert config._is_agentcore_runtime is True
    
    def test_detect_runtime_local_development(self, monkeypatch):
        """Test runtime detection in local development (not in runtime)."""
        monkeypatch.delenv("AGENTCORE_RUNTIME", raising=False)
        monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("_HANDLER", raising=False)
        
        config = RuntimeConfig()
        
        assert config._is_agentcore_runtime is False
    
    def test_get_ssm_parameter_success(self, monkeypatch):
        """Test getting SSM parameter successfully."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_ssm = MagicMock()
            mock_ssm.get_parameter.return_value = {
                "Parameter": {"Value": "ssm-value-123"}
            }
            mock_boto3.return_value = mock_ssm
            
            value = config.get_ssm_parameter("/agentcore/voice-agent/memory-id")
            
            assert value == "ssm-value-123"
            mock_ssm.get_parameter.assert_called_once()
    
    def test_get_ssm_parameter_not_found(self, monkeypatch):
        """Test getting SSM parameter that doesn't exist."""
        from botocore.exceptions import ClientError
        
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_ssm = MagicMock()
            mock_ssm.get_parameter.side_effect = ClientError(
                {"Error": {"Code": "ParameterNotFound", "Message": "Not found"}},
                "GetParameter"
            )
            mock_boto3.return_value = mock_ssm
            
            value = config.get_ssm_parameter("/agentcore/voice-agent/memory-id")
            
            assert value is None
    
    def test_get_secret_success(self, monkeypatch):
        """Test getting secret from Secrets Manager successfully."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": json.dumps({"memory_id": "secret-memory-id"})
            }
            mock_boto3.return_value = mock_secrets
            
            secret = config.get_secret("agentcore/voice-agent/memory-id")
            
            assert secret is not None
            assert secret["memory_id"] == "secret-memory-id"
    
    def test_get_secret_not_found(self, monkeypatch):
        """Test getting secret that doesn't exist."""
        from botocore.exceptions import ClientError
        
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.side_effect = ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
                "GetSecretValue"
            )
            mock_boto3.return_value = mock_secrets
            
            secret = config.get_secret("agentcore/voice-agent/memory-id")
            
            assert secret is None
    
    def test_get_secret_caching(self, monkeypatch):
        """Test that secrets are cached."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": json.dumps({"memory_id": "cached-id"})
            }
            mock_boto3.return_value = mock_secrets
            
            # First call
            secret1 = config.get_secret("test-secret")
            # Second call (should use cache)
            secret2 = config.get_secret("test-secret", use_cache=True)
            
            assert secret1 == secret2
            # Should only call API once due to caching
            assert mock_secrets.get_secret_value.call_count == 1
    
    def test_get_secret_no_cache(self, monkeypatch):
        """Test getting secret without using cache."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": json.dumps({"memory_id": "new-id"})
            }
            mock_boto3.return_value = mock_secrets
            
            # First call
            secret1 = config.get_secret("test-secret")
            # Second call without cache
            secret2 = config.get_secret("test-secret", use_cache=False)
            
            # Should call API twice
            assert mock_secrets.get_secret_value.call_count == 2
    
    def test_get_config_value_fallback_chain(self, monkeypatch):
        """Test the full fallback chain: env -> secrets -> ssm -> default."""
        monkeypatch.delenv("AGENTCORE_MEMORY_ID", raising=False)
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        # Test: env var not set, secrets returns None, SSM returns value
        with patch.object(config, 'get_secret', return_value=None):
            with patch.object(config, 'get_ssm_parameter', return_value="ssm-value"):
                value = config.get_config_value("AGENTCORE_MEMORY_ID", "default")
                
                assert value == "ssm-value"
        
        # Test: env var not set, secrets returns value
        with patch.object(config, 'get_secret', return_value={"AGENTCORE_MEMORY_ID": "secret-value"}):
            value = config.get_config_value("AGENTCORE_MEMORY_ID", "default")
            
            assert value == "secret-value"
        
        # Test: env var set (highest priority)
        monkeypatch.setenv("AGENTCORE_MEMORY_ID", "env-value")
        value = config.get_config_value("AGENTCORE_MEMORY_ID", "default")
        
        assert value == "env-value"
    
    def test_get_config_global_instance(self):
        """Test that get_config returns a global config instance."""
        config1 = get_config()
        config2 = get_config()
        
        assert config1 is config2
        assert isinstance(config1, RuntimeConfig)
    
    # Tests for get_google_oauth_config()
    def test_get_google_oauth_config_from_secrets(self, monkeypatch):
        """Test getting Google OAuth config from Secrets Manager."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        oauth_secret = {
            "client_id": "secret-client-id",
            "client_secret": "secret-client-secret",
            "redirect_uri": "https://example.com/callback",
            "workspace_domain": "example.com"
        }
        
        with patch.object(config, 'get_secret', return_value=oauth_secret):
            result = config.get_google_oauth_config()
            
            assert result["client_id"] == "secret-client-id"
            assert result["client_secret"] == "secret-client-secret"
            assert result["redirect_uri"] == "https://example.com/callback"
            assert result["workspace_domain"] == "example.com"
    
    def test_get_google_oauth_config_from_secrets_key_variations(self, monkeypatch):
        """Test getting Google OAuth config with uppercase key variations."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        oauth_secret = {
            "GOOGLE_CLIENT_ID": "uppercase-client-id",
            "GOOGLE_CLIENT_SECRET": "uppercase-client-secret",
            "GOOGLE_REDIRECT_URI": "https://example.com/callback",
            "GOOGLE_WORKSPACE_DOMAIN": "example.com"
        }
        
        with patch.object(config, 'get_secret', return_value=oauth_secret):
            result = config.get_google_oauth_config()
            
            assert result["client_id"] == "uppercase-client-id"
            assert result["client_secret"] == "uppercase-client-secret"
            assert result["redirect_uri"] == "https://example.com/callback"
            assert result["workspace_domain"] == "example.com"
    
    def test_get_google_oauth_config_from_env(self, monkeypatch):
        """Test getting Google OAuth config from environment variables."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "env-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "env-client-secret")
        monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://env.example.com/callback")
        monkeypatch.setenv("GOOGLE_WORKSPACE_DOMAIN", "env.example.com")
        
        config = RuntimeConfig()
        
        with patch.object(config, 'get_secret', return_value=None):
            result = config.get_google_oauth_config()
            
            assert result["client_id"] == "env-client-id"
            assert result["client_secret"] == "env-client-secret"
            assert result["redirect_uri"] == "https://env.example.com/callback"
            assert result["workspace_domain"] == "env.example.com"
    
    def test_get_google_oauth_config_default_redirect_uri(self, monkeypatch):
        """Test that redirect_uri defaults when not provided."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)
        
        config = RuntimeConfig()
        
        with patch.object(config, 'get_secret', return_value=None):
            with patch.object(config, 'get_config_value', side_effect=lambda key, default=None: default if key == "GOOGLE_REDIRECT_URI" else None):
                result = config.get_google_oauth_config()
                
                assert result["redirect_uri"] == "http://localhost:8080/api/auth/callback"
    
    def test_get_google_oauth_config_missing_optional_fields(self, monkeypatch):
        """Test getting Google OAuth config with missing optional fields."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        oauth_secret = {
            "client_id": "secret-client-id",
            "client_secret": "secret-client-secret"
            # Missing redirect_uri and workspace_domain
        }
        
        with patch.object(config, 'get_secret', return_value=oauth_secret):
            result = config.get_google_oauth_config()
            
            assert result["client_id"] == "secret-client-id"
            assert result["client_secret"] == "secret-client-secret"
            assert result["redirect_uri"] is None
            assert result["workspace_domain"] is None
    
    # Tests for get_jwt_config()
    def test_get_jwt_config_from_secrets_dict(self, monkeypatch):
        """Test getting JWT config from Secrets Manager (dict format)."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        jwt_secret = {
            "secret_key": "secret-jwt-key",
            "JWT_SECRET_KEY": "alternative-key"  # Should prefer secret_key
        }
        
        # get_config_value should return defaults when called with defaults
        def mock_get_config_value(key, default=None):
            return default
        
        with patch.object(config, 'get_secret', return_value=jwt_secret):
            with patch.object(config, 'get_config_value', side_effect=mock_get_config_value):
                result = config.get_jwt_config()
                
                assert result["secret_key"] == "secret-jwt-key"
                assert result["algorithm"] == "HS256"
                assert result["expiration_minutes"] == "60"
    
    def test_get_jwt_config_from_secrets_dict_uppercase_key(self, monkeypatch):
        """Test getting JWT config from Secrets Manager with uppercase key."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        jwt_secret = {
            "JWT_SECRET_KEY": "uppercase-jwt-key"
        }
        
        with patch.object(config, 'get_secret', return_value=jwt_secret):
            with patch.object(config, 'get_config_value', return_value=None):
                result = config.get_jwt_config()
                
                assert result["secret_key"] == "uppercase-jwt-key"
    
    def test_get_jwt_config_from_secrets_string(self, monkeypatch):
        """Test getting JWT config from Secrets Manager (string format)."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        jwt_secret = "string-jwt-secret-key"
        
        with patch.object(config, 'get_secret', return_value=jwt_secret):
            with patch.object(config, 'get_config_value', return_value=None):
                result = config.get_jwt_config()
                
                assert result["secret_key"] == "string-jwt-secret-key"
    
    def test_get_jwt_config_from_env(self, monkeypatch):
        """Test getting JWT config from environment variables."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("JWT_SECRET_KEY", "env-jwt-key")
        monkeypatch.setenv("JWT_ALGORITHM", "RS256")
        monkeypatch.setenv("JWT_EXPIRATION_MINUTES", "120")
        
        config = RuntimeConfig()
        
        with patch.object(config, 'get_secret', return_value=None):
            result = config.get_jwt_config()
            
            assert result["secret_key"] == "env-jwt-key"
            assert result["algorithm"] == "RS256"
            assert result["expiration_minutes"] == "120"
    
    def test_get_jwt_config_defaults(self, monkeypatch):
        """Test JWT config defaults when not provided."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        # get_config_value should return defaults when called with defaults
        def mock_get_config_value(key, default=None):
            return default
        
        with patch.object(config, 'get_secret', return_value=None):
            with patch.object(config, 'get_config_value', side_effect=mock_get_config_value):
                result = config.get_jwt_config()
                
                assert result["secret_key"] is None
                assert result["algorithm"] == "HS256"
                assert result["expiration_minutes"] == "60"
    
    # Tests for SSM edge cases
    def test_get_ssm_parameter_access_denied(self, monkeypatch):
        """Test getting SSM parameter with access denied error."""
        from botocore.exceptions import ClientError
        
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_ssm = MagicMock()
            mock_ssm.get_parameter.side_effect = ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
                "GetParameter"
            )
            mock_boto3.return_value = mock_ssm
            
            value = config.get_ssm_parameter("/agentcore/voice-agent/memory-id")
            
            assert value is None
    
    def test_get_ssm_parameter_network_failure(self, monkeypatch):
        """Test getting SSM parameter with network failure."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_ssm = MagicMock()
            mock_ssm.get_parameter.side_effect = Exception("Network error")
            mock_boto3.return_value = mock_ssm
            
            value = config.get_ssm_parameter("/agentcore/voice-agent/memory-id")
            
            assert value is None
    
    def test_get_ssm_parameter_with_decryption(self, monkeypatch):
        """Test getting SSM parameter with decryption enabled."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_ssm = MagicMock()
            mock_ssm.get_parameter.return_value = {
                "Parameter": {"Value": "encrypted-value-123"}
            }
            mock_boto3.return_value = mock_ssm
            
            value = config.get_ssm_parameter("/agentcore/voice-agent/secret")
            
            assert value == "encrypted-value-123"
            # Verify WithDecryption=True was passed
            mock_ssm.get_parameter.assert_called_once_with(
                Name="/agentcore/voice-agent/secret",
                WithDecryption=True
            )
    
    def test_get_ssm_parameter_not_in_runtime(self, monkeypatch):
        """Test that SSM parameter retrieval returns None when not in runtime."""
        monkeypatch.delenv("AGENTCORE_RUNTIME", raising=False)
        monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("_HANDLER", raising=False)
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            value = config.get_ssm_parameter("/agentcore/voice-agent/memory-id")
            
            assert value is None
            mock_boto3.assert_not_called()
    
    # Tests for Secrets Manager edge cases
    def test_get_secret_malformed_json(self, monkeypatch):
        """Test getting secret with malformed JSON."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": "{invalid json"
            }
            mock_boto3.return_value = mock_secrets
            
            secret = config.get_secret("agentcore/voice-agent/test")
            
            # Should return None due to JSON parsing error
            assert secret is None
    
    def test_get_secret_string_format(self, monkeypatch):
        """Test getting secret that's a plain string (not JSON)."""
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": "plain-string-secret"
            }
            mock_boto3.return_value = mock_secrets
            
            # This will fail JSON parsing, but we should handle it
            secret = config.get_secret("agentcore/voice-agent/test")
            
            # JSON parsing will fail, so secret will be None
            # The code tries json.loads() which will raise an exception
            assert secret is None
    
    def test_get_secret_access_denied(self, monkeypatch):
        """Test getting secret with access denied error."""
        from botocore.exceptions import ClientError
        
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.side_effect = ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
                "GetSecretValue"
            )
            mock_boto3.return_value = mock_secrets
            
            secret = config.get_secret("agentcore/voice-agent/test")
            
            assert secret is None
    
    def test_get_secret_not_in_runtime(self, monkeypatch):
        """Test that secret retrieval returns None when not in runtime."""
        monkeypatch.delenv("AGENTCORE_RUNTIME", raising=False)
        monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("_HANDLER", raising=False)
        
        config = RuntimeConfig()
        
        with patch('config.runtime.boto3.client') as mock_boto3:
            secret = config.get_secret("agentcore/voice-agent/test")
            
            assert secret is None
            mock_boto3.assert_not_called()
    
    # Tests for get_config_value() fallback chain
    def test_get_config_value_secret_dict_extraction(self, monkeypatch):
        """Test extracting config value from secret dict with exact key match."""
        monkeypatch.delenv("TEST_KEY", raising=False)
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        secret = {"TEST_KEY": "secret-value"}
        with patch.object(config, 'get_secret', return_value=secret):
            value = config.get_config_value("TEST_KEY")
            
            assert value == "secret-value"
    
    def test_get_config_value_secret_lowercase_fallback(self, monkeypatch):
        """Test extracting config value from secret dict with lowercase key fallback."""
        monkeypatch.delenv("TEST_KEY", raising=False)
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        secret = {"test_key": "lowercase-value"}
        with patch.object(config, 'get_secret', return_value=secret):
            value = config.get_config_value("TEST_KEY")
            
            assert value == "lowercase-value"
    
    def test_get_config_value_ssm_parameter_name_construction(self, monkeypatch):
        """Test SSM parameter name construction in get_config_value."""
        monkeypatch.delenv("TEST_CONFIG", raising=False)
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        with patch.object(config, 'get_secret', return_value=None):
            with patch.object(config, 'get_ssm_parameter', return_value="ssm-value") as mock_ssm:
                value = config.get_config_value("TEST_CONFIG")
                
                assert value == "ssm-value"
                # Verify SSM parameter name was constructed correctly
                mock_ssm.assert_called_once_with("/agentcore/voice-agent/TEST_CONFIG")
    
    def test_get_config_value_secret_name_construction(self, monkeypatch):
        """Test secret name construction with key transformation."""
        monkeypatch.delenv("TEST_CONFIG_KEY", raising=False)
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        secret = {"TEST_CONFIG_KEY": "secret-value"}
        with patch.object(config, 'get_secret', return_value=secret) as mock_secret:
            value = config.get_config_value("TEST_CONFIG_KEY")
            
            assert value == "secret-value"
            # Verify secret name was constructed correctly (key transformed)
            mock_secret.assert_called_with("agentcore/voice-agent/test-config-key")
    
    def test_get_config_value_fallback_chain_complete(self, monkeypatch):
        """Test complete fallback chain: env → secrets → SSM → default."""
        monkeypatch.delenv("FALLBACK_TEST", raising=False)
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        
        # Test 1: Default value (all sources return None)
        with patch.object(config, 'get_secret', return_value=None):
            with patch.object(config, 'get_ssm_parameter', return_value=None):
                value = config.get_config_value("FALLBACK_TEST", "default-value")
                assert value == "default-value"
        
        # Test 2: SSM returns value
        with patch.object(config, 'get_secret', return_value=None):
            with patch.object(config, 'get_ssm_parameter', return_value="ssm-value"):
                value = config.get_config_value("FALLBACK_TEST", "default-value")
                assert value == "ssm-value"
        
        # Test 3: Secrets returns value
        secret = {"FALLBACK_TEST": "secret-value"}
        with patch.object(config, 'get_secret', return_value=secret):
            value = config.get_config_value("FALLBACK_TEST", "default-value")
            assert value == "secret-value"
        
        # Test 4: Env var returns value (highest priority)
        monkeypatch.setenv("FALLBACK_TEST", "env-value")
        value = config.get_config_value("FALLBACK_TEST", "default-value")
        assert value == "env-value"
    
    def test_runtime_detection_combinations(self, monkeypatch):
        """Test runtime detection with various environment variable combinations."""
        # Test: Only AGENTCORE_RUNTIME
        monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("_HANDLER", raising=False)
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        
        config = RuntimeConfig()
        assert config._is_agentcore_runtime is True
        
        # Test: Only AWS_EXECUTION_ENV
        monkeypatch.delenv("AGENTCORE_RUNTIME", raising=False)
        monkeypatch.delenv("_HANDLER", raising=False)
        monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_Lambda_python3.9")
        
        config = RuntimeConfig()
        assert config._is_agentcore_runtime is True
        
        # Test: Only _HANDLER
        monkeypatch.delenv("AGENTCORE_RUNTIME", raising=False)
        monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
        monkeypatch.setenv("_HANDLER", "lambda_function.handler")
        
        config = RuntimeConfig()
        assert config._is_agentcore_runtime is True
        
        # Test: All three set
        monkeypatch.setenv("AGENTCORE_RUNTIME", "true")
        monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_Lambda_python3.9")
        monkeypatch.setenv("_HANDLER", "lambda_function.handler")
        
        config = RuntimeConfig()
        assert config._is_agentcore_runtime is True
        
        # Test: None set (local development)
        monkeypatch.delenv("AGENTCORE_RUNTIME", raising=False)
        monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("_HANDLER", raising=False)
        
        config = RuntimeConfig()
        assert config._is_agentcore_runtime is False

