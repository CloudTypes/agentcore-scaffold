# Infrastructure Architecture

This document describes the AWS infrastructure architecture for the AgentCore Voice Agent system.

## Overview

The infrastructure is managed entirely through AWS CDK (Cloud Development Kit) and consists of multiple stacks:

1. **Base Stack**: ECR repositories, IAM roles, secrets
2. **Web Client Stack**: S3 bucket and CloudFront distribution
3. **Runtime Stack**: Voice agent AgentCore Runtime deployment
4. **Multi-Agent Stack**: Orchestrator and specialist agents
5. **Vision Stack**: S3 bucket for vision uploads
6. **CodeBuild Stack**: CI/CD pipelines
7. **Deployment Stack**: Deployment orchestration and health checks

## CDK Stack Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CDK Application                          │
│  (infrastructure/cdk/app.py)                                │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Base Stack   │    │ Web Client   │    │ Vision Stack │
│              │    │ Stack        │    │              │
│ - ECR Repos  │    │ - S3 Bucket  │    │ - S3 Bucket  │
│ - IAM Roles  │    │ - CloudFront │    │ - IAM Roles  │
│ - Secrets    │    │              │    │              │
└──────┬───────┘    └──────┬───────┘    └──────────────┘
       │                   │
       │                   │
       ▼                   ▼
┌──────────────┐    ┌──────────────┐
│ Runtime      │    │ CodeBuild    │
│ Stack        │    │ Stack        │
│              │    │              │
│ - Voice      │    │ - Build      │
│   Runtime    │    │   Projects   │
└──────┬───────┘    │ - IAM Roles  │
       │            └──────────────┘
       │
       ▼
┌──────────────┐
│ Multi-Agent  │
│ Stack        │
│              │
│ - Orchestrator│
│ - Specialist │
│   Agents     │
└──────────────┘
```

## ECR Repository Structure

Each agent has its own ECR repository for independent versioning and lifecycle management:

| Repository Name | Agent | Purpose |
|----------------|-------|---------|
| `agentcore-voice-agent-orchestrator` | Orchestrator | Routes requests to specialist agents |
| `agentcore-voice-agent-vision` | Vision | Image and video analysis |
| `agentcore-voice-agent-document` | Document | Document processing |
| `agentcore-voice-agent-data` | Data | Data analysis and SQL queries |
| `agentcore-voice-agent-tool` | Tool | Calculator, weather, utilities |
| `agentcore-voice-agent-voice` | Voice | Bi-directional voice streaming |

### Image Tagging Strategy

Images are tagged with: `{branch}-{commit-sha}`

Examples:
- `main-abc1234` - Production deployment from main branch
- `develop-def5678` - Development deployment from develop branch
- `latest` - Always points to most recent successful build

## CodeBuild Pipeline Architecture

```
GitHub Repository
       │
       │ (Webhook)
       ▼
┌──────────────────┐
│  CodeBuild       │
│  Projects        │
│                  │
│  - orchestrator  │
│  - vision        │
│  - document      │
│  - data          │
│  - tool          │
│  - voice         │
│  - web-client    │
└────────┬─────────┘
         │
         │ (Build & Push)
         ▼
┌──────────────────┐
│  ECR Repositories│
│  (per agent)     │
└────────┬─────────┘
         │
         │ (Update Tag)
         ▼
┌──────────────────┐
│  SSM Parameter   │
│  Store           │
│  (image tags)    │
└────────┬─────────┘
         │
         │ (Deploy)
         ▼
┌──────────────────┐
│  AgentCore       │
│  Runtime         │
│  (Agents)        │
└──────────────────┘
```

### Build Process

1. **Source**: GitHub repository (webhook on push)
2. **Build**: Docker image build in CodeBuild
3. **Tag**: Commit SHA and branch name
4. **Push**: To agent-specific ECR repository
5. **Update**: SSM parameter with new image tag
6. **Deploy**: CDK stack (if infrastructure changed)
7. **Update Runtime**: AgentCore Runtime with new image

## Web Client Deployment Architecture

```
┌──────────────────┐
│  CodeBuild       │
│  (web-client)    │
└────────┬─────────┘
         │
         │ (Build & Upload)
         ▼
┌──────────────────┐
│  S3 Bucket       │
│  (Static Files)  │
└────────┬─────────┘
         │
         │ (Origin)
         ▼
┌──────────────────┐
│  CloudFront      │
│  Distribution    │
└────────┬─────────┘
         │
         │ (HTTPS)
         ▼
┌──────────────────┐
│  Users           │
└──────────────────┘
```

### Web Client Build Process

1. **Build**: Static files (HTML/JS/CSS or React build)
2. **Generate Config**: Runtime configuration from SSM parameters
3. **Upload**: Files to S3 bucket
4. **Invalidate**: CloudFront cache

## AgentCore Runtime Architecture

```
┌─────────────────────────────────────────┐
│         AgentCore Runtime               │
│                                         │
│  ┌──────────────┐  ┌──────────────┐    │
│  │ Orchestrator │  │ Voice Agent  │    │
│  │ Runtime      │  │ Runtime      │    │
│  └──────┬───────┘  └──────────────┘    │
│         │                               │
│         ▼                               │
│  ┌──────────────┐                       │
│  │ Vision       │                       │
│  │ Document     │                       │
│  │ Data         │                       │
│  │ Tool         │                       │
│  │ Runtimes     │                       │
│  └──────────────┘                       │
└─────────────────────────────────────────┘
         │
         │ (A2A Protocol)
         ▼
┌──────────────────┐
│  Amazon Bedrock  │
│  (Nova Models)   │
└──────────────────┘
```

## Network and Security Configuration

### IAM Roles

| Role | Purpose | Permissions |
|------|---------|-------------|
| `AgentCoreRuntimeRole` | AgentCore Runtime execution | Bedrock, Memory, Secrets, SSM, CloudWatch |
| `CodeBuildRole` | CodeBuild execution | ECR, CloudFormation, SSM, Secrets, S3, CloudFront |
| `{Agent}AgentRole` | Per-agent execution | Bedrock, Memory, Secrets, SSM |

### Security Groups

Agents run in AgentCore Runtime which handles networking internally. No security groups are required.

### Secrets Management

- **Secrets Manager**: Sensitive values (OAuth, JWT, API keys)
- **SSM Parameter Store**: Non-sensitive configuration
- **IAM Roles**: No access keys in production

### Network Isolation

- Agents communicate via A2A protocol (internal to AgentCore Runtime)
- Web client served via CloudFront (public HTTPS)
- API endpoints via AgentCore Runtime (HTTPS)

## Environment Configuration

### Development Environment

- **Prefix**: `dev`
- **Branch**: `develop`
- **Resources**: Lower capacity, shorter retention

### Production Environment

- **Prefix**: `prod`
- **Branch**: `main`
- **Resources**: Higher capacity, longer retention
- **Monitoring**: Enhanced logging and alerts

## Monitoring and Observability

### CloudWatch Logs

- **Log Groups**: `/aws/agentcore/voice-agent`
- **Retention**: 7 days (dev), 30 days (prod)
- **Streams**: Per agent runtime

### CloudWatch Metrics

- **CodeBuild**: Build success/failure rates
- **AgentCore Runtime**: Invocation counts, errors
- **CloudFront**: Request counts, error rates

### SNS Notifications

- **Topic**: `agentcore-deployment-notifications-{env}`
- **Events**: Build completion, deployment success/failure, health check results

## Cost Optimization

### ECR Lifecycle Rules

- Keep last 10 images per repository
- Automatic cleanup of old images

### CloudFront Caching

- Static assets cached at edge
- API responses not cached
- SPA support with error page redirects

### AgentCore Runtime

- Pay-per-use pricing
- No idle costs
- Automatic scaling

## Disaster Recovery

### Backup Strategy

- **ECR Images**: Versioned in repositories
- **SSM Parameters**: Versioned in Parameter Store
- **Secrets**: Versioned in Secrets Manager
- **CloudFormation**: Stack templates in CDK code

### Recovery Procedures

1. **Infrastructure**: Redeploy CDK stacks
2. **Agents**: Pull images from ECR
3. **Configuration**: Restore from SSM/Secrets Manager
4. **Data**: AgentCore Memory is persistent

## Scaling Considerations

### Horizontal Scaling

- AgentCore Runtime handles scaling automatically
- Multiple runtime instances can be created per agent

### Vertical Scaling

- Adjust CodeBuild compute type if builds are slow
- Adjust Lambda memory for health checks if needed

## See Also

- [DEPLOYMENT.md](./DEPLOYMENT.md) - Deployment procedures
- [ENVIRONMENT_VARIABLES.md](./ENVIRONMENT_VARIABLES.md) - Environment variable reference
- [README.md](../README.md) - Project overview
