"""Vision specialist agent for image and video analysis."""

from typing import List, Dict, Any, Optional
import time
import os
import base64
from strands import Agent
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.memory_client import MemoryClient
from agents.shared.observability import AgentLogger, track_latency


class VisionAgent:
    """Specialist agent for image and video analysis and visual content understanding."""
    
    def __init__(self):
        self.agent_name = "vision"
        self.logger = AgentLogger(self.agent_name)
        self.memory = MemoryClient()
        
        # Initialize Strands agent with vision model (Nova Pro for vision capabilities)
        model_id = os.getenv("VISION_MODEL", "amazon.nova-pro-v1:0")
        self.strands_agent = Agent(
            model=model_id,
            system_prompt=self._get_system_prompt()
        )
        self.max_tokens = int(os.getenv("BEDROCK_MAX_TOKENS", "4096"))
    
    def _get_system_prompt(self) -> str:
        return """You are a vision specialist agent focused on image and video analysis and visual content understanding.

Your capabilities:
- Analyze images and describe their content
- Analyze videos and summarize their content
- Identify objects, people, text in images and videos
- Provide detailed visual descriptions
- Answer questions about images and videos
- Extract information from visual content

Be detailed and accurate in your visual analysis."""
    
    async def analyze_image(
        self,
        prompt: str,
        image_base64_string: Optional[str] = None,
        image_s3_uri: Optional[str] = None,
        image_format: str = "jpeg",
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze image using base64-encoded string or S3 URI."""
        
        # Validate inputs
        if not prompt or not prompt.strip():
            raise ValueError("Prompt is required")
        
        if not image_base64_string and not image_s3_uri:
            raise ValueError("Either image_base64_string or image_s3_uri must be provided")
        
        # Build content array for message
        content = []
        
        # Add image content block
        if image_base64_string:
            # CRITICAL: Decode base64 string to bytes for Strands
            try:
                # Remove any whitespace/newlines
                clean_base64 = image_base64_string.strip().replace('\n', '').replace('\r', '')
                
                # Decode to bytes
                image_bytes = base64.b64decode(clean_base64)
                logger.info(f"Decoded image: {len(image_bytes)} bytes, format={image_format}")
                
                # Validate it's actually an image
                if len(image_bytes) < 100:
                    logger.error(f"Image too small: {len(image_bytes)} bytes")
                    return {"error": "Image data too small - may be corrupted"}
                
            except Exception as e:
                logger.error(f"Failed to decode base64: {e}")
                return {"error": f"Invalid base64 image data: {str(e)}"}
            
            # Build Strands ContentBlock with bytes
            content.append({
                "image": {
                    "format": image_format,
                    "source": {
                        "bytes": image_bytes  # bytes object, not string!
                    }
                }
            })
        elif image_s3_uri:
            # Use S3 URI directly
            if not image_s3_uri.startswith("s3://"):
                raise ValueError("S3 URI must start with 's3://'")
            
            content.append({
                "image": {
                    "format": image_format,
                    "source": {
                        "s3Location": {
                            "uri": image_s3_uri
                        }
                    }
                }
            })
            logger.info(f"Using S3 URI: {image_s3_uri}")
        else:
            logger.error("No image provided (neither base64 nor S3 URI)")
            return {"error": "No image provided"}
        
        # Add text prompt
        full_prompt = prompt
        if additional_context:
            full_prompt = f"{additional_context}\n\n{prompt}"
        
        content.append({"text": full_prompt})
        
        # Build message for Strands
        messages = [{"role": "user", "content": content}]
        
        # Log what we're sending to Strands
        logger.info(f"Invoking vision model with prompt: '{prompt[:100]}...'")
        logger.info(f"Content blocks: {len(content)} blocks (image: {any('image' in block for block in content)}, text: {any('text' in block for block in content)})")
        if any('image' in block for block in content):
            image_block = next((block for block in content if 'image' in block), None)
            if image_block and 'image' in image_block:
                image_info = image_block['image']
                if 'source' in image_info:
                    source = image_info['source']
                    if 'bytes' in source:
                        logger.info(f"Image bytes size: {len(source['bytes'])} bytes")
                    elif 's3Location' in source:
                        logger.info(f"Image S3 URI: {source['s3Location'].get('uri', 'unknown')}")
        
        # Invoke agent
        try:
            response = await self.strands_agent.invoke_async(messages=messages)
            
            # Extract response text
            if hasattr(response, 'message'):
                content_blocks = response.message.content
                # Extract text from content blocks
                text_parts = []
                for block in content_blocks:
                    if isinstance(block, dict) and "text" in block:
                        text_parts.append(block["text"])
                response_text = " ".join(text_parts)
            else:
                response_text = str(response)
            
            logger.info(f"Vision analysis complete: {len(response_text)} chars")
            
            return {
                "text": response_text,
                "usage": getattr(response, 'usage', None)
            }
            
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}", exc_info=True)
            return {"error": f"Analysis failed: {str(e)}"}
    
    async def analyze_video(
        self,
        prompt: str,
        video_base64_string: Optional[str] = None,
        video_s3_uri: Optional[str] = None,
        video_format: str = "mp4",
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze video using base64-encoded string or S3 URI."""
        
        # Validate inputs
        if not prompt or not prompt.strip():
            raise ValueError("Prompt is required")
        
        if not video_base64_string and not video_s3_uri:
            raise ValueError("Either video_base64_string or video_s3_uri must be provided")
        
        # Special case for 3GP format
        if video_format == "3gp":
            video_format = "three_gp"
        
        # Build content array for message
        content = []
        
        # Add video content block
        if video_base64_string:
            try:
                # CRITICAL: Decode base64 string to bytes
                video_bytes = base64.b64decode(video_base64_string)
            except Exception as e:
                raise ValueError(f"Invalid base64 data: {str(e)}")
            
            content.append({
                "video": {
                    "format": video_format,
                    "source": {
                        "bytes": video_bytes  # bytes object, not string!
                    }
                }
            })
        elif video_s3_uri:
            if not video_s3_uri.startswith("s3://"):
                raise ValueError("S3 URI must start with 's3://'")
            
            content.append({
                "video": {
                    "format": video_format,
                    "source": {
                        "s3Location": {
                            "uri": video_s3_uri
                        }
                    }
                }
            })
        
        # Add text prompt
        full_prompt = f"{additional_context}\n\n{prompt}" if additional_context else prompt
        content.append({"text": full_prompt})
        
        # Build message
        messages = [{"role": "user", "content": content}]
        
        # Invoke agent
        response = await self.strands_agent.invoke_async(
            messages=messages,
            max_tokens=self.max_tokens
        )
        
        # Extract response content
        response_text = ""
        if hasattr(response, 'content') and response.content:
            if isinstance(response.content, list) and len(response.content) > 0:
                if isinstance(response.content[0], dict) and "text" in response.content[0]:
                    response_text = response.content[0]["text"]
                else:
                    response_text = str(response.content[0])
            elif isinstance(response.content, str):
                response_text = response.content
            else:
                response_text = str(response.content)
        
        return {
            "text": response_text,
            "usage": {
                "inputTokens": response.usage.input_tokens if hasattr(response, 'usage') and response.usage else None,
                "outputTokens": response.usage.output_tokens if hasattr(response, 'usage') and response.usage else None
            }
        }
    
    @track_latency("vision")
    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process vision-related request."""
        start_time = time.time()
        
        self.logger.log_request(
            user_id=request.user_id,
            session_id=request.session_id,
            message=request.message
        )
        
        try:
            # Build messages with context
            messages = request.context + [
                {"role": "user", "content": request.message}
            ]
            
            # Process with Strands agent
            response = await self.strands_agent.invoke_async(messages=messages, max_tokens=self.max_tokens)
            
            # Extract response content
            response_content = ""
            if hasattr(response, 'content') and response.content:
                if isinstance(response.content, list) and len(response.content) > 0:
                    if isinstance(response.content[0], dict) and "text" in response.content[0]:
                        response_content = response.content[0]["text"]
                    else:
                        response_content = str(response.content[0])
                elif isinstance(response.content, str):
                    response_content = response.content
                else:
                    response_content = str(response.content)
            
            processing_time = (time.time() - start_time) * 1000
            
            # Store interaction in memory
            await self.memory.store_interaction(
                user_id=request.user_id,
                session_id=request.session_id,
                user_message=request.message,
                agent_response=response_content,
                agent_name=self.agent_name
            )
            
            self.logger.log_response(
                user_id=request.user_id,
                session_id=request.session_id,
                processing_time_ms=processing_time,
                success=True
            )
            
            return AgentResponse(
                content=response_content,
                agent_name=self.agent_name,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            self.logger.log_error(e, request.user_id, request.session_id)
            raise

