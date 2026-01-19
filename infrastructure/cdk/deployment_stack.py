"""CDK stack for deployment orchestration and health checks."""

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_sns as sns,
    aws_ssm as ssm,
    CfnOutput,
    Duration,
)
from constructs import Construct
import json


class DeploymentStack(Stack):
    """Stack for orchestrating multi-agent deployments with health checks."""

    def __init__(self, scope: Construct, construct_id: str, base_stack=None, **kwargs) -> None:
        """
        Initialize Deployment stack.

        Args:
            scope: Parent construct
            construct_id: Stack ID
            base_stack: Base stack with infrastructure
        """
        super().__init__(scope, construct_id, **kwargs)

        env_name = self.node.try_get_context("environment") or "dev"

        # SNS Topic for deployment notifications
        deployment_topic = sns.Topic(
            self,
            "DeploymentNotifications",
            topic_name=f"agentcore-deployment-notifications-{env_name}",
            display_name=f"AgentCore Deployment Notifications ({env_name})",
        )

        # Lambda function for health checks
        health_check_function = _lambda.Function(
            self,
            "HealthCheckFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline(self._get_health_check_code()),
            timeout=Duration.minutes(5),
            memory_size=256,
            environment={
                "ENVIRONMENT": env_name,
                "SNS_TOPIC_ARN": deployment_topic.topic_arn,
            },
        )

        # Grant permissions for health checks
        health_check_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "ssm:GetParametersByPath",
                    "bedrock-agentcore:GetRuntime",
                    "bedrock-agentcore:ListRuntimes",
                ],
                resources=["*"],
            )
        )

        deployment_topic.grant_publish(health_check_function)

        # EventBridge rule to trigger health checks after deployments
        # This would be triggered by CodeBuild completion events
        health_check_rule = events.Rule(
            self,
            "HealthCheckRule",
            description="Trigger health checks after agent deployments",
            event_pattern=events.EventPattern(
                source=["aws.codebuild"],
                detail_type=["CodeBuild Build State Change"],
                detail={
                    "project-name": [
                        f"agentcore-orchestrator-build-{env_name}",
                        f"agentcore-vision-build-{env_name}",
                        f"agentcore-document-build-{env_name}",
                        f"agentcore-data-build-{env_name}",
                        f"agentcore-tool-build-{env_name}",
                        f"agentcore-voice-build-{env_name}",
                    ],
                    "build-status": ["SUCCEEDED"],
                },
            ),
        )

        health_check_rule.add_target(targets.LambdaFunction(health_check_function))

        # Store SNS topic ARN in SSM
        ssm.StringParameter(
            self,
            "DeploymentTopicARNParam",
            parameter_name=f"/agentcore/scaffold/{env_name}/deployment-topic-arn",
            string_value=deployment_topic.topic_arn,
            description="SNS topic ARN for deployment notifications",
        )

        # Outputs
        CfnOutput(
            self,
            "DeploymentTopicARN",
            value=deployment_topic.topic_arn,
            description="SNS topic ARN for deployment notifications",
        )

        self.deployment_topic = deployment_topic
        self.health_check_function = health_check_function

    def _get_health_check_code(self) -> str:
        """Get Lambda handler code for health checks."""
        return """
import boto3
import json
import os
import urllib.request
import urllib.error

def handler(event, context):
    ssm = boto3.client('ssm')
    bedrock = boto3.client('bedrock-agentcore')
    sns = boto3.client('sns')
    
    env = os.environ.get('ENVIRONMENT', 'dev')
    topic_arn = os.environ.get('SNS_TOPIC_ARN')
    
    agents = ['orchestrator', 'vision', 'document', 'data', 'tool', 'voice']
    results = {}
    
        for agent_name in agents:
            try:
                # Get endpoint from SSM
                endpoint_param = f"/agentcore/scaffold/{env}/{agent_name}-endpoint"
                if agent_name == 'voice':
                    endpoint_param = f"/agentcore/scaffold/{env}/voice-agent-endpoint"
            
            try:
                endpoint = ssm.get_parameter(Name=endpoint_param)['Parameter']['Value']
            except:
                # Try legacy parameter
                if agent_name == 'voice':
                    endpoint = ssm.get_parameter(Name="/agentcore/scaffold/runtime-endpoint")['Parameter']['Value']
                else:
                    endpoint = ssm.get_parameter(Name=f"/agentcore/multi-agent/{agent_name}-endpoint")['Parameter']['Value']
            
            # Perform health check
            health_url = f"{endpoint}/ping" if agent_name == 'voice' else f"{endpoint}/.well-known/agent-card.json"
            
            try:
                req = urllib.request.Request(health_url)
                response = urllib.request.urlopen(req, timeout=5)
                status_code = response.getcode()
                results[agent_name] = {
                    'status': 'healthy' if status_code == 200 else 'unhealthy',
                    'status_code': status_code,
                    'endpoint': endpoint
                }
            except Exception as e:
                results[agent_name] = {
                    'status': 'unhealthy',
                    'error': str(e),
                    'endpoint': endpoint
                }
        except Exception as e:
            results[agent_name] = {
                'status': 'error',
                'error': str(e)
            }
    
    # Send notification
    healthy_count = sum(1 for r in results.values() if r.get('status') == 'healthy')
    total_count = len(results)
    
    message = f"Health check completed for {env} environment:\\n"
    message += f"Healthy: {healthy_count}/{total_count}\\n\\n"
    for agent, result in results.items():
        status = result.get('status', 'unknown')
        message += f"{agent}: {status}\\n"
        if 'error' in result:
            message += f"  Error: {result['error']}\\n"
    
    if topic_arn:
        sns.publish(
            TopicArn=topic_arn,
            Subject=f"AgentCore Health Check - {env}",
            Message=message
        )
    
    return {
        'statusCode': 200,
        'body': json.dumps(results)
    }
"""
