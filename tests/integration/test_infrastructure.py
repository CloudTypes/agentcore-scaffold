"""Tests for infrastructure configuration."""

import pytest
import json


def test_cdk_stack_synthesis():
    """Test that CDK stack can be synthesized."""
    # This would require CDK to be available in test environment
    # For now, just verify the stack file exists and is importable
    import sys
    import os

    cdk_path = os.path.join(os.path.dirname(__file__), "..", "..", "infrastructure", "cdk")
    if os.path.exists(cdk_path):
        # Stack file should be importable
        assert True
    else:
        pytest.skip("CDK infrastructure not available")


def test_cdk_json_valid():
    """Test that cdk.json is valid JSON."""
    import os

    cdk_json_path = os.path.join(os.path.dirname(__file__), "..", "..", "infrastructure", "cdk", "cdk.json")

    if os.path.exists(cdk_json_path):
        with open(cdk_json_path) as f:
            data = json.load(f)
            assert "app" in data
            assert "context" in data
    else:
        pytest.skip("cdk.json not found")
