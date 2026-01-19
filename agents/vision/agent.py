"""Vision specialist agent for image and video analysis."""

from typing import Dict, Any, Optional
import time
import os
import base64
from strands import Agent
from agents.shared.models import AgentRequest, AgentResponse
from agents.shared.memory_client import MemoryClient
from agents.shared.observability import AgentLogger, track_latency


class VisionAgent:
    """Specialist agent for image and video analysis and visual content understanding.
    
    This agent uses Amazon Bedrock's vision-capable models (e.g., Nova Pro) to analyze
    images and videos. It supports both base64-encoded media and S3 URIs as input sources.
    
    The agent can:
    - Analyze images and describe their content
    - Analyze videos and summarize their content
    - Identify objects, people, and text in visual media
    - Provide detailed visual descriptions
    - Answer questions about visual content
    - Extract information from images and videos
    
    Attributes:
        agent_name (str): The name of the agent ("vision").
        logger (AgentLogger): Logger instance for observability.
        memory (MemoryClient): Client for storing interactions in memory.
        strands_agent (Agent): The underlying Strands agent instance.
        max_tokens (int): Maximum tokens for agent responses.
    """
    
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
    
    def _extract_response_text(self, response: Any) -> str:
        """Extract text content from a Strands agent response.
        
        Handles different response formats:
        - Response with message.content (list of content blocks)
        - Response with content attribute (list or string)
        - Direct string conversion fallback
        
        Args:
            response: The response object from Strands agent invocation.
            
        Returns:
            str: Extracted text content from the response.
        """
        # Handle response with message attribute
        if hasattr(response, 'message'):
            content_blocks = response.message.content
            text_parts = []
            for block in content_blocks:
                if isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
            return " ".join(text_parts)
        
        # Handle response with content attribute
        if hasattr(response, 'content') and response.content:
            if isinstance(response.content, list) and len(response.content) > 0:
                if isinstance(response.content[0], dict) and "text" in response.content[0]:
                    return response.content[0]["text"]
                else:
                    return str(response.content[0])
            elif isinstance(response.content, str):
                return response.content
            else:
                return str(response.content)
        
        # Fallback to string conversion
        return str(response)
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for the vision agent.
        
        Returns:
            str: The system prompt describing the agent's capabilities.
        """
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
        """Analyze an image using base64-encoded string or S3 URI.
        
        This method processes an image and returns a detailed analysis based on the
        provided prompt. The image can be provided either as a base64-encoded string
        or as an S3 URI.
        
        Args:
            prompt: The text prompt describing what analysis to perform on the image.
            image_base64_string: Base64-encoded image data. Must be provided if
                image_s3_uri is not provided.
            image_s3_uri: S3 URI pointing to the image (format: s3://bucket/key).
                Must be provided if image_base64_string is not provided.
            image_format: Format of the image (e.g., "jpeg", "png", "gif").
                Defaults to "jpeg".
            additional_context: Optional additional context to prepend to the prompt.
        
        Returns:
            Dict containing:
                - "text" (str): The analysis response text
                - "usage" (dict, optional): Token usage information if available
                - "error" (str): Error message if analysis failed
        
        Raises:
            ValueError: If prompt is empty or neither image source is provided.
            ValueError: If S3 URI doesn't start with "s3://".
        
        Example:
            >>> agent = VisionAgent()
            >>> result = await agent.analyze_image(
            ...     prompt="What objects are in this image?",
            ...     image_base64_string="iVBORw0KGgoAAAANS..."
            ... )
            >>> print(result["text"])
        """
        
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
                self.logger.info(f"Decoded image: {len(image_bytes)} bytes, format={image_format}")
                
                # Validate it's actually an image
                if len(image_bytes) < 100:
                    self.logger.error(f"Image too small: {len(image_bytes)} bytes")
                    return {"error": "Image data too small - may be corrupted"}
                
            except Exception as e:
                self.logger.error(f"Failed to decode base64: {e}")
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
            self.logger.info(f"Using S3 URI: {image_s3_uri}")
        else:
            self.logger.error("No image provided (neither base64 nor S3 URI)")
            return {"error": "No image provided"}
        
        # Add text prompt
        full_prompt = prompt
        if additional_context:
            full_prompt = f"{additional_context}\n\n{prompt}"
        
        content.append({"text": full_prompt})
        
        # Build message for Strands
        messages = [{"role": "user", "content": content}]
        
        # Log what we're sending to Strands
        self.logger.info(f"Invoking vision model with prompt: '{prompt[:100]}...'")
        self.logger.info(f"Content blocks: {len(content)} blocks (image: {any('image' in block for block in content)}, text: {any('text' in block for block in content)})")
        if any('image' in block for block in content):
            image_block = next((block for block in content if 'image' in block), None)
            if image_block and 'image' in image_block:
                image_info = image_block['image']
                if 'source' in image_info:
                    source = image_info['source']
                    if 'bytes' in source:
                        self.logger.info(f"Image bytes size: {len(source['bytes'])} bytes")
                    elif 's3Location' in source:
                        self.logger.info(f"Image S3 URI: {source['s3Location'].get('uri', 'unknown')}")
        
        # Invoke agent
        try:
            response = await self.strands_agent.invoke_async(messages=messages)
            
            # Extract response text
            response_text = self._extract_response_text(response)
            
            self.logger.info(f"Vision analysis complete: {len(response_text)} chars")
            
            return {
                "text": response_text,
                "usage": getattr(response, 'usage', None)
            }
            
        except Exception as e:
            self.logger.error(f"Vision analysis failed: {e}", exc_info=True)
            return {"error": f"Analysis failed: {str(e)}"}
    
    async def analyze_video(
        self,
        prompt: str,
        video_base64_string: Optional[str] = None,
        video_s3_uri: Optional[str] = None,
        video_format: str = "mp4",
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze a video using base64-encoded string or S3 URI.
        
        This method processes a video and returns a detailed analysis based on the
        provided prompt. The video can be provided either as a base64-encoded string
        or as an S3 URI.
        
        Args:
            prompt: The text prompt describing what analysis to perform on the video.
            video_base64_string: Base64-encoded video data. Must be provided if
                video_s3_uri is not provided.
            video_s3_uri: S3 URI pointing to the video (format: s3://bucket/key).
                Must be provided if video_base64_string is not provided.
            video_format: Format of the video (e.g., "mp4", "mov", "avi", "3gp").
                Note: "3gp" is automatically converted to "three_gp" for compatibility.
                Defaults to "mp4".
            additional_context: Optional additional context to prepend to the prompt.
        
        Returns:
            Dict containing:
                - "text" (str): The analysis response text
                - "usage" (dict): Token usage information with "inputTokens" and
                  "outputTokens" keys (may be None if unavailable)
                - "error" (str): Error message if analysis failed
        
        Raises:
            ValueError: If prompt is empty or neither video source is provided.
            ValueError: If S3 URI doesn't start with "s3://".
        
        Example:
            >>> agent = VisionAgent()
            >>> result = await agent.analyze_video(
            ...     prompt="Summarize what happens in this video",
            ...     video_s3_uri="s3://my-bucket/video.mp4"
            ... )
            >>> print(result["text"])
        """
        
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
                # CRITICAL: Decode base64 string to bytes for Strands
                # Remove any whitespace/newlines
                clean_base64 = video_base64_string.strip().replace('\n', '').replace('\r', '')
                
                # Decode to bytes
                video_bytes = base64.b64decode(clean_base64)
                self.logger.info(f"Decoded video: {len(video_bytes)} bytes, format={video_format}")
                
                # Validate it's actually a video (videos are typically larger than images)
                if len(video_bytes) < 1000:
                    self.logger.error(f"Video too small: {len(video_bytes)} bytes")
                    return {"error": "Video data too small - may be corrupted"}
                
            except Exception as e:
                self.logger.error(f"Failed to decode base64: {e}")
                return {"error": f"Invalid base64 video data: {str(e)}"}
            
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
            
            self.logger.info(f"Using S3 URI: {video_s3_uri}")
            
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
        try:
            response = await self.strands_agent.invoke_async(
                messages=messages,
                max_tokens=self.max_tokens
            )
            
            # Extract response content
            response_text = self._extract_response_text(response)
            
            self.logger.info(f"Video analysis complete: {len(response_text)} chars")
            
            return {
                "text": response_text,
                "usage": {
                    "inputTokens": response.usage.input_tokens if hasattr(response, 'usage') and response.usage else None,
                    "outputTokens": response.usage.output_tokens if hasattr(response, 'usage') and response.usage else None
                }
            }
            
        except Exception as e:
            self.logger.error(f"Video analysis failed: {e}", exc_info=True)
            return {"error": f"Analysis failed: {str(e)}"}
    
    @track_latency("vision")
    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process a vision-related request from the orchestrator.
        
        This is the main entry point for processing requests in the A2A (agent-to-agent)
        communication flow. It handles the request, invokes the vision model, stores
        the interaction in memory, and returns a standardized response.
        
        Args:
            request: The agent request containing message, context, user_id, and
                session_id. The context may include previous conversation history.
        
        Returns:
            AgentResponse containing:
                - content (str): The agent's response text
                - agent_name (str): Name of the agent ("vision")
                - processing_time_ms (float): Processing time in milliseconds
                - metadata (dict, optional): Additional metadata
                - timestamp (datetime): Response timestamp
        
        Raises:
            Exception: Any exception raised during processing will be logged and
                re-raised. The error is logged with user_id and session_id for
                observability.
        
        Note:
            This method is decorated with @track_latency to automatically track
            performance metrics. Interactions are automatically stored in memory
            for conversation continuity.
        """
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
            response_content = self._extract_response_text(response)
            
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

