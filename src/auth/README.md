# Google OAuth2 Authentication Setup Guide

This guide provides step-by-step instructions for configuring Google OAuth2 authentication for the AgentCore Voice Agent, including Google Cloud Console setup and optional Google Workspace domain restriction.

## Prerequisites

- Google account with access to Google Cloud Console
- (Optional) Google Workspace Admin account if restricting to a specific domain
- AWS account for storing secrets (when deploying to AgentCore Runtime)

## Step 1: Google Cloud Console - Create or Select Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown at the top of the page
3. Either:
   - **Select an existing project**, or
   - **Create a new project** by clicking "New Project"
     - Enter project name: "AgentCore Voice Agent" (or your preferred name)
     - Click "Create"
4. Wait for the project to be created/selected
5. Note your **Project ID** for reference

## Step 2: Enable Required APIs

1. In Google Cloud Console, navigate to **APIs & Services** > **Library**
2. Search for "Google Identity" or "Google+ API"
3. Click on the API result
4. Click **Enable** if not already enabled
5. (Optional) Enable "Google Workspace Admin SDK" if you plan to use domain restrictions

## Step 3: Configure OAuth Consent Screen

1. Navigate to **APIs & Services** > **OAuth consent screen**
2. Choose user type:
   - **External**: For testing or public use (requires app verification for production)
   - **Internal**: For Google Workspace organizations only (automatically restricts to your organization)
3. Fill in the required application information:
   - **App name**: `AgentCore Voice Agent` (or your preferred name)
   - **User support email**: Your email address
   - **Developer contact information**: Your email address
   - (Optional) **App logo**: Upload a logo if desired
4. Click **Save and Continue**

5. **Add Scopes** (click "Add or Remove Scopes"):
   - Select the following scopes:
     - `openid` (OpenID Connect)
     - `https://www.googleapis.com/auth/userinfo.email` (View your email address)
     - `https://www.googleapis.com/auth/userinfo.profile` (View your basic profile info)
   - Click **Update** to save scopes
   - Click **Save and Continue**

6. **Add Test Users** (if using External app type):
   - Click **Add Users**
   - Enter email addresses of users who will test the application
   - Click **Add**
   - Click **Save and Continue**

7. **Review and Submit**:
   - Review your configuration
   - Click **Back to Dashboard** (for testing) or submit for verification (for production)

## Step 4: Create OAuth2 Credentials

1. Navigate to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth client ID**
3. If prompted, configure the consent screen first (follow Step 3 above)
4. Select application type: **Web application**
5. Configure the OAuth client:
   - **Name**: `AgentCore Voice Agent Web Client`
   - **Authorized JavaScript origins**:
     - For local development: `http://localhost:8080`
     - For production: `https://your-production-domain.com`
     - Click **Add URI** for each origin
   - **Authorized redirect URIs**:
     - For local development: `http://localhost:8080/api/auth/callback`
     - For production: `https://your-production-domain.com/api/auth/callback`
     - Click **Add URI** for each redirect URI
6. Click **Create**
7. **IMPORTANT**: A popup will appear with your credentials:
   - **Client ID**: Copy this value immediately (you'll need it for `GOOGLE_CLIENT_ID`)
   - **Client Secret**: Copy this value immediately (you'll only see it once!)
   - Click **OK** to close the popup

## Step 5: Configure Google Workspace Domain Restriction (Optional)

If you want to restrict access to users from a specific Google Workspace domain:

### Option A: Use Internal App Type (Recommended)

1. In Google Cloud Console, go to **OAuth consent screen**
2. Change from **External** to **Internal**
   - This automatically restricts access to your Google Workspace organization
   - No additional configuration needed

### Option B: Restrict by Domain in Application

1. Ensure you have **Super Admin** privileges in Google Workspace
2. In Google Cloud Console, keep the app as **External**
3. Set the `GOOGLE_WORKSPACE_DOMAIN` environment variable (see Step 7)
4. The application will verify the `hd` (hosted domain) claim in the ID token

## Step 6: Generate JWT Secret Key

Generate a secure random secret key for signing JWT tokens. Choose one method:

### Method 1: Using OpenSSL (Recommended)

```bash
openssl rand -hex 32
```

### Method 2: Using Python

```python
import secrets
print(secrets.token_urlsafe(32))
```

### Method 3: Using Online Generator

Use a secure random string generator (at least 32 characters, preferably 64).

**Save this secret key** - you'll need it for `JWT_SECRET_KEY` in Step 7.

## Step 7: Configure Environment Variables

### For Local Development

Add the following to your `.env` file:

```bash
# Google OAuth2 Configuration
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret-here
GOOGLE_REDIRECT_URI=http://localhost:8080/api/auth/callback
GOOGLE_WORKSPACE_DOMAIN=  # Optional: e.g., "example.com" to restrict to specific domain

# JWT Configuration
JWT_SECRET_KEY=your-generated-secret-key-from-step-6
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60
```

**Example:**
```bash
GOOGLE_CLIENT_ID=123456789-abcdefghijklmnop.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-abcdefghijklmnopqrstuvwxyz
GOOGLE_REDIRECT_URI=http://localhost:8080/api/auth/callback
GOOGLE_WORKSPACE_DOMAIN=example.com
JWT_SECRET_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60
```

### For AgentCore Runtime Deployment

Store credentials in AWS Secrets Manager:

1. **Google OAuth2 Credentials** (`agentcore/scaffold/google-oauth2`):
```json
{
  "client_id": "your-client-id.apps.googleusercontent.com",
  "client_secret": "your-client-secret",
  "redirect_uri": "https://your-agentcore-endpoint/api/auth/callback",
  "workspace_domain": "example.com"
}
```

2. **JWT Secret** (`agentcore/scaffold/jwt-secret`):
```json
{
  "secret_key": "your-generated-secret-key-from-step-6"
}
```

**Using AWS CLI:**
```bash
# Store Google OAuth2 credentials
aws secretsmanager put-secret-value \
  --secret-id agentcore/scaffold/google-oauth2 \
  --secret-string '{"client_id":"your-client-id","client_secret":"your-secret","redirect_uri":"https://endpoint/api/auth/callback"}'

# Store JWT secret
aws secretsmanager put-secret-value \
  --secret-id agentcore/scaffold/jwt-secret \
  --secret-string '{"secret_key":"your-jwt-secret-key"}'
```

## Step 8: Update Redirect URI for Production

When deploying to AgentCore Runtime:

1. **Get your AgentCore Runtime endpoint** from the CDK stack outputs
2. **Update Google Cloud Console**:
   - Go to **APIs & Services** > **Credentials**
   - Click on your OAuth 2.0 Client ID
   - Add the production redirect URI: `https://<your-agentcore-endpoint>/api/auth/callback`
   - Add the production JavaScript origin: `https://<your-agentcore-endpoint>`
   - Click **Save**
3. **Update Secrets Manager** (if using):
   - Update the `redirect_uri` in the `agentcore/scaffold/google-oauth2` secret

## Step 9: Verify Configuration

### Test Locally

1. Start the application:
   ```bash
   python src/agent.py
   ```

2. Open browser to `http://localhost:8080`

3. Click "Sign in with Google"

4. You should be redirected to Google's consent screen

5. After authorization, you should be redirected back with a token

### Common Issues

**"Redirect URI mismatch" error:**
- Verify the redirect URI in `.env` matches **exactly** with Google Cloud Console
- Check for trailing slashes, http vs https, port numbers
- Ensure the URI is listed in "Authorized redirect URIs"

**"Access blocked: This app's request is invalid":**
- Check OAuth consent screen configuration
- Verify test users are added (for External app type)
- Check if app is in testing mode vs published

**"Invalid client secret":**
- Regenerate client secret in Google Cloud Console
- Update `.env` file or Secrets Manager with new secret

**Domain restriction not working:**
- Verify `GOOGLE_WORKSPACE_DOMAIN` is set correctly (without @ symbol)
- Check ID token contains `hd` claim (use browser dev tools)
- Verify user is from the specified domain

## Security Best Practices

1. **Never commit secrets to version control**
   - Use `.env` file locally (add to `.gitignore`)
   - Use AWS Secrets Manager in production

2. **Use strong JWT secrets**
   - Minimum 32 characters, preferably 64
   - Use cryptographically secure random generation

3. **Rotate secrets regularly**
   - Update OAuth client secret if compromised
   - Rotate JWT secret periodically

4. **Restrict OAuth scopes**
   - Only request scopes you actually need
   - Review and minimize scope permissions

5. **Use HTTPS in production**
   - Always use HTTPS for redirect URIs in production
   - Never use HTTP for production OAuth flows

## Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Google Workspace Admin Console](https://admin.google.com/)
- [AWS Secrets Manager Documentation](https://docs.aws.amazon.com/secretsmanager/)

## Troubleshooting

### Check OAuth2 Configuration

1. Verify client ID and secret are correct
2. Check redirect URI matches exactly
3. Ensure OAuth consent screen is configured
4. Verify required scopes are added

### Check JWT Configuration

1. Verify JWT secret is set and not empty
2. Check JWT algorithm matches (default: HS256)
3. Verify token expiration is reasonable (default: 60 minutes)

### Debug Authentication Flow

1. Check application logs for authentication errors
2. Use browser developer tools to inspect OAuth redirect
3. Verify ID token claims in browser console
4. Check CloudWatch Logs (for AgentCore Runtime deployment)

