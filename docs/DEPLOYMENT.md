# Deployment Guide

This guide covers production deployment of the AgentCore Voice Agent system using AWS CDK and CodeBuild pipelines.

## Overview

The deployment system uses:
- **AWS CDK**: Infrastructure as Code for all AWS resources
- **CodeBuild**: Automated Docker builds and deployments
- **GitHub**: Source control and webhook triggers
- **ECR**: Separate Docker image repositories per agent
- **AgentCore Runtime**: Container runtime for agents
- **S3 + CloudFront**: Web client hosting

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** configured with credentials
3. **CDK CLI** installed: `npm install -g aws-cdk`
4. **Python 3.11+** for CDK stacks
5. **Docker** for local testing (not required for CodeBuild)
6. **GitHub Repository** with webhook access

## Initial Infrastructure Setup

### 1. Bootstrap CDK

First-time setup requires bootstrapping CDK in your target region:

```bash
cd infrastructure/cdk
cdk bootstrap aws://ACCOUNT-ID/us-west-2
```

Replace `ACCOUNT-ID` with your AWS account ID and `us-west-2` with your target region.

### 2. Configure GitHub Integration

Set environment variables for CodeBuild to connect to GitHub:

```bash
export GITHUB_OWNER=your-github-username
export GITHUB_REPO=agentcore-voice-agent
```

These will be used when deploying the CodeBuild stack.

### 3. Deploy Base Infrastructure

Deploy the base stack which creates ECR repositories, IAM roles, and secrets:

```bash
cd infrastructure/cdk
cdk deploy AgentCoreVoiceAgent-Base-dev --context environment=dev
```

This creates:
- 6 separate ECR repositories (one per agent)
- IAM roles for AgentCore Runtime
- Secrets Manager secrets (empty, to be populated)
- SSM Parameter Store parameters

### 4. Create AgentCore Memory

Memory is created separately using the management script:

```bash
# From project root
python scripts/manage_memory.py create
```

This creates memory with all three strategies and stores the ID in SSM and Secrets Manager.

### 5. Configure Secrets

Populate secrets in AWS Secrets Manager:

#### Google OAuth2 Credentials

```bash
aws secretsmanager put-secret-value \
  --secret-id agentcore/voice-agent/dev/google-oauth2 \
  --secret-string '{
    "client_id": "your-client-id.apps.googleusercontent.com",
    "client_secret": "your-client-secret",
    "redirect_uri": "https://your-endpoint/api/auth/callback"
  }'
```

#### JWT Secret

```bash
JWT_SECRET=$(openssl rand -hex 32)
aws secretsmanager put-secret-value \
  --secret-id agentcore/voice-agent/dev/jwt-secret \
  --secret-string "{\"secret_key\": \"$JWT_SECRET\"}"
```

#### Agent Auth Secret

```bash
AGENT_AUTH_SECRET=$(openssl rand -hex 32)
aws secretsmanager put-secret-value \
  --secret-id agentcore/voice-agent/dev/agent-auth-secret \
  --secret-string "{\"secret_key\": \"$AGENT_AUTH_SECRET\"}"
```

### 6. Configure SSM Parameters

Set model configurations and other parameters:

```bash
# Model IDs
aws ssm put-parameter \
  --name "/agentcore/voice-agent/dev/orchestrator-model" \
  --value "us.amazon.nova-pro-v1:0" \
  --type "String"

aws ssm put-parameter \
  --name "/agentcore/voice-agent/dev/vision-model" \
  --value "us.amazon.nova-pro-v1:0" \
  --type "String"

# Memory configuration
aws ssm put-parameter \
  --name "/agentcore/voice-agent/dev/memory-id" \
  --value "your-memory-id" \
  --type "String"

aws ssm put-parameter \
  --name "/agentcore/voice-agent/dev/memory-region" \
  --value "us-west-2" \
  --type "String"

aws ssm put-parameter \
  --name "/agentcore/voice-agent/dev/memory-enabled" \
  --value "true" \
  --type "String"
```

### 7. Deploy Web Client Stack

Deploy S3 + CloudFront for web client:

```bash
cdk deploy AgentCoreWebClient-dev --context environment=dev
```

### 8. Deploy CodeBuild Stack

Deploy CodeBuild pipelines:

```bash
cdk deploy AgentCoreCodeBuild-dev --context environment=dev
```

This creates CodeBuild projects for each agent and the web client, connected to GitHub.

### 9. Configure GitHub Webhook

After CodeBuild stack is deployed, configure GitHub webhook:

1. Go to your GitHub repository settings
2. Navigate to Webhooks
3. Add webhook with CodeBuild webhook URL (from stack outputs)
4. Set events: Push, Pull Request

### 10. Deploy Agent Stacks

Deploy runtime and multi-agent stacks:

```bash
# Deploy voice agent runtime
cdk deploy AgentCoreVoiceAgent-Runtime-dev --context environment=dev

# Deploy multi-agent system
cdk deploy AgentCoreMultiAgent-dev --context environment=dev
```

## Automated Deployment Workflow

Once infrastructure is set up, deployments are automated via CodeBuild:

### Deployment Flow

1. **Push to GitHub**: Developer pushes code to `main` (production) or `develop` (dev) branch
2. **CodeBuild Triggered**: GitHub webhook triggers CodeBuild project
3. **Build Docker Image**: CodeBuild builds agent-specific Docker image
4. **Tag Image**: Image tagged with `{branch}-{commit-sha}` format
5. **Push to ECR**: Image pushed to agent-specific ECR repository
6. **Update SSM**: Image tag stored in SSM Parameter Store
7. **Deploy CDK**: If infrastructure changed, CDK stacks are deployed
8. **Update Runtime**: AgentCore Runtime updated with new image
9. **Health Check**: Automated health check verifies deployment
10. **Notification**: SNS notification sent on completion

### Branch-Based Deployments

- **`main` branch** → Deploys to production environment
- **`develop` branch** → Deploys to development environment
- **Pull Requests** → Builds and tests only (no deployment)

## Manual Deployment (If Needed)

If you need to manually deploy without CodeBuild:

### Build and Push Docker Image

```bash
# Set variables
AGENT_NAME=orchestrator
ENVIRONMENT=dev
COMMIT_SHA=$(git rev-parse --short HEAD)
BRANCH_NAME=$(git branch --show-current)
IMAGE_TAG="${BRANCH_NAME}-${COMMIT_SHA}"

# Get ECR repository URI
ECR_REPO_URI=$(aws ssm get-parameter \
  --name "/agentcore/voice-agent/${ENVIRONMENT}/ecr-${AGENT_NAME}-uri" \
  --query 'Parameter.Value' \
  --output text)

# Login to ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin $ECR_REPO_URI

# Build and push
docker build -t $ECR_REPO_URI:$IMAGE_TAG -f agents/$AGENT_NAME/Dockerfile .
docker tag $ECR_REPO_URI:$IMAGE_TAG $ECR_REPO_URI:latest
docker push $ECR_REPO_URI:$IMAGE_TAG
docker push $ECR_REPO_URI:latest

# Update SSM parameter
aws ssm put-parameter \
  --name "/agentcore/voice-agent/${ENVIRONMENT}/${AGENT_NAME}-image-tag" \
  --value "$IMAGE_TAG" \
  --type "String" \
  --overwrite
```

### Deploy CDK Stack

```bash
cd infrastructure/cdk
cdk deploy AgentCoreMultiAgent-dev \
  --context environment=dev \
  --context image_tag=$IMAGE_TAG
```

## Rollback Procedures

### Rollback Agent Deployment

1. **Get Previous Image Tag**:
   ```bash
   # List recent image tags in ECR
   aws ecr describe-images \
     --repository-name agentcore-voice-agent-orchestrator \
     --query 'sort_by(imageDetails,&imagePushedAt)[-5:].imageTags[0]' \
     --output text
   ```

2. **Update SSM Parameter**:
   ```bash
   aws ssm put-parameter \
     --name "/agentcore/voice-agent/dev/orchestrator-image-tag" \
     --value "main-abc1234" \
     --type "String" \
     --overwrite
   ```

3. **Redeploy Stack**:
   ```bash
   cdk deploy AgentCoreMultiAgent-dev --context environment=dev
   ```

### Rollback Infrastructure

```bash
# Destroy specific stack
cdk destroy AgentCoreMultiAgent-dev

# Or rollback to previous CloudFormation stack version
aws cloudformation continue-update-rollback \
  --stack-name AgentCoreMultiAgent-dev
```

## Environment-Specific Deployments

### Development Environment

```bash
cd infrastructure/cdk
cdk deploy --all --context environment=dev
```

### Production Environment

```bash
cd infrastructure/cdk
cdk deploy --all --context environment=prod
```

## Monitoring Deployments

### CodeBuild Logs

View build logs in AWS Console:
- Navigate to CodeBuild → Build projects
- Select project → View recent builds → View logs

### CloudWatch Logs

Agent logs are in CloudWatch:
- Log group: `/aws/agentcore/voice-agent`
- Filter by agent name or runtime ID

### Health Checks

Health check function runs after deployments:
- Lambda function: `DeploymentStack-HealthCheckFunction`
- SNS notifications: `agentcore-deployment-notifications-{env}`

## Troubleshooting

### CodeBuild Failures

1. **Check IAM Permissions**: Ensure CodeBuild role has ECR push permissions
2. **Verify GitHub Connection**: Check webhook configuration
3. **Review Build Logs**: Check CodeBuild console for detailed errors

### ECR Push Failures

1. **Authentication**: Verify ECR login succeeded
2. **Permissions**: Check CodeBuild role has `ecr:BatchGetImage` and `ecr:PutImage`
3. **Repository Exists**: Verify ECR repository was created

### CDK Deployment Failures

1. **Check Stack Dependencies**: Ensure base stack is deployed first
2. **Verify SSM Parameters**: All required parameters must exist
3. **Review CloudFormation Events**: Check stack events for specific errors

### Runtime Update Failures

1. **Verify Image Exists**: Check ECR for image with specified tag
2. **Check Runtime Status**: Verify runtime is in active state
3. **Review Runtime Logs**: Check CloudWatch logs for runtime errors

## Next Steps

- See [ENVIRONMENT_VARIABLES.md](./ENVIRONMENT_VARIABLES.md) for production variable configuration
- See [INFRASTRUCTURE.md](./INFRASTRUCTURE.md) for architecture details
- See [README.md](../README.md) for general project information
