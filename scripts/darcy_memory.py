#!/usr/bin/env python3
"""
AgentCore Memory Query and Retrieval Script

This script queries AWS Bedrock AgentCore Memory across all memory strategies
(SessionSummarizer, SemanticMemory, and UserPreferences) for development and debugging.

Key Features:
- Multi-Strategy Querying: Automatically queries all three memory strategies with correct namespace patterns
- Flexible Query Options: Query all strategies, filter by strategy, search by session ID, or semantic search
- Error Handling: Gracefully handles API errors with detailed feedback
- Multiple Output Formats: JSON for programmatic processing or human-readable summary

API Methods Used:
- list_memory_records: Lists all records in a namespace (no semantic search required)
- retrieve_memory_records: Performs semantic search within a namespace

IAM Permissions Required:
- bedrock-agentcore:ListMemoryRecords
- bedrock-agentcore:RetrieveMemoryRecords
- bedrock-agentcore:GetMemory (for memory resource details)

Requirements:
    pip install boto3

Usage Examples:
    # Query all memories for a user
    python scripts/darcy_memory.py --user-id nathan_cloudtypes_io

    # Query specific session
    python scripts/darcy_memory.py --user-id nathan_cloudtypes_io --session-id f9ecb4cf-261b-4fd7-9319-708a27ca9a1d

    # Query only semantic memories
    python scripts/darcy_memory.py --user-id nathan_cloudtypes_io --strategy semantic

    # Semantic search
    python scripts/darcy_memory.py --user-id nathan_cloudtypes_io --search "weather Cincinnati"

    # List all sessions
    python scripts/darcy_memory.py --user-id nathan_cloudtypes_io --list-sessions

    # Export to JSON file
    python scripts/darcy_memory.py --user-id nathan_cloudtypes_io --format json --output memories.json
"""

import boto3
import json
import argparse
import sys
from typing import List, Dict, Optional
from datetime import datetime
from botocore.exceptions import ClientError


class AgentCoreMemoryQuery:
    """Query and retrieve memories from AWS Bedrock AgentCore Memory"""
    
    def __init__(self, memory_id: str, region: str = 'us-west-2', verbose: bool = False):
        """
        Initialize the memory query client
        
        Args:
            memory_id: The AgentCore Memory ID (e.g., 'voice_agent_memory-yupt8b5dkN')
            region: AWS region where the memory is deployed
            verbose: Enable verbose debugging output
        """
        self.memory_id = memory_id
        self.region = region
        self.verbose = verbose
        self.client = boto3.client('bedrock-agentcore', region_name=region)
        
        # Memory strategy configurations from your logs
        self.strategies = {
            'session': {
                'id': 'SessionSummarizer-mpvofi3SVJ',
                'namespace_pattern': '/summaries/{user_id}/{session_id}',
                'description': 'Session-level conversation summaries'
            },
            'semantic': {
                'id': 'SemanticMemory-b6NB9xEwVW',
                'namespace_pattern': '/semantic/{user_id}',
                'description': 'Semantic memory of user queries and interactions'
            },
            'preferences': {
                'id': 'UserPreferences-5PL4o66W5Y',
                'namespace_pattern': '/preferences/{user_id}',
                'description': 'User preferences and interests'
            }
        }
    
    def get_memories(self, user_id: str, session_id: Optional[str] = None, 
                     strategy: Optional[str] = None, max_results: int = 100) -> Dict:
        """
        Retrieve memories for a user across all or specific strategies
        
        Args:
            user_id: User identifier (e.g., 'nathan_cloudtypes_io')
            session_id: Optional session ID for session-specific queries
            strategy: Optional strategy filter ('session', 'semantic', 'preferences')
            max_results: Maximum number of results per strategy
            
        Returns:
            Dictionary containing memories organized by strategy
        """
        results = {
            'user_id': user_id,
            'session_id': session_id,
            'timestamp': datetime.utcnow().isoformat(),
            'memories': {}
        }
        
        # Determine which strategies to query
        strategies_to_query = [strategy] if strategy else ['semantic', 'preferences', 'session']
        
        for strat_name in strategies_to_query:
            if strat_name not in self.strategies:
                print(f"Warning: Unknown strategy '{strat_name}', skipping...")
                continue
            
            # Skip session strategy if no session_id provided
            if strat_name == 'session' and not session_id:
                print("Skipping session strategy (no session_id provided)")
                continue
            
            strategy_config = self.strategies[strat_name]
            
            # Build namespace
            if strat_name == 'session':
                namespace = strategy_config['namespace_pattern'].format(
                    user_id=user_id, 
                    session_id=session_id
                )
            else:
                namespace = strategy_config['namespace_pattern'].format(user_id=user_id)
            
            print(f"\n{'='*80}")
            print(f"Querying {strat_name} strategy...")
            print(f"  Strategy ID: {strategy_config['id']}")
            print(f"  Namespace: {namespace}")
            print(f"  Memory ID: {self.memory_id}")
            print(f"  Region: {self.region}")
            print(f"{'='*80}")
            
            try:
                memories = self._query_strategy(namespace, max_results)
                results['memories'][strat_name] = {
                    'strategy_id': strategy_config['id'],
                    'namespace': namespace,
                    'description': strategy_config['description'],
                    'count': len(memories),
                    'records': memories
                }
                if len(memories) > 0:
                    print(f"  ✅ SUCCESS: Found {len(memories)} memory record(s)")
                else:
                    print(f"  ⚠️  WARNING: No records found (but API call succeeded)")
                    print(f"     This could mean:")
                    print(f"     - Records haven't been indexed yet (wait 2-5 minutes)")
                    print(f"     - No records exist in this namespace")
                    print(f"     - Check CloudWatch logs to verify records were created")
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_msg = e.response['Error']['Message']
                print(f"  ❌ Error querying {strat_name}: {error_code}")
                print(f"     Message: {error_msg}")
                
                # Check for IAM permission errors
                if error_code in ['AccessDenied', 'AccessDeniedException', 'UnauthorizedOperation']:
                    print(f"     ⚠️  IAM PERMISSION ISSUE DETECTED!")
                    print(f"     Required permission: bedrock-agentcore:ListMemoryRecords")
                    print(f"     or bedrock-agentcore:RetrieveMemoryRecords")
                
                results['memories'][strat_name] = {
                    'error': error_msg,
                    'error_code': error_code,
                    'is_permission_error': error_code in ['AccessDenied', 'AccessDeniedException', 'UnauthorizedOperation']
                }
        
        return results
    
    def test_permissions(self) -> Dict[str, bool]:
        """
        Test IAM permissions for AgentCore Memory operations.
        
        Returns:
            Dictionary indicating which permissions are available
        """
        print("\n🔍 Testing IAM permissions for AgentCore Memory...")
        permissions = {
            'list_memory_records': False,
            'retrieve_memory_records': False,
            'get_memory': False
        }
        
        # Test 1: ListMemoryRecords
        try:
            print("  Testing bedrock-agentcore:ListMemoryRecords...")
            self.client.list_memory_records(
                memoryId=self.memory_id,
                namespace='/summaries/test',
                maxResults=1
            )
            permissions['list_memory_records'] = True
            print("    ✅ ListMemoryRecords permission: GRANTED")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ['AccessDenied', 'AccessDeniedException', 'UnauthorizedOperation']:
                print(f"    ❌ ListMemoryRecords permission: DENIED ({error_code})")
            elif error_code == 'ResourceNotFoundException':
                # This is OK - means permission works but namespace doesn't exist
                permissions['list_memory_records'] = True
                print("    ✅ ListMemoryRecords permission: GRANTED (namespace not found is expected)")
            else:
                # Other validation errors mean permission might be OK
                permissions['list_memory_records'] = True
                print(f"    ✅ ListMemoryRecords permission: GRANTED (validation error is expected)")
        except Exception as e:
            print(f"    ⚠️  Unexpected error: {str(e)}")
        
        # Test 2: RetrieveMemoryRecords
        try:
            print("  Testing bedrock-agentcore:RetrieveMemoryRecords...")
            self.client.retrieve_memory_records(
                memoryId=self.memory_id,
                namespace='/semantic/test',
                searchCriteria={
                    'searchQuery': 'test',
                    'topK': 1
                }
            )
            permissions['retrieve_memory_records'] = True
            print("    ✅ RetrieveMemoryRecords permission: GRANTED")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ['AccessDenied', 'AccessDeniedException', 'UnauthorizedOperation']:
                print(f"    ❌ RetrieveMemoryRecords permission: DENIED ({error_code})")
            elif error_code == 'ResourceNotFoundException':
                permissions['retrieve_memory_records'] = True
                print("    ✅ RetrieveMemoryRecords permission: GRANTED (namespace not found is expected)")
            else:
                permissions['retrieve_memory_records'] = True
                print(f"    ✅ RetrieveMemoryRecords permission: GRANTED (validation error is expected)")
        except Exception as e:
            print(f"    ⚠️  Unexpected error: {str(e)}")
        
        # Test 3: GetMemory (control plane)
        try:
            print("  Testing bedrock-agentcore:GetMemory (control plane)...")
            control_plane = boto3.client('bedrock-agentcore', region_name=self.region)
            # Note: GetMemory might be in a different service/endpoint
            # This is a placeholder - adjust based on actual API
            permissions['get_memory'] = True
            print("    ⚠️  GetMemory test not implemented (may require different endpoint)")
        except Exception as e:
            print(f"    ⚠️  GetMemory test error: {str(e)}")
        
        print("\n📊 Permission Summary:")
        all_granted = all(permissions.values())
        if all_granted:
            print("  ✅ All required permissions appear to be GRANTED")
        else:
            print("  ❌ Some permissions may be DENIED")
            for perm, granted in permissions.items():
                status = "✅ GRANTED" if granted else "❌ DENIED or UNTESTED"
                print(f"    {perm}: {status}")
        
        return permissions
    
    def _query_strategy(self, namespace: str, max_results: int) -> List[Dict]:
        """
        Query a specific memory namespace using ListMemoryRecords API.
        
        This method uses the bedrock-agentcore:ListMemoryRecords API which is the
        recommended approach for retrieving all records in a namespace without
        requiring semantic search. It automatically handles pagination.
        
        Falls back to semantic search if ListMemoryRecords fails (e.g., for namespaces
        that require semantic search or if there's a validation error).
        
        Args:
            namespace: The memory namespace to query
            max_results: Maximum number of results to return
            
        Returns:
            List of memory records
        """
        memories = []
        
        try:
            # Use ListMemoryRecords to get all records in the namespace
            # This is the primary method - no semantic search query required
            if self.verbose:
                print(f"    🔍 Calling list_memory_records with:")
                print(f"       memoryId: {self.memory_id}")
                print(f"       namespace: {namespace}")
                print(f"       maxResults: {max_results}")
            
            all_records = []
            next_token = None
            page_count = 0
            
            while len(all_records) < max_results:
                page_count += 1
                params = {
                    'memoryId': self.memory_id,
                    'namespace': namespace,
                    'maxResults': min(100, max_results - len(all_records))
                }
                if next_token:
                    params['nextToken'] = next_token
                
                if self.verbose:
                    print(f"    📄 Page {page_count}: Requesting up to {params['maxResults']} records...")
                
                response = self.client.list_memory_records(**params)
                
                if self.verbose:
                    # Debug: Show full response structure
                    print(f"    📊 Response keys: {list(response.keys())}")
                    if 'nextToken' in response:
                        print(f"    🔑 Has nextToken: Yes (length: {len(response.get('nextToken', ''))})")
                    else:
                        print(f"    🔑 Has nextToken: No")
                
                records = response.get('memoryRecordSummaries', response.get('memoryRecords', []))
                
                # Add namespace to each record (since it's not in the response)
                for record in records:
                    if 'namespace' not in record:
                        record['namespace'] = namespace
                
                if self.verbose:
                    print(f"    📦 Records in this page: {len(records)}")
                
                if records:
                    if self.verbose:
                        print(f"    ✅ Found {len(records)} record(s) in page {page_count}")
                        # Show first record structure for debugging
                        first_record = records[0]
                        print(f"    📋 First record keys: {list(first_record.keys())}")
                        print(f"    📋 First record namespace: {first_record.get('namespace', 'N/A')}")
                elif self.verbose:
                    print(f"    ⚠️  No records in page {page_count}")
                
                all_records.extend(records)
                
                next_token = response.get('nextToken')
                if not next_token or len(records) == 0:
                    if self.verbose:
                        print(f"    🏁 No more pages (nextToken: {bool(next_token)}, records: {len(records)})")
                    break
            
            if self.verbose:
                print(f"    📊 Total records collected: {len(all_records)}")
            memories = all_records[:max_results]
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_msg = e.response.get('Error', {}).get('Message', '')
            
            # Check for IAM permission errors first
            if error_code in ['AccessDenied', 'AccessDeniedException', 'UnauthorizedOperation']:
                print(f"    ❌ IAM PERMISSION ERROR: {error_code}")
                print(f"       Message: {error_msg}")
                print(f"       Required permission: bedrock-agentcore:ListMemoryRecords")
                print(f"       This is likely why no memories are being returned!")
                raise  # Re-raise to surface the permission error
            
            # If ListMemoryRecords doesn't work, try semantic search as fallback
            # This can happen if the namespace requires semantic search or if there's
            # an indexing delay (records may exist but not be queryable yet)
            if error_code == 'ValidationException':
                print(f"    Note: ListMemoryRecords returned ValidationException, trying semantic search fallback...")
                # Try semantic search with a generic query as fallback
                try:
                    response = self.client.retrieve_memory_records(
                        memoryId=self.memory_id,
                        namespace=namespace,
                        searchCriteria={
                            'searchQuery': 'memory',
                            'topK': max_results
                        }
                    )
                    memories = response.get('memoryRecords', [])
                    if memories:
                        print(f"    Found {len(memories)} record(s) via semantic search fallback")
                except ClientError as fallback_error:
                    fallback_code = fallback_error.response.get('Error', {}).get('Code', '')
                    if fallback_code in ['AccessDenied', 'AccessDeniedException', 'UnauthorizedOperation']:
                        print(f"    ❌ IAM PERMISSION ERROR on fallback: {fallback_code}")
                        print(f"       Required permission: bedrock-agentcore:RetrieveMemoryRecords")
                    # If both methods fail, raise the original error
                    print(f"    Semantic search fallback also failed: {fallback_error}")
                    raise e
            else:
                raise
        
        return memories
    
    def search_memories(self, user_id: str, query_text: str, 
                       session_id: Optional[str] = None, 
                       max_results: int = 10) -> Dict:
        """
        Search memories using semantic search
        
        Args:
            user_id: User identifier
            query_text: Search query text
            session_id: Optional session ID for context
            max_results: Maximum number of results
            
        Returns:
            Dictionary containing search results
        """
        print(f"\nSearching memories for: '{query_text}'")
        
        # Determine which namespace to search
        namespace = f"/semantic/{user_id}"
        if session_id:
            namespace = f"/summaries/{user_id}/{session_id}"
        
        try:
            response = self.client.retrieve_memory_records(
                memoryId=self.memory_id,
                namespace=namespace,
                searchCriteria={
                    'searchQuery': query_text,
                    'topK': max_results
                }
            )
            
            return {
                'query': query_text,
                'user_id': user_id,
                'session_id': session_id,
                'namespace': namespace,
                'results': response.get('memoryRecordSummaries', response.get('memoryRecords', [])),
                'count': len(response.get('memoryRecordSummaries', response.get('memoryRecords', [])))
            }
            
        except ClientError as e:
            return {
                'query': query_text,
                'error': str(e),
                'error_code': e.response['Error']['Code']
            }
    
    def list_sessions(self, user_id: str) -> List[str]:
        """
        List all sessions for a user by querying the summaries namespace.
        
        Since there's no direct API for listing sessions, this method queries the
        parent summaries namespace and extracts unique session IDs from the
        record namespaces. This is more reliable than maintaining a separate
        session registry.
        
        Alternative: You could also use CloudWatch Logs Insights queries to
        discover session IDs from the logs.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of session IDs
        """
        print(f"\nListing sessions for user: {user_id}")
        print(f"  Querying namespace: /summaries/{user_id}")
        
        sessions = []
        namespace = f"/summaries/{user_id}"
        
        try:
            all_records = []
            next_token = None
            
            # Get up to 1000 records to find all sessions
            while len(all_records) < 1000:
                params = {
                    'memoryId': self.memory_id,
                    'namespace': namespace,
                    'maxResults': 100
                }
                if next_token:
                    params['nextToken'] = next_token
                
                response = self.client.list_memory_records(**params)
                records = response.get('memoryRecordSummaries', response.get('memoryRecords', []))
                all_records.extend(records)
                
                next_token = response.get('nextToken')
                if not next_token or len(records) == 0:
                    break
            
            # Extract unique session IDs from namespaces
            # Namespace format: /summaries/{user_id}/{session_id}
            seen_sessions = set()
            for record in all_records:
                ns = record.get('namespace', '')
                parts = ns.split('/')
                if len(parts) >= 4 and parts[1] == 'summaries':
                    session_id = parts[-1]
                    if session_id and session_id not in seen_sessions:
                        seen_sessions.add(session_id)
                        sessions.append(session_id)
            
            print(f"  Found {len(sessions)} session(s)")
            if len(sessions) > 0:
                print(f"  Session IDs: {', '.join(sessions[:10])}{'...' if len(sessions) > 10 else ''}")
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_msg = e.response.get('Error', {}).get('Message', '')
            print(f"  Error listing sessions: {error_code} - {error_msg}")
            print(f"  Note: This may indicate no sessions exist yet, or there's an indexing delay")
        except Exception as e:
            print(f"  Unexpected error: {str(e)}")
        
        return sessions
    
    def diagnose_namespace(self, user_id: str, session_id: Optional[str] = None) -> Dict:
        """
        Diagnose what's actually in the memory namespaces.
        This helps debug why records aren't being found.
        
        Args:
            user_id: User identifier
            session_id: Optional session ID
            
        Returns:
            Diagnostic information
        """
        print("\n" + "="*80)
        print("🔬 DIAGNOSTIC MODE: Checking what's actually in memory")
        print("="*80)
        
        diagnostics = {
            'user_id': user_id,
            'session_id': session_id,
            'memory_id': self.memory_id,
            'region': self.region,
            'checks': {}
        }
        
        # Check 1: Try parent namespace (summaries without session)
        parent_ns = f"/summaries/{user_id}"
        print(f"\n📍 Check 1: Parent namespace '{parent_ns}'")
        try:
            response = self.client.list_memory_records(
                memoryId=self.memory_id,
                namespace=parent_ns,
                maxResults=10
            )
            records = response.get('memoryRecordSummaries', response.get('memoryRecords', []))
            # Add namespace to each record (since it's not in the response)
            for record in records:
                if 'namespace' not in record:
                    record['namespace'] = parent_ns
            
            diagnostics['checks']['parent_namespace'] = {
                'namespace': parent_ns,
                'record_count': len(records),
                'records': records[:3] if records else []  # First 3 for inspection
            }
            print(f"   ✅ Found {len(records)} record(s)")
            if records:
                for i, rec in enumerate(records[:3], 1):
                    rec_ns = rec.get('namespace', parent_ns)
                    print(f"      {i}. Namespace: {rec_ns}")
                    record_id = rec.get('memoryRecordId', rec.get('recordId', 'N/A'))
                    if record_id != 'N/A':
                        print(f"         Record ID: {record_id}")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_msg = e.response.get('Error', {}).get('Message', '')
            diagnostics['checks']['parent_namespace'] = {
                'error': error_msg,
                'error_code': error_code
            }
            print(f"   ❌ Error: {error_code} - {error_msg}")
        
        # Check 2: Try exact session namespace if session_id provided
        if session_id:
            exact_ns = f"/summaries/{user_id}/{session_id}"
            print(f"\n📍 Check 2: Exact session namespace '{exact_ns}'")
            try:
                response = self.client.list_memory_records(
                    memoryId=self.memory_id,
                    namespace=exact_ns,
                    maxResults=10
                )
                records = response.get('memoryRecordSummaries', response.get('memoryRecords', []))
                # Add namespace to each record (since it's not in the response)
                for record in records:
                    if 'namespace' not in record:
                        record['namespace'] = exact_ns
                
                diagnostics['checks']['exact_namespace'] = {
                    'namespace': exact_ns,
                    'record_count': len(records),
                    'records': records
                }
                print(f"   ✅ Found {len(records)} record(s)")
                if records:
                    for rec in records:
                        rec_ns = rec.get('namespace', exact_ns)
                        print(f"      - Namespace: {rec_ns}")
                        record_id = rec.get('memoryRecordId', rec.get('recordId', 'N/A'))
                        print(f"        Record ID: {record_id}")
                        # Show content preview
                        content = rec.get('content', {})
                        if isinstance(content, dict):
                            text = content.get('text', '')
                            if text:
                                preview = text[:100] + '...' if len(text) > 100 else text
                                print(f"        Content: {preview}")
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                error_msg = e.response.get('Error', {}).get('Message', '')
                diagnostics['checks']['exact_namespace'] = {
                    'error': error_msg,
                    'error_code': error_code
                }
                print(f"   ❌ Error: {error_code} - {error_msg}")
        
        # Check 3: Try semantic namespace
        semantic_ns = f"/semantic/{user_id}"
        print(f"\n📍 Check 3: Semantic namespace '{semantic_ns}'")
        try:
            response = self.client.list_memory_records(
                memoryId=self.memory_id,
                namespace=semantic_ns,
                maxResults=10
            )
            records = response.get('memoryRecordSummaries', response.get('memoryRecords', []))
            # Add namespace to each record
            for record in records:
                if 'namespace' not in record:
                    record['namespace'] = semantic_ns
            
            diagnostics['checks']['semantic_namespace'] = {
                'namespace': semantic_ns,
                'record_count': len(records),
                'records': records[:3] if records else []
            }
            print(f"   ✅ Found {len(records)} record(s)")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_msg = e.response.get('Error', {}).get('Message', '')
            diagnostics['checks']['semantic_namespace'] = {
                'error': error_msg,
                'error_code': error_code
            }
            print(f"   ❌ Error: {error_code} - {error_msg}")
        
        # Check 4: Try preferences namespace
        prefs_ns = f"/preferences/{user_id}"
        print(f"\n📍 Check 4: Preferences namespace '{prefs_ns}'")
        try:
            response = self.client.list_memory_records(
                memoryId=self.memory_id,
                namespace=prefs_ns,
                maxResults=10
            )
            records = response.get('memoryRecordSummaries', response.get('memoryRecords', []))
            # Add namespace to each record
            for record in records:
                if 'namespace' not in record:
                    record['namespace'] = prefs_ns
            
            diagnostics['checks']['preferences_namespace'] = {
                'namespace': prefs_ns,
                'record_count': len(records),
                'records': records[:3] if records else []
            }
            print(f"   ✅ Found {len(records)} record(s)")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_msg = e.response.get('Error', {}).get('Message', '')
            diagnostics['checks']['preferences_namespace'] = {
                'error': error_msg,
                'error_code': error_code
            }
            print(f"   ❌ Error: {error_code} - {error_msg}")
        
        # Check 5: Try using bedrock_agentcore.memory SDK instead of boto3
        print(f"\n📍 Check 5: Testing with bedrock_agentcore.memory SDK")
        try:
            from bedrock_agentcore.memory import MemoryClient as AgentCoreMemoryClient
            sdk_client = AgentCoreMemoryClient(region_name=self.region)
            
            # Try to list events which might show records differently
            print(f"   Testing SDK MemoryClient...")
            # Note: SDK might have different methods - this is exploratory
            print(f"   ⚠️  SDK methods may differ from boto3 API")
            print(f"   💡 Consider checking SDK documentation for alternative query methods")
            
        except ImportError:
            print(f"   ⚠️  bedrock_agentcore.memory SDK not available")
            print(f"   Install with: pip install bedrock-agentcore")
        except Exception as e:
            print(f"   ⚠️  SDK test error: {str(e)}")
        
        # Check 6: Inspect raw API response structure
        print(f"\n📍 Check 6: Inspecting raw API response structure")
        try:
            test_ns = f"/summaries/{user_id}"
            response = self.client.list_memory_records(
                memoryId=self.memory_id,
                namespace=test_ns,
                maxResults=10  # Get more to see actual records
            )
            records = response.get('memoryRecordSummaries', response.get('memoryRecords', []))
            # Add namespace to each record
            for record in records:
                if 'namespace' not in record:
                    record['namespace'] = test_ns
            
            print(f"   Records found: {len(records)}")
            if records:
                print(f"   ✅ SUCCESS! Found {len(records)} record(s)!")
                for i, rec in enumerate(records[:3], 1):
                    print(f"      {i}. Record ID: {rec.get('memoryRecordId', 'N/A')}")
                    print(f"         Namespace: {rec.get('namespace', test_ns)}")
                    content = rec.get('content', {})
                    if isinstance(content, dict):
                        text = content.get('text', '')
                        if text:
                            print(f"         Content preview: {text[:100]}...")
            else:
                print(f"   ⚠️  No records in response")
            print(f"   Response keys: {list(response.keys())}")
            print(f"   Response structure:")
            print(f"     Keys: {list(response.keys())}")
            print(f"     Full response (first 500 chars): {str(response)[:500]}")
            
            # Check if there are any other fields that might indicate records
            for key, value in response.items():
                if key != 'memoryRecords':
                    print(f"     {key}: {type(value).__name__} = {str(value)[:100]}")
            
        except Exception as e:
            print(f"   ⚠️  Error inspecting response: {str(e)}")
        
        print("\n" + "="*80)
        print("📊 DIAGNOSTIC SUMMARY")
        print("="*80)
        total_found = sum(
            check.get('record_count', 0) 
            for check in diagnostics['checks'].values() 
            if isinstance(check, dict) and 'record_count' in check
        )
        print(f"Total records found across all namespaces: {total_found}")
        
        if total_found == 0:
            print("\n⚠️  NO RECORDS FOUND - Critical Analysis:")
            print("\n🔍 The API calls are SUCCEEDING but returning 0 records.")
            print("   This suggests one of the following:")
            print("\n   1. ⏱️  INDEXING DELAY (Most Likely)")
            print("      - Records exist (CloudWatch confirms) but aren't queryable yet")
            print("      - AgentCore Memory may take 5-15 minutes to index records")
            print("      - The 'Succeeded operation' log means creation succeeded, not queryability")
            print("\n   2. 🔄 DIFFERENT API METHOD REQUIRED")
            print("      - ListMemoryRecords might only return 'finalized' records")
            print("      - Records in 'processing' state may not be returned")
            print("      - May need to use different SDK methods or wait for state change")
            print("\n   3. 📋 NAMESPACE MISMATCH")
            print("      - CloudWatch shows namespace but actual storage might differ")
            print("      - Check AWS Console > AgentCore Memory for actual namespaces")
            print("\n   4. 🎯 RECORD STATE")
            print("      - Records might be in 'pending' or 'processing' state")
            print("      - Only 'completed' records might be queryable")
            print("\n💡 RECOMMENDED ACTIONS:")
            print("   1. Wait 10-15 minutes after record creation (not just 2-5)")
            print("   2. Check AWS Console > AgentCore Memory observability dashboard")
            print("   3. Look for 'extraction status' or 'record state' indicators")
            print("   4. Try querying again after waiting longer")
            print("   5. Check if there's a 'GetMemoryRecord' API by record ID")
            print("   6. Contact AWS Support if issue persists after 15+ minutes")
        
        return diagnostics


def format_output(results: Dict, output_format: str = 'json') -> str:
    """Format query results for display"""
    
    if output_format == 'json':
        return json.dumps(results, indent=2, default=str)
    
    elif output_format == 'summary':
        output = []
        output.append(f"\n{'='*80}")
        output.append(f"AgentCore Memory Query Results")
        output.append(f"{'='*80}")
        output.append(f"User ID: {results['user_id']}")
        output.append(f"Session ID: {results.get('session_id', 'N/A')}")
        output.append(f"Timestamp: {results['timestamp']}")
        output.append(f"{'='*80}\n")
        
        for strategy_name, strategy_data in results['memories'].items():
            output.append(f"\n{strategy_name.upper()} STRATEGY")
            output.append(f"{'-'*80}")
            
            if 'error' in strategy_data:
                output.append(f"Error: {strategy_data['error']}")
                continue
            
            output.append(f"Description: {strategy_data['description']}")
            output.append(f"Namespace: {strategy_data['namespace']}")
            output.append(f"Record Count: {strategy_data['count']}")
            
            if strategy_data['count'] > 0:
                output.append(f"\nMemory Records:")
                for idx, record in enumerate(strategy_data['records'], 1):
                    output.append(f"\n  Record {idx}:")
                    output.append(f"    Namespace: {record.get('namespace', 'N/A')}")
                    content = record.get('content', {})
                    if isinstance(content, dict):
                        text = content.get('text', '')
                        output.append(f"    Content: {text[:200] if text else 'N/A'}")
                    else:
                        output.append(f"    Content: {str(content)[:200]}")
                    record_id = record.get('memoryRecordId', record.get('recordId', 'N/A'))
                    if record_id != 'N/A':
                        output.append(f"    Record ID: {record_id}")
            
            output.append(f"\n{'-'*80}")
        
        return '\n'.join(output)
    
    return str(results)


def main():
    """Main execution function"""
    
    parser = argparse.ArgumentParser(
        description='Query and retrieve AWS Bedrock AgentCore Memory records'
    )
    parser.add_argument(
        '--memory-id',
        default='voice_agent_memory-yupt8b5dkN',
        help='AgentCore Memory ID'
    )
    parser.add_argument(
        '--region',
        default='us-west-2',
        help='AWS region'
    )
    parser.add_argument(
        '--user-id',
        required=True,
        help='User identifier (e.g., nathan_cloudtypes_io)'
    )
    parser.add_argument(
        '--session-id',
        help='Optional session ID for session-specific queries'
    )
    parser.add_argument(
        '--strategy',
        choices=['session', 'semantic', 'preferences'],
        help='Query specific strategy only'
    )
    parser.add_argument(
        '--search',
        help='Search query text for semantic search'
    )
    parser.add_argument(
        '--max-results',
        type=int,
        default=100,
        help='Maximum results per strategy'
    )
    parser.add_argument(
        '--format',
        choices=['json', 'summary'],
        default='summary',
        help='Output format'
    )
    parser.add_argument(
        '--output',
        help='Output file path (default: stdout)'
    )
    parser.add_argument(
        '--list-sessions',
        action='store_true',
        help='List all sessions for the user'
    )
    parser.add_argument(
        '--test-permissions',
        action='store_true',
        help='Test IAM permissions for AgentCore Memory operations'
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Enable verbose debugging output'
    )
    parser.add_argument(
        '--diagnose',
        action='store_true',
        help='Run diagnostic checks to see what namespaces contain records'
    )
    
    args = parser.parse_args()
    
    # Initialize query client
    query_client = AgentCoreMemoryQuery(
        memory_id=args.memory_id,
        region=args.region,
        verbose=args.verbose
    )
    
    # Run diagnostics if requested
    if args.diagnose:
        diagnostics = query_client.diagnose_namespace(
            user_id=args.user_id,
            session_id=args.session_id
        )
        if args.format == 'json':
            print(json.dumps(diagnostics, indent=2, default=str))
        sys.exit(0)
    
    # Test permissions if requested
    if args.test_permissions:
        permissions = query_client.test_permissions()
        if not all(permissions.values()):
            print("\n⚠️  WARNING: Some permissions may be missing!")
            print("   This could explain why no memories are being returned.")
            print("\n   Required IAM permissions:")
            print("   - bedrock-agentcore:ListMemoryRecords")
            print("   - bedrock-agentcore:RetrieveMemoryRecords")
            print("   - bedrock-agentcore:GetMemory (optional, for memory details)")
            print("\n   Example IAM policy:")
            print("   {")
            print('     "Effect": "Allow",')
            print('     "Action": [')
            print('       "bedrock-agentcore:ListMemoryRecords",')
            print('       "bedrock-agentcore:RetrieveMemoryRecords",')
            print('       "bedrock-agentcore:GetMemory"')
            print('     ],')
            print(f'     "Resource": "arn:aws:bedrock-agentcore:{args.region}:*:memory/{args.memory_id}"')
            print("   }")
        sys.exit(0)
    
    # Execute query or search
    if args.list_sessions:
        sessions = query_client.list_sessions(user_id=args.user_id)
        if args.format == 'json':
            print(json.dumps({'sessions': sessions}, indent=2))
        else:
            print(f"\nFound {len(sessions)} session(s):")
            for session_id in sessions:
                print(f"  - {session_id}")
    elif args.search:
        results = query_client.search_memories(
            user_id=args.user_id,
            query_text=args.search,
            session_id=args.session_id,
            max_results=args.max_results
        )
        formatted_output = json.dumps(results, indent=2, default=str) if args.format == 'json' else str(results)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(formatted_output)
            print(f"\nResults written to: {args.output}")
        else:
            print(formatted_output)
    else:
        results = query_client.get_memories(
            user_id=args.user_id,
            session_id=args.session_id,
            strategy=args.strategy,
            max_results=args.max_results
        )
        
        # Format output
        formatted_output = format_output(results, args.format)
        
        # Write output
        if args.output:
            with open(args.output, 'w') as f:
                f.write(formatted_output)
            print(f"\nResults written to: {args.output}")
        else:
            print(formatted_output)


if __name__ == '__main__':
    main()

