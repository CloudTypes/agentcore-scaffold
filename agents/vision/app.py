"""Vision Agent using Strands framework with A2A protocol."""

import os
import logging
from strands import Agent
from strands.multiagent.a2a import A2AServer
from agents.vision.agent import VisionAgent
from agents.shared.observability import sanitize_for_logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Disable FastAPI and uvicorn loggers to reduce logging noise
# Note: This doesn't prevent Pydantic validation errors from being printed
# Those appear to be printed before our code can intercept them
for logger_name in ['fastapi', 'uvicorn', 'uvicorn.error', 'uvicorn.access']:
    logging.getLogger(logger_name).disabled = True

logger.info("=" * 80)
logger.info("Vision agent app.py module loaded")
logger.info("=" * 80)


class MemoryIntegratedAgent:
    """Wrapper that adds memory integration to Strands Agent for A2A protocol."""
    
    def __init__(self, vision_agent_wrapper: VisionAgent):
        """Initialize with vision agent wrapper that has memory client."""
        self.vision_agent_wrapper = vision_agent_wrapper
        # Store reference to Strands agent but don't expose it directly
        # A2AServer might access strands_agent directly, so we need to intercept that
        self._strands_agent = vision_agent_wrapper.strands_agent
        # Set description on the underlying Strands agent for A2AServer
        if not hasattr(self._strands_agent, 'description') or not self._strands_agent.description:
            self._strands_agent.description = 'Vision agent for image analysis and visual content understanding'
        # Copy agent attributes for A2AServer compatibility
        self.model = self._strands_agent.model
        self.tools = getattr(self._strands_agent, 'tools', [])
        self.system_prompt = getattr(self._strands_agent, 'system_prompt', '')
        self.name = getattr(self._strands_agent, 'name', 'vision-agent')
        self.description = self._strands_agent.description
        # Delegate tool_registry to underlying Strands agent for A2AServer
        self.tool_registry = getattr(self._strands_agent, 'tool_registry', None)
        
        logger.info("MemoryIntegratedAgent initialized")
    
    @property
    def strands_agent(self):
        """
        Return self instead of underlying agent - this ensures A2AServer uses our wrapper's methods.
        If A2AServer accesses strands_agent and then calls invoke_async on it, it will use our invoke_async.
        """
        logger.info("strands_agent property accessed - returning self to ensure A2AServer uses our wrapper")
        return self
    
    def __getattr__(self, name):
        """Delegate attribute access to underlying Strands agent for A2AServer compatibility."""
        logger.info(f"__getattr__ called for attribute: {name}")
        # CRITICAL: Don't delegate invoke_async, stream_async, or __call__ - we define these ourselves
        # This ensures A2AServer uses our methods, not the underlying agent's
        if name in ['invoke_async', 'stream_async', '__call__', 'strands_agent']:
            raise AttributeError(f"'{type(self).__name__}' object should have '{name}' defined directly")
        # For other attributes, delegate to underlying Strands agent
        if hasattr(self._strands_agent, name):
            attr = getattr(self._strands_agent, name)
            logger.info(f"Delegating {name} to _strands_agent, type: {type(attr)}")
            return attr
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
    
    async def invoke_async(self, messages=None, **kwargs):
        """
        Override invoke_async to intercept multimodal messages from A2AServer.
        
        A2AServer converts A2A parts to Strands ContentBlock format before calling invoke_async.
        The messages will already be in Strands format with ContentBlocks like:
        - {"text": "..."} for text
        - {"image": {"format": "png", "source": {"bytes": b"..."}}} for images
        
        We log and verify the content is being passed correctly, then pass through to Strands agent.
        """
        logger.info("=" * 80)
        logger.info("*** invoke_async CALLED on MemoryIntegratedAgent ***")
        logger.info(f"messages type: {type(messages)}, kwargs keys: {list(kwargs.keys())}")
        
        # A2AServer has already converted A2A parts to Strands ContentBlock format
        # Messages should already be in the correct format
        if messages and isinstance(messages, list):
            logger.info(f"Processing {len(messages)} messages")
            for idx, msg in enumerate(messages):
                logger.info(f"Message {idx}: type={type(msg)}, keys={list(msg.keys()) if isinstance(msg, dict) else 'N/A'}")
                if isinstance(msg, dict):
                    content = msg.get("content", [])
                    logger.info(f"Message {idx} content: type={type(content)}, length={len(content) if isinstance(content, list) else 'N/A'}")
                    if isinstance(content, list):
                        # Log what we're receiving
                        has_image = any("image" in block for block in content if isinstance(block, dict))
                        has_text = any("text" in block for block in content if isinstance(block, dict))
                        logger.info(f"invoke_async: {len(content)} content blocks (image: {has_image}, text: {has_text})")
                        
                        if has_image:
                            # Find and log image details
                            for block_idx, block in enumerate(content):
                                if isinstance(block, dict) and "image" in block:
                                    image_info = block["image"]
                                    logger.info(f"Image block {block_idx}: {list(image_info.keys())}")
                                    if "source" in image_info:
                                        source = image_info["source"]
                                        logger.info(f"Image source keys: {list(source.keys())}")
                                        if "bytes" in source:
                                            logger.info(f"*** Image found in invoke_async: {len(source['bytes'])} bytes, format={image_info.get('format', 'unknown')} ***")
                                        elif "s3Location" in source:
                                            logger.info(f"Image S3 URI found: {source['s3Location'].get('uri', 'unknown')}")
                        else:
                            logger.warning(f"*** NO IMAGE FOUND in content blocks! Content: {content} ***")
                    else:
                        logger.info(f"invoke_async: content is not a list: {type(content)}")
                else:
                    logger.info(f"invoke_async: message is not a dict: {type(msg)}")
        else:
            logger.warning(f"*** invoke_async: messages is not a list: {type(messages)}, value: {messages} ***")
        
        # Pass through to Strands agent - A2AServer has already done the conversion
        logger.info("Calling _strands_agent.invoke_async...")
        result = await self._strands_agent.invoke_async(messages=messages, **kwargs)
        logger.info("_strands_agent.invoke_async returned")
        return result
    
    async def __call__(self, task_input: str = None, **kwargs) -> str:
        """
        Handle A2A task request - called by A2AServer.
        
        This method receives A2A protocol messages and converts them to
        Strands-compatible format for the vision agent.
        """
        import json
        import base64
        
        logger.info(f"__call__ invoked with task_input={task_input}, kwargs keys: {list(kwargs.keys())}")
        
        # Check if parts are passed directly in kwargs (A2AServer may pass parts separately)
        parts = kwargs.get('parts')
        if not parts:
            # Check if message is passed in kwargs (A2AServer may pass the full message object)
            message_obj = kwargs.get('message')
            if message_obj and isinstance(message_obj, dict) and 'parts' in message_obj:
                parts = message_obj.get('parts', [])
        
        if not parts:
            logger.error("No parts provided in A2A request")
            return json.dumps({"error": "No parts provided"})
        
        logger.info(f"Received A2A request with {len(parts)} parts")
        
        # Debug: log all parts
        for idx, part in enumerate(parts):
            logger.info(f"Part {idx}: {type(part)}, keys: {list(part.keys()) if isinstance(part, dict) else 'N/A'}")
            if isinstance(part, dict):
                logger.info(f"Part {idx} content preview: {str(part)[:200]}")
        
        # Parse A2A parts into Strands-compatible format
        prompt = ""
        image_base64 = None
        image_format = "jpeg"
        s3_uri = None
        
        for idx, part in enumerate(parts):
            if not isinstance(part, dict):
                logger.warning(f"Part {idx} is not a dict: {type(part)}")
                continue
            
            part_type = part.get('type')
            logger.info(f"Processing part {idx}: type={part_type}")
            
            # Handle A2A DataPart (for base64 content)
            if part_type == 'data':
                mime_type = part.get('mimeType', '')
                data_field = part.get('data', {})
                
                # A2A server sends data as a dict with base64 key
                if isinstance(data_field, dict):
                    data_base64 = data_field.get('base64', '')
                elif isinstance(data_field, str):
                    # Fallback: handle if it's still a string (backward compatibility)
                    data_base64 = data_field
                else:
                    logger.error(f"DataPart {idx} data is not dict or string: {type(data_field)}")
                    continue
                
                if not data_base64:
                    logger.warning(f"DataPart {idx} has no base64 data")
                    continue
                
                if not isinstance(data_base64, str):
                    logger.error(f"DataPart {idx} base64 data is not string: {type(data_base64)}")
                    continue
                
                # Extract format from mimeType
                if mime_type.startswith('image/'):
                    image_format = mime_type.split('/')[-1]
                    # Normalize format
                    if image_format == 'jpg':
                        image_format = 'jpeg'
                    
                    # Store the base64 string (don't decode yet)
                    image_base64 = data_base64
                    logger.info(f"Received image DataPart: format={image_format}, size={len(data_base64)} chars")
                elif mime_type.startswith('video/'):
                    # Handle video if needed
                    logger.info(f"Received video DataPart: {mime_type}")
            
            # Handle A2A FilePart (for S3 URIs)
            elif part_type == 'file':
                file_uri = part.get('fileUri', '')
                mime_type = part.get('mimeType', '')
                
                if file_uri:
                    logger.info(f"Received FilePart: uri={file_uri}, mimeType={mime_type}")
                    s3_uri = file_uri
                    
                    if mime_type.startswith('image/'):
                        image_format = mime_type.split('/')[-1]
                        if image_format == 'jpg':
                            image_format = 'jpeg'
            
            # Handle A2A TextPart
            elif part_type == 'text':
                text_content = part.get('text', '')
                if text_content:
                    prompt = text_content
                    logger.info(f"Received TextPart: '{text_content[:100]}...'")
        
        # Validate we have what we need
        if not prompt:
            logger.error("No text prompt provided in A2A request")
            return json.dumps({"error": "No text prompt provided"})
        
        if not image_base64 and not s3_uri:
            logger.error("No image data or S3 URI provided in A2A request")
            return json.dumps({"error": "No image data provided"})
        
        # Log what we're about to send
        logger.info(f"Calling vision agent: prompt='{prompt[:50]}...', format={image_format}, has_base64={bool(image_base64)}, has_s3={bool(s3_uri)}")
        if image_base64:
            logger.info(f"Image base64 length: {len(image_base64)} chars")
        
        # Call vision agent with the extracted data
        try:
            result = await self.vision_agent_wrapper.analyze_image(
                prompt=prompt,
                image_base64_string=image_base64,  # Pass as string, not bytes
                image_s3_uri=s3_uri,
                image_format=image_format
            )
            
            logger.info(f"Vision analysis completed successfully, result type: {type(result)}")
            # Return as JSON string - A2A server will wrap this in artifacts
            return json.dumps(result)
            
        except Exception as e:
            logger.error(f"Error analyzing image: {e}", exc_info=True)
            return json.dumps({"error": f"Analysis failed: {str(e)}"})
        
        # Legacy code removed - simplified handler above handles all cases
        # This should never be reached, but return error if it is
        return json.dumps({"error": "Invalid request format"})
    
    async def stream_async(self, content_blocks):
        """
        Stream agent response - called by A2AServer for streaming responses.
        
        Args:
            content_blocks: List of content blocks from the A2A message (can include A2A parts: FilePart, DataPart, TextPart)
            
        Yields:
            Streaming events from the agent
        """
        logger.info("=" * 80)
        logger.info("*** stream_async CALLED on MemoryIntegratedAgent ***")
        logger.info(f"content_blocks type: {type(content_blocks)}, length: {len(content_blocks) if isinstance(content_blocks, list) else 'N/A'}")
        logger.info(f"Full content_blocks structure: {str(content_blocks)[:500]}")
        
        import base64
        import json
        
        # A2AServer may pass content_blocks in different formats
        # Check if it's already in Strands format or still in A2A format
        has_image = False
        if content_blocks and isinstance(content_blocks, list):
            logger.info(f"Processing {len(content_blocks)} content blocks")
            for idx, block in enumerate(content_blocks):
                logger.info(f"Content block {idx}: type={type(block)}")
                if isinstance(block, dict):
                    block_keys = list(block.keys())
                    logger.info(f"  Keys: {block_keys}")
                    logger.info(f"  Full block: {str(block)[:300]}")
                    # Check if it's already in Strands format (has "image" or "text" keys)
                    if "image" in block:
                        logger.info(f"*** IMAGE FOUND in stream_async block {idx} ***")
                        has_image = True
                        image_info = block["image"]
                        logger.info(f"  Image format: {image_info.get('format', 'unknown')}")
                        if "source" in image_info:
                            source = image_info["source"]
                            logger.info(f"  Image source keys: {list(source.keys())}")
                            if "bytes" in source:
                                logger.info(f"  Image bytes length: {len(source['bytes'])}")
                            elif "s3Location" in source:
                                logger.info(f"  Image S3 URI: {source['s3Location'].get('uri', 'unknown')}")
                    elif "text" in block:
                        logger.info(f"Text found in stream_async block {idx}: {str(block.get('text', ''))[:100]}")
                    # Check if it's in A2A format (has "type" key)
                    elif "type" in block:
                        logger.info(f"*** A2A format block {idx}: type={block.get('type')} ***")
                        if block.get('type') == 'data':
                            logger.info(f"  *** A2A DataPart found - this should contain the image! ***")
                            logger.info(f"  MimeType: {block.get('mimeType', 'unknown')}")
                            data_field = block.get('data', {})
                            logger.info(f"  Data field type: {type(data_field)}")
                            if isinstance(data_field, dict):
                                logger.info(f"  Data field keys: {list(data_field.keys())}")
                                if 'base64' in data_field:
                                    base64_len = len(data_field['base64'])
                                    logger.info(f"  *** Base64 data found: {base64_len} chars ***")
                                    has_image = True
                    else:
                        logger.warning(f"  Unknown block format: {block}")
        
        if not has_image:
            logger.error("*** NO IMAGE FOUND in content_blocks! A2AServer may have dropped it during conversion. ***")
            logger.error("*** However, the vision agent IS analyzing the image, so it must be getting through somehow. ***")
            logger.error("*** This suggests A2AServer might be calling invoke_async directly on the underlying agent. ***")
        
        # Build content array preserving multimodal content
        # Handle A2A parts format (FilePart, DataPart, TextPart) and convert to Strands ContentBlocks
        # ALSO handle the case where A2AServer converts DataPart to a text block with base64 data
        content = []
        prompt = ""
        
        for block in content_blocks:
            if isinstance(block, dict):
                # Check if this is a text block that contains base64 image data (A2AServer bug/workaround)
                if "text" in block and "image" not in block and "type" not in block:
                    text_content = block["text"]
                    # Check if it starts with "[Structured Data]" and contains base64
                    if text_content.startswith("[Structured Data]") and '"base64":' in text_content:
                        logger.info("*** Found base64 data in text block - A2AServer converted DataPart to text! ***")
                        try:
                            # Extract JSON from the text block
                            # The text contains: [Structured Data]\n{ "base64": "..." }
                            # Find where the JSON object starts (after "[Structured Data]\n")
                            json_start = text_content.find('{')
                            if json_start == -1:
                                logger.error("No JSON object found in structured data text")
                                continue
                            
                            # Find the matching closing brace (should be at the end)
                            json_end = text_content.rfind('}')
                            if json_end <= json_start:
                                logger.error("No valid JSON object found")
                                continue
                            
                            # Extract the JSON string
                            json_str = text_content[json_start:json_end+1]
                            
                            # Parse the JSON
                            try:
                                data_obj = json.loads(json_str)
                                base64_data = data_obj.get("base64", "")
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse JSON: {e}")
                                # Fallback: try regex extraction
                                import re
                                # Match "base64": "..." where ... is the base64 string
                                # The base64 string can be very long, so we need to match until the closing quote
                                base64_match = re.search(r'"base64"\s*:\s*"([^"]+)"', json_str, re.DOTALL)
                                if base64_match:
                                    base64_data = base64_match.group(1)
                                else:
                                    logger.error("Could not extract base64 data from text block")
                                    continue
                            
                            if base64_data:
                                logger.info(f"*** Extracted base64 data: {len(base64_data)} chars ***")
                                # Decode base64 to bytes
                                data_bytes = base64.b64decode(base64_data)
                                logger.info(f"*** Decoded to {len(data_bytes)} bytes ***")
                                # Determine format from base64 header
                                # JPEG starts with /9j/, PNG starts with iVBORw0KGgo
                                if base64_data.startswith("/9j/"):
                                    format_str = "jpeg"
                                elif base64_data.startswith("iVBORw0KGgo"):
                                    format_str = "png"
                                else:
                                    # Default to jpeg if we can't determine
                                    format_str = "jpeg"
                                
                                logger.info(f"*** Creating ImageBlock with format: {format_str} ***")
                                # Create proper Strands ImageBlock
                                content.append({
                                    "image": {
                                        "format": format_str,
                                        "source": {
                                            "bytes": data_bytes
                                        }
                                    }
                                })
                                # Skip adding this as text
                                continue
                        except Exception as e:
                            logger.error(f"Failed to extract base64 from text block: {e}", exc_info=True)
                            # Fall through to treat it as regular text
                
                # Handle normal A2A format blocks
                block_type = block.get("type")
                
                # Handle A2A FilePart (for S3 URIs)
                if block_type == "file" and "fileUri" in block:
                    file_uri = block["fileUri"]
                    mime_type = block.get("mimeType", "")
                    
                    if file_uri.startswith("s3://"):
                        if mime_type.startswith("image/"):
                            format_str = mime_type.split("/")[-1]
                            content.append({
                                    "image": {
                                        "format": format_str,
                                        "source": {
                                            "s3Location": {
                                                "uri": file_uri
                                            }
                                        }
                                    }
                                })
                        elif mime_type.startswith("video/"):
                            format_str = mime_type.split("/")[-1]
                            if format_str == "3gp":
                                format_str = "three_gp"
                            content.append({
                                "video": {
                                    "format": format_str,
                                    "source": {
                                        "s3Location": {
                                            "uri": file_uri
                                        }
                                    }
                                }
                            })
                
                # Handle A2A DataPart (for base64 content)
                # DataPart structure: {"type": "data", "data": {"base64": "..."}, "mimeType": "image/jpeg"}
                elif block_type == "data" and "data" in block:
                    mime_type = block.get("mimeType", "")
                    data_field = block.get("data", {})
                    
                    # A2A server sends data as a dict with base64 key
                    if isinstance(data_field, dict):
                        data_base64 = data_field.get("base64", "")
                    elif isinstance(data_field, str):
                        # Fallback: handle if it's still a string (backward compatibility)
                        data_base64 = data_field
                    else:
                        logger.error(f"DataPart data is not dict or string: {type(data_field)}")
                        continue
                    
                    if not data_base64:
                        continue
                    
                    # Decode base64 to bytes
                    try:
                        data_bytes = base64.b64decode(data_base64)
                    except Exception as e:
                        logger.error(f"Failed to decode base64 data: {e}")
                        continue
                    
                    # Determine format from mimeType
                    def get_format_from_mime(mime: str) -> str:
                        format_map = {
                            "image/jpeg": "jpeg",
                            "image/png": "png",
                            "image/gif": "gif",
                            "image/webp": "webp",
                            "video/mp4": "mp4",
                            "video/quicktime": "mov",
                            "video/x-matroska": "mkv",
                            "video/webm": "webm",
                            "video/x-flv": "flv",
                            "video/mpeg": "mpeg",
                            "video/x-ms-wmv": "wmv",
                            "video/3gpp": "three_gp"
                        }
                        return format_map.get(mime, mime.split('/')[-1])
                    
                    format_str = get_format_from_mime(mime_type)
                    
                    # Build ContentBlock based on mimeType
                    if mime_type.startswith("image/"):
                        content.append({
                            "image": {
                                "format": format_str,
                                "source": {
                                    "bytes": data_bytes
                                }
                            }
                        })
                    elif mime_type.startswith("video/"):
                        if format_str == "3gp":
                            format_str = "three_gp"
                        content.append({
                            "video": {
                                "format": format_str,
                                "source": {
                                    "bytes": data_bytes
                                }
                            }
                        })
                
                # Handle A2A TextPart
                elif block_type == "text" and "text" in block:
                    text_content = block.get("text", "")
                    if text_content:
                        prompt = text_content
                        content.append({"text": text_content})
                
                # Handle legacy format (direct image/video parts) for backward compatibility
                elif block_type == "image" and "image" in block:
                    image_block = block["image"]
                    image_format = image_block.get("format", "jpeg")
                    source = image_block.get("source", {})
                    
                    if "base64" in source:
                        base64_str = source["base64"]
                        image_bytes = base64.b64decode(base64_str)
                        content.append({
                            "image": {
                                "format": image_format,
                                "source": {
                                    "bytes": image_bytes
                                }
                            }
                        })
                    elif "s3Location" in source:
                        content.append({
                            "image": {
                                "format": image_format,
                                "source": {
                                    "s3Location": {
                                        "uri": source["s3Location"].get("uri")
                                    }
                                }
                            }
                        })
                
                elif block_type == "video" and "video" in block:
                    video_block = block["video"]
                    video_format = video_block.get("format", "mp4")
                    if video_format == "3gp":
                        video_format = "three_gp"
                    source = video_block.get("source", {})
                    
                    if "base64" in source:
                        base64_str = source["base64"]
                        video_bytes = base64.b64decode(base64_str)
                        content.append({
                            "video": {
                                "format": video_format,
                                "source": {
                                    "bytes": video_bytes
                                }
                            }
                        })
                    elif "s3Location" in source:
                        content.append({
                            "video": {
                                "format": video_format,
                                "source": {
                                    "s3Location": {
                                        "uri": source["s3Location"].get("uri")
                                    }
                                }
                            }
                        })
        
        # Ensure we have at least text content - Bedrock requires conversation to start with user message
        # If we only have media and no text, add a default prompt
        if not any(isinstance(c, dict) and "text" in c for c in content):
            if prompt:
                content.append({"text": prompt})
            else:
                # If no text at all, add a default prompt based on what media we have
                has_image = any(isinstance(c, dict) and "image" in c for c in content)
                has_video = any(isinstance(c, dict) and "video" in c for c in content)
                if has_image:
                    content.append({"text": "Analyze this image."})
                elif has_video:
                    content.append({"text": "Analyze this video."})
                else:
                    content.append({"text": "Analyze this content."})
        
        # Build normalized messages with multimodal content - MUST start with user role
        normalized_messages = [{"role": "user", "content": content}]
        
        # If Strands agent has stream_async, delegate to it
        if hasattr(self._strands_agent, 'stream_async'):
            async for event in self._strands_agent.stream_async(prompt=normalized_messages):
                yield event
        else:
            # Fallback: use invoke_async and yield the result as a single event
            response = await self._strands_agent.invoke_async(messages=normalized_messages)
            # Yield the response as a content delta event
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                response_content = response.message.content
                if isinstance(response_content, list):
                    for block in response_content:
                        if isinstance(block, dict) and "text" in block:
                            yield {"type": "content_delta", "delta": {"text": block["text"]}}
                elif isinstance(response_content, str):
                    yield {"type": "content_delta", "delta": {"text": response_content}}
    
    async def run(self, messages, **kwargs):
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "user").lower()
                content = msg.get("content", "")
                # Convert to list of ContentBlocks format
                if isinstance(content, str):
                    content = [{"text": content}]
                elif isinstance(content, dict):
                    if "text" in content:
                        content = [content]
                    else:
                        content = [{"text": str(content)}]
                elif isinstance(content, list):
                    # Ensure each element is a ContentBlock dict
                    formatted_blocks = []
                    for block in content:
                        if isinstance(block, str):
                            formatted_blocks.append({"text": block})
                        elif isinstance(block, dict) and "text" in block:
                            formatted_blocks.append(block)
                        else:
                            formatted_blocks.append({"text": str(block)})
                    content = formatted_blocks
                else:
                    content = [{"text": str(content) if content else ""}]
                normalized_messages.append({"role": role, "content": content})
            else:
                normalized_messages.append(msg)
        
        response = await self.strands_agent.invoke_async(prompt=normalized_messages)
        
        # Extract content from AgentResult
        response_content = ""
        if hasattr(response, 'message'):
            message = response.message
            if isinstance(message, dict):
                content = message.get("content", [])
            else:
                content = getattr(message, "content", [])
            
            # Extract text from content blocks
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        if text:
                            text_parts.append(text)
                    elif isinstance(block, str):
                        text_parts.append(block)
                response_content = " ".join(text_parts) if text_parts else ""
            elif isinstance(content, str):
                response_content = content
            else:
                response_content = str(content) if content else ""
        elif hasattr(response, 'content'):
            response_content = response.content
        else:
            response_content = str(response) if response else ""
        
        # Create a response object with content attribute for compatibility
        class Response:
            def __init__(self, content):
                self.content = content
        
        response = Response(response_content)
        
        # Store interaction in memory if we have user info
        if user_message and "user_id" in kwargs and "session_id" in kwargs:
            try:
                await self.vision_agent_wrapper.memory.store_interaction(
                    user_id=kwargs["user_id"],
                    session_id=kwargs["session_id"],
                    user_message=user_message,
                    agent_response=response.content,
                    agent_name=self.vision_agent_wrapper.agent_name
                )
            except Exception as e:
                logger.warning(f"Failed to store interaction in memory: {e}")
        
        return response


def create_vision_agent():
    """Create vision agent with Strands and memory integration."""
    # Create the vision agent wrapper (handles memory integration)
    vision_agent_wrapper = VisionAgent()
    
    # Create memory-integrated agent
    return MemoryIntegratedAgent(vision_agent_wrapper)


def main():
    """Start vision agent A2A server."""
    logger.info("Starting Vision Agent A2A Server...")
    
    # Create agent
    agent = create_vision_agent()
    
    # Log agent type and methods to debug
    logger.info(f"Agent type: {type(agent)}")
    logger.info(f"Agent has invoke_async: {hasattr(agent, 'invoke_async')}")
    logger.info(f"Agent has __call__: {hasattr(agent, '__call__')}")
    logger.info(f"Agent has strands_agent: {hasattr(agent, 'strands_agent')}")
    if hasattr(agent, 'invoke_async'):
        logger.info(f"invoke_async type: {type(agent.invoke_async)}")
    
    # Create A2A server (agent card is auto-generated from the agent)
    server = A2AServer(
        agent=agent,
        port=9000,
        host="0.0.0.0"
    )
    
    logger.info("Vision Agent ready on port 9000")
    logger.info("Agent Card: http://0.0.0.0:9000/.well-known/agent-card.json")
    
    # Start server (BLOCKING - runs forever)
    server.serve()


if __name__ == "__main__":
    main()
