#!/usr/bin/env python3
"""
MFA Fix: Pre-authenticate once and cache credentials for all subsequent AWS calls.
This eliminates multiple MFA prompts during development workflows.

Automatically loads configuration from .env file in project root.
"""

import os
import sys
import boto3
import json
import tempfile
from datetime import datetime, timedelta, UTC
from pathlib import Path

# Auto-load .env file from project root
def load_env_file():
    """Load .env file from project root automatically."""
    # Find project root (look for .env file)
    current_dir = Path(__file__).resolve()
    project_root = None
    
    # Walk up the directory tree to find .env file
    for parent in [current_dir.parent.parent.parent] + list(current_dir.parents):
        env_file = parent / '.env'
        if env_file.exists():
            project_root = parent
            break
    
    if project_root:
        env_file = project_root / '.env'
        print(f"📋 Loading configuration from: {env_file}")
        
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Only set if not already in environment
                        if key not in os.environ:
                            os.environ[key] = value
            return True
        except Exception as e:
            print(f"⚠️  Could not load .env file: {e}")
            return False
    else:
        print("⚠️  No .env file found - using existing environment variables")
        return False

# Load .env file automatically
load_env_file()

def get_cached_credentials_path():
    """Get path for cached credentials file."""
    return Path(tempfile.gettempdir()) / "aws_mfa_cache" / f"{os.getenv('AWS_PROFILE', 'default')}_credentials.json"

def load_cached_credentials():
    """Load cached credentials if they exist and are still valid."""
    cache_file = get_cached_credentials_path()
    
    if not cache_file.exists():
        return None
        
    try:
        with open(cache_file, 'r') as f:
            cached_data = json.load(f)
        
        # Check if credentials are still valid (with 5 minute buffer)
        expiry_time = datetime.fromisoformat(cached_data['expiry'])
        if datetime.now(UTC) + timedelta(minutes=5) < expiry_time:
            print(f"✅ Using cached AWS credentials (expires: {cached_data['expiry']})")
            return cached_data['credentials']
        else:
            print(f"⏰ Cached credentials expired ({cached_data['expiry']})")
            cache_file.unlink()  # Remove expired cache
            
    except Exception as e:
        print(f"⚠️ Error reading cached credentials: {e}")
        if cache_file.exists():
            cache_file.unlink()
            
    return None

def save_credentials_to_cache(credentials, expiry_time):
    """Save credentials to cache file."""
    cache_file = get_cached_credentials_path()
    cache_file.parent.mkdir(exist_ok=True)
    
    cache_data = {
        'credentials': credentials,
        'expiry': expiry_time.isoformat()
    }
    
    with open(cache_file, 'w') as f:
        json.dump(cache_data, f)
    
    # Set restrictive permissions
    os.chmod(cache_file, 0o600)
    print(f"✅ Cached credentials until {expiry_time}")

def authenticate_with_mfa():
    """Authenticate once with MFA and cache the credentials."""
    aws_profile = os.getenv('AWS_PROFILE')
    region = os.getenv('AWS_REGION', 'us-east-1')
    project_name = os.getenv('PROJECT_NAME', 'my-agent')
    
    print("🔐 AWS MFA Authentication")
    print("=" * 40)
    print(f"📋 Configuration loaded:")
    print(f"   AWS Profile: {aws_profile}")
    print(f"   AWS Region: {region}")
    print(f"   Project Name: {project_name}")
    print()
    
    if not aws_profile:
        print("❌ AWS_PROFILE not found in .env file or environment")
        print("💡 Add AWS_PROFILE=YourProfileName to your .env file")
        return None
    
    # Check for cached credentials first
    cached_creds = load_cached_credentials()
    if cached_creds:
        print("✅ Using cached credentials (no MFA prompt needed)")
        return cached_creds
    
    print(f"🔐 Authenticating with AWS profile: {aws_profile}")
    
    try:
        # Create session (this will prompt for MFA if needed)
        session = boto3.Session(profile_name=aws_profile, region_name=region)
        
        # Get credentials and account info
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        
        # Force credential resolution
        credentials = session.get_credentials()
        frozen_creds = credentials.get_frozen_credentials()
        
        # Calculate expiry time (typically 1 hour for assumed roles)
        expiry_time = datetime.now(UTC) + timedelta(hours=1)
        
        creds_dict = {
            'access_key': frozen_creds.access_key,
            'secret_key': frozen_creds.secret_key,
            'session_token': frozen_creds.token,
            'region': region,
            'account': identity['Account']
        }
        
        # Cache the credentials
        save_credentials_to_cache(creds_dict, expiry_time)
        
        print(f"✅ Authenticated successfully")
        print(f"   Account: {identity['Account']}")
        print(f"   Region: {region}")
        print(f"   User: {identity['Arn']}")
        
        return creds_dict
        
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return None

def set_environment_credentials(credentials):
    """Set AWS credentials as environment variables for all subprocesses."""
    if not credentials:
        return False
        
    os.environ['AWS_ACCESS_KEY_ID'] = credentials['access_key']
    os.environ['AWS_SECRET_ACCESS_KEY'] = credentials['secret_key']
    
    if credentials.get('session_token'):
        os.environ['AWS_SESSION_TOKEN'] = credentials['session_token']
    
    os.environ['AWS_DEFAULT_REGION'] = credentials['region']
    os.environ['AWS_ACCOUNT_ID'] = credentials['account']
    
    # Keep profile for reference but credentials take precedence
    if os.getenv('AWS_PROFILE'):
        os.environ['AWS_PROFILE'] = os.getenv('AWS_PROFILE')
    
    print("🔧 Set environment credentials for all AWS SDK calls")
    return True

def clear_credential_cache():
    """Clear the credential cache."""
    cache_file = get_cached_credentials_path()
    if cache_file.exists():
        cache_file.unlink()
        print("🧹 Cleared credential cache")
    else:
        print("ℹ️ No credential cache found")

def main():
    """Main function to handle MFA authentication and credential caching."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fix MFA prompts by caching credentials")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cached credentials")
    parser.add_argument("--status", action="store_true", help="Show current credential status")
    parser.add_argument("--export", action="store_true", help="Print export commands to set in shell")
    
    args = parser.parse_args()
    
    if args.clear_cache:
        clear_credential_cache()
        return
    
    if args.status:
        cached_creds = load_cached_credentials()
        if cached_creds:
            print(f"✅ Valid cached credentials found")
            print(f"   Account: {cached_creds.get('account')}")
            print(f"   Region: {cached_creds.get('region')}")
        else:
            print("❌ No valid cached credentials")
        return
    
    if args.export:
        cached_creds = load_cached_credentials()
        if cached_creds:
            # Use double quotes and proper escaping for shell safety
            import shlex
            print(f"export AWS_ACCESS_KEY_ID={shlex.quote(cached_creds['access_key'])}")
            print(f"export AWS_SECRET_ACCESS_KEY={shlex.quote(cached_creds['secret_key'])}")
            if cached_creds.get('session_token'):
                print(f"export AWS_SESSION_TOKEN={shlex.quote(cached_creds['session_token'])}")
            print(f"export AWS_DEFAULT_REGION={shlex.quote(cached_creds['region'])}")
            print(f"export AWS_ACCOUNT_ID={shlex.quote(cached_creds['account'])}")
        else:
            print("❌ No cached credentials found")
        return
    
    # Authenticate and set up environment
    credentials = authenticate_with_mfa()
    if credentials:
        set_environment_credentials(credentials)
        
        print("\n🎯 ZERO MFA SOLUTION - Copy and run these commands:")
        print("="*70)
        import shlex
        print(f"export AWS_ACCESS_KEY_ID={shlex.quote(credentials['access_key'])}")
        print(f"export AWS_SECRET_ACCESS_KEY={shlex.quote(credentials['secret_key'])}")
        if credentials.get('session_token'):
            print(f"export AWS_SESSION_TOKEN={shlex.quote(credentials['session_token'])}")
        print(f"export AWS_DEFAULT_REGION={shlex.quote(credentials['region'])}")
        print(f"export AWS_ACCOUNT_ID={shlex.quote(credentials['account'])}")
        # CRITICAL: Remove AWS_PROFILE to prevent any profile-based credential lookups
        print("unset AWS_PROFILE")
        print("="*70)
        print("\nThen run your agent commands:")
        print("   python dev_workflows.py agent-hybrid")
        print("   python scripts/dev/agent_modes.py --mode hybrid")
        
        print(f"\n💡 ZERO-MFA Test: unset AWS_PROFILE && python dev_workflows.py agent-hybrid")
        
    else:
        print("❌ Failed to authenticate")
        sys.exit(1)

if __name__ == "__main__":
    main()
