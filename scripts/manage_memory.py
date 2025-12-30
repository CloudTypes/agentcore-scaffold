#!/usr/bin/env python3
"""AgentCore Memory Management Script.

Create and delete AgentCore memory resources with strategies.
Based on AWS sample: https://github.com/awslabs/amazon-bedrock-agentcore-samples
"""

import click
import boto3
import sys
import os
import json
from pathlib import Path
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load .env file from project root
script_dir = Path(__file__).parent
project_root = script_dir.parent
env_file = project_root / '.env'
if env_file.exists():
    load_dotenv(env_file)

# Try to import AgentCore Memory SDK
try:
    from bedrock_agentcore.memory import MemoryClient
    from bedrock_agentcore.memory import MemoryControlPlaneClient
    from bedrock_agentcore.memory.constants import StrategyType
except ImportError:
    click.echo("❌ bedrock-agentcore package not found. Install it with: pip install bedrock-agentcore", err=True)
    sys.exit(1)

# Get region from environment or default
REGION = os.getenv("AWS_REGION") or os.getenv("AGENTCORE_MEMORY_REGION") or "us-east-1"

# Initialize clients (will be recreated if region changes)
def get_ssm_client(region=None):
    """Get SSM client for specified region."""
    return boto3.client("ssm", region_name=region or REGION)

def get_secrets_client(region=None):
    """Get Secrets Manager client for specified region."""
    return boto3.client("secretsmanager", region_name=region or REGION)

# Default clients for current region
ssm = get_ssm_client()
secrets_client = get_secrets_client()
memory_client = MemoryClient(region_name=REGION)

# Configuration
# Memory name must match pattern: [a-zA-Z][a-zA-Z0-9_]{0,47} (no hyphens, must start with letter)
MEMORY_NAME = "voice_agent_memory"
SSM_PARAM = "/agentcore/voice-agent/memory-id"
SECRET_NAME = "agentcore/voice-agent/memory-id"
EVENT_EXPIRY_DAYS = 30


def store_memory_id(memory_id: str):
    """Store memory ID in both SSM and Secrets Manager."""
    try:
        # Store in SSM
        ssm.put_parameter(
            Name=SSM_PARAM,
            Value=memory_id,
            Type="String",
            Overwrite=True
        )
        click.echo(f"🔐 Stored memory_id in SSM: {SSM_PARAM}")
    except Exception as e:
        click.echo(f"⚠️  Failed to store in SSM: {e}")
    
    try:
        # Store in Secrets Manager
        try:
            secrets_client.create_secret(
                Name=SECRET_NAME,
                SecretString=json.dumps({"memory_id": memory_id}),
                Description="AgentCore Memory resource ID"
            )
            click.echo(f"🔐 Created memory_id in Secrets Manager: {SECRET_NAME}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceExistsException':
                secrets_client.update_secret(
                    SecretId=SECRET_NAME,
                    SecretString=json.dumps({"memory_id": memory_id})
                )
                click.echo(f"🔐 Updated memory_id in Secrets Manager: {SECRET_NAME}")
            else:
                raise
    except Exception as e:
        click.echo(f"⚠️  Failed to store in Secrets Manager: {e}")


def get_memory_id(show_debug=False, region=None):
    """Get memory ID from environment variable, SSM, or Secrets Manager."""
    check_region = region or REGION
    
    # First, try environment variables (useful for direct testing)
    memory_arn = os.getenv("AGENTCORE_MEMORY_ARN", "")
    memory_id_env = os.getenv("AGENTCORE_MEMORY_ID", "")
    
    if memory_arn:
        memory_id = get_memory_id_from_arn(memory_arn)
        if show_debug:
            click.echo(f"🔍 Looking for memory ID in region: {check_region}")
            click.echo(f"   ✅ Found in environment variable AGENTCORE_MEMORY_ARN: {memory_id}")
        return memory_id
    
    if memory_id_env:
        if show_debug:
            click.echo(f"🔍 Looking for memory ID in region: {check_region}")
            click.echo(f"   ✅ Found in environment variable AGENTCORE_MEMORY_ID: {memory_id_env}")
        return memory_id_env
    
    # Fall back to SSM and Secrets Manager
    ssm_client = get_ssm_client(check_region)
    secrets_mgr_client = get_secrets_client(check_region)
    
    if show_debug:
        click.echo(f"🔍 Looking for memory ID in region: {check_region}")
        click.echo(f"   SSM Parameter: {SSM_PARAM}")
        click.echo(f"   Secrets Manager: {SECRET_NAME}")
    
    # Try SSM first
    try:
        if show_debug:
            click.echo(f"   Checking SSM Parameter Store...")
        response = ssm_client.get_parameter(Name=SSM_PARAM)
        memory_id = response["Parameter"]["Value"]
        if show_debug:
            click.echo(f"   ✅ Found in SSM: {memory_id}")
        return memory_id
    except ClientError as e:
        if show_debug:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', '')
            click.echo(f"   ❌ SSM error: {error_code}")
            if error_msg:
                click.echo(f"      {error_msg}")
        # Try Secrets Manager as fallback
        try:
            if show_debug:
                click.echo(f"   Checking Secrets Manager...")
            response = secrets_mgr_client.get_secret_value(SecretId=SECRET_NAME)
            secret_data = json.loads(response["SecretString"])
            memory_id = secret_data.get("memory_id") or response["SecretString"]
            if show_debug:
                click.echo(f"   ✅ Found in Secrets Manager: {memory_id}")
            return memory_id
        except ClientError as e2:
            if show_debug:
                error_code = e2.response.get('Error', {}).get('Code', 'Unknown')
                error_msg = e2.response.get('Error', {}).get('Message', '')
                click.echo(f"   ❌ Secrets Manager error: {error_code}")
                if error_msg:
                    click.echo(f"      {error_msg}")
            return None
        except json.JSONDecodeError:
            if show_debug:
                click.echo(f"   ❌ Secrets Manager: Invalid JSON")
            return None


def sanitize_actor_id(actor_id: str) -> str:
    """
    Sanitize actor_id to match AgentCore Memory requirements.
    Pattern: [a-zA-Z0-9][a-zA-Z0-9-_/]*(?::[a-zA-Z0-9-_/]+)*[a-zA-Z0-9-_/]*
    Replaces @ with _ and ensures it starts with alphanumeric.
    """
    # Replace @ with _ and ensure it starts with alphanumeric
    sanitized = actor_id.replace("@", "_").replace(".", "_")
    # Ensure it starts with alphanumeric
    if not sanitized[0].isalnum():
        sanitized = "user_" + sanitized
    return sanitized


def get_memory_id_from_arn(arn: str) -> str:
    """Extract memory ID from ARN."""
    # ARN format: arn:aws:bedrock-agentcore:region:account:memory/ID
    if "/" in arn:
        return arn.split("/")[-1]
    return arn


@click.group()
def cli():
    """AgentCore Memory Management CLI."""
    pass


@cli.command()
def create():
    """Create a new AgentCore memory resource with strategies."""
    click.echo(f"🚀 Creating AgentCore memory: {MEMORY_NAME}")
    click.echo(f"📍 Region: {REGION}")
    click.echo(f"⏱️  Event expiry: {EVENT_EXPIRY_DAYS} days")

    # Format strategies using StrategyType constants (matches AWS sample pattern)
    # Each strategy requires a "name" field
    strategies = [
        {
            StrategyType.SUMMARY.value: {
                "name": "SessionSummarizer",
                "description": "Captures summaries of conversations",
                "namespaces": ["/summaries/{actorId}/{sessionId}"]
            }
        },
        {
            StrategyType.USER_PREFERENCE.value: {
                "name": "UserPreferences",
                "description": "Captures user preferences and behavior",
                "namespaces": ["/preferences/{actorId}"]
            }
        },
        {
            StrategyType.SEMANTIC.value: {
                "name": "SemanticMemory",
                "description": "Stores factual information using vector embeddings",
                "namespaces": ["/semantic/{actorId}"]
            }
        }
    ]

    try:
        click.echo("🔄 Creating memory resource with strategies...")
        memory = memory_client.create_memory(
            name=MEMORY_NAME,
            strategies=strategies,
            description="Memory resource for voice agent with short-term and long-term memory",
            event_expiry_days=EVENT_EXPIRY_DAYS
        )
        memory_id = memory.get("memoryId") or memory.get("id")
        click.echo(f"✅ Memory created successfully: {memory_id}")

    except Exception as e:
        if "already exists" in str(e).lower():
            click.echo("📋 Memory already exists, finding existing resource...")
            control_plane = MemoryControlPlaneClient(region_name=REGION)
            memories = control_plane.list_memories()
            memory_id = next(
                (m.get("memoryId") or m.get("id") 
                 for m in memories 
                 if MEMORY_NAME in m.get("name", "")), 
                None
            )
            if memory_id:
                click.echo(f"✅ Using existing memory: {memory_id}")
            else:
                click.echo("❌ Could not find existing memory resource", err=True)
                sys.exit(1)
        else:
            click.echo(f"❌ Error creating memory: {str(e)}", err=True)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    try:
        store_memory_id(memory_id)
        click.echo("🎉 Memory setup completed successfully!")
        click.echo(f"   Memory ID: {memory_id}")
        click.echo(f"   SSM Parameter: {SSM_PARAM}")
        click.echo(f"   Secrets Manager: {SECRET_NAME}")

    except Exception as e:
        click.echo(f"⚠️  Memory created but failed to store ID: {str(e)}", err=True)


@cli.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete(confirm):
    """Delete the AgentCore memory resource."""
    memory_id = get_memory_id(show_debug=True)
    
    if not memory_id:
        click.echo("")
        click.echo("❌ No memory ID found in SSM or Secrets Manager", err=True)
        click.echo(f"   Current region: {REGION}")
        click.echo(f"   SSM Parameter: {SSM_PARAM}")
        click.echo(f"   Secrets Manager: {SECRET_NAME}")
        sys.exit(1)

    if not confirm:
        if not click.confirm(
            f"⚠️  Are you sure you want to delete memory {memory_id}? This action cannot be undone."
        ):
            click.echo("❌ Operation cancelled")
            sys.exit(0)

    click.echo(f"🗑️  Deleting memory: {memory_id}")

    try:
        control_plane = MemoryControlPlaneClient(region_name=REGION)
        control_plane.delete_memory(memory_id=memory_id)
        click.echo(f"✅ Memory deleted successfully: {memory_id}")
    except Exception as e:
        click.echo(f"❌ Error deleting memory: {str(e)}", err=True)
        sys.exit(1)

    # Clean up stored IDs
    try:
        ssm.delete_parameter(Name=SSM_PARAM)
        click.echo(f"🧹 Deleted SSM parameter: {SSM_PARAM}")
    except Exception as e:
        click.echo(f"⚠️  Failed to delete SSM parameter: {e}")

    try:
        secrets_client.delete_secret(
            SecretId=SECRET_NAME,
            ForceDeleteWithoutRecovery=True
        )
        click.echo(f"🧹 Deleted Secrets Manager secret: {SECRET_NAME}")
    except Exception as e:
        click.echo(f"⚠️  Failed to delete Secrets Manager secret: {e}")

    click.echo("🎉 Memory and stored IDs deleted successfully")


@cli.command()
def status():
    """Check the status of the memory resource."""
    import json
    
    click.echo(f"🔍 Checking memory status in region: {REGION}")
    click.echo("")
    
    memory_id = get_memory_id(show_debug=True)
    
    if not memory_id:
        click.echo("")
        click.echo("❌ No memory ID found in SSM or Secrets Manager")
        click.echo("")
        click.echo("Troubleshooting:")
        click.echo(f"  • Current region: {REGION}")
        click.echo(f"  • SSM Parameter: {SSM_PARAM}")
        click.echo(f"  • Secrets Manager: {SECRET_NAME}")
        click.echo("")
        click.echo("Possible solutions:")
        click.echo("  1. Check if memory was created in a different region")
        click.echo("  2. Set AWS_REGION or AGENTCORE_MEMORY_REGION in .env file")
        click.echo("  3. Run 'python scripts/manage_memory.py create' to create memory")
        click.echo("  4. Manually check AWS Console for the parameter/secret")
        sys.exit(1)

    click.echo(f"📋 Memory ID: {memory_id}")
    
    try:
        control_plane = MemoryControlPlaneClient(region_name=REGION)
        memory = control_plane.get_memory(memory_id=memory_id)
        
        strategies = memory.get("strategies", [])
        click.echo(f"📊 Strategies: {len(strategies)}")
        if strategies:
            for strategy in strategies:
                strategy_type = strategy.get("type", "unknown")
                namespaces = strategy.get("namespaces", [])
                click.echo(f"   - {strategy_type}: {', '.join(namespaces)}")
        else:
            click.echo("   ⚠️  No strategies configured!")
        
        click.echo("✅ Memory is active and configured")
    except Exception as e:
        click.echo(f"❌ Error checking memory status: {str(e)}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option("--actor-id", required=True, help="Actor ID (user email)")
@click.option("--session-id", required=True, help="Session ID to query")
@click.option("--try-all-namespaces", is_flag=True, help="Try multiple namespace patterns to find the session")
@click.option("--memory-id", help="Override memory ID (useful for direct testing or ARN)")
def query_session(actor_id, session_id, try_all_namespaces, memory_id):
    """Query a specific session summary from AgentCore Memory."""
    # Allow direct memory ID override (supports both ID and ARN)
    if memory_id:
        if memory_id.startswith("arn:"):
            memory_id = get_memory_id_from_arn(memory_id)
        click.echo(f"💡 Using provided memory ID: {memory_id}")
    else:
        memory_id = get_memory_id(show_debug=True)
    
    if not memory_id:
        click.echo("")
        click.echo("❌ No memory ID found in SSM or Secrets Manager", err=True)
        click.echo("")
        click.echo("Troubleshooting:")
        click.echo(f"  • Current region: {REGION}")
        click.echo(f"  • SSM Parameter: {SSM_PARAM}")
        click.echo(f"  • Secrets Manager: {SECRET_NAME}")
        click.echo("")
        click.echo("Possible solutions:")
        click.echo("  1. Check if memory was created in a different region")
        click.echo("  2. Set AWS_REGION or AGENTCORE_MEMORY_REGION in .env file")
        click.echo("  3. Run 'python scripts/manage_memory.py create' to create memory")
        sys.exit(1)
    
    # Sanitize actor_id
    sanitized_actor_id = sanitize_actor_id(actor_id)
    
    # Try different namespace patterns
    namespaces_to_try = [
        f"/summaries/{sanitized_actor_id}/{session_id}",  # Expected pattern
    ]
    
    if try_all_namespaces:
        # Also try with unsanitized actor_id (in case AgentCore uses raw value)
        namespaces_to_try.extend([
            f"/summaries/{actor_id}/{session_id}",
            f"/summaries/{actor_id.replace('@', '_')}/{session_id}",
        ])
    
    click.echo(f"🔍 Querying session: {session_id}")
    click.echo(f"👤 Actor: {actor_id} (sanitized: {sanitized_actor_id})")
    click.echo(f"💾 Memory ID: {memory_id}")
    click.echo(f"🌍 Region: {REGION}")
    click.echo("")
    
    client = MemoryClient(region_name=REGION)
    records_found = False
    
    for namespace in namespaces_to_try:
        click.echo(f"📍 Trying namespace: {namespace}")
        # Try multiple query terms - summaries contain conversation topics
        # Based on logs, summaries have topics like "Initial Greeting"
        query_terms = [
            "greeting",      # From logs: "Initial Greeting"
            "initial",       # Topic name
            "conversation",  # Generic term
            "user",          # User interactions
            "assistant",     # Assistant responses
            "hello",         # Common greeting word
            "help",          # Common request
        ]
        records = []
        
        try:
            # First, try ListMemoryRecords (no semantic search required)
            # This is the recommended approach for listing all records in a namespace
            bedrock_client = boto3.client('bedrock-agentcore', region_name=REGION)
            
            # Try the exact namespace first
            try:
                response = bedrock_client.list_memory_records(
                    memoryId=memory_id,
                    namespace=namespace,
                    maxResults=10
                )
                
                found_records = response.get("memoryRecords", [])
                
                # Handle pagination if there's a nextToken
                next_token = response.get("nextToken")
                while next_token and len(found_records) < 10:
                    try:
                        next_response = bedrock_client.list_memory_records(
                            memoryId=memory_id,
                            namespace=namespace,
                            maxResults=10,
                            nextToken=next_token
                        )
                        found_records.extend(next_response.get("memoryRecords", []))
                        next_token = next_response.get("nextToken")
                    except Exception:
                        break
                
                if found_records:
                    records = found_records
                    click.echo(f"   ✅ Found {len(records)} record(s) using ListMemoryRecords")
                else:
                    click.echo(f"   ❌ No records found with ListMemoryRecords in exact namespace")
                    click.echo(f"   💡 Note: There may be an indexing delay (records can take 1-2 minutes to appear)")
                    
                    # Try parent namespace (without session ID)
                    parent_namespace = f"/summaries/{sanitized_actor_id}"
                    try:
                        response = bedrock_client.list_memory_records(
                            memoryId=memory_id,
                            namespace=parent_namespace,
                            maxResults=100
                        )
                        found_records = response.get("memoryRecords", [])
                        
                        # Handle pagination
                        next_token = response.get("nextToken")
                        while next_token:
                            try:
                                next_response = bedrock_client.list_memory_records(
                                    memoryId=memory_id,
                                    namespace=parent_namespace,
                                    maxResults=100,
                                    nextToken=next_token
                                )
                                found_records.extend(next_response.get("memoryRecords", []))
                                next_token = next_response.get("nextToken")
                            except Exception:
                                break
                        
                        # Filter for this session ID
                        for record in found_records:
                            record_ns = record.get("namespace", "")
                            if session_id in record_ns:
                                records.append(record)
                        if records:
                            click.echo(f"   ✅ Found {len(records)} record(s) in parent namespace (filtered by session ID)")
                    except Exception as e2:
                        click.echo(f"   ⚠️  Parent namespace query failed: {str(e2)[:100]}")
            except Exception as e:
                error_msg = str(e)
                click.echo(f"   ⚠️  ListMemoryRecords failed: {error_msg[:100]}")
                click.echo(f"   🔄 Falling back to semantic search...")
                
                # Fallback to semantic search
                for query_term in query_terms:
                    try:
                        response = client.retrieve_memory_records(
                            memoryId=memory_id,
                            namespace=namespace,
                            searchCriteria={
                                "searchQuery": query_term,
                                "topK": 1
                            }
                        )
                        found_records = response.get("memoryRecords", [])
                        if found_records:
                            records = found_records
                            click.echo(f"   ✅ Found with semantic search query: '{query_term}'")
                            break
                    except Exception:
                        continue
                
                # If still no records, try fallback terms
                if not records:
                    for fallback_term in ["summary", "session", "memory", "topic"]:
                        try:
                            response = client.retrieve_memory_records(
                                memoryId=memory_id,
                                namespace=namespace,
                                searchCriteria={
                                    "searchQuery": fallback_term,
                                    "topK": 1
                                }
                            )
                            found_records = response.get("memoryRecords", [])
                            if found_records:
                                records = found_records
                                click.echo(f"   ✅ Found with fallback query: '{fallback_term}'")
                                break
                        except Exception:
                            continue
            
            if records:
                records_found = True
                click.echo(f"✅ Found {len(records)} record(s) in namespace: {namespace}")
                click.echo("")
                for i, record in enumerate(records, 1):
                    click.echo(f"--- Record {i} ---")
                    click.echo(f"Namespace: {record.get('namespace', 'N/A')}")
                    
                    content = record.get("content", {})
                    if isinstance(content, dict):
                        text = content.get("text", "")
                        if text:
                            click.echo(f"Summary:")
                            click.echo(f"  {text}")
                        else:
                            click.echo("Summary: (empty)")
                    else:
                        click.echo(f"Content: {content}")
                    
                    # Show other fields if present
                    metadata = {k: v for k, v in record.items() if k not in ("namespace", "content")}
                    if metadata:
                        click.echo(f"Metadata: {json.dumps(metadata, indent=2)}")
                    
                    if i < len(records):
                        click.echo("")
                break  # Found records, stop trying other namespaces
            else:
                click.echo(f"  ❌ No records in this namespace")
        except Exception as e:
            click.echo(f"  ⚠️  Error querying namespace: {str(e)}")
    
    if not records_found:
        click.echo("")
        click.echo("❌ No records found in any namespace")
        click.echo("")
        click.echo("Possible reasons:")
        click.echo("  • Summary hasn't been generated yet (wait 20-40 seconds after session end)")
        click.echo("  • Summary generation may take longer for short conversations")
        click.echo("  • Memory strategies not configured correctly")
        click.echo("  • Session ID or actor ID is incorrect")
        click.echo("  • Events may not have been stored properly")
        click.echo("")
        click.echo("Troubleshooting steps:")
        click.echo("  1. Verify memory has strategies: python scripts/manage_memory.py status")
        click.echo("  2. Check server logs for event storage errors")
        click.echo("  3. Try with --try-all-namespaces flag to test different namespace patterns")
        click.echo("  4. Wait longer (summaries can take 1-2 minutes for some conversations)")
        sys.exit(1)


@cli.command()
@click.option("--actor-id", required=True, help="Actor ID (user email)")
@click.option("--namespace-prefix", default="/summaries", help="Namespace prefix to search (default: /summaries)")
@click.option("--top-k", default=50, help="Maximum number of records to retrieve")
@click.option("--use-list-api", is_flag=True, help="Use ListMemoryRecords API instead of semantic search")
@click.option("--memory-id", help="Override memory ID (useful for direct testing or ARN)")
def list_namespaces(actor_id, namespace_prefix, top_k, use_list_api, memory_id):
    """List all memory records in a namespace prefix to see what's actually stored."""
    # Allow direct memory ID override (supports both ID and ARN)
    if memory_id:
        if memory_id.startswith("arn:"):
            memory_id = get_memory_id_from_arn(memory_id)
        click.echo(f"💡 Using provided memory ID: {memory_id}")
    else:
        memory_id = get_memory_id(show_debug=True)
    
    if not memory_id:
        click.echo("")
        click.echo("❌ No memory ID found in SSM or Secrets Manager", err=True)
        sys.exit(1)
    
    # Sanitize actor_id
    sanitized_actor_id = sanitize_actor_id(actor_id)
    
    # Try different namespace patterns
    namespaces_to_try = [
        f"{namespace_prefix}/{sanitized_actor_id}",
        f"{namespace_prefix}/{actor_id}",
    ]
    
    click.echo("")
    click.echo(f"🔍 Searching for records in namespace prefix: {namespace_prefix}")
    click.echo(f"👤 Actor: {actor_id} (sanitized: {sanitized_actor_id})")
    click.echo(f"💾 Memory ID: {memory_id}")
    click.echo(f"🌍 Region: {REGION}")
    click.echo("")
    
    client = MemoryClient(region_name=REGION)
    total_records = 0
    
    bedrock_client = boto3.client('bedrock-agentcore', region_name=REGION)
    
    for namespace in namespaces_to_try:
        click.echo(f"📍 Querying namespace: {namespace}")
        
        # If use_list_api flag is set, try ListMemoryRecords first
        if use_list_api:
            try:
                response = bedrock_client.list_memory_records(
                    memoryId=memory_id,
                    namespace=namespace,
                    maxResults=top_k
                )
                records = response.get("memoryRecords", [])
                if records:
                    total_records += len(records)
                    click.echo(f"   ✅ Found {len(records)} record(s) using ListMemoryRecords")
                    for i, record in enumerate(records[:5], 1):
                        actual_namespace = record.get("namespace", "N/A")
                        click.echo(f"      {i}. Namespace: {actual_namespace}")
                        content = record.get("content", {})
                        if isinstance(content, dict):
                            text = content.get("text", "")
                            if text:
                                preview = text[:100] + "..." if len(text) > 100 else text
                                click.echo(f"         Preview: {preview}")
                    continue  # Found records, skip semantic search
                else:
                    click.echo(f"   ❌ No records with ListMemoryRecords")
            except Exception as e:
                click.echo(f"   ⚠️  ListMemoryRecords failed: {str(e)[:100]}")
        
        # Fallback to semantic search
        try:
            # Use a very broad query to get any records
            response = client.retrieve_memory_records(
                memoryId=memory_id,
                namespace=namespace,
                searchCriteria={
                    "searchQuery": "*",  # Try wildcard
                    "topK": top_k
                }
            )
            
            records = response.get("memoryRecords", [])
            
            if records:
                total_records += len(records)
                click.echo(f"   ✅ Found {len(records)} record(s)")
                for i, record in enumerate(records[:5], 1):  # Show first 5
                    actual_namespace = record.get("namespace", "N/A")
                    click.echo(f"      {i}. Namespace: {actual_namespace}")
                    content = record.get("content", {})
                    if isinstance(content, dict):
                        text = content.get("text", "")
                        if text:
                            preview = text[:100] + "..." if len(text) > 100 else text
                            click.echo(f"         Preview: {preview}")
            else:
                click.echo(f"   ❌ No records")
        except Exception as e:
            error_msg = str(e)
            if "ValidationException" in error_msg and "searchQuery" in error_msg:
                # Wildcard not supported, try a different query
                try:
                    response = client.retrieve_memory_records(
                        memoryId=memory_id,
                        namespace=namespace,
                        searchCriteria={
                            "searchQuery": "summary",  # Try generic term
                            "topK": top_k
                        }
                    )
                    records = response.get("memoryRecords", [])
                    if records:
                        total_records += len(records)
                        click.echo(f"   ✅ Found {len(records)} record(s) (with 'summary' query)")
                        for i, record in enumerate(records[:5], 1):
                            actual_namespace = record.get("namespace", "N/A")
                            click.echo(f"      {i}. Namespace: {actual_namespace}")
                    else:
                        click.echo(f"   ❌ No records (even with 'summary' query)")
                except Exception as e2:
                    click.echo(f"   ⚠️  Error: {str(e2)[:100]}")
            else:
                click.echo(f"   ⚠️  Error: {error_msg[:100]}")
    
    click.echo("")
    if total_records > 0:
        click.echo(f"✅ Total records found: {total_records}")
        click.echo("")
        click.echo("💡 Tip: Check the actual namespaces above to see the pattern AgentCore Memory is using")
    else:
        click.echo("❌ No records found in any namespace")
        click.echo("")
        click.echo("This could mean:")
        click.echo("  • Summaries haven't been generated yet")
        click.echo("  • Events weren't stored properly")
        click.echo("  • The namespace pattern is different than expected")
        click.echo("")
        click.echo("Check server logs to verify events are being stored.")


@cli.command("list-all-records")
@click.option("--top-k", default=100, help="Maximum number of records to retrieve")
@click.option("--memory-id", help="Override memory ID (useful for direct testing or ARN)")
def list_all_records(top_k, memory_id):
    """List ALL memory records across all namespaces to see what's actually stored."""
    # Allow direct memory ID override (supports both ID and ARN)
    if memory_id:
        if memory_id.startswith("arn:"):
            memory_id = get_memory_id_from_arn(memory_id)
        click.echo(f"💡 Using provided memory ID: {memory_id}")
    else:
        memory_id = get_memory_id(show_debug=True)
    
    if not memory_id:
        click.echo("")
        click.echo("❌ No memory ID found in SSM or Secrets Manager", err=True)
        sys.exit(1)
    
    click.echo("")
    click.echo(f"🔍 Listing ALL memory records (up to {top_k})")
    click.echo(f"💾 Memory ID: {memory_id}")
    click.echo(f"🌍 Region: {REGION}")
    click.echo("")
    click.echo("⚠️  Note: This queries common namespace patterns. If records are in")
    click.echo("   unexpected namespaces, they may not appear here.")
    click.echo("")
    
    client = MemoryClient(region_name=REGION)
    all_records = []
    namespaces_checked = []
    
    # Common namespace patterns to check
    namespace_patterns = [
        "/summaries",  # Root summaries
        "/preferences",  # Root preferences
        "/semantic",  # Root semantic
    ]
    
    # Also try with common actor ID patterns
    common_actor_patterns = [
        "nathan_cloudtypes_io",
        "nathan@cloudtypes.io",
        "nathan.cloudtypes.io",
    ]
    
    # Known session ID from user's logs
    known_session_id = "120f7fbd-42c1-4397-a24b-244e7ad9a02f"
    
    # Try different query terms that might match summaries
    # Use terms from the actual conversation
    query_terms = ["summary", "conversation", "session", "user", "weather", "denver", "colorado", "hello", "help"]
    
    for base_ns in namespace_patterns:
        # Try root namespace with different queries
        for query_term in query_terms:
            namespaces_checked.append(f"{base_ns} (query: {query_term})")
            try:
                response = client.retrieve_memory_records(
                    memoryId=memory_id,
                    namespace=base_ns,
                    searchCriteria={
                        "searchQuery": query_term,
                        "topK": top_k
                    }
                )
                records = response.get("memoryRecords", [])
                if records:
                    click.echo(f"✅ Found {len(records)} record(s) in namespace: {base_ns} (query: '{query_term}')")
                    all_records.extend(records)
                    # Show unique namespaces found
                    unique_ns = set(r.get("namespace", "") for r in records)
                    for ns in sorted(unique_ns)[:10]:  # Show first 10 unique namespaces
                        click.echo(f"   - {ns}")
                    if len(unique_ns) > 10:
                        click.echo(f"   ... and {len(unique_ns) - 10} more namespaces")
                    break  # Found records, try next namespace
            except Exception as e:
                error_msg = str(e)
                if "ValidationException" in error_msg and "namespace" in error_msg.lower():
                    # Can't query root namespace, skip
                    break
                # Continue trying other query terms
        
        # Try with actor ID patterns
        for actor_pattern in common_actor_patterns:
            ns = f"{base_ns}/{actor_pattern}"
            for query_term in query_terms:
                namespaces_checked.append(f"{ns} (query: {query_term})")
                try:
                    response = client.retrieve_memory_records(
                        memoryId=memory_id,
                        namespace=ns,
                        searchCriteria={
                            "searchQuery": query_term,
                            "topK": top_k
                        }
                    )
                    records = response.get("memoryRecords", [])
                    if records:
                        click.echo(f"✅ Found {len(records)} record(s) in namespace: {ns} (query: '{query_term}')")
                        all_records.extend(records)
                        # Show unique namespaces found
                        unique_ns = set(r.get("namespace", "") for r in records)
                        for ns_found in sorted(unique_ns)[:5]:
                            click.echo(f"   - {ns_found}")
                        break  # Found records, try next actor pattern
                except Exception as e:
                    error_msg = str(e)
                    if "ValidationException" in error_msg:
                        # Invalid namespace pattern, skip this actor pattern
                        break
                    # Continue trying other query terms
    
    # Also try querying the known session ID namespace directly
    click.echo("")
    click.echo("🔍 Trying known session ID namespace...")
    for actor_pattern in common_actor_patterns:
        ns = f"/summaries/{actor_pattern}/{known_session_id}"
        for query_term in query_terms:
            try:
                response = client.retrieve_memory_records(
                    memoryId=memory_id,
                    namespace=ns,
                    searchCriteria={
                        "searchQuery": query_term,
                        "topK": top_k
                    }
                )
                records = response.get("memoryRecords", [])
                if records:
                    click.echo(f"✅ Found {len(records)} record(s) in namespace: {ns} (query: '{query_term}')")
                    all_records.extend(records)
                    # Show the actual namespace from the record
                    for record in records:
                        actual_ns = record.get("namespace", "N/A")
                        click.echo(f"   Actual namespace: {actual_ns}")
                        content = record.get("content", {})
                        if isinstance(content, dict):
                            text = content.get("text", "")
                            if text:
                                click.echo(f"   Content preview: {text[:200]}")
                    break
            except Exception as e:
                error_msg = str(e)
                if "ValidationException" in error_msg and "namespace" in error_msg.lower():
                    break
                # Continue trying other query terms
    
    click.echo("")
    if all_records:
        # Group by namespace
        by_namespace = {}
        for record in all_records:
            ns = record.get("namespace", "unknown")
            if ns not in by_namespace:
                by_namespace[ns] = []
            by_namespace[ns].append(record)
        
        click.echo(f"📊 Summary: Found {len(all_records)} total records in {len(by_namespace)} unique namespaces")
        click.echo("")
        click.echo("Namespaces with records:")
        for ns in sorted(by_namespace.keys()):
            count = len(by_namespace[ns])
            click.echo(f"  • {ns}: {count} record(s)")
            
            # Show a sample record
            sample = by_namespace[ns][0]
            content = sample.get("content", {})
            if isinstance(content, dict):
                text = content.get("text", "")
                if text:
                    preview = text[:150] + "..." if len(text) > 150 else text
                    click.echo(f"    Sample: {preview}")
    else:
        click.echo("❌ No records found in any checked namespace")
        click.echo("")
        click.echo("This could mean:")
        click.echo("  • Records are in namespaces we didn't check")
        click.echo("  • The query terms don't match the content")
        click.echo("  • Records haven't been indexed yet")
        click.echo("")
        click.echo("💡 Tip: Check AWS Console > AgentCore Memory observability")
        click.echo("   to see actual API calls and memory extraction counts")


@cli.command()
@click.option("--actor-id", required=True, help="Actor ID (user email)")
@click.option("--session-id", help="Optional session ID to filter by")
@click.option("--memory-id", help="Override memory ID (useful for direct testing or ARN)")
def debug_memory(actor_id, session_id, memory_id):
    """Debug memory records - shows what's actually stored using multiple methods."""
    # Allow direct memory ID override (supports both ID and ARN)
    if memory_id:
        if memory_id.startswith("arn:"):
            memory_id = get_memory_id_from_arn(memory_id)
        click.echo(f"💡 Using provided memory ID: {memory_id}")
    else:
        memory_id = get_memory_id(show_debug=True)
    
    if not memory_id:
        click.echo("")
        click.echo("❌ No memory ID found in SSM or Secrets Manager", err=True)
        sys.exit(1)
    
    sanitized_actor_id = sanitize_actor_id(actor_id)
    bedrock_client = boto3.client('bedrock-agentcore', region_name=REGION)
    
    click.echo("")
    click.echo("🔍 Debugging memory records")
    click.echo(f"👤 Actor: {actor_id} (sanitized: {sanitized_actor_id})")
    click.echo(f"💾 Memory ID: {memory_id}")
    click.echo(f"🌍 Region: {REGION}")
    if session_id:
        click.echo(f"📋 Session ID: {session_id}")
    click.echo("")
    
    # Try different namespace levels
    namespaces_to_try = [
        f"/summaries/{sanitized_actor_id}",
    ]
    
    if session_id:
        namespaces_to_try.insert(0, f"/summaries/{sanitized_actor_id}/{session_id}")
    
    all_records = []
    
    for ns in namespaces_to_try:
        click.echo(f"📍 Testing namespace: {ns}")
        
        # Method 1: ListMemoryRecords
        try:
            response = bedrock_client.list_memory_records(
                memoryId=memory_id,
                namespace=ns,
                maxResults=100
            )
            records = response.get("memoryRecords", [])
            click.echo(f"   ListMemoryRecords: {len(records)} record(s)")
            if records:
                for i, record in enumerate(records[:3], 1):
                    record_ns = record.get("namespace", "N/A")
                    click.echo(f"      {i}. Namespace: {record_ns}")
                    if session_id and session_id not in record_ns:
                        continue
                    all_records.append(record)
        except Exception as e:
            click.echo(f"   ListMemoryRecords: Error - {str(e)[:100]}")
        
        # Method 2: Try semantic search with various terms
        client = MemoryClient(region_name=REGION)
        search_terms = ["greeting", "conversation", "user", "hello", "initial", "topic", "weather", "square root", "colorado"]
        semantic_found = False
        for term in search_terms:
            try:
                response = client.retrieve_memory_records(
                    memoryId=memory_id,
                    namespace=ns,
                    searchCriteria={
                        "searchQuery": term,
                        "topK": 10
                    }
                )
                records = response.get("memoryRecords", [])
                if records:
                    click.echo(f"   Semantic search ('{term}'): {len(records)} record(s)")
                    semantic_found = True
                    for record in records:
                        # Check if this record is already in all_records by comparing namespace
                        record_ns = record.get("namespace", "")
                        if not any(r.get("namespace", "") == record_ns for r in all_records):
                            all_records.append(record)
                    break
            except Exception as e:
                continue
        
        if not semantic_found:
            click.echo(f"   Semantic search: No records found with any query term")
    
    click.echo("")
    if all_records:
        click.echo(f"✅ Total unique records found: {len(all_records)}")
        click.echo("")
        for i, record in enumerate(all_records[:5], 1):
            click.echo(f"--- Record {i} ---")
            click.echo(f"Namespace: {record.get('namespace', 'N/A')}")
            content = record.get("content", {})
            if isinstance(content, dict):
                text = content.get("text", "")
                if text:
                    preview = text[:200] + "..." if len(text) > 200 else text
                    click.echo(f"Content: {preview}")
    else:
        click.echo("❌ No records found with any method")
        click.echo("")
        click.echo("This suggests:")
        click.echo("  • Records may not be indexed yet (wait 2-5 minutes)")
        click.echo("  • Records may be in a different namespace pattern")
        click.echo("  • There may be an issue with memory extraction")
        click.echo("")
        click.echo("Check AWS Console > AgentCore Memory observability for extraction status")


if __name__ == "__main__":
    cli()

