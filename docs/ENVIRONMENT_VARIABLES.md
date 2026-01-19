# Environment Variables Guide

This document describes all environment variables used in the AgentCore Voice Agent system, including local development and production configurations.

## Overview

Environment variables are managed differently for local development vs production:

- **Local Development**: Use `.env` file (see `env.example`)
- **Production**: Use AWS Systems Manager (SSM) Parameter Store and Secrets Manager

## Variable Categories

### 1. Secrets (Secrets Manager)

Sensitive values stored in AWS Secrets Manager:

| Variable | Local Dev | Production | Description |
|----------|-----------|------------|-------------|
| `GOOGLE_CLIENT_ID` | `.env` | `agentcore/voice-agent/{env}/google-oauth2` | Google OAuth2 client ID |
| `GOOGLE_CLIENT_SECRET` | `.env` | `agentcore/voice-agent/{env}/google-oauth2` | Google OAuth2 client secret |
| `GOOGLE_REDIRECT_URI` | `.env` | `agentcore/voice-agent/{env}/google-oauth2` | OAuth2 redirect URI |
| `JWT_SECRET_KEY` | `.env` | `agentcore/voice-agent/{env}/jwt-secret` | JWT signing secret |
| `AGENT_AUTH_SECRET` | `.env` | `agentcore/voice-agent/{env}/agent-auth-secret` | Inter-agent auth secret |
| `WEATHER_API_KEY` | `.env` | `agentcore/voice-agent/{env}/weather-api-key` | Weather API key (optional) |
| `AGENTCORE_MEMORY_ID` | `.env` | `agentcore/voice-agent/{env}/memory-id` | Memory resource ID |

### 2. Configuration (SSM Parameter Store)

Non-sensitive configuration stored in SSM Parameter Store:

| Variable | Local Dev | Production SSM Path | Description |
|----------|-----------|---------------------|-------------|
| `ORCHESTRATOR_MODEL` | `.env` | `/agentcore/voice-agent/{env}/orchestrator-model` | Bedrock model for orchestrator |
| `VISION_MODEL` | `.env` | `/agentcore/voice-agent/{env}/vision-model` | Bedrock model for vision agent |
| `DOCUMENT_MODEL` | `.env` | `/agentcore/voice-agent/{env}/document-model` | Bedrock model for document agent |
| `DATA_MODEL` | `.env` | `/agentcore/voice-agent/{env}/data-model` | Bedrock model for data agent |
| `TOOL_MODEL` | `.env` | `/agentcore/voice-agent/{env}/tool-model` | Bedrock model for tool agent |
| `MODEL_ID` | `.env` | `/agentcore/voice-agent/{env}/voice-model` | Bedrock model for voice agent |
| `AGENTCORE_MEMORY_REGION` | `.env` | `/agentcore/voice-agent/{env}/memory-region` | AWS region for memory |
| `MEMORY_ENABLED` | `.env` | `/agentcore/voice-agent/{env}/memory-enabled` | Enable/disable memory |
| `S3_VISION_BUCKET` | `.env` | `/agentcore/voice-agent/{env}/s3-vision-bucket` | S3 bucket for vision uploads |
| `AWS_REGION` | `.env` | `/agentcore/voice-agent/{env}/aws-region` | AWS region |

### 3. Runtime Endpoints (SSM Parameter Store)

Agent endpoints discovered at runtime:

| Variable | Production SSM Path | Description |
|----------|---------------------|-------------|
| `ORCHESTRATOR_ENDPOINT` | `/agentcore/voice-agent/{env}/orchestrator-endpoint` | Orchestrator API endpoint |
| `VOICE_AGENT_ENDPOINT` | `/agentcore/voice-agent/{env}/voice-agent-endpoint` | Voice agent API endpoint |
| `VISION_AGENT_ENDPOINT` | `/agentcore/voice-agent/{env}/vision-endpoint` | Vision agent endpoint |
| `WEB_CLIENT_URL` | `/agentcore/voice-agent/{env}/web-client-url` | CloudFront distribution URL |

### 4. Image Tags (SSM Parameter Store)

Docker image tags updated by CodeBuild:

| Variable | Production SSM Path | Description |
|----------|---------------------|-------------|
| `ORCHESTRATOR_IMAGE_TAG` | `/agentcore/voice-agent/{env}/orchestrator-image-tag` | Orchestrator image tag |
| `VISION_IMAGE_TAG` | `/agentcore/voice-agent/{env}/vision-image-tag` | Vision agent image tag |
| `DOCUMENT_IMAGE_TAG` | `/agentcore/voice-agent/{env}/document-image-tag` | Document agent image tag |
| `DATA_IMAGE_TAG` | `/agentcore/voice-agent/{env}/data-image-tag` | Data agent image tag |
| `TOOL_IMAGE_TAG` | `/agentcore/voice-agent/{env}/tool-image-tag` | Tool agent image tag |
| `VOICE_IMAGE_TAG` | `/agentcore/voice-agent/{env}/voice-image-tag` | Voice agent image tag |

## Local Development Setup

### 1. Copy Example File

```bash
cp env.example .env
```

### 2. Configure Variables

Edit `.env` with your local development values. See `env.example` for detailed comments.

### 3. Required for Local Dev

Minimum required variables for local development:

```bash
# AWS Credentials (if using MFA, run scripts/fix_mfa.py first)
AWS_REGION=us-west-2
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_SESSION_TOKEN=your-token  # If using MFA

# Model IDs
ORCHESTRATOR_MODEL=us.amazon.nova-pro-v1:0
VISION_MODEL=us.amazon.nova-pro-v1:0
# ... etc

# Memory
AGENTCORE_MEMORY_ID=your-memory-id
AGENTCORE_MEMORY_REGION=us-west-2
MEMORY_ENABLED=true

# Authentication
AGENT_AUTH_SECRET=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)
```

## Production Configuration

### Setting SSM Parameters

```bash
# Model configuration
aws ssm put-parameter \
  --name "/agentcore/voice-agent/prod/orchestrator-model" \
  --value "us.amazon.nova-pro-v1:0" \
  --type "String" \
  --region us-west-2

# Memory configuration
aws ssm put-parameter \
  --name "/agentcore/voice-agent/prod/memory-id" \
  --value "your-memory-id" \
  --type "String" \
  --region us-west-2
```

### Setting Secrets Manager Secrets

```bash
# Google OAuth2 (JSON format)
aws secretsmanager put-secret-value \
  --secret-id agentcore/voice-agent/prod/google-oauth2 \
  --secret-string '{
    "client_id": "your-client-id.apps.googleusercontent.com",
    "client_secret": "your-secret",
    "redirect_uri": "https://your-domain/api/auth/callback"
  }' \
  --region us-west-2

# JWT Secret (JSON format)
JWT_SECRET=$(openssl rand -hex 32)
aws secretsmanager put-secret-value \
  --secret-id agentcore/voice-agent/prod/jwt-secret \
  --secret-string "{\"secret_key\": \"$JWT_SECRET\"}" \
  --region us-west-2
```

## Migration from Local to Production

### Step 1: Export Local Variables

```bash
# Export all variables from .env
export $(cat .env | grep -v '^#' | xargs)
```

### Step 2: Create SSM Parameters

```bash
# Script to migrate model configurations
for model in ORCHESTRATOR_MODEL VISION_MODEL DOCUMENT_MODEL DATA_MODEL TOOL_MODEL MODEL_ID; do
  value=$(grep "^${model}=" .env | cut -d'=' -f2)
  if [ -n "$value" ]; then
    param_name=$(echo $model | tr '[:upper:]' '[:lower:]' | sed 's/_model//')
    aws ssm put-parameter \
      --name "/agentcore/voice-agent/prod/${param_name}-model" \
      --value "$value" \
      --type "String" \
      --region us-west-2
  fi
done
```

### Step 3: Create Secrets

```bash
# Migrate Google OAuth2
aws secretsmanager put-secret-value \
  --secret-id agentcore/voice-agent/prod/google-oauth2 \
  --secret-string "{
    \"client_id\": \"$GOOGLE_CLIENT_ID\",
    \"client_secret\": \"$GOOGLE_CLIENT_SECRET\",
    \"redirect_uri\": \"$GOOGLE_REDIRECT_URI\"
  }" \
  --region us-west-2

# Migrate JWT secret
aws secretsmanager put-secret-value \
  --secret-id agentcore/voice-agent/prod/jwt-secret \
  --secret-string "{\"secret_key\": \"$JWT_SECRET_KEY\"}" \
  --region us-west-2
```

## Variable Reference Table

### Complete Variable List

| Variable | Type | Local | Production | Required |
|----------|------|-------|------------|----------|
| `AWS_REGION` | Config | `.env` | SSM | Yes |
| `AWS_ACCESS_KEY_ID` | Secret | `.env` | IAM Role | Local only |
| `AWS_SECRET_ACCESS_KEY` | Secret | `.env` | IAM Role | Local only |
| `ORCHESTRATOR_MODEL` | Config | `.env` | SSM | Yes |
| `VISION_MODEL` | Config | `.env` | SSM | Yes |
| `DOCUMENT_MODEL` | Config | `.env` | SSM | Yes |
| `DATA_MODEL` | Config | `.env` | SSM | Yes |
| `TOOL_MODEL` | Config | `.env` | SSM | Yes |
| `MODEL_ID` | Config | `.env` | SSM | Yes |
| `AGENTCORE_MEMORY_ID` | Secret | `.env` | Secrets Manager | Yes |
| `AGENTCORE_MEMORY_REGION` | Config | `.env` | SSM | Yes |
| `MEMORY_ENABLED` | Config | `.env` | SSM | No (default: true) |
| `AGENT_AUTH_SECRET` | Secret | `.env` | Secrets Manager | Yes |
| `GOOGLE_CLIENT_ID` | Secret | `.env` | Secrets Manager | Optional |
| `GOOGLE_CLIENT_SECRET` | Secret | `.env` | Secrets Manager | Optional |
| `JWT_SECRET_KEY` | Secret | `.env` | Secrets Manager | Yes |
| `WEATHER_API_KEY` | Secret | `.env` | Secrets Manager | Optional |
| `S3_VISION_BUCKET` | Config | `.env` | SSM | Yes |
| `ENVIRONMENT` | Config | `.env` | Context | Yes |

## Environment-Specific Paths

Replace `{env}` with your environment name (`dev`, `prod`, etc.):

- **SSM Parameters**: `/agentcore/voice-agent/{env}/*`
- **Secrets Manager**: `agentcore/voice-agent/{env}/*`

## Best Practices

1. **Never commit `.env` files**: Add to `.gitignore`
2. **Use different secrets per environment**: Don't share secrets between dev/prod
3. **Rotate secrets regularly**: Update JWT and auth secrets periodically
4. **Use IAM roles in production**: Don't use access keys in production
5. **Validate parameters**: Verify all required parameters exist before deployment

## Troubleshooting

### Variable Not Found

**Error**: `Parameter /agentcore/voice-agent/prod/xxx not found`

**Solution**: Create the parameter:
```bash
aws ssm put-parameter \
  --name "/agentcore/voice-agent/prod/xxx" \
  --value "default-value" \
  --type "String"
```

### Secret Access Denied

**Error**: `AccessDeniedException when calling GetSecretValue`

**Solution**: Verify IAM role has `secretsmanager:GetSecretValue` permission

### Wrong Environment

**Error**: Reading from wrong environment

**Solution**: Verify `ENVIRONMENT` context or SSM path matches your deployment

## See Also

- [DEPLOYMENT.md](./DEPLOYMENT.md) - Deployment procedures
- [INFRASTRUCTURE.md](./INFRASTRUCTURE.md) - Infrastructure architecture
- [README.md](../README.md) - Project overview
