"""Unit tests for vision API routes."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import os
import sys
import base64
import json
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from routes.vision import (
    router,
    get_s3_client,
    get_format_string,
    _extract_format_from_s3_uri,
    _build_media_content,
    PresignedUrlRequest,
    PresignedUrlResponse,
    VisionAnalysisRequest,
    VisionAnalysisResponse,
)


# Create test app
app = FastAPI()
app.include_router(router)


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_s3_client():
    """Mock S3 client."""
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/bucket/key?signature=xyz"
    return mock_client


@pytest.fixture
def sample_base64_image():
    """Sample base64-encoded image data."""
    # Small 1x1 PNG image in base64
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


@pytest.fixture
def sample_base64_video():
    """Sample base64-encoded video data (minimal)."""
    # Minimal valid base64 string
    return base64.b64encode(b"fake video data").decode("utf-8")


class TestPresignedUrlEndpoint:
    """Tests for /vision/presigned-url endpoint."""

    @patch("routes.vision.get_s3_client")
    def test_presigned_url_success(self, mock_get_s3, client, mock_s3_client):
        """Test successful presigned URL generation."""
        mock_get_s3.return_value = mock_s3_client

        response = client.post("/vision/presigned-url", json={"fileName": "test.jpg", "fileType": "image/jpeg"})

        assert response.status_code == 200
        data = response.json()
        assert "uploadUrl" in data
        assert "s3Uri" in data
        assert "key" in data
        assert data["s3Uri"].startswith("s3://")
        mock_s3_client.generate_presigned_url.assert_called_once()

    def test_presigned_url_invalid_file_type(self, client):
        """Test presigned URL with invalid file type."""
        response = client.post("/vision/presigned-url", json={"fileName": "test.txt", "fileType": "text/plain"})

        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    @patch("routes.vision.boto3.client")
    def test_presigned_url_s3_client_failure(self, mock_boto3, client):
        """Test presigned URL when S3 client creation fails."""
        mock_boto3.side_effect = Exception("S3 client error")

        response = client.post("/vision/presigned-url", json={"fileName": "test.jpg", "fileType": "image/jpeg"})

        assert response.status_code == 503
        assert "S3 client not available" in response.json()["detail"]

    @patch("routes.vision.get_s3_client")
    def test_presigned_url_generation_failure(self, mock_get_s3, client, mock_s3_client):
        """Test presigned URL when generation fails."""
        mock_get_s3.return_value = mock_s3_client
        mock_s3_client.generate_presigned_url.side_effect = Exception("Generation failed")

        response = client.post("/vision/presigned-url", json={"fileName": "test.jpg", "fileType": "image/jpeg"})

        assert response.status_code == 500
        assert "Failed to generate presigned URL" in response.json()["detail"]

    @patch("routes.vision.get_s3_client")
    def test_presigned_url_file_without_extension(self, mock_get_s3, client, mock_s3_client):
        """Test presigned URL with file name without extension."""
        mock_get_s3.return_value = mock_s3_client

        response = client.post("/vision/presigned-url", json={"fileName": "testfile", "fileType": "image/png"})

        assert response.status_code == 200
        data = response.json()
        assert "key" in data
        # Should use 'bin' as default extension
        assert data["key"].endswith(".bin") or "testfile" in data["key"]

    @patch("routes.vision.get_s3_client")
    def test_presigned_url_video_file(self, mock_get_s3, client, mock_s3_client):
        """Test presigned URL for video file."""
        mock_get_s3.return_value = mock_s3_client

        response = client.post("/vision/presigned-url", json={"fileName": "video.mp4", "fileType": "video/mp4"})

        assert response.status_code == 200
        data = response.json()
        assert "uploadUrl" in data
        # Verify ContentType was set correctly
        call_args = mock_s3_client.generate_presigned_url.call_args
        assert call_args[1]["Params"]["ContentType"] == "video/mp4"


class TestVisionAnalysisEndpoint:
    """Tests for /vision/analyze endpoint."""

    @patch("routes.vision.httpx.AsyncClient")
    @patch("routes.vision.get_s3_client")
    def test_analyze_base64_image_success(self, mock_get_s3, mock_httpx_client, client, sample_base64_image):
        """Test successful vision analysis with base64 image."""
        # Mock httpx response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "This is an image of a test pattern", "usage": {"tokens": 100}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_client.return_value = mock_client_instance

        response = client.post(
            "/vision/analyze",
            json={
                "prompt": "What is in this image?",
                "mediaType": "image",
                "base64Data": sample_base64_image,
                "mimeType": "image/png",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert data["text"] == "This is an image of a test pattern"
        assert "usage" in data

    @patch("routes.vision.httpx.AsyncClient")
    @patch("routes.vision.get_s3_client")
    def test_analyze_s3_uri_success(self, mock_get_s3, mock_httpx_client, client):
        """Test successful vision analysis with S3 URI."""
        # Mock httpx response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "This is a video analysis", "usage": {"tokens": 200}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_client.return_value = mock_client_instance

        response = client.post(
            "/vision/analyze",
            json={"prompt": "What is in this video?", "mediaType": "video", "s3Uri": "s3://bucket/path/video.mp4"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "text" in data

    def test_analyze_missing_prompt(self, client):
        """Test vision analysis with missing prompt."""
        response = client.post("/vision/analyze", json={"mediaType": "image", "base64Data": "dGVzdA=="})

        # FastAPI returns 422 for missing required fields (validation error)
        assert response.status_code == 422

    def test_analyze_empty_prompt(self, client):
        """Test vision analysis with empty prompt."""
        response = client.post("/vision/analyze", json={"prompt": "   ", "mediaType": "image", "base64Data": "dGVzdA=="})

        assert response.status_code == 400
        assert "Prompt is required" in response.json()["detail"]

    def test_analyze_missing_media_data(self, client):
        """Test vision analysis with missing both base64Data and s3Uri."""
        response = client.post("/vision/analyze", json={"prompt": "What is this?", "mediaType": "image"})

        assert response.status_code == 400
        assert "Either base64Data or s3Uri must be provided" in response.json()["detail"]

    def test_analyze_invalid_base64(self, client):
        """Test vision analysis with invalid base64 data."""
        response = client.post(
            "/vision/analyze",
            json={
                "prompt": "What is this?",
                "mediaType": "image",
                "base64Data": "invalid base64!!!",
                "mimeType": "image/jpeg",
            },
        )

        assert response.status_code == 400
        assert "Invalid base64 data" in response.json()["detail"]

    def test_analyze_missing_mimetype(self, client, sample_base64_image):
        """Test vision analysis with base64Data but missing mimeType."""
        response = client.post(
            "/vision/analyze", json={"prompt": "What is this?", "mediaType": "image", "base64Data": sample_base64_image}
        )

        assert response.status_code == 400
        assert "mimeType is required when base64Data is provided" in response.json()["detail"]

    def test_analyze_mimetype_mismatch(self, client, sample_base64_image):
        """Test vision analysis with mimeType that doesn't match mediaType."""
        response = client.post(
            "/vision/analyze",
            json={"prompt": "What is this?", "mediaType": "image", "base64Data": sample_base64_image, "mimeType": "video/mp4"},
        )

        assert response.status_code == 400
        assert "mimeType" in response.json()["detail"]
        assert "does not match mediaType" in response.json()["detail"]

    def test_analyze_unsupported_mimetype(self, client, sample_base64_image):
        """Test vision analysis with unsupported mimeType."""
        response = client.post(
            "/vision/analyze",
            json={"prompt": "What is this?", "mediaType": "image", "base64Data": sample_base64_image, "mimeType": "image/bmp"},
        )

        assert response.status_code == 400
        assert "Unsupported mimeType" in response.json()["detail"]

    def test_analyze_invalid_s3_uri(self, client):
        """Test vision analysis with invalid S3 URI format."""
        response = client.post(
            "/vision/analyze",
            json={"prompt": "What is this?", "mediaType": "image", "s3Uri": "https://s3.amazonaws.com/bucket/key"},
        )

        assert response.status_code == 400
        assert "S3 URI must start with 's3://'" in response.json()["detail"]

    @patch("routes.vision.httpx.AsyncClient")
    def test_analyze_orchestrator_connection_failure(self, mock_httpx_client, client, sample_base64_image):
        """Test vision analysis when orchestrator connection fails."""
        from httpx import RequestError

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(side_effect=RequestError("Connection failed"))
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_client.return_value = mock_client_instance

        response = client.post(
            "/vision/analyze",
            json={"prompt": "What is this?", "mediaType": "image", "base64Data": sample_base64_image, "mimeType": "image/png"},
        )

        assert response.status_code == 503
        assert "Failed to connect to orchestrator" in response.json()["detail"]

    @patch("routes.vision.httpx.AsyncClient")
    def test_analyze_orchestrator_404(self, mock_httpx_client, client, sample_base64_image):
        """Test vision analysis when orchestrator returns 404."""
        from httpx import HTTPStatusError

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(
            side_effect=HTTPStatusError("Not found", request=MagicMock(), response=mock_response)
        )
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_client.return_value = mock_client_instance

        response = client.post(
            "/vision/analyze",
            json={"prompt": "What is this?", "mediaType": "image", "base64Data": sample_base64_image, "mimeType": "image/png"},
        )

        assert response.status_code == 503
        assert "Orchestrator vision endpoint not found" in response.json()["detail"]

    @patch("routes.vision.httpx.AsyncClient")
    def test_analyze_orchestrator_500(self, mock_httpx_client, client, sample_base64_image):
        """Test vision analysis when orchestrator returns 500."""
        from httpx import HTTPStatusError

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(
            side_effect=HTTPStatusError("Server error", request=MagicMock(), response=mock_response)
        )
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_client.return_value = mock_client_instance

        response = client.post(
            "/vision/analyze",
            json={"prompt": "What is this?", "mediaType": "image", "base64Data": sample_base64_image, "mimeType": "image/png"},
        )

        assert response.status_code == 500
        assert "Orchestrator error" in response.json()["detail"]


class TestVisionHelperFunctions:
    """Tests for vision helper functions."""

    def test_get_format_string_jpeg(self):
        """Test get_format_string for JPEG."""
        assert get_format_string("image/jpeg") == "jpeg"

    def test_get_format_string_png(self):
        """Test get_format_string for PNG."""
        assert get_format_string("image/png") == "png"

    def test_get_format_string_mp4(self):
        """Test get_format_string for MP4."""
        assert get_format_string("video/mp4") == "mp4"

    def test_get_format_string_quicktime(self):
        """Test get_format_string for QuickTime (special case)."""
        assert get_format_string("video/quicktime") == "mov"

    def test_get_format_string_3gpp(self):
        """Test get_format_string for 3GPP (special case)."""
        assert get_format_string("video/3gpp") == "three_gp"

    def test_get_format_string_unknown(self):
        """Test get_format_string for unknown MIME type (fallback)."""
        assert get_format_string("image/unknown") == "unknown"

    def test_extract_format_from_s3_uri_mp4(self):
        """Test _extract_format_from_s3_uri for MP4."""
        assert _extract_format_from_s3_uri("s3://bucket/path/video.mp4") == "mp4"

    def test_extract_format_from_s3_uri_jpeg(self):
        """Test _extract_format_from_s3_uri for JPEG."""
        assert _extract_format_from_s3_uri("s3://bucket/path/image.jpg") == "jpg"

    def test_extract_format_from_s3_uri_3gp(self):
        """Test _extract_format_from_s3_uri for 3GP (special case)."""
        assert _extract_format_from_s3_uri("s3://bucket/path/video.3gp") == "three_gp"

    def test_extract_format_from_s3_uri_no_extension(self):
        """Test _extract_format_from_s3_uri with no extension (fallback)."""
        assert _extract_format_from_s3_uri("s3://bucket/path/file") == "jpeg"

    def test_build_media_content_base64_image(self):
        """Test _build_media_content with base64 image."""
        result = _build_media_content(media_type="image", format_str="jpeg", base64_data="dGVzdA==", s3_uri=None)

        assert result["type"] == "image"
        assert "image" in result
        assert result["image"]["format"] == "jpeg"
        assert "base64" in result["image"]["source"]
        assert result["image"]["source"]["base64"] == "dGVzdA=="

    def test_build_media_content_base64_video(self):
        """Test _build_media_content with base64 video."""
        result = _build_media_content(media_type="video", format_str="mp4", base64_data="dGVzdA==", s3_uri=None)

        assert result["type"] == "video"
        assert "video" in result
        assert result["video"]["format"] == "mp4"
        assert "base64" in result["video"]["source"]

    def test_build_media_content_s3_uri_image(self):
        """Test _build_media_content with S3 URI image."""
        result = _build_media_content(
            media_type="image", format_str="png", base64_data=None, s3_uri="s3://bucket/path/image.png"
        )

        assert result["type"] == "image"
        assert "s3Location" in result["image"]["source"]
        assert result["image"]["source"]["s3Location"]["uri"] == "s3://bucket/path/image.png"

    def test_build_media_content_s3_uri_video(self):
        """Test _build_media_content with S3 URI video."""
        result = _build_media_content(
            media_type="video", format_str="mp4", base64_data=None, s3_uri="s3://bucket/path/video.mp4"
        )

        assert result["type"] == "video"
        assert "s3Location" in result["video"]["source"]
        assert result["video"]["source"]["s3Location"]["uri"] == "s3://bucket/path/video.mp4"

    def test_build_media_content_missing_both(self):
        """Test _build_media_content with neither base64 nor S3 URI."""
        with pytest.raises(ValueError, match="Either base64_data or s3_uri must be provided"):
            _build_media_content(media_type="image", format_str="jpeg", base64_data=None, s3_uri=None)

    @patch("routes.vision.boto3.client")
    def test_get_s3_client_lazy_initialization(self, mock_boto3):
        """Test that S3 client is created lazily."""
        # Reset global state
        import routes.vision

        routes.vision._s3_client = None

        mock_client = MagicMock()
        mock_boto3.return_value = mock_client

        client1 = get_s3_client()
        client2 = get_s3_client()

        # Should be the same instance (singleton)
        assert client1 is client2
        # Should only create client once
        assert mock_boto3.call_count == 1

    @patch("routes.vision.boto3.client")
    def test_get_s3_client_error_handling(self, mock_boto3):
        """Test S3 client error handling."""
        # Reset global state
        import routes.vision

        routes.vision._s3_client = None

        mock_boto3.side_effect = Exception("S3 client creation failed")

        with pytest.raises(Exception) as exc_info:
            get_s3_client()

        # Should raise HTTPException with 503 status
        from fastapi import HTTPException

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 503
