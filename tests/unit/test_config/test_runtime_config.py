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

