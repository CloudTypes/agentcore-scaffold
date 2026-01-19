# AgentCore Memory Management Script

A command-line tool for managing Amazon Bedrock AgentCore Memory resources. This script handles creation, deletion, status checking, and querying of memory resources with their associated strategies.

## Overview

The `manage_memory.py` script provides a CLI interface for managing AgentCore Memory resources that cannot be fully configured via AWS CDK. It creates memory resources with three built-in strategies:

- **SessionSummarizer**: Captures summaries of conversations in `/summaries/{actorId}/{sessionId}`
- **UserPreferences**: Captures user preferences and behavior in `/preferences/{actorId}`
- **SemanticMemory**: Stores factual information using vector embeddings in `/semantic/{actorId}`

## Prerequisites

1. **Python Dependencies**:
   ```bash
   pip install bedrock-agentcore click python-dotenv boto3
   ```

2. **AWS Credentials**: Configured via AWS CLI, environment variables, or IAM role

3. **Environment Variables** (optional, in `.env` file):
   - `AGENTCORE_MEMORY_REGION` or `AWS_REGION`: AWS region for memory operations (checked in that order, default: `us-east-1`)
   - `AGENTCORE_MEMORY_ARN`: Full ARN of the memory resource (e.g., `arn:aws:bedrock-agentcore:us-west-2:account:memory/voice_agent_memory-yupt8b5dkN`)
   - `AGENTCORE_MEMORY_ID`: Direct memory ID override (e.g., `voice_agent_memory-yupt8b5dkN`)

## Configuration

The script uses the following default configuration:

- **Memory Name**: `voice_agent_memory` (must match pattern: `[a-zA-Z][a-zA-Z0-9_]{0,47}`)
- **SSM Parameter**: `/agentcore/scaffold/memory-id`
- **Secrets Manager**: `agentcore/scaffold/memory-id`
- **Event Expiry**: 30 days

The memory ID is retrieved in the following order (first match wins):
1. Command-line `--memory-id` option (if provided)
2. Environment variable `AGENTCORE_MEMORY_ARN` (ARN format, extracts ID)
3. Environment variable `AGENTCORE_MEMORY_ID` (direct ID)
4. SSM Parameter Store: `/agentcore/scaffold/memory-id`
5. Secrets Manager: `agentcore/scaffold/memory-id` (fallback)

This allows for flexible configuration: use environment variables for local testing, or rely on SSM/Secrets Manager for deployed environments.

## API Usage and Pagination

The script uses the most appropriate API method for each operation:

- **`ListMemoryRecords` API**: Used for summaries and preferences (no semantic search required)
  - Automatically handles pagination using `nextToken`
  - Retrieves all records across multiple pages
  - More efficient for listing all records in a namespace

- **Semantic Search (`retrieve_memory_records`)**: Used for semantic memory and as a fallback
  - Requires a search query
  - Useful for finding relevant memories based on content

All commands that use `ListMemoryRecords` now properly handle pagination to ensure all records are retrieved, even if there are many records across multiple pages.

## Commands

### `create`

Create a new AgentCore memory resource with all three strategies configured.

```bash
python scripts/manage_memory.py create
```

**What it does**:
- Creates a memory resource named `voice_agent_memory`
- Configures three memory strategies (Summary, User Preference, Semantic)
- Stores the memory ID in SSM Parameter Store and Secrets Manager
- If memory already exists, finds and uses the existing resource

**Output**:
- Memory ID
- SSM Parameter path
- Secrets Manager secret name

**Example**:
```bash
$ python scripts/manage_memory.py create
🚀 Creating AgentCore memory: voice_agent_memory
📍 Region: us-west-2
⏱️  Event expiry: 30 days
🔄 Creating memory resource with strategies...
✅ Memory created successfully: voice_agent_memory-yupt8b5dkN
🔐 Stored memory_id in SSM: /agentcore/scaffold/memory-id
🔐 Created memory_id in Secrets Manager: agentcore/scaffold/memory-id
🎉 Memory setup completed successfully!
   Memory ID: voice_agent_memory-yupt8b5dkN
   SSM Parameter: /agentcore/scaffold/memory-id
   Secrets Manager: agentcore/scaffold/memory-id
```

---

### `delete`

Delete the AgentCore memory resource and clean up stored IDs.

```bash
python scripts/manage_memory.py delete
```

Or skip confirmation:

```bash
python scripts/manage_memory.py delete --confirm
```

**Options**:
- `--confirm`: Skip confirmation prompt (use with caution)

**What it does**:
- Deletes the memory resource
- Removes the memory ID from SSM Parameter Store
- Removes the memory ID from Secrets Manager

**Example**:
```bash
$ python scripts/manage_memory.py delete
🔍 Looking for memory ID in region: us-west-2
   SSM Parameter: /agentcore/scaffold/memory-id
   Secrets Manager: agentcore/scaffold/memory-id
   Checking SSM Parameter Store...
   ✅ Found in SSM: voice_agent_memory-yupt8b5dkN
⚠️  Are you sure you want to delete memory voice_agent_memory-yupt8b5dkN? This action cannot be undone. [y/N]: y
🗑️  Deleting memory: voice_agent_memory-yupt8b5dkN
✅ Memory deleted successfully: voice_agent_memory-yupt8b5dkN
🧹 Deleted SSM parameter: /agentcore/scaffold/memory-id
🧹 Deleted Secrets Manager secret: agentcore/scaffold/memory-id
🎉 Memory and stored IDs deleted successfully
```

---

### `status`

Check the status and configuration of the memory resource.

```bash
python scripts/manage_memory.py status
```

**What it does**:
- Retrieves the memory ID from SSM or Secrets Manager
- Fetches memory resource details from AgentCore
- Displays configured strategies and their namespaces

**Example**:
```bash
$ python scripts/manage_memory.py status
🔍 Checking memory status in region: us-west-2
   SSM Parameter: /agentcore/scaffold/memory-id
   Secrets Manager: agentcore/scaffold/memory-id
   Checking SSM Parameter Store...
   ✅ Found in SSM: voice_agent_memory-yupt8b5dkN
📋 Memory ID: voice_agent_memory-yupt8b5dkN
📊 Strategies: 3
   - summaryMemoryStrategy: /summaries/{actorId}/{sessionId}
   - userPreferenceMemoryStrategy: /preferences/{actorId}
   - semanticMemoryStrategy: /semantic/{actorId}
✅ Memory is active and configured
```

---

### `query-session`

Query a specific session summary from AgentCore Memory.

```bash
python scripts/manage_memory.py query-session \
  --actor-id "user@example.com" \
  --session-id "session-uuid"
```

Or with optional flags:

```bash
python scripts/manage_memory.py query-session \
  --actor-id "user@example.com" \
  --session-id "session-uuid" \
  --try-all-namespaces \
  --memory-id "memory-id-or-arn"
```

**Options**:
- `--actor-id` (required): User identifier (email address)
- `--session-id` (required): Session identifier (UUID)
- `--try-all-namespaces`: Try multiple namespace patterns to find the session
- `--memory-id`: Override memory ID lookup (useful for direct testing). Can be a memory ID or ARN

**What it does**:
- Attempts to retrieve session summary using `ListMemoryRecords` API with full pagination support (no semantic search required)
- Automatically handles pagination using `nextToken` to retrieve all records
- Falls back to semantic search with multiple query terms if direct listing fails
- Tries parent namespace if exact namespace returns no records (also with pagination)
- Displays the session summary content

**Example**:
```bash
$ python scripts/manage_memory.py query-session \
    --actor-id "nathan@cloudtypes.io" \
    --session-id "f9ecb4cf-261b-4fd7-9319-708a27ca9a1d"
```

**Direct Memory ID Override** (useful for testing):
```bash
$ python scripts/manage_memory.py query-session \
    --actor-id "nathan@cloudtypes.io" \
    --session-id "f9ecb4cf-261b-4fd7-9319-708a27ca9a1d" \
    --memory-id "voice_agent_memory-yupt8b5dkN"
🔍 Looking for memory ID in region: us-west-2
   ✅ Found in SSM: voice_agent_memory-yupt8b5dkN
🔍 Querying session: f9ecb4cf-261b-4fd7-9319-708a27ca9a1d
👤 Actor: nathan@cloudtypes.io (sanitized: nathan_cloudtypes_io)
💾 Memory ID: voice_agent_memory-yupt8b5dkN
🌍 Region: us-west-2

📍 Trying namespace: /summaries/nathan_cloudtypes_io/f9ecb4cf-261b-4fd7-9319-708a27ca9a1d
   ✅ Found 1 record(s) using ListMemoryRecords
✅ Found 1 record(s) in namespace: /summaries/nathan_cloudtypes_io/f9ecb4cf-261b-4fd7-9319-708a27ca9a1d

--- Record 1 ---
Namespace: /summaries/nathan_cloudtypes_io/f9ecb4cf-261b-4fd7-9319-708a27ca9a1d
Summary:
  The user initiated a conversation with a greeting. The assistant responded...
```

**Note**: There may be a 20-40 second delay (or up to 1-2 minutes) after a session ends before summaries are available. This is normal behavior for AgentCore Memory's asynchronous extraction process.

---

### `list-namespaces`

List all memory records in a namespace prefix to see what's actually stored.

```bash
python scripts/manage_memory.py list-namespaces \
  --actor-id "user@example.com"
```

Or with optional flags:

```bash
python scripts/manage_memory.py list-namespaces \
  --actor-id "user@example.com" \
  --namespace-prefix "/summaries" \
  --top-k 50 \
  --use-list-api \
  --memory-id "memory-id-or-arn"
```

**Options**:
- `--actor-id` (required): User identifier (email address)
- `--namespace-prefix`: Namespace prefix to search (default: `/summaries`)
- `--top-k`: Maximum number of records to retrieve (default: 50)
- `--use-list-api`: Use `ListMemoryRecords` API instead of semantic search
- `--memory-id`: Override memory ID lookup (useful for direct testing). Can be a memory ID or ARN

**What it does**:
- Lists all records in the specified namespace prefix using `ListMemoryRecords` API (when `--use-list-api` is set or for summaries/preferences)
- Automatically handles pagination to retrieve all records
- Falls back to semantic search if `ListMemoryRecords` is not used or fails
- Shows actual namespaces where records are stored
- Provides content previews for found records

**Example**:
```bash
$ python scripts/manage_memory.py list-namespaces \
    --actor-id "nathan@cloudtypes.io" \
    --namespace-prefix "/summaries" \
    --use-list-api \
    --top-k 100
🔍 Looking for memory ID in region: us-west-2
   ✅ Found in SSM: voice_agent_memory-yupt8b5dkN

🔍 Searching for records in namespace prefix: /summaries
👤 Actor: nathan@cloudtypes.io (sanitized: nathan_cloudtypes_io)
💾 Memory ID: voice_agent_memory-yupt8b5dkN
🌍 Region: us-west-2

📍 Querying namespace: /summaries/nathan_cloudtypes_io
   ✅ Found 3 record(s) using ListMemoryRecords
      1. Namespace: /summaries/nathan_cloudtypes_io/f9ecb4cf-261b-4fd7-9319-708a27ca9a1d
         Preview: The user initiated a conversation with a greeting...
      2. Namespace: /summaries/nathan_cloudtypes_io/120f7fbd-42c1-4397-a24b-244e7ad9a02f
         Preview: The user asked about the weather in Denver...
      3. Namespace: /summaries/nathan_cloudtypes_io/a1b2c3d4-5678-90ef-ghij-klmnopqrstuv
         Preview: The user requested help with calculations...
```

---

### `list-all-records`

List ALL memory records across all namespaces to discover what's stored.

```bash
python scripts/manage_memory.py list-all-records
```

Or with optional flags:

```bash
python scripts/manage_memory.py list-all-records \
  --top-k 100 \
  --memory-id "memory-id-or-arn"
```

**Options**:
- `--top-k`: Maximum number of records to retrieve (default: 100)
- `--memory-id`: Override memory ID lookup (useful for direct testing). Can be a memory ID or ARN

**What it does**:
- Searches across common namespace patterns (`/summaries`, `/preferences`, `/semantic`)
- Uses multiple semantic search queries to find records
- Groups results by namespace and shows summaries

**Example**:
```bash
$ python scripts/manage_memory.py list-all-records --top-k 100
🔍 Looking for memory ID in region: us-west-2
   ✅ Found in SSM: voice_agent_memory-yupt8b5dkN

🔍 Listing ALL memory records (up to 100)
💾 Memory ID: voice_agent_memory-yupt8b5dkN
🌍 Region: us-west-2

⚠️  Note: This queries common namespace patterns. If records are in
   unexpected namespaces, they may not appear here.

✅ Found 5 record(s) in namespace: /summaries (query: 'summary')
   - /summaries/nathan_cloudtypes_io/f9ecb4cf-261b-4fd7-9319-708a27ca9a1d
   - /summaries/nathan_cloudtypes_io/120f7fbd-42c1-4397-a24b-244e7ad9a02f
   ...

📊 Summary: Found 5 total records in 5 unique namespaces

Namespaces with records:
  • /summaries/nathan_cloudtypes_io/f9ecb4cf-261b-4fd7-9319-708a27ca9a1d: 1 record(s)
    Sample: The user initiated a conversation with a greeting...
  • /summaries/nathan_cloudtypes_io/120f7fbd-42c1-4397-a24b-244e7ad9a02f: 1 record(s)
    Sample: The user asked about the weather in Denver...
```

---

### `debug-memory`

Debug memory records using multiple retrieval methods to troubleshoot issues.

```bash
python scripts/manage_memory.py debug-memory \
  --actor-id "user@example.com"
```

Or with optional flags:

```bash
python scripts/manage_memory.py debug-memory \
  --actor-id "user@example.com" \
  --session-id "session-uuid" \
  --memory-id "memory-id-or-arn"
```

**Options**:
- `--actor-id` (required): User identifier (email address)
- `--session-id` (optional): Session ID to filter by
- `--memory-id`: Override memory ID lookup (useful for direct testing). Can be a memory ID or ARN

**What it does**:
- Tests `ListMemoryRecords` API on multiple namespace levels with full pagination support
- Automatically handles pagination to retrieve all records across pages
- Tries semantic search with various query terms as a fallback
- Shows which method successfully retrieves records
- Provides troubleshooting suggestions if no records are found

**Example**:
```bash
$ python scripts/manage_memory.py debug-memory \
    --actor-id "nathan@cloudtypes.io" \
    --session-id "f9ecb4cf-261b-4fd7-9319-708a27ca9a1d"
🔍 Looking for memory ID in region: us-west-2
   ✅ Found in SSM: voice_agent_memory-yupt8b5dkN

🔍 Debugging memory records
👤 Actor: nathan@cloudtypes.io (sanitized: nathan_cloudtypes_io)
💾 Memory ID: voice_agent_memory-yupt8b5dkN
🌍 Region: us-west-2
📋 Session ID: f9ecb4cf-261b-4fd7-9319-708a27ca9a1d

📍 Testing namespace: /summaries/nathan_cloudtypes_io/f9ecb4cf-261b-4fd7-9319-708a27ca9a1d
   ListMemoryRecords: 1 record(s)
      1. Namespace: /summaries/nathan_cloudtypes_io/f9ecb4cf-261b-4fd7-9319-708a27ca9a1d
   Semantic search: No records found with any query term

✅ Total unique records found: 1

--- Record 1 ---
Namespace: /summaries/nathan_cloudtypes_io/f9ecb4cf-261b-4fd7-9319-708a27ca9a1d
Content: The user initiated a conversation with a greeting. The assistant responded...
```

---

## Actor ID Sanitization

The script automatically sanitizes actor IDs (email addresses) to match AgentCore Memory's namespace requirements:

- Replaces `@` with `_`
- Replaces `.` with `_`
- Ensures the ID starts with an alphanumeric character

**Example**:
- Input: `nathan@cloudtypes.io`
- Sanitized: `nathan_cloudtypes_io`
- Namespace: `/summaries/nathan_cloudtypes_io/{sessionId}`

## Troubleshooting

### Memory ID Not Found

If you see "No memory ID found in SSM or Secrets Manager":

1. **Check the region**: The script looks for the memory ID in the region specified by `AWS_REGION` or `AGENTCORE_MEMORY_REGION` environment variables
2. **Verify memory exists**: Run `python scripts/manage_memory.py status` to check if memory was created
3. **Check AWS Console**: Manually verify the SSM parameter or Secrets Manager secret exists
4. **Create memory**: If memory doesn't exist, run `python scripts/manage_memory.py create`

### No Records Found

If queries return no records:

1. **Wait for indexing**: Summaries can take 20-40 seconds (or up to 1-2 minutes) to be available after a session ends
2. **Check memory strategies**: Run `python scripts/manage_memory.py status` to verify strategies are configured
3. **Verify events are stored**: Check server logs to ensure events are being created successfully
4. **Try different namespace patterns**: Use `--try-all-namespaces` flag with `query-session`
5. **Use debug command**: Run `debug-memory` to see which retrieval methods work
6. **Check AWS Console**: Use AgentCore Memory observability dashboard to see extraction status

### Region Mismatch

If the script can't find memory in the expected region:

1. Set `AGENTCORE_MEMORY_REGION` (preferred) or `AWS_REGION` in your `.env` file:
   ```
   AGENTCORE_MEMORY_REGION=us-west-2
   # Or
   AWS_REGION=us-west-2
   ```
   The script checks `AGENTCORE_MEMORY_REGION` first, then falls back to `AWS_REGION`.

2. Or export the environment variable:
   ```bash
   export AGENTCORE_MEMORY_REGION=us-west-2
   # Or
   export AWS_REGION=us-west-2
   ```

### Direct Memory ID Testing

If you want to bypass SSM/Secrets Manager lookup for testing:

1. **Use command-line option**:
   ```bash
   python scripts/manage_memory.py query-session \
     --actor-id "user@example.com" \
     --session-id "session-id" \
     --memory-id "voice_agent_memory-yupt8b5dkN"
   ```

2. **Use environment variable** (in `.env` file):
   ```
   AGENTCORE_MEMORY_ID=voice_agent_memory-yupt8b5dkN
   # Or with ARN:
   AGENTCORE_MEMORY_ARN=arn:aws:bedrock-agentcore:us-west-2:account:memory/voice_agent_memory-yupt8b5dkN
   ```

### Memory Creation Fails

If memory creation fails with validation errors:

1. **Memory name format**: Must match `[a-zA-Z][a-zA-Z0-9_]{0,47}` (no hyphens, must start with letter)
2. **Strategy format**: Strategies must include a `name` field
3. **Check AWS Console**: Verify you have permissions to create AgentCore Memory resources

## Integration with Application

The memory ID stored by this script is automatically used by the application's `MemoryClient` class. The application reads the memory ID from:

1. SSM Parameter Store: `/agentcore/scaffold/memory-id`
2. Secrets Manager: `agentcore/scaffold/memory-id` (fallback)

No additional configuration is needed in the application code.

## Related Files

- `src/memory/client.py`: Application's memory client that uses the memory ID
- `infrastructure/cdk/app.py`: CDK app (memory is managed separately via this script)
- `.env`: Environment configuration file

## References

- [AWS Bedrock AgentCore Samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
- [AgentCore Memory Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-memory.html)

