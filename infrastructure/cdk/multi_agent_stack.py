"""CDK stack for Multi-Agent System deployment to AgentCore Runtime."""

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_ecr as ecr,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
    custom_resources as cr,
    CfnOutput,
    Duration,
)
from constructs import Construct
import json
import os


class MultiAgentStack(Stack):
    """Stack for deploying multi-agent system to AgentCore Runtime with A2A protocol."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        base_stack=None,
        **kwargs
    ) -> None:
        """
        Initialize Multi-Agent stack.
        
        Args:
            scope: Parent construct
            construct_id: Stack ID
            base_stack: Base stack with ECR repo and IAM roles
        """
        super().__init__(scope, construct_id, **kwargs)

        # Get ECR repository from base stack or context
        if base_stack:
            ecr_repo = base_stack.ecr_repo
            agentcore_role = base_stack.agentcore_role
        else:
            # Try to get from context or create new
            ecr_repo_uri = self.node.try_get_context("ecr_repo_uri")
            if ecr_repo_uri:
                ecr_repo = ecr.Repository.from_repository_attributes(
                    self, "ECRRepo",
                    repository_arn=f"arn:aws:ecr:{self.region}:{self.account}:repository/agentcore-voice-agent",
                    repository_name="agentcore-voice-agent"
                )
            else:
                raise ValueError("ECR repository is required. Provide base_stack or set ecr_repo_uri in context.")
            
            role_arn = self.node.try_get_context("agentcore_role_arn")
            if role_arn:
                agentcore_role = iam.Role.from_role_arn(
                    self, "AgentCoreRole",
                    role_arn=role_arn
                )
            else:
                raise ValueError("AgentCore role is required. Provide base_stack or set agentcore_role_arn in context.")

        # Get memory configuration
        memory_id = os.getenv("AGENTCORE_MEMORY_ID") or self.node.try_get_context("memory_id")
        memory_region = os.getenv("AGENTCORE_MEMORY_REGION") or self.region

        # Lambda function for AgentCore Runtime custom resource
        runtime_handler = _lambda.Function(
            self,
            "AgentCoreRuntimeHandler",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline(self._get_runtime_handler_code()),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "REGION": self.region,
            }
        )

        # Grant permissions to Lambda
        runtime_handler.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:CreateRuntime",
                    "bedrock-agentcore:GetRuntime",
                    "bedrock-agentcore:UpdateRuntime",
                    "bedrock-agentcore:DeleteRuntime",
                    "bedrock-agentcore:ListRuntimes",
                    "bedrock-agentcore:InvokeAgent",
                ],
                resources=["*"]
            )
        )

        # Custom resource provider
        provider = cr.Provider(
            self,
            "AgentCoreRuntimeProvider",
            on_event_handler=runtime_handler,
        )

        # Deploy specialist agents first
        agents = ["vision", "document", "data", "tool"]
        agent_runtimes = {}
        agent_endpoints = {}

        for agent_name in agents:
            runtime_name = f"{agent_name}-agent-{self.node.try_get_context('environment') or 'dev'}"
            image_tag = self.node.try_get_context("image_tag") or "latest"
            
            # Construct full image URI
            repo_uri_clean = ecr_repo.repository_uri.replace("https://", "").replace("http://", "")
            image_uri = f"{repo_uri_clean}:{agent_name}-{image_tag}"
            
            # Create IAM role for this agent
            agent_role = iam.Role(
                self,
                f"{agent_name.capitalize()}AgentRole",
                assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
                description=f"IAM role for {agent_name} agent",
            )
            
            # Grant Bedrock permissions
            agent_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream",
                    ],
                    resources=["*"]
                )
            )
            
            # Grant Memory permissions
            agent_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "bedrock-agentcore:CreateMemory",
                        "bedrock-agentcore:GetMemory",
                        "bedrock-agentcore:CreateEvent",
                        "bedrock-agentcore:RetrieveMemoryRecords",
                        "bedrock-agentcore:ListMemoryRecords"
                    ],
                    resources=["*"]
                )
            )

            # Create runtime for this agent
            runtime = cdk.CustomResource(
                self,
                f"{agent_name.capitalize()}AgentRuntime",
                service_token=provider.service_token,
                properties={
                    "RuntimeName": runtime_name,
                    "ImageUri": image_uri,
                    "RoleArn": agent_role.role_arn,
                    "Region": self.region,
                    "Protocol": "A2A",  # Use A2A protocol
                    "Port": "9000",
                }
            )

            agent_runtimes[agent_name] = runtime
            agent_endpoints[agent_name] = runtime.get_att_string("Endpoint")

            # Store endpoint in SSM
            ssm.StringParameter(
                self,
                f"{agent_name.capitalize()}AgentEndpointParam",
                parameter_name=f"/agentcore/multi-agent/{agent_name}-endpoint",
                string_value=runtime.get_att_string("Endpoint"),
                description=f"{agent_name.capitalize()} agent endpoint URL"
            )

            # Output
            CfnOutput(
                self,
                f"{agent_name.capitalize()}AgentEndpoint",
                value=runtime.get_att_string("Endpoint"),
                description=f"{agent_name.capitalize()} agent endpoint URL"
            )

        # Deploy orchestrator (depends on specialist agents)
        orchestrator_runtime_name = f"orchestrator-agent-{self.node.try_get_context('environment') or 'dev'}"
        image_tag = self.node.try_get_context("image_tag") or "latest"
        repo_uri_clean = ecr_repo.repository_uri.replace("https://", "").replace("http://", "")
        orchestrator_image_uri = f"{repo_uri_clean}:orchestrator-{image_tag}"

        # Create IAM role for orchestrator (can invoke other agents)
        orchestrator_role = iam.Role(
            self,
            "OrchestratorAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="IAM role for orchestrator agent",
        )

        # Grant Bedrock permissions
        orchestrator_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"]
            )
        )

        # Grant AgentCore permissions (to invoke other agents)
        orchestrator_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:InvokeAgent",
                ],
                resources=["*"]
            )
        )

        # Grant Memory permissions
        orchestrator_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:CreateMemory",
                    "bedrock-agentcore:GetMemory",
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:ListMemoryRecords"
                ],
                resources=["*"]
            )
        )

        # Create orchestrator runtime
        orchestrator_runtime = cdk.CustomResource(
            self,
            "OrchestratorAgentRuntime",
            service_token=provider.service_token,
            properties={
                "RuntimeName": orchestrator_runtime_name,
                "ImageUri": orchestrator_image_uri,
                "RoleArn": orchestrator_role.role_arn,
                "Region": self.region,
                "Protocol": "A2A",  # Use A2A protocol
                "Port": "9000",
                "Environment": json.dumps({
                    "VISION_AGENT_URL": agent_endpoints["vision"],
                    "DOCUMENT_AGENT_URL": agent_endpoints["document"],
                    "DATA_AGENT_URL": agent_endpoints["data"],
                    "TOOL_AGENT_URL": agent_endpoints["tool"],
                    "AGENTCORE_MEMORY_ID": memory_id or "",
                    "AGENTCORE_MEMORY_REGION": memory_region,
                    "AWS_REGION": self.region,
                    "ENVIRONMENT": "production",
                })
            }
        )

        # Add dependencies
        for agent_name, runtime in agent_runtimes.items():
            orchestrator_runtime.node.add_dependency(runtime)

        # Store orchestrator endpoint in SSM
        ssm.StringParameter(
            self,
            "OrchestratorAgentEndpointParam",
            parameter_name="/agentcore/multi-agent/orchestrator-endpoint",
            string_value=orchestrator_runtime.get_att_string("Endpoint"),
            description="Orchestrator agent endpoint URL"
        )

        # Output
        CfnOutput(
            self,
            "OrchestratorAgentEndpoint",
            value=orchestrator_runtime.get_att_string("Endpoint"),
            description="Orchestrator agent endpoint URL"
        )

    def _get_runtime_handler_code(self) -> str:
        """Get Lambda handler code for AgentCore Runtime custom resource."""
        return """
import boto3
import json
import urllib3
http = urllib3.PoolManager()

def send(event, context, response_status, response_data, physical_resource_id=None, reason=None):
    response_url = event['ResponseURL']
    response_body = {
        'Status': response_status,
        'Reason': reason or f"See the details in CloudWatch Log Stream: {context.log_stream_name}",
        'PhysicalResourceId': physical_resource_id or context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': response_data
    }
    json_response_body = json.dumps(response_body)
    http.request('PUT', response_url, body=json_response_body.encode('utf-8'), headers={'Content-Type': ''})

def handler(event, context):
    client = boto3.client('bedrock-agentcore', region_name=event['ResourceProperties']['Region'])
    runtime_name = event['ResourceProperties']['RuntimeName']
    image_uri = event['ResourceProperties']['ImageUri']
    role_arn = event['ResourceProperties']['RoleArn']
    protocol = event['ResourceProperties'].get('Protocol', 'HTTP')
    port = event['ResourceProperties'].get('Port', '8080')
    environment = json.loads(event['ResourceProperties'].get('Environment', '{}'))
    
    try:
        if event['RequestType'] == 'Create':
            # Create runtime with A2A protocol
            create_params = {
                'runtimeName': runtime_name,
                'containerConfiguration': {
                    'imageUri': image_uri,
                    'port': int(port)
                },
                'roleArn': role_arn,
                'protocolConfiguration': protocol,
                'healthCheckConfiguration': {
                    'healthCheckEndpoint': '/.well-known/agent-card.json'
                }
            }
            
            # Add environment variables if provided
            if environment:
                create_params['containerConfiguration']['environment'] = environment
            
            response = client.create_runtime(**create_params)
            runtime_id = response['runtimeId']
            endpoint = response.get('endpoint', '')
            
            send(event, context, 'SUCCESS', {
                'RuntimeId': runtime_id,
                'Endpoint': endpoint
            }, physical_resource_id=runtime_id)
            
        elif event['RequestType'] == 'Update':
            runtime_id = event['PhysicalResourceId']
            update_params = {
                'runtimeId': runtime_id,
                'containerConfiguration': {
                    'imageUri': image_uri,
                    'port': int(port)
                }
            }
            
            # Add environment variables if provided
            if environment:
                update_params['containerConfiguration']['environment'] = environment
            
            response = client.update_runtime(**update_params)
            endpoint = response.get('endpoint', '')
            
            send(event, context, 'SUCCESS', {
                'RuntimeId': runtime_id,
                'Endpoint': endpoint
            }, physical_resource_id=runtime_id)
            
        elif event['RequestType'] == 'Delete':
            runtime_id = event['PhysicalResourceId']
            try:
                client.delete_runtime(runtimeId=runtime_id)
            except Exception as e:
                print(f"Error deleting runtime: {e}")
            
            send(event, context, 'SUCCESS', {}, physical_resource_id=runtime_id)
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        send(event, context, 'FAILED', {}, reason=str(e))
"""

