# A2A, Strands, and Multimodal Content Integration

## Overview

This document captures the findings and solutions from integrating Agent-to-Agent (A2A) protocol, Strands framework, and multimodal content (images/videos) in the vision agent. This was a complex integration that required deep understanding of how A2AServer handles multimodal messages and how to properly intercept and convert content formats.

**⚠️ IMPORTANT**: Strands A2A support is marked as "Experimental" in the documentation. The behavior described in this document is specific to the library versions used. Upgrading Strands or related dependencies may change behavior and require updates to this implementation.

## Library Versions

The following library versions were used in this implementation. **Version compatibility is critical** due to the experimental nature of A2A support:

### Core Dependencies

- **strands-agents[a2a]**: `>=1.20.0`
  - Provides the Strands Agent framework and A2A protocol support
  - The `[a2a]` extra includes A2AServer and related A2A functionality
  - **Note**: A2A support is experimental and behavior may vary between versions

- **bedrock-agentcore**: `>=1.1.2`
  - AWS Bedrock integration for AgentCore
  - Used for underlying model access

- **bedrock-agentcore-starter-toolkit**: `>=0.2.5`
  - Starter toolkit for AgentCore development

### Web Framework

- **fastapi**: `>=0.128.0`
  - Used for the A2A server HTTP endpoints
  - Handles request/response processing

- **uvicorn[standard]**: `>=0.40.0`
  - ASGI server for FastAPI
  - Handles async request processing

### Data Validation

- **pydantic**: `>=2.12.5`
  - Used by FastAPI for request validation
  - Used by A2AServer for message part validation
  - **Critical**: Pydantic v2 behavior differs from v1, affecting validation error handling

### HTTP Client

- **httpx**: `>=0.28.1`
  - Used by orchestrator's A2A client for inter-agent communication
  - Async HTTP client for A2A protocol requests

### Python Version

- **Python**: `3.11+` (verified working on Python 3.11)
  - Note: Some newer AWS SDK packages require Python 3.12+, but this implementation works with 3.11

### Version Compatibility Notes

1. **strands-agents 1.20.0+**: This version introduced A2A support. Earlier versions may not have A2AServer functionality.

2. **Pydantic v2**: The validation error handling and base64 data structure expectations are based on Pydantic v2 behavior. If downgrading to Pydantic v1, validation error handling may need adjustment.

3. **FastAPI 0.128.0+**: Request validation error handling uses FastAPI's exception handlers, which may vary by version.

4. **A2A Protocol**: The A2A protocol implementation in Strands is experimental. Behavior described here is specific to strands-agents 1.20.0+. Future versions may:
   - Fix the DataPart → ImageBlock conversion issue
   - Change method invocation patterns
   - Modify content block formats

### Checking Current Versions

To check installed versions in your environment:

```bash
pip show strands-agents
pip show fastapi
pip show pydantic
pip show httpx
```

Or check the requirements files:
- Root: `requirements.txt`
- Vision agent: `agents/vision/requirements.txt`

## Problem Statement

The vision agent needed to:
1. Receive multimodal content (images/videos) via A2A protocol from the orchestrator
2. Process the content through the Strands framework
3. Return formatted, analyzed responses to the web client

Initial challenges included:
- A2AServer converting DataPart (base64 image data) to text blocks instead of proper ImageBlocks
- Wrapper methods not being called by A2AServer
- Response formatting issues in the web client

## Key Findings

### 1. A2AServer's Multimodal Message Handling

**Critical Discovery**: A2AServer does NOT properly convert A2A DataPart to Strands ImageBlock format as documented. Instead, it converts the DataPart to a **text block** containing the base64 string wrapped in a JSON-like structure.

#### Expected Behavior (Per Documentation)
According to Strands documentation, A2AServer should convert:
```json
{
  "type": "data",
  "mimeType": "image/jpeg",
  "data": {"base64": "..."}
}
```

To Strands format:
```json
{
  "image": {
    "format": "jpeg",
    "source": {"bytes": <decoded_bytes>}
  }
}
```

#### Actual Behavior
A2AServer converts the DataPart to:
```json
{
  "text": "[Structured Data]\n{\n  \"base64\": \"/9j/4AAQSkZJRg...\"\n}"
}
```

The base64 data is embedded as a string within a text block, not converted to a proper ImageBlock.

### 2. A2AServer Method Invocation Pattern

**Finding**: A2AServer caches method references at initialization time and may bypass wrapper classes if not properly structured.

#### Solution: Wrapper Pattern
We implemented a `MemoryIntegratedAgent` wrapper that:
- Returns `self` from the `strands_agent` property (instead of the underlying agent)
- Defines `invoke_async` and `stream_async` directly on the wrapper class
- Prevents delegation of critical methods through `__getattr__`

```python
@property
def strands_agent(self):
    """
    Return self instead of underlying agent - this ensures A2AServer uses our wrapper's methods.
    """
    logger.info("strands_agent property accessed - returning self")
    return self

def __getattr__(self, name):
    """Delegate attribute access, but prevent delegation of critical methods."""
    if name in ['invoke_async', 'stream_async', '__call__', 'strands_agent']:
        raise AttributeError(f"'{type(self).__name__}' object should have '{name}' defined directly")
    # ... delegate other attributes
```

### 3. Stream vs Invoke

**Finding**: A2AServer calls `stream_async` for multimodal messages, not `invoke_async`. The `stream_async` method receives content blocks that may be in A2A format or already converted (incorrectly) to text blocks.

## Solution Implementation

### 1. Base64 Extraction from Text Blocks

Since A2AServer converts DataPart to text blocks, we implemented extraction logic in `stream_async`:

```python
async def stream_async(self, content_blocks):
    # Check if this is a text block that contains base64 image data
    if "text" in block and "image" not in block and "type" not in block:
        text_content = block["text"]
        if text_content.startswith("[Structured Data]") and '"base64":' in text_content:
            # Extract JSON from the text block
            json_start = text_content.find('{')
            json_end = text_content.rfind('}')
            if json_start != -1 and json_end > json_start:
                json_str = text_content[json_start:json_end+1]
                try:
                    data_obj = json.loads(json_str)
                    base64_data = data_obj.get("base64", "")
                    if base64_data:
                        # Decode and create proper ImageBlock
                        data_bytes = base64.b64decode(base64_data)
                        format_str = "jpeg" if base64_data.startswith("/9j/") else "png"
                        content.append({
                            "image": {
                                "format": format_str,
                                "source": {"bytes": data_bytes}
                            }
                        })
                        continue  # Skip adding as text
                except json.JSONDecodeError:
                    # Fallback to regex extraction
                    pass
```

### 2. Format Detection

We detect image format from base64 header:
- JPEG: starts with `/9j/`
- PNG: starts with `iVBORw0KGgo`

### 3. Content Block Conversion

The extracted base64 is converted to proper Strands ImageBlock format:
```python
{
    "image": {
        "format": "jpeg",  # or "png"
        "source": {
            "bytes": <decoded_bytes>  # Raw bytes, not base64
        }
    }
}
```

## Code Structure

### MemoryIntegratedAgent Wrapper

Located in `agents/vision/app.py`, this wrapper:
1. Intercepts A2AServer calls
2. Extracts base64 from text blocks
3. Converts to proper Strands format
4. Delegates to underlying Strands agent
5. Handles memory integration

Key methods:
- `stream_async`: Main entry point for multimodal messages
- `invoke_async`: Backup entry point (though A2AServer primarily uses stream_async)
- `__call__`: Legacy handler (not typically used by A2AServer)

### Web Client Markdown Rendering

The web client (`client/web/app.js`) includes a markdown parser that:
1. Detects numbered lists embedded in paragraphs
2. Splits them into proper list items
3. Renders markdown (bold, italic, code, lists, headers)
4. Maintains list continuity (ensures sequential numbering)

## Lessons Learned

### 1. Don't Trust Documentation Blindly
The Strands documentation suggested A2AServer would handle DataPart conversion automatically. In reality, it converts to text blocks, requiring manual extraction.

### 2. Wrapper Patterns Must Be Explicit
A2AServer's method caching means wrapper classes must:
- Define methods directly (not through `__getattr__`)
- Return `self` from properties that A2AServer might access
- Prevent attribute delegation for critical methods

### 3. Logging is Essential
Extensive logging at every step was crucial for debugging:
- When methods are called
- What format content is in
- Where conversions happen
- What gets passed to Strands

### 4. Format Detection Matters
Base64 strings can be detected by their headers, allowing format detection without MIME type information.

### 5. Web Client Formatting
Markdown rendering in the web client requires:
- Detection of embedded lists in paragraphs
- Proper list continuity handling
- Inline markdown processing (bold, italic, code)

## Testing

To test the integration:
1. Upload an image via the web client
2. Check orchestrator logs to verify A2A request format
3. Check vision agent logs to verify:
   - `stream_async` is called
   - Base64 is extracted from text block
   - ImageBlock is created
   - Strands agent receives proper format
4. Verify web client displays formatted response

## Version-Specific Behavior

### A2AServer DataPart Conversion (strands-agents 1.20.0+)

The workaround for extracting base64 from text blocks is **specific to strands-agents 1.20.0+**. The exact format of the text block may vary:

**Current format (1.20.0+)**:
```json
{
  "text": "[Structured Data]\n{\n  \"base64\": \"...\"\n}"
}
```

**If upgrading strands-agents**:
1. Test the DataPart conversion behavior
2. Verify the text block format hasn't changed
3. Update the extraction regex/parsing logic if needed
4. Check if A2AServer now properly converts to ImageBlocks (ideal case - workaround can be removed)

### Pydantic v2 Validation Behavior

The validation error handling assumes Pydantic v2 (`>=2.12.5`). Key differences from v1:
- Validation errors are raised as `ValidationError` (not `RequestValidationError` in some cases)
- Error message formatting differs
- Base64 data structure validation may differ

### FastAPI Request Handling

FastAPI `>=0.128.0` is used. The custom `RequestValidationError` handler may need adjustment if upgrading to a major version.

## Known Limitations

1. **Format Detection**: Currently only detects JPEG and PNG. Other formats default to JPEG.
2. **Large Images**: Very large base64 strings in text blocks may cause performance issues.
3. **Error Handling**: If base64 extraction fails, the image is lost (no fallback).
4. **Version Dependency**: Solution is tightly coupled to strands-agents 1.20.0+ behavior.

## Future Improvements

1. **Better Format Detection**: Use MIME type from original request if available
2. **Error Recovery**: Implement fallback mechanisms if base64 extraction fails
3. **Caching**: Cache decoded images to avoid re-decoding
4. **Validation**: Validate image data after decoding
5. **A2AServer Fix**: Ideally, A2AServer should be fixed to properly convert DataPart to ImageBlocks
6. **Version Detection**: Add runtime checks to detect Strands version and adapt behavior accordingly
7. **Backward Compatibility**: Support multiple Strands versions if possible

## Upgrading Considerations

### Before Upgrading Strands

1. **Check Release Notes**: Review strands-agents changelog for A2A-related changes
2. **Test DataPart Conversion**: Verify if A2AServer behavior has changed
3. **Update Tests**: Ensure integration tests cover multimodal scenarios
4. **Monitor Logs**: Watch for changes in content block formats

### Testing After Upgrade

1. Upload a test image via web client
2. Verify base64 extraction still works (check logs)
3. Confirm ImageBlock creation succeeds
4. Validate response formatting in web client
5. Test with different image formats (JPEG, PNG)

### If A2AServer Behavior Changes

If a future Strands version fixes DataPart conversion:
1. Remove base64 extraction from text blocks
2. Verify A2AServer now passes proper ImageBlocks
3. Simplify `stream_async` to handle only proper ImageBlocks
4. Update this document to reflect the change

## Related Files

- `agents/vision/app.py`: Main vision agent with A2A server and wrapper
- `agents/vision/agent.py`: Core vision agent logic
- `agents/orchestrator/a2a_client.py`: A2A client that sends multimodal requests
- `client/web/app.js`: Web client with markdown rendering
- `docs/strands_a2aserver_multimodal_message_handling.md`: Research findings on A2AServer behavior

## References

- [Strands A2A Documentation](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/agent-to-agent/)
- [A2A Protocol Specification](https://a2a-protocol.org/dev/specification/)
- Internal research document: `docs/strands_a2aserver_multimodal_message_handling.md`

## Conclusion

This integration required deep debugging of A2AServer's internal behavior and implementation of workarounds for its limitations. The key insight was that A2AServer converts DataPart to text blocks rather than proper ImageBlocks, requiring manual extraction and conversion. The wrapper pattern ensures our code intercepts A2AServer calls and performs the necessary conversions before delegating to the Strands agent.

The solution is robust and handles the current A2AServer behavior, but ideally A2AServer should be updated to properly support multimodal content conversion as documented.
