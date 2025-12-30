"""CDK stack for AgentCore Runtime deployment."""

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
    aws_logs as logs,
    CfnOutput,
)
from constructs import Construct


class AgentCoreStack(Stack):
    """Stack for AgentCore Voice Agent infrastructure."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ECR Repository for Docker images
        ecr_repo = ecr.Repository(
            self,
            "VoiceAgentECRRepo",
            repository_name="agentcore-voice-agent",
            image_scan_on_push=True,
            lifecycle_rules=[
                ecr.LifecycleRule(
                    rule_priority=1,
                    description="Keep last 10 images",
                    max_image_count=10
                )
            ]
        )

        # IAM Role for AgentCore Runtime
        agentcore_role = iam.Role(
            self,
            "AgentCoreRuntimeRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Role for AgentCore Runtime to access Bedrock, Memory, and Secrets",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )

        # Bedrock permissions
        agentcore_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=["*"]
            )
        )

        # AgentCore Memory permissions
        agentcore_role.add_to_policy(
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

        # Secrets Manager permissions
        agentcore_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret"
                ],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:agentcore/voice-agent/*"
                ]
            )
        )

        # SSM Parameter Store permissions
        agentcore_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "ssm:GetParametersByPath"
                ],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/agentcore/voice-agent/*"
                ]
            )
        )

        # CloudWatch Logs permissions
        agentcore_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/agentcore/voice-agent:*"
                ]
            )
        )

        # Secrets Manager secrets
        google_oauth_secret = secretsmanager.Secret(
            self,
            "GoogleOAuthSecret",
            secret_name="agentcore/voice-agent/google-oauth2",
            description="Google OAuth2 credentials for voice agent",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"client_id": "", "client_secret": "", "redirect_uri": ""}',
                generate_string_key="placeholder",
                exclude_characters='"'
            )
        )

        jwt_secret = secretsmanager.Secret(
            self,
            "JWTSecret",
            secret_name="agentcore/voice-agent/jwt-secret",
            description="JWT signing secret for voice agent",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"secret_key": ""}',
                generate_string_key="secret_key",
                password_length=64,
                exclude_characters='"'
            )
        )

        memory_id_secret = secretsmanager.Secret(
            self,
            "MemoryIdSecret",
            secret_name="agentcore/voice-agent/memory-id",
            description="AgentCore Memory resource ID",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"memory_id": ""}',
                generate_string_key="memory_id",
                exclude_characters='"'
            )
        )

        # Grant read access to secrets
        google_oauth_secret.grant_read(agentcore_role)
        jwt_secret.grant_read(agentcore_role)
        memory_id_secret.grant_read(agentcore_role)

        # CloudWatch Log Group
        log_group = logs.LogGroup(
            self,
            "VoiceAgentLogGroup",
            log_group_name="/aws/agentcore/voice-agent",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY
        )

        # SSM Parameters for non-sensitive configuration
        ssm.StringParameter(
            self,
            "MemoryRegionParam",
            parameter_name="/agentcore/voice-agent/memory-region",
            string_value=self.region,
            description="AWS region for AgentCore Memory"
        )

        # Store references for use by other stacks
        self.ecr_repo = ecr_repo
        self.agentcore_role = agentcore_role
        self.memory_id_secret = memory_id_secret

        # Outputs
        CfnOutput(
            self,
            "ECRRepositoryURI",
            value=ecr_repo.repository_uri,
            description="ECR repository URI for Docker images",
            export_name=f"{self.stack_name}-ECRRepositoryURI"
        )

        CfnOutput(
            self,
            "AgentCoreRoleARN",
            value=agentcore_role.role_arn,
            description="IAM role ARN for AgentCore Runtime",
            export_name=f"{self.stack_name}-AgentCoreRoleARN"
        )

        CfnOutput(
            self,
            "GoogleOAuthSecretARN",
            value=google_oauth_secret.secret_arn,
            description="Secrets Manager ARN for Google OAuth2 credentials"
        )

        CfnOutput(
            self,
            "JWTSecretARN",
            value=jwt_secret.secret_arn,
            description="Secrets Manager ARN for JWT secret"
        )

        CfnOutput(
            self,
            "LogGroupName",
            value=log_group.log_group_name,
            description="CloudWatch Log Group name"
        )

