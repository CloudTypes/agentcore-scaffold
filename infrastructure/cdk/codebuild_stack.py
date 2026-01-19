"""CDK stack for CodeBuild pipelines for automated Docker builds and deployments."""

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_codebuild as codebuild,
    aws_iam as iam,
    aws_ecr as ecr,
    aws_s3 as s3,
    aws_ssm as ssm,
    aws_secretsmanager as secretsmanager,
    aws_cloudfront as cloudfront,
    CfnOutput,
    Duration,
)
from constructs import Construct
import os


class CodeBuildStack(Stack):
    """Stack for CodeBuild projects for automated agent builds and deployments."""

    def __init__(self, scope: Construct, construct_id: str, base_stack=None, web_client_stack=None, **kwargs) -> None:
        """
        Initialize CodeBuild stack.

        Args:
            scope: Parent construct
            construct_id: Stack ID
            base_stack: Base stack with ECR repositories
            web_client_stack: Web client stack with S3 bucket
        """
        super().__init__(scope, construct_id, **kwargs)

        env_name = self.node.try_get_context("environment") or "dev"

        # Get ECR repositories from base stack
        if base_stack:
            ecr_repos = base_stack.ecr_repos
        else:
            raise ValueError("Base stack with ECR repositories is required.")

        # Get S3 bucket from web client stack (if available)
        web_bucket = None
        cloudfront_distribution_id = None
        if web_client_stack:
            web_bucket = web_client_stack.web_bucket
            if hasattr(web_client_stack, "cloudfront_distribution"):
                cloudfront_distribution_id = web_client_stack.cloudfront_distribution.distribution_id

        # Create IAM role for CodeBuild projects
        codebuild_role = iam.Role(
            self,
            "CodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            description="Role for CodeBuild projects to build and deploy agents",
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLogsFullAccess")],
        )

        # Grant ECR permissions
        for agent_name, ecr_repo in ecr_repos.items():
            ecr_repo.grant_pull_push(codebuild_role)

        # Grant CDK/CloudFormation deploy permissions
        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudformation:*",
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "ssm:PutParameter",
                    "ssm:GetParametersByPath",
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret",
                    "bedrock-agentcore:GetRuntime",
                    "bedrock-agentcore:UpdateRuntime",
                    "bedrock-agentcore:ListRuntimes",
                ],
                resources=["*"],
            )
        )

        # Grant S3 permissions for web client deployment (if web client stack exists)
        if web_bucket:
            web_bucket.grant_read_write(codebuild_role)
            codebuild_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "cloudfront:CreateInvalidation",
                        "cloudfront:GetInvalidation",
                        "cloudfront:ListInvalidations",
                    ],
                    resources=["*"],
                )
            )

        # Grant additional permissions for Docker builds
        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                ],
                resources=["*"],
            )
        )

        # Create CodeBuild projects for each agent
        agents = ["orchestrator", "vision", "document", "data", "tool", "voice"]
        build_projects = {}

        for agent_name in agents:
            project = codebuild.Project(
                self,
                f"{agent_name.capitalize()}BuildProject",
                project_name=f"agentcore-{agent_name}-build-{env_name}",
                role=codebuild_role,
                environment=codebuild.BuildEnvironment(
                    build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                    compute_type=codebuild.ComputeType.SMALL,
                    privileged=True,  # Required for Docker builds
                ),
                build_spec=codebuild.BuildSpec.from_source_filename(f"buildspecs/buildspec-{agent_name}.yml"),
                source=codebuild.Source.git_hub(
                    owner=os.getenv("GITHUB_OWNER", ""),
                    repo=os.getenv("GITHUB_REPO", "agentcore-scaffold"),
                    webhook=True,
                    webhook_filters=[
                        codebuild.FilterGroup.in_event_of(codebuild.EventAction.PUSH).and_branch_is("main"),  # Production
                        codebuild.FilterGroup.in_event_of(codebuild.EventAction.PUSH).and_branch_is("develop"),  # Development
                    ],
                ),
                timeout=Duration.minutes(30),
                environment_variables={
                    "AGENT_NAME": codebuild.BuildEnvironmentVariable(value=agent_name),
                    "ENVIRONMENT": codebuild.BuildEnvironmentVariable(value=env_name),
                    "AWS_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
                    "AWS_ACCOUNT_ID": codebuild.BuildEnvironmentVariable(value=self.account),
                    "ECR_REPO_URI": codebuild.BuildEnvironmentVariable(value=ecr_repos[agent_name].repository_uri),
                },
            )

            build_projects[agent_name] = project

        # Create CodeBuild project for web client
        if web_bucket:
            web_client_project = codebuild.Project(
                self,
                "WebClientBuildProject",
                project_name=f"agentcore-web-client-build-{env_name}",
                role=codebuild_role,
                environment=codebuild.BuildEnvironment(
                    build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                    compute_type=codebuild.ComputeType.SMALL,
                ),
                build_spec=codebuild.BuildSpec.from_source_filename("buildspecs/buildspec-web-client.yml"),
                source=codebuild.Source.git_hub(
                    owner=os.getenv("GITHUB_OWNER", ""),
                    repo=os.getenv("GITHUB_REPO", "agentcore-scaffold"),
                    webhook=True,
                    webhook_filters=[
                        codebuild.FilterGroup.in_event_of(codebuild.EventAction.PUSH).and_branch_is("main"),
                        codebuild.FilterGroup.in_event_of(codebuild.EventAction.PUSH).and_branch_is("develop"),
                    ],
                ),
                timeout=Duration.minutes(15),
                environment_variables={
                    "ENVIRONMENT": codebuild.BuildEnvironmentVariable(value=env_name),
                    "AWS_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
                    "S3_BUCKET": codebuild.BuildEnvironmentVariable(value=web_bucket.bucket_name),
                    "CLOUDFRONT_DISTRIBUTION_ID": codebuild.BuildEnvironmentVariable(value=cloudfront_distribution_id or ""),
                },
            )

            self.web_client_project = web_client_project

        self.build_projects = build_projects
        self.codebuild_role = codebuild_role

        # Outputs
        for agent_name, project in build_projects.items():
            CfnOutput(
                self,
                f"{agent_name.capitalize()}BuildProjectName",
                value=project.project_name,
                description=f"CodeBuild project name for {agent_name} agent",
            )

        if web_bucket:
            CfnOutput(
                self,
                "WebClientBuildProjectName",
                value=web_client_project.project_name,
                description="CodeBuild project name for web client",
            )
