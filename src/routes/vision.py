"""Vision API routes for image and video analysis."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal, Dict, Any
import boto3
from datetime import datetime
import os
import uuid
import base64
import logging
import httpx

logger = logging.getLogger(__name__)

# Disable httpx request/response body logging to avoid logging base64 encoded media
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)  # Only log warnings and errors, not request/response bodies

router = APIRouter(prefix="/vision", tags=["vision"])

# Configuration constants
S3_BUCKET = os.getenv("S3_VISION_BUCKET", "agentcore-vision-uploads")
S3_UPLOAD_PREFIX = os.getenv("S3_UPLOAD_PREFIX", "uploads/")
PRESIGNED_URL_EXPIRY = int(os.getenv("VISION_PRESIGNED_URL_EXPIRY", "3600"))

# Accepted file types for uploads
ACCEPTED_FILE_TYPES = [
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "video/mp4", "video/quicktime", "video/x-matroska", "video/webm",
    "video/x-flv", "video/mpeg", "video/x-ms-wmv", "video/3gpp"
]

# Initialize S3 client lazily to avoid errors if boto3 isn't configured at import time
_s3_client = None

def get_s3_client() -> boto3.client:
    """Get or create S3 client.
    
    Creates a singleton S3 client instance. The client is created lazily
    on first access to avoid errors if boto3 credentials aren't configured
    at import time.
    
    Returns:
        boto3.client: Configured S3 client instance.
        
    Raises:
        HTTPException: If S3 client creation fails (status 503).
    """
    global _s3_client
    if _s3_client is None:
        try:
            _s3_client = boto3.client('s3')
        except Exception as e:
            logger.error(f"Failed to create S3 client: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"S3 client not available: {str(e)}"
            )
    return _s3_client


def get_format_string(mime_type: str) -> str:
    """Convert MIME type to Bedrock format string.
    
    Maps common MIME types to their corresponding format strings used by
    AWS Bedrock for multimodal content. Handles special cases like
    video/quicktime -> mov and video/3gpp -> three_gp.
    
    Args:
        mime_type: MIME type string (e.g., "image/jpeg", "video/mp4").
        
    Returns:
        str: Format string for Bedrock. If MIME type is not in the mapping,
             returns the subtype (part after '/') as fallback.
    """
    format_map = {
        # Images
        "image/jpeg": "jpeg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
        # Videos
        "video/mp4": "mp4",
        "video/quicktime": "mov",
        "video/x-matroska": "mkv",
        "video/webm": "webm",
        "video/x-flv": "flv",
        "video/mpeg": "mpeg",
        "video/x-ms-wmv": "wmv",
        "video/3gpp": "three_gp"  # SPECIAL CASE: 3GP uses "three_gp"
    }
    return format_map.get(mime_type, mime_type.split('/')[-1])


def _extract_format_from_s3_uri(s3_uri: str) -> str:
    """Extract format string from S3 URI.
    
    Extracts the file extension from an S3 URI and converts it to a
    Bedrock-compatible format string. Handles special cases like 3gp.
    
    Args:
        s3_uri: S3 URI string (e.g., "s3://bucket/path/file.mp4").
        
    Returns:
        str: Format string (e.g., "mp4", "three_gp"). Defaults to "jpeg"
             if no extension is found.
    """
    # Extract extension from URI
    if '.' in s3_uri:
        extension = s3_uri.split('.')[-1].lower()
        # Handle special case for 3gp
        if extension == "3gp":
            return "three_gp"
        return extension
    # Default fallback if no extension found
    return "jpeg"


def _build_media_content(
    media_type: Literal["image", "video"],
    format_str: str,
    base64_data: Optional[str],
    s3_uri: Optional[str]
) -> Dict[str, Any]:
    """Build media content block for A2A protocol.
    
    Constructs the media content structure required by the A2A protocol
    for multimodal requests. Supports both base64-encoded data and S3 URIs.
    
    Args:
        media_type: Type of media, either "image" or "video".
        format_str: Format string for the media (e.g., "jpeg", "mp4").
        base64_data: Optional base64-encoded media data.
        s3_uri: Optional S3 URI pointing to the media file.
        
    Returns:
        dict: Media content block with type, format, and source information.
        
    Raises:
        ValueError: If neither base64_data nor s3_uri is provided.
    """
    if not base64_data and not s3_uri:
        raise ValueError("Either base64_data or s3_uri must be provided")
    
    if base64_data:
        source = {"base64": base64_data}
    else:
        source = {"s3Location": {"uri": s3_uri}}
    
    if media_type == "image":
        return {
            "type": "image",
            "image": {
                "format": format_str,
                "source": source
            }
        }
    else:  # video
        return {
            "type": "video",
            "video": {
                "format": format_str,
                "source": source
            }
        }


class PresignedUrlRequest(BaseModel):
    """Request model for generating S3 presigned upload URLs.
    
    Attributes:
        fileName: Name of the file to be uploaded.
        fileType: MIME type of the file (must be in ACCEPTED_FILE_TYPES).
    """
    fileName: str
    fileType: str


class PresignedUrlResponse(BaseModel):
    """Response model for presigned URL generation.
    
    Attributes:
        uploadUrl: Presigned URL for uploading the file to S3.
        s3Uri: Full S3 URI where the file will be stored.
        key: S3 object key (path) for the uploaded file.
    """
    uploadUrl: str
    s3Uri: str
    key: str


class VisionAnalysisRequest(BaseModel):
    """Request model for vision analysis.
    
    Attributes:
        prompt: Text prompt/question about the media to analyze.
        mediaType: Type of media, either "image" or "video".
        base64Data: Optional base64-encoded media data.
        mimeType: Optional MIME type of the media (required if base64Data is provided).
        s3Uri: Optional S3 URI pointing to the media file.
        
    Note:
        Either base64Data or s3Uri must be provided. If base64Data is provided,
        mimeType should also be provided to ensure correct format detection.
    """
    prompt: str
    mediaType: Literal["image", "video"]
    base64Data: Optional[str] = None
    mimeType: Optional[str] = None
    s3Uri: Optional[str] = None


class VisionAnalysisResponse(BaseModel):
    """Response model for vision analysis results.
    
    Attributes:
        text: The vision agent's analysis response text.
        usage: Optional usage metadata (tokens, cost, etc.) from the vision agent.
    """
    text: str
    usage: Optional[dict] = None


@router.post("/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_url(request: PresignedUrlRequest) -> PresignedUrlResponse:
    """Generate S3 presigned URL for file upload.
    
    Creates a presigned URL that allows clients to upload media files directly
    to S3 without exposing AWS credentials. The URL is valid for a configurable
    period (default 1 hour).
    
    Args:
        request: Request containing fileName and fileType.
        
    Returns:
        PresignedUrlResponse containing the upload URL, S3 URI, and object key.
        
    Raises:
        HTTPException: 
            - 400 if file type is not supported.
            - 500 if presigned URL generation fails.
            - 503 if S3 client is not available.
    """
    try:
        # Validate file type
        if request.fileType not in ACCEPTED_FILE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {request.fileType}. Supported types: {', '.join(ACCEPTED_FILE_TYPES)}"
            )
        
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        file_extension = request.fileName.split('.')[-1] if '.' in request.fileName else 'bin'
        key = f"{S3_UPLOAD_PREFIX}{timestamp}-{unique_id}.{file_extension}"
        
        s3 = get_s3_client()
        upload_url = s3.generate_presigned_url(
            'put_object',
            Params={'Bucket': S3_BUCKET, 'Key': key, 'ContentType': request.fileType},
            ExpiresIn=PRESIGNED_URL_EXPIRY
        )
        
        s3_uri = f"s3://{S3_BUCKET}/{key}"
        return PresignedUrlResponse(uploadUrl=upload_url, s3Uri=s3_uri, key=key)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned URL: {str(e)}")


@router.post("/analyze", response_model=VisionAnalysisResponse)
async def analyze_vision(request: VisionAnalysisRequest) -> VisionAnalysisResponse:
    """Analyze image or video via vision agent.
    
    Processes vision analysis requests by forwarding them to the orchestrator,
    which routes to the vision specialist agent. Supports both base64-encoded
    media and S3 URIs.
    
    Args:
        request: VisionAnalysisRequest containing prompt, media type, and media data.
        
    Returns:
        VisionAnalysisResponse containing the analysis text and optional usage metadata.
        
    Raises:
        HTTPException:
            - 400 if prompt is missing, no media data provided, media type is invalid,
              base64 data is invalid, S3 URI format is invalid, or mimeType doesn't
              match mediaType.
            - 500 if vision analysis fails.
            - 503 if orchestrator is unavailable or endpoint not found.
    """
    # Validate request
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")
    
    # Validate that either base64Data or s3Uri is provided
    if not request.base64Data and not request.s3Uri:
        raise HTTPException(status_code=400, detail="Either base64Data or s3Uri must be provided")
    
    # Validate media type
    if request.mediaType not in ["image", "video"]:
        raise HTTPException(status_code=400, detail="mediaType must be 'image' or 'video'")
    
    # Validate base64 data if provided
    if request.base64Data:
        try:
            # Try to decode to validate base64
            base64.b64decode(request.base64Data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 data")
        
        # Validate mimeType is provided when base64Data is used
        if not request.mimeType:
            raise HTTPException(
                status_code=400,
                detail="mimeType is required when base64Data is provided"
            )
        
        # Validate mimeType matches mediaType
        expected_prefix = "image/" if request.mediaType == "image" else "video/"
        if not request.mimeType.startswith(expected_prefix):
            raise HTTPException(
                status_code=400,
                detail=f"mimeType '{request.mimeType}' does not match mediaType '{request.mediaType}'"
            )
        
        # Validate mimeType is in accepted types
        if request.mimeType not in ACCEPTED_FILE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported mimeType: {request.mimeType}. Supported types: {', '.join(ACCEPTED_FILE_TYPES)}"
            )
    
    # Validate S3 URI format if provided
    if request.s3Uri and not request.s3Uri.startswith("s3://"):
        raise HTTPException(status_code=400, detail="S3 URI must start with 's3://'")
    
    # Build media content block for A2A protocol
    if request.base64Data:
        format_str = get_format_string(request.mimeType)
    else:  # s3Uri
        format_str = _extract_format_from_s3_uri(request.s3Uri)
    
    try:
        media_content = _build_media_content(
            media_type=request.mediaType,
            format_str=format_str,
            base64_data=request.base64Data,
            s3_uri=request.s3Uri
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Forward request to orchestrator (port 9000) which will route to vision agent
    orchestrator_base = os.getenv("ORCHESTRATOR_BASE", "http://localhost:9000")
    
    try:
        # Build request to orchestrator with multimodal content
        orchestrator_payload = {
            "message": request.prompt,
            "media_content": media_content,
            "media_type": request.mediaType
        }
        
        logger.info(f"Forwarding vision request to orchestrator at {orchestrator_base}/api/vision")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Call orchestrator's vision endpoint
            response = await client.post(
                f"{orchestrator_base}/api/vision",
                json=orchestrator_payload,
                headers={"Content-Type": "application/json"}
            )
            
            response.raise_for_status()
            result = response.json()
            
            return VisionAnalysisResponse(
                text=result.get("text", str(result)),
                usage=result.get("usage")
            )
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=503,
                detail="Orchestrator vision endpoint not found. Please ensure the orchestrator is running on port 9000."
            )
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Orchestrator error: {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to orchestrator: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to orchestrator at {orchestrator_base}. Please ensure the orchestrator is running."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Vision analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {str(e)}")
