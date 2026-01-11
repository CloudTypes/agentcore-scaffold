"""CDK Stack for Vision Agent Infrastructure."""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_s3 as s3,
    aws_iam as iam,
    CfnOutput
)
from constructs import Construct


class VisionInfrastructureStack(Stack):
    """
    CDK Stack for AgentCore Vision Agent Infrastructure
    Creates S3 bucket, IAM roles, and policies for vision capabilities
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 Bucket for vision uploads
        self.vision_bucket = s3.Bucket(
            self, "VisionUploadsBucket",
            bucket_name="agentcore-vision-uploads",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                # Delete uploads after 7 days
                s3.LifecycleRule(
                    id="DeleteOldUploads",
                    enabled=True,
                    prefix="uploads/",
                    expiration=Duration.days(7)
                ),
                # Transition processed files to Infrequent Access after 30 days
                s3.LifecycleRule(
                    id="TransitionProcessed",
                    enabled=True,
                    prefix="processed/",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30)
                        )
                    ]
                )
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.PUT,
                        s3.HttpMethods.POST
                    ],
                    allowed_origins=["*"],  # Update with your domain in production
                    allowed_headers=["*"],
                    exposed_headers=["ETag"],
                    max_age=3000
                )
            ]
        )

        # IAM Role for Backend Service
        self.backend_role = iam.Role(
            self, "VisionBackendRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for AgentCore Vision Backend Service"
        )

        # Policy for Bedrock access
        bedrock_policy = iam.PolicyStatement(
            sid="BedrockInvoke",
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            resources=[
                f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-pro-v1:0"
            ]
        )

        # Policy for S3 access
        s3_policy = iam.PolicyStatement(
            sid="S3VisionBucket",
            effect=iam.Effect.ALLOW,
            actions=[
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:ListBucket"
            ],
            resources=[
                self.vision_bucket.bucket_arn,
                f"{self.vision_bucket.bucket_arn}/*"
            ]
        )

        # Attach policies to role
        self.backend_role.add_to_policy(bedrock_policy)
        self.backend_role.add_to_policy(s3_policy)

        # Outputs
        CfnOutput(
            self, "VisionBucketName",
            value=self.vision_bucket.bucket_name,
            description="S3 bucket for vision uploads"
        )

        CfnOutput(
            self, "VisionBucketArn",
            value=self.vision_bucket.bucket_arn,
            description="ARN of vision uploads bucket"
        )

        CfnOutput(
            self, "BackendRoleArn",
            value=self.backend_role.role_arn,
            description="ARN of backend service role"
        )
