#!/usr/bin/env python3
"""CDK app for AgentCore Voice Agent infrastructure."""

import os
from pathlib import Path
from dotenv import load_dotenv
import aws_cdk as cdk
from agentcore_stack import AgentCoreStack
from agentcore_runtime_stack import AgentCoreRuntimeStack
# Memory stack removed - use scripts/manage_memory.py instead
# from agentcore_memory_stack import AgentCoreMemoryStack

# Load .env file from project root
# CDK app is in infrastructure/cdk/, so go up 3 levels to project root
cdk_dir = Path(__file__).parent
project_root = cdk_dir.parent.parent
env_file = project_root / '.env'
if env_file.exists():
    load_dotenv(env_file)
    print(f"📋 Loaded configuration from: {env_file}")
else:
    print(f"⚠️  No .env file found at {env_file} - using environment variables and defaults")

app = cdk.App()

# Get environment from context or default to dev
env_name = app.node.try_get_context("environment") or "dev"

# Get region with priority:
# 1. CDK context (--context region=...)
# 2. Environment variable (AWS_REGION or AGENTCORE_MEMORY_REGION from .env)
# 3. Default to us-east-1
region = (
    app.node.try_get_context("region") or
    os.getenv("AWS_REGION") or
    os.getenv("AGENTCORE_MEMORY_REGION") or
    "us-east-1"
)

account = app.node.try_get_context("account") or None

print(f"🌍 Using region: {region}")

# Create environment object
env = cdk.Environment(
    account=account,
    region=region
)

# Create base infrastructure stack (ECR, IAM, Secrets, etc.)
base_stack = AgentCoreStack(
    app,
    f"AgentCoreVoiceAgent-Base-{env_name}",
    env=env,
    description=f"AgentCore Voice Agent base infrastructure ({env_name})"
)

# Memory management is now handled via scripts/manage_memory.py
# This allows memory to be created with strategies via the SDK
# See infrastructure/cdk/README.md for instructions

# Create Runtime stack (depends on base stack for ECR and IAM role)
# Note: Runtime stack requires ECR image to be pushed first
runtime_stack = AgentCoreRuntimeStack(
    app,
    f"AgentCoreVoiceAgent-Runtime-{env_name}",
    env=env,
    description=f"AgentCore Runtime deployment ({env_name})",
    ecr_repo=base_stack.ecr_repo,
    agentcore_role=base_stack.agentcore_role,
)

# Add dependencies
runtime_stack.add_dependency(base_stack)

app.synth()

