"""
Unit tests for weather tool.
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from tools.weather import geocode_location, weather_api


class TestGeocodeLocation:
    """Test cases for geocode_location function."""

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.requests.get")
    def test_valid_location_with_comma(self, mock_get):
        """Test geocoding a location with comma."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = [{"lat": 39.7392, "lon": -104.9903, "name": "Denver", "state": "Colorado"}]
        mock_get.return_value = mock_response

        result = geocode_location("Denver, Colorado")
        assert result == (39.7392, -104.9903)
        mock_get.assert_called_once()

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.requests.get")
    def test_valid_location_without_comma(self, mock_get):
        """Test geocoding a location without comma (normalization)."""
        # First call fails, second succeeds with normalized format
        mock_response1 = Mock()
        mock_response1.status_code = 200
        mock_response1.ok = True
        mock_response1.json.return_value = []

        mock_response2 = Mock()
        mock_response2.status_code = 200
        mock_response2.ok = True
        mock_response2.json.return_value = [{"lat": 39.7392, "lon": -104.9903}]

        mock_get.side_effect = [mock_response1, mock_response2]

        result = geocode_location("Denver Colorado")
        assert result == (39.7392, -104.9903)
        assert mock_get.call_count == 2

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.requests.get")
    def test_location_not_found(self, mock_get):
        """Test location not found."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        result = geocode_location("Nonexistent City")
        assert result is None

    @patch("tools.weather.WEATHER_API_KEY", "")
    def test_missing_api_key(self):
        """Test missing API key."""
        result = geocode_location("Denver")
        assert result is None

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.requests.get")
    def test_api_error_401(self, mock_get):
        """Test API error 401 (invalid key)."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.ok = False
        mock_get.return_value = mock_response

        result = geocode_location("Denver")
        assert result is None

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.requests.get")
    def test_api_error_500(self, mock_get):
        """Test API error 500."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.ok = False
        mock_get.return_value = mock_response

        result = geocode_location("Denver")
        assert result is None

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.requests.get")
    def test_network_timeout(self, mock_get):
        """Test network timeout."""
        import requests

        mock_get.side_effect = requests.exceptions.Timeout("Connection timeout")

        result = geocode_location("Denver")
        assert result is None

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.requests.get")
    def test_network_error(self, mock_get):
        """Test network error."""
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("Connection error")

        result = geocode_location("Denver")
        assert result is None


class TestWeatherAPI:
    """Test cases for weather_api function."""

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.geocode_location")
    @patch("tools.weather.requests.get")
    def test_successful_weather_retrieval(self, mock_get, mock_geocode):
        """Test successful weather retrieval."""
        # Mock geocoding
        mock_geocode.return_value = (39.7392, -104.9903)

        # Mock weather API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "current": {"temp": 33.35, "humidity": 40, "wind_speed": 4.0, "weather": [{"description": "light rain"}]}
        }
        mock_get.return_value = mock_response

        result = weather_api("Denver, Colorado")

        assert "error" not in result
        assert result["location"] == "Denver, Colorado"
        assert result["temperature"] == 33.35
        assert result["temperature_unit"] == "Fahrenheit"
        assert result["humidity"] == 40
        assert result["humidity_unit"] == "percent"
        assert result["wind_speed"] == 4.0
        assert result["wind_speed_unit"] == "miles per hour"
        assert result["description"] == "light rain"

    @patch("tools.weather.WEATHER_API_KEY", "")
    def test_missing_api_key(self):
        """Test missing API key."""
        result = weather_api("Denver")
        assert "error" in result
        assert "not configured" in result["error"].lower()
        assert result["location"] == "Denver"

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.geocode_location")
    def test_invalid_location(self, mock_geocode):
        """Test invalid location."""
        mock_geocode.return_value = None

        result = weather_api("Invalid City")
        assert "error" in result
        assert "not found" in result["error"].lower()
        assert result["location"] == "Invalid City"

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.geocode_location")
    @patch("tools.weather.requests.get")
    def test_api_error_401(self, mock_get, mock_geocode):
        """Test API error 401 (invalid key/subscription)."""
        mock_geocode.return_value = (39.7392, -104.9903)

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.ok = False
        mock_get.return_value = mock_response

        result = weather_api("Denver")
        assert "error" in result
        assert "401" in result["error"] or "invalid" in result["error"].lower()
        assert result["location"] == "Denver"

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.geocode_location")
    @patch("tools.weather.requests.get")
    def test_api_error_404(self, mock_get, mock_geocode):
        """Test API error 404."""
        mock_geocode.return_value = (39.7392, -104.9903)

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.ok = False
        mock_get.return_value = mock_response

        result = weather_api("Denver")
        assert "error" in result
        assert "404" in result["error"] or "not found" in result["error"].lower()
        assert result["location"] == "Denver"

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.geocode_location")
    @patch("tools.weather.requests.get")
    def test_api_error_429(self, mock_get, mock_geocode):
        """Test API error 429 (rate limit)."""
        mock_geocode.return_value = (39.7392, -104.9903)

        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.ok = False
        mock_get.return_value = mock_response

        result = weather_api("Denver")
        assert "error" in result
        assert "429" in result["error"] or "rate limit" in result["error"].lower()
        assert result["location"] == "Denver"

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.geocode_location")
    @patch("tools.weather.requests.get")
    def test_network_error(self, mock_get, mock_geocode):
        """Test network error."""
        mock_geocode.return_value = (39.7392, -104.9903)

        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("Connection error")

        result = weather_api("Denver")
        assert "error" in result
        assert "network" in result["error"].lower() or "connection" in result["error"].lower()
        assert result["location"] == "Denver"

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.geocode_location")
    @patch("tools.weather.requests.get")
    def test_malformed_api_response_missing_current(self, mock_get, mock_geocode):
        """Test malformed API response missing current data."""
        mock_geocode.return_value = (39.7392, -104.9903)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {}  # Missing "current"
        mock_get.return_value = mock_response

        result = weather_api("Denver")
        assert "error" in result
        assert "unexpected" in result["error"].lower() or "missing" in result["error"].lower()
        assert result["location"] == "Denver"

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.geocode_location")
    @patch("tools.weather.requests.get")
    def test_malformed_api_response_missing_weather(self, mock_get, mock_geocode):
        """Test malformed API response missing weather description."""
        mock_geocode.return_value = (39.7392, -104.9903)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "current": {
                "temp": 33.35,
                "humidity": 40,
                "wind_speed": 4.0,
                # Missing "weather" array
            }
        }
        mock_get.return_value = mock_response

        result = weather_api("Denver")
        assert "error" in result
        assert "unexpected" in result["error"].lower() or "missing" in result["error"].lower()
        assert result["location"] == "Denver"

    @patch("tools.weather.WEATHER_API_KEY", "test_key")
    @patch("tools.weather.geocode_location")
    @patch("tools.weather.requests.get")
    def test_location_normalization_suggestion(self, mock_get, mock_geocode):
        """Test that location normalization suggestions are provided."""
        mock_geocode.return_value = None

        result = weather_api("Denver Colorado")
        assert "error" in result
        assert "suggestion" in result["error"].lower() or "try" in result["error"].lower()
