#!/usr/bin/env python3
"""CDK app for AgentCore Voice Agent infrastructure."""

import os
from pathlib import Path
from dotenv import load_dotenv
import aws_cdk as cdk
from agentcore_stack import AgentCoreStack
from agentcore_runtime_stack import AgentCoreRuntimeStack
from multi_agent_stack import MultiAgentStack
from vision_stack import VisionInfrastructureStack
from codebuild_stack import CodeBuildStack
from web_client_stack import WebClientStack
from deployment_stack import DeploymentStack
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

# Create Web Client stack (S3 + CloudFront)
web_client_stack = WebClientStack(
    app,
    f"AgentCoreWebClient-{env_name}",
    env=env,
    description=f"Web client deployment (S3 + CloudFront) ({env_name})"
)

# Create Runtime stack (depends on base stack for ECR and IAM role)
# Note: Runtime stack requires ECR image to be pushed first
runtime_stack = AgentCoreRuntimeStack(
    app,
    f"AgentCoreVoiceAgent-Runtime-{env_name}",
    env=env,
    description=f"AgentCore Runtime deployment ({env_name})",
    base_stack=base_stack,
)

# Add dependencies
runtime_stack.add_dependency(base_stack)
web_client_stack.add_dependency(base_stack)

# Create Multi-Agent stack (for orchestrator + specialist agents)
multi_agent_stack = MultiAgentStack(
    app,
    f"AgentCoreMultiAgent-{env_name}",
    env=env,
    description=f"Multi-agent system with A2A protocol ({env_name})",
    base_stack=base_stack,
)

# Multi-agent stack depends on base stack
multi_agent_stack.add_dependency(base_stack)

# Create Vision Infrastructure stack
vision_stack = VisionInfrastructureStack(
    app,
    f"AgentCoreVision-{env_name}",
    env=env,
    description=f"Infrastructure for AgentCore Vision Agent capabilities ({env_name})"
)

# Create CodeBuild stack (depends on base stack and web client stack)
codebuild_stack = CodeBuildStack(
    app,
    f"AgentCoreCodeBuild-{env_name}",
    env=env,
    description=f"CodeBuild pipelines for automated builds and deployments ({env_name})",
    base_stack=base_stack,
    web_client_stack=web_client_stack,  # Optional, can be None
)

# Add dependencies
codebuild_stack.add_dependency(base_stack)
if web_client_stack:
    codebuild_stack.add_dependency(web_client_stack)

# Create Deployment stack (orchestration and health checks)
deployment_stack = DeploymentStack(
    app,
    f"AgentCoreDeployment-{env_name}",
    env=env,
    description=f"Deployment orchestration and health checks ({env_name})",
    base_stack=base_stack,
)

# Add dependencies
deployment_stack.add_dependency(base_stack)

app.synth()

