"""CDK stack for AgentCore Runtime deployment."""

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


class AgentCoreRuntimeStack(Stack):
    """Stack for AgentCore Runtime deployment."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        base_stack=None,
        ecr_repo: ecr.IRepository = None,
        agentcore_role: iam.IRole = None,
        **kwargs
    ) -> None:
        """
        Initialize AgentCore Runtime stack.
        
        Args:
            scope: Parent construct
            construct_id: Stack ID
            base_stack: Base stack with ECR repositories and IAM roles
            ecr_repo: ECR repository for Docker images (legacy, use base_stack instead)
            agentcore_role: IAM role for AgentCore Runtime (legacy, use base_stack instead)
        """
        super().__init__(scope, construct_id, **kwargs)

        env_name = self.node.try_get_context("environment") or "dev"
        
        # Get ECR repository from base stack (preferred) or use provided (legacy)
        if base_stack:
            ecr_repos = base_stack.ecr_repos
            if "voice" not in ecr_repos:
                raise ValueError("Voice agent ECR repository not found in base_stack.ecr_repos")
            voice_ecr_repo = ecr_repos["voice"]
            ecr_repo_uri = voice_ecr_repo.repository_uri
            agentcore_role = base_stack.agentcore_role
        elif ecr_repo:
            # Legacy support
            ecr_repo_uri = ecr_repo.repository_uri
        else:
            ecr_repo_uri = self.node.try_get_context("ecr_repo_uri")
            if not ecr_repo_uri:
                raise ValueError("ECR repository URI is required. Provide base_stack, ecr_repo, or set ecr_repo_uri in context.")

        # Get role ARN from parameter or use provided
        role_arn = self.node.try_get_context("agentcore_role_arn")
        if not role_arn and agentcore_role:
            role_arn = agentcore_role.role_arn
        if not role_arn:
            raise ValueError("AgentCore role ARN is required. Provide base_stack, agentcore_role, or set agentcore_role_arn in context.")

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

        # Add urllib3 to Lambda layer (or include in inline code)
        # urllib3 is available in Lambda runtime, but we'll use it directly

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

        # AgentCore Runtime custom resource
        runtime_name = self.node.try_get_context("runtime_name") or f"voice-agent-runtime-{env_name}"
        
        # Get image tag from SSM Parameter Store (updated by CodeBuild)
        # Parameter is created in base stack, reference it here
        image_tag_param = ssm.StringParameter.from_string_parameter_name(
            self,
            "VoiceImageTagParam",
            string_parameter_name=f"/agentcore/voice-agent/{env_name}/voice-image-tag"
        )
        image_tag = image_tag_param.string_value or self.node.try_get_context("image_tag") or "latest"
        
        # Construct full image URI
        if ecr_repo_uri:
            # Remove https:// or http:// if present, extract just the URI
            repo_uri_clean = ecr_repo_uri.replace("https://", "").replace("http://", "")
            image_uri = f"{repo_uri_clean}:{image_tag}"
        else:
            image_uri = ""
        
        runtime = cdk.CustomResource(
            self,
            "AgentCoreRuntime",
            service_token=provider.service_token,
            properties={
                "RuntimeName": runtime_name,
                "ImageUri": image_uri,
                "RoleArn": role_arn,
                "Region": self.region,
            }
        )

        # Store runtime endpoint in SSM (environment-specific)
        ssm.StringParameter(
            self,
            "RuntimeEndpointParam",
            parameter_name=f"/agentcore/voice-agent/{env_name}/voice-agent-endpoint",
            string_value=runtime.get_att_string("Endpoint"),
            description="AgentCore Runtime endpoint URL for voice agent"
        )
        
        # Also store at root level for backward compatibility
        ssm.StringParameter(
            self,
            "RuntimeEndpointParamLegacy",
            parameter_name="/agentcore/voice-agent/runtime-endpoint",
            string_value=runtime.get_att_string("Endpoint"),
            description="AgentCore Runtime endpoint URL (legacy)"
        )

        # Store runtime ID in SSM (environment-specific)
        ssm.StringParameter(
            self,
            "RuntimeIdParam",
            parameter_name=f"/agentcore/voice-agent/{env_name}/voice-agent-runtime-id",
            string_value=runtime.get_att_string("RuntimeId"),
            description="AgentCore Runtime ID for voice agent"
        )
        
        # Also store at root level for backward compatibility
        ssm.StringParameter(
            self,
            "RuntimeIdParamLegacy",
            parameter_name="/agentcore/voice-agent/runtime-id",
            string_value=runtime.get_att_string("RuntimeId"),
            description="AgentCore Runtime ID (legacy)"
        )

        # Outputs
        CfnOutput(
            self,
            "RuntimeEndpoint",
            value=runtime.get_att_string("Endpoint"),
            description="AgentCore Runtime endpoint URL"
        )

        CfnOutput(
            self,
            "RuntimeId",
            value=runtime.get_att_string("RuntimeId"),
            description="AgentCore Runtime ID"
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
    
    try:
        if event['RequestType'] == 'Create':
            response = client.create_runtime(
                runtimeName=runtime_name,
                containerConfiguration={
                    'imageUri': image_uri
                },
                roleArn=role_arn,
                protocolConfiguration='HTTP',
                healthCheckConfiguration={
                    'healthCheckEndpoint': '/ping'
                }
            )
            runtime_id = response['runtimeId']
            endpoint = response.get('endpoint', '')
            
            send(event, context, 'SUCCESS', {
                'RuntimeId': runtime_id,
                'Endpoint': endpoint
            }, physical_resource_id=runtime_id)
            
        elif event['RequestType'] == 'Update':
            runtime_id = event['PhysicalResourceId']
            response = client.update_runtime(
                runtimeId=runtime_id,
                containerConfiguration={
                    'imageUri': image_uri
                }
            )
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

