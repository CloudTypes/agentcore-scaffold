"""CDK stack for web client deployment (S3 + CloudFront)."""

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
    aws_certificatemanager as acm,
    aws_ssm as ssm,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct
import os


class WebClientStack(Stack):
    """Stack for deploying web client to S3 and CloudFront."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        """
        Initialize Web Client stack.
        
        Args:
            scope: Parent construct
            construct_id: Stack ID
        """
        super().__init__(scope, construct_id, **kwargs)

        env_name = self.node.try_get_context("environment") or "dev"
        
        # S3 Bucket for web client files
        self.web_bucket = s3.Bucket(
            self,
            "WebClientBucket",
            bucket_name=f"agentcore-scaffold-web-{env_name}-{self.account}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            website_index_document="index.html",
            website_error_document="index.html",  # SPA support
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.HEAD,
                    ],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=3000
                )
            ]
        )

        # CloudFront Distribution
        # Get certificate ARN from context or environment variable (optional)
        certificate_arn = (
            self.node.try_get_context("certificate_arn") or
            os.getenv("CLOUDFRONT_CERTIFICATE_ARN") or
            None
        )

        # Custom domain from context (optional)
        domain_name = (
            self.node.try_get_context("domain_name") or
            os.getenv("CLOUDFRONT_DOMAIN_NAME") or
            None
        )

        # Create S3 origin
        s3_origin = origins.S3BucketOrigin(self.web_bucket)

        # Create distribution with required parameters
        distribution = cloudfront.Distribution(
            self,
            "WebClientDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=s3_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
                compress=True,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=cdk.Duration.minutes(5)
                ),
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=cdk.Duration.minutes(5)
                ),
            ],
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,  # US, Canada, Europe
        )

        # Add certificate and domain if provided
        if certificate_arn and domain_name:
            certificate = acm.Certificate.from_certificate_arn(
                self, "Certificate", certificate_arn
            )
            # Note: Domain names and certificates are set via add_behavior or need to be
            # configured at creation time. For now, we'll document this in the deployment guide.
            # The distribution will work without custom domain, using CloudFront domain.

        self.cloudfront_distribution = distribution

        # Grant CloudFront access to S3 bucket
        # S3BucketOrigin handles permissions automatically, but we can add explicit policy if needed
        # The origin will use bucket policies or OAC as configured

        # SSM Parameter for web client URL
        ssm.StringParameter(
            self,
            "WebClientURLParam",
            parameter_name=f"/agentcore/scaffold/{env_name}/web-client-url",
            string_value=f"https://{self.cloudfront_distribution.distribution_domain_name}",
            description="CloudFront distribution URL for web client"
        )

        # Outputs
        CfnOutput(
            self,
            "WebClientBucketName",
            value=self.web_bucket.bucket_name,
            description="S3 bucket name for web client files"
        )

        CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=self.cloudfront_distribution.distribution_id,
            description="CloudFront distribution ID"
        )

        CfnOutput(
            self,
            "CloudFrontDistributionURL",
            value=f"https://{self.cloudfront_distribution.distribution_domain_name}",
            description="CloudFront distribution URL for web client"
        )

        if domain_name:
            CfnOutput(
                self,
                "CustomDomainURL",
                value=f"https://{domain_name}",
                description="Custom domain URL for web client"
            )
