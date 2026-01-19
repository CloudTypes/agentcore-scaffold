# Agent Authentication Secret (AGENT_AUTH_SECRET)

## Overview

`AGENT_AUTH_SECRET` is a **secret key** (not a JWT) used to sign and verify JWT tokens for **agent-to-agent (A2A) communication** in the multi-agent system.

## Key Points

1. **Not a JWT**: It's a secret key used to create/verify JWTs, similar to `JWT_SECRET_KEY`
2. **Different from JWT_SECRET_KEY**: 
   - `AGENT_AUTH_SECRET`: For agent-to-agent authentication
   - `JWT_SECRET_KEY`: For user authentication (OAuth2)
3. **Must be shared**: All agents (orchestrator, vision, document, data, tool) must use the **same** value
4. **Stored in Secrets Manager**: Not SSM, since it's sensitive

## Generation

Generate a secure random secret key using one of these methods:

### Method 1: Using OpenSSL (Recommended)
```bash
openssl rand -hex 32
```

### Method 2: Using Python
```python
import secrets
print(secrets.token_urlsafe(32))
```

### Method 3: Using OpenSSL (64 bytes)
```bash
openssl rand -hex 64
```

**Minimum length**: 32 characters (64 hex characters = 32 bytes)
**Recommended**: 64 characters (128 hex characters = 64 bytes)

## Configuration

### Local Development (.env file)

```bash
# Agent Authentication (for inter-agent communication)
AGENT_AUTH_SECRET=your-generated-secret-key-here
```

**Example**:
```bash
AGENT_AUTH_SECRET=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2
```

### Production (AWS Secrets Manager)

**Secret Name**: `agentcore/scaffold/agent-auth-secret`

**Secret Value Format**:
```json
{
  "secret_key": "your-generated-secret-key-here"
}
```

**CLI Command to Update**:
```bash
# Generate a secure random key
AGENT_AUTH_SECRET=$(openssl rand -hex 32)

# Update the secret (replace REGION with your AWS region, e.g., us-west-2)
aws secretsmanager put-secret-value \
  --region us-west-2 \
  --secret-id agentcore/scaffold/agent-auth-secret \
  --secret-string "{\"secret_key\": \"$AGENT_AUTH_SECRET\"}"
```

**Alternative: Using a JSON file**:
```bash
# Create a file agent-auth-secret.json with:
# {"secret_key": "your-secret-key"}

aws secretsmanager put-secret-value \
  --region us-west-2 \
  --secret-id agentcore/scaffold/agent-auth-secret \
  --secret-string file://agent-auth-secret.json
```

## Usage in Code

The `AGENT_AUTH_SECRET` is used by the `InterAgentAuth` class in `agents/shared/auth.py`:

```python
from agents.shared.auth import InterAgentAuth

# Initialize with secret from environment
auth = InterAgentAuth()  # Reads AGENT_AUTH_SECRET from os.getenv()

# Create a JWT token for agent-to-agent calls
token = auth.create_token("orchestrator")

# Verify a token from another agent
payload = auth.verify_token(token)
```

## Security Best Practices

1. **Never commit to version control**: Add to `.gitignore`
2. **Use strong secrets**: Minimum 32 characters, preferably 64
3. **Rotate periodically**: Change the secret if compromised
4. **Store securely**: Use Secrets Manager in production, not SSM
5. **Keep separate**: Use different values for `AGENT_AUTH_SECRET` and `JWT_SECRET_KEY`

## Verification

To verify the secret is correctly configured:

```bash
# Check if secret exists in Secrets Manager
aws secretsmanager describe-secret \
  --region us-west-2 \
  --secret-id agentcore/scaffold/agent-auth-secret

# Get the secret value (decrypted)
aws secretsmanager get-secret-value \
  --region us-west-2 \
  --secret-id agentcore/scaffold/agent-auth-secret \
  --query 'SecretString' \
  --output text | jq .
```

## Troubleshooting

### Error: "AGENT_AUTH_SECRET not set"

**Solution**: Ensure the environment variable is set in your `.env` file or passed to Docker containers.

### Error: "Invalid token" in A2A calls

**Possible causes**:
1. Different `AGENT_AUTH_SECRET` values across agents
2. Secret was changed but agents weren't restarted
3. Token expired (tokens expire after 5 minutes)

**Solution**:
1. Verify all agents use the same `AGENT_AUTH_SECRET` value
2. Restart all agents after changing the secret
3. Check token expiration (tokens are valid for 5 minutes)

### Error: "Token expired"

**Solution**: This is expected behavior. Tokens expire after 5 minutes for security. The calling agent will automatically create a new token for each request.

## Related Documentation

- [Docker Compose Guide](./DOCKER_COMPOSE.md) - Local development setup
- [CDK Infrastructure README](../infrastructure/cdk/README.md) - Production deployment
- [Multi-Agent Architecture Plan](./true_multi_agent_architecture_refactor_plan.md) - System architecture

