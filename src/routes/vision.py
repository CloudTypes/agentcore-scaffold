"""Vision API routes for image and video analysis."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal
import boto3
from datetime import datetime
import os
import uuid
import base64
import logging

logger = logging.getLogger(__name__)

# Disable httpx request/response body logging to avoid logging base64 encoded media
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)  # Only log warnings and errors, not request/response bodies

router = APIRouter(prefix="/vision", tags=["vision"])

S3_BUCKET = os.getenv("S3_VISION_BUCKET", "agentcore-vision-uploads")
S3_UPLOAD_PREFIX = os.getenv("S3_UPLOAD_PREFIX", "uploads/")
PRESIGNED_URL_EXPIRY = int(os.getenv("VISION_PRESIGNED_URL_EXPIRY", "3600"))

# Initialize S3 client lazily to avoid errors if boto3 isn't configured at import time
_s3_client = None

def get_s3_client():
    """Get or create S3 client."""
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
    """Convert MIME type to Bedrock format string."""
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


class PresignedUrlRequest(BaseModel):
    fileName: str
    fileType: str


class PresignedUrlResponse(BaseModel):
    uploadUrl: str
    s3Uri: str
    key: str


class VisionAnalysisRequest(BaseModel):
    prompt: str
    mediaType: Literal["image", "video"]
    base64Data: Optional[str] = None
    mimeType: Optional[str] = None
    s3Uri: Optional[str] = None


class VisionAnalysisResponse(BaseModel):
    text: str
    usage: Optional[dict] = None


@router.post("/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_url(request: PresignedUrlRequest):
    """Generate S3 presigned URL for file upload."""
    try:
        # Validate file type
        accepted_types = [
            "image/jpeg", "image/png", "image/gif", "image/webp",
            "video/mp4", "video/quicktime", "video/x-matroska", "video/webm",
            "video/x-flv", "video/mpeg", "video/x-ms-wmv", "video/3gpp"
        ]
        if request.fileType not in accepted_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {request.fileType}. Supported types: {', '.join(accepted_types)}"
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
async def analyze_vision(request: VisionAnalysisRequest):
    """Analyze image or video via vision agent."""
    try:
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
        
        # Validate S3 URI format if provided
        if request.s3Uri and not request.s3Uri.startswith("s3://"):
            raise HTTPException(status_code=400, detail="S3 URI must start with 's3://'")
        
        # Build media content block for A2A protocol
        format_str = None
        if request.base64Data:
            # Keep base64 string - will be decoded to bytes in vision agent
            format_str = get_format_string(request.mimeType or "image/jpeg")
            
            if request.mediaType == "image":
                media_content = {
                    "type": "image",
                    "image": {
                        "format": format_str,
                        "source": {
                            "base64": request.base64Data  # Pass base64 string, will decode in agent
                        }
                    }
                }
            else:  # video
                media_content = {
                    "type": "video",
                    "video": {
                        "format": format_str,
                        "source": {
                            "base64": request.base64Data  # Pass base64 string, will decode in agent
                        }
                    }
                }
        else:  # s3Uri
            # Extract format from file extension or use default
            format_str = request.s3Uri.split('.')[-1].lower()
            if format_str == "3gp":
                format_str = "three_gp"
            
            if request.mediaType == "image":
                media_content = {
                    "type": "image",
                    "image": {
                        "format": format_str,
                        "source": {
                            "s3Location": {
                                "uri": request.s3Uri
                            }
                        }
                    }
                }
            else:  # video
                media_content = {
                    "type": "video",
                    "video": {
                        "format": format_str,
                        "source": {
                            "s3Location": {
                                "uri": request.s3Uri
                            }
                        }
                    }
                }
        
        # Forward request to orchestrator (port 9000) which will route to vision agent
        orchestrator_base = os.getenv("ORCHESTRATOR_BASE", "http://localhost:9000")
        
        try:
            import httpx
            
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
                
                if response.status_code == 404:
                    raise HTTPException(
                        status_code=503,
                        detail="Orchestrator vision endpoint not found. Please ensure the orchestrator is running on port 9000."
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
        except Exception as e:
            logger.error(f"Vision analysis error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Vision analysis failed: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Vision analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {str(e)}")
