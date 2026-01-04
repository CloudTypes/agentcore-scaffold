# AgentCore Voice Agent Infrastructure

This directory contains AWS CDK code for provisioning infrastructure for the AgentCore Voice Agent.

## Prerequisites

- AWS CLI configured with appropriate credentials
- CDK CLI installed: `npm install -g aws-cdk`
- Python 3.10+
- Docker (for building images)

## Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Bootstrap CDK in your target region (first time only):
```bash
# Bootstrap in the region specified in your .env file (e.g., us-west-2)
cdk bootstrap aws://ACCOUNT-ID/us-west-2

# Or if AWS_REGION is set in your environment
cdk bootstrap
```

## Deployment

1. Synthesize CloudFormation templates:
```bash
cdk synth
```

2. Deploy base infrastructure:
```bash
cdk deploy AgentCoreVoiceAgent-Base-dev
```

3. Create memory resource with strategies (using script, not CDK):
```bash
# From project root
python scripts/manage_memory.py create
```

4. Deploy runtime (after pushing Docker image to ECR):
```bash
cdk deploy AgentCoreVoiceAgent-Runtime-dev
```

5. Deploy all CDK stacks at once:
```bash
cdk deploy --all
# Note: This does NOT create memory - run the script separately
```

4. Deploy to specific environment:
```bash
cdk deploy --all --context environment=prod --context region=us-east-1
```

5. Deploy with custom image tag:
```bash
cdk deploy AgentCoreVoiceAgent-Runtime-dev --context image_tag=v1.0.0
```

## Stack Components

The infrastructure is split into two CDK stacks:

### 1. Base Stack (`AgentCoreVoiceAgent-Base-{env}`)
- **ECR Repository**: Stores Docker images for AgentCore Runtime
- **IAM Role**: Permissions for Bedrock, Memory, Secrets Manager, CloudWatch
- **Secrets Manager**: Secure storage for OAuth credentials, JWT secrets, and Memory ID
- **SSM Parameters**: Non-sensitive configuration
- **CloudWatch Log Group**: Application logging

### 2. Runtime Stack (`AgentCoreVoiceAgent-Runtime-{env}`)
- **AgentCore Runtime**: Deploys the voice agent container to AgentCore Runtime
- **Custom Resource**: Lambda function to manage Runtime lifecycle
- **SSM Parameters**: Stores Runtime endpoint and ID
- **Dependencies**: Requires Base stack for ECR repository and IAM role

### Memory Management (via Script)

**AgentCore Memory is NOT managed via CDK** because CloudFormation cannot set strategies at creation time. Instead, use the standalone script:

```bash
# Create memory with strategies
python scripts/manage_memory.py create

# Check memory status
python scripts/manage_memory.py status

# Delete memory
python scripts/manage_memory.py delete
```

The script creates memory with all three strategies:
- Summary Memory Strategy (session summaries)
- User Preference Memory Strategy
- Semantic Memory Strategy

The memory ID is automatically stored in:
- SSM Parameter: `/agentcore/voice-agent/memory-id`
- Secrets Manager: `agentcore/voice-agent/memory-id`

See `scripts/manage_memory.py --help` for more details.

## Configuration

### Region Configuration

The CDK app determines the AWS region using the following priority order:

1. **CDK Context** (highest priority): `--context region=us-west-2`
2. **Environment Variables**: `AWS_REGION` or `AGENTCORE_MEMORY_REGION` from `.env` file
3. **Default**: `us-east-1` (lowest priority)

The app automatically loads the `.env` file from the project root. To use a specific region:

**Option 1: Set in `.env` file** (recommended for local development):
```bash
AWS_REGION=us-west-2
AGENTCORE_MEMORY_REGION=us-west-2
```

**Option 2: Use CDK context** (for one-time deployments):
```bash
cdk deploy --all --context region=us-west-2
```

**Note**: CDK must be bootstrapped in the target region before deployment:
```bash
cdk bootstrap aws://ACCOUNT-ID/us-west-2
```

### Secrets Configuration

After deployment, configure secrets in AWS Secrets Manager. The Base stack creates empty secrets that need to be populated with actual values.

#### 1. Google OAuth2 Credentials

**Secret Name**: `agentcore/voice-agent/google-oauth2`

**Secret Value Format**:
```json
{
  "client_id": "your-client-id.apps.googleusercontent.com",
  "client_secret": "your-client-secret",
  "redirect_uri": "https://your-endpoint/api/auth/callback"
}
```

**CLI Command to Update**:
```bash
# Replace REGION with your AWS region (e.g., us-west-2)
aws secretsmanager put-secret-value \
  --region REGION \
  --secret-id agentcore/voice-agent/google-oauth2 \
  --secret-string '{
    "client_id": "your-client-id.apps.googleusercontent.com",
    "client_secret": "your-client-secret",
    "redirect_uri": "https://your-endpoint/api/auth/callback"
  }'
```

**Alternative: Using a JSON file**:
```bash
# Create a file oauth2-secret.json with the secret content
aws secretsmanager put-secret-value \
  --region REGION \
  --secret-id agentcore/voice-agent/google-oauth2 \
  --secret-string file://oauth2-secret.json
```

#### 2. JWT Secret (User Authentication)

**Secret Name**: `agentcore/voice-agent/jwt-secret`

**Purpose**: Secret key for signing/verifying JWT tokens for **user authentication** (OAuth2 flow).

**Secret Value Format**:
```json
{
  "secret_key": "your-secure-random-secret-key"
}
```

**CLI Command to Update**:
```bash
# Generate a secure random key (optional)
JWT_SECRET=$(openssl rand -hex 32)

# Update the secret
aws secretsmanager put-secret-value \
  --region REGION \
  --secret-id agentcore/voice-agent/jwt-secret \
  --secret-string "{\"secret_key\": \"$JWT_SECRET\"}"
```

**Alternative: Using a JSON file**:
```bash
# Create a file jwt-secret.json with: {"secret_key": "your-secret-key"}
aws secretsmanager put-secret-value \
  --region REGION \
  --secret-id agentcore/voice-agent/jwt-secret \
  --secret-string file://jwt-secret.json
```

#### 3. Agent Authentication Secret (Inter-Agent Communication)

**Secret Name**: `agentcore/voice-agent/agent-auth-secret`

**Purpose**: Secret key for signing/verifying JWT tokens for **agent-to-agent (A2A) communication**. This is used by the orchestrator and specialist agents to authenticate with each other.

**Important**: This is **different** from `JWT_SECRET_KEY`. They serve different purposes:
- `JWT_SECRET_KEY`: User authentication (OAuth2)
- `AGENT_AUTH_SECRET`: Agent-to-agent authentication (A2A)

**Secret Value Format**:
```json
{
  "secret_key": "your-secure-random-secret-key"
}
```

**CLI Command to Update**:
```bash
# Generate a secure random key (same method as JWT_SECRET_KEY)
AGENT_AUTH_SECRET=$(openssl rand -hex 32)

# Update the secret
aws secretsmanager put-secret-value \
  --region REGION \
  --secret-id agentcore/voice-agent/agent-auth-secret \
  --secret-string "{\"secret_key\": \"$AGENT_AUTH_SECRET\"}"
```

**Alternative: Using a JSON file**:
```bash
# Create a file agent-auth-secret.json with: {"secret_key": "your-secret-key"}
aws secretsmanager put-secret-value \
  --region REGION \
  --secret-id agentcore/voice-agent/agent-auth-secret \
  --secret-string file://agent-auth-secret.json
```

**Note**: All agents (orchestrator, vision, document, data, tool) must use the **same** `AGENT_AUTH_SECRET` value to communicate with each other. This secret should be:
- At least 32 characters (preferably 64)
- Cryptographically secure random string
- Stored in Secrets Manager (not SSM, since it's sensitive)
- Different from `JWT_SECRET_KEY`

#### 4. Memory ID

**Secret Name**: `agentcore/voice-agent/memory-id`

**Note**: This secret is automatically populated by the `manage_memory.py` script when the memory resource is created. You typically don't need to manually update this.

**Secret Value Format**:
```json
{
  "memory_id": "your-memory-id"
}
```

**To Create/Update Memory**:
```bash
# Create memory with strategies (automatically stores ID in secret and SSM)
python scripts/manage_memory.py create

# Check memory status
python scripts/manage_memory.py status
```

#### Verifying Secrets

To verify that secrets are correctly configured:

```bash
# List all secrets
aws secretsmanager list-secrets \
  --region REGION \
  --filters Key=name,Values=agentcore/voice-agent

# Get a specific secret value (decrypted)
aws secretsmanager get-secret-value \
  --region REGION \
  --secret-id agentcore/voice-agent/google-oauth2 \
  --query 'SecretString' \
  --output text | jq .
```

**Note**: Replace `REGION` with your AWS region (e.g., `us-west-2`) in all commands above.

## Destroying Infrastructure

Destroy stacks in reverse order:
```bash
# Delete memory resource first (using script)
python scripts/manage_memory.py delete

# Destroy runtime
cdk destroy AgentCoreVoiceAgent-Runtime-dev

# Finally base infrastructure
cdk destroy AgentCoreVoiceAgent-Base-dev

# Or destroy all CDK stacks at once (memory must be deleted separately)
cdk destroy --all
```

## CI/CD Integration

The CDK stacks can be integrated into CI/CD pipelines:

1. **Build and Push Docker Image**:
```bash
docker buildx build --platform linux/arm64 -t agentcore-voice-agent:latest .
docker tag agentcore-voice-agent:latest <account>.dkr.ecr.<region>.amazonaws.com/agentcore-voice-agent:latest
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker push <account>.dkr.ecr.<region>.amazonaws.com/agentcore-voice-agent:latest
```

2. **Deploy Infrastructure**:
```bash
# Deploy base stack
cdk deploy AgentCoreVoiceAgent-Base-prod

# Create memory resource with strategies (using script, not CDK)
python scripts/manage_memory.py create

# Deploy runtime stack (with image tag)
cdk deploy AgentCoreVoiceAgent-Runtime-prod --context image_tag=latest
```

3. **Update Runtime** (for new image versions):
```bash
cdk deploy AgentCoreVoiceAgent-Runtime-prod --context image_tag=v1.1.0
```

## Stack Dependencies

- **Base Stack**: No dependencies
- **Runtime Stack**: Depends on Base Stack (for ECR repository and IAM role)
- **Memory Resource**: Created separately via `scripts/manage_memory.py` (not a CDK stack)

Deploy in order: Base → Memory (via script) → Runtime

