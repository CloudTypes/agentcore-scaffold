#!/usr/bin/env python3
"""
Generate config.js for web client with runtime API endpoints.

This script reads API endpoints from SSM Parameter Store and generates
a config.js file for the web client. Used by CodeBuild during web client deployment.
"""

import os
import sys
import boto3
import json
import argparse


def get_ssm_parameter(ssm_client, parameter_name, default=""):
    """Get SSM parameter value or return default."""
    try:
        response = ssm_client.get_parameter(Name=parameter_name)
        return response["Parameter"]["Value"]
    except ssm_client.exceptions.ParameterNotFound:
        return default
    except Exception as e:
        print(f"Warning: Could not get parameter {parameter_name}: {e}", file=sys.stderr)
        return default


def generate_config(environment="dev", region=None, output_file="config.js"):
    """Generate config.js file from SSM parameters."""
    if not region:
        region = os.getenv("AWS_REGION", "us-west-2")

    ssm_client = boto3.client("ssm", region_name=region)

    # Get API endpoints from SSM
    voice_endpoint = get_ssm_parameter(ssm_client, f"/agentcore/scaffold/{environment}/voice-agent-endpoint")

    orchestrator_endpoint = get_ssm_parameter(ssm_client, f"/agentcore/scaffold/{environment}/orchestrator-endpoint")

    # Derive WebSocket endpoint from voice endpoint
    ws_base = ""
    if voice_endpoint:
        if voice_endpoint.startswith("https://"):
            ws_base = voice_endpoint.replace("https://", "wss://")
        elif voice_endpoint.startswith("http://"):
            ws_base = voice_endpoint.replace("http://", "ws://")
        else:
            ws_base = f"wss://{voice_endpoint}"

    # Generate config.js content
    config_content = f"""// Auto-generated runtime configuration
// Generated for environment: {environment}
// Region: {region}

window.API_BASE = "{voice_endpoint}";
window.ORCHESTRATOR_BASE = "{orchestrator_endpoint}";
window.WS_BASE = "{ws_base}";
"""

    # Write to file
    with open(output_file, "w") as f:
        f.write(config_content)

    print(f"Generated {output_file} with endpoints:")
    print(f"  API_BASE: {voice_endpoint}")
    print(f"  ORCHESTRATOR_BASE: {orchestrator_endpoint}")
    print(f"  WS_BASE: {ws_base}")


def main():
    parser = argparse.ArgumentParser(description="Generate web client config.js from SSM parameters")
    parser.add_argument("--environment", "-e", default="dev", help="Environment name (dev, prod)")
    parser.add_argument("--region", "-r", help="AWS region (default: from AWS_REGION env var)")
    parser.add_argument("--output", "-o", default="config.js", help="Output file path")

    args = parser.parse_args()

    generate_config(environment=args.environment, region=args.region, output_file=args.output)


if __name__ == "__main__":
    main()
