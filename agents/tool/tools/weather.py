"""
Weather API tool for getting weather information.

This module provides a weather tool that retrieves current weather information
for locations using the OpenWeatherMap API. It requires:
- A valid OpenWeatherMap API key (set via WEATHER_API_KEY environment variable)
- An active One Call API 3.0 subscription

The tool uses a two-step process:
1. Geocoding: Converts location names to coordinates using the Geocoding API
2. Weather retrieval: Gets current weather data using the One Call API 3.0

The tool handles various location formats and provides helpful error messages
when locations cannot be found or API calls fail.
"""

import os
import requests
from dotenv import load_dotenv
from strands.tools import tool

# Load environment variables from .env file
load_dotenv()

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
GEOCODING_API_URL = "https://api.openweathermap.org/geo/1.0/direct"
ONE_CALL_API_URL = "https://api.openweathermap.org/data/3.0/onecall"


def geocode_location(location: str) -> tuple[float, float] | None:
    """
    Convert city name to latitude/longitude coordinates using Geocoding API.

    This function attempts to geocode a location name by trying multiple
    format variants. This is particularly useful for voice input where
    users might say "Denver Colorado" instead of "Denver, Colorado". The
    function will try:
    1. The original location string
    2. If no comma is present and there are spaces, try adding a comma
       between the first word and the rest (e.g., "Denver Colorado" -> "Denver, Colorado")

    Args:
        location: City name in various formats:
            - "Denver, Colorado" (preferred format)
            - "London, UK"
            - "Denver" (city only)
            - "Denver Colorado" (will be normalized to "Denver, Colorado")

    Returns:
        Tuple of (latitude, longitude) if the location is found, or None if:
        - The location cannot be found
        - The API key is invalid or missing
        - A network error occurs

    Note:
        This function will stop trying variants if it receives a 401 (unauthorized)
        response, indicating an API key issue rather than a location format problem.
    """
    if not WEATHER_API_KEY:
        return None

    # Try to normalize location format (add comma if it looks like "City State" format)
    # This helps with voice input that might say "Denver Colorado" instead of "Denver, Colorado"
    location_variants = [location]
    if "," not in location and " " in location:
        # Split by space and try adding comma between last two parts
        parts = location.split()
        if len(parts) >= 2:
            # Try "City, State" format
            location_variants.append(f"{parts[0]}, {' '.join(parts[1:])}")

    # Try each variant until one works
    for loc_variant in location_variants:
        try:
            response = requests.get(
                GEOCODING_API_URL, params={"q": loc_variant, "limit": 1, "appid": WEATHER_API_KEY}, timeout=10
            )

            if response.status_code == 401:
                # API key issue - don't try other variants
                return None
            elif not response.ok:
                # Try next variant
                continue

            response.raise_for_status()
            data = response.json()

            if data and len(data) > 0:
                # Return first result's coordinates
                first_result = data[0]
                return (first_result["lat"], first_result["lon"])

        except (requests.exceptions.RequestException, KeyError, IndexError):
            # Try next variant
            continue

    # None of the variants worked
    return None


@tool
def weather_api(location: str) -> dict:
    """
    Get current weather information for a location.

    Retrieves current weather data for the specified location using the
    OpenWeatherMap One Call API 3.0. The function first geocodes the location
    name to coordinates, then retrieves weather data for those coordinates.

    Args:
        location: City name or location in various formats:
            - "New York" or "New York, NY"
            - "London, UK"
            - "Denver, Colorado"
            The function will attempt to normalize the format if needed.

    Returns:
        Dictionary containing weather information with the following fields:
        - location: The location name as provided
        - temperature: Temperature in Fahrenheit (float)
        - temperature_unit: "Fahrenheit" (always)
        - description: Weather condition description (e.g., "clear sky", "partly cloudy")
        - humidity: Humidity percentage (0-100, integer)
        - humidity_unit: "percent" (always)
        - wind_speed: Wind speed in miles per hour (float)
        - wind_speed_unit: "miles per hour" (always)

        If an error occurs, returns a dictionary with:
        - error: Error message describing what went wrong
        - location: The location name that was requested

    Raises:
        No exceptions are raised; errors are returned in the response dictionary.
        Common error scenarios:
        - API key not configured
        - Location not found
        - Invalid API key or subscription issue
        - API rate limit exceeded
        - Network errors

    Example:
        >>> weather_api("Seattle")
        {
            "location": "Seattle",
            "temperature": 45.5,
            "temperature_unit": "Fahrenheit",
            "description": "partly cloudy",
            "humidity": 65,
            "humidity_unit": "percent",
            "wind_speed": 5.2,
            "wind_speed_unit": "miles per hour"
        }

        >>> weather_api("InvalidCityName")
        {
            "error": "Location 'InvalidCityName' not found. Please try a different location name or format (e.g., 'City, State' or 'City, Country').",
            "location": "InvalidCityName"
        }
    """
    if not WEATHER_API_KEY:
        return {"error": "Weather API key not configured", "location": location}

    # Step 1: Geocode location to get coordinates
    coordinates = geocode_location(location)
    if coordinates is None:
        # Try to provide helpful suggestions
        suggestion = ""
        if "," not in location and " " in location:
            parts = location.split()
            city = parts[0]
            state = " ".join(parts[1:])
            suggestion = f" Try '{city}, {state}' or just '{city}'."
        return {
            "error": f"Location '{location}' not found.{suggestion} Please try a different location name or format (e.g., 'City, State' or 'City, Country').",
            "location": location,
        }

    lat, lon = coordinates

    # Step 2: Call One Call API 3.0 with coordinates
    try:
        response = requests.get(
            ONE_CALL_API_URL,
            params={
                "lat": lat,
                "lon": lon,
                "appid": WEATHER_API_KEY,
                "units": "imperial",
                "exclude": "minutely,hourly,daily,alerts",  # Only get current weather
            },
            timeout=10,
        )

        # Check for HTTP errors
        if response.status_code == 401:
            return {
                "error": "Invalid API key or subscription issue. Please check your WEATHER_API_KEY and ensure you have an active One Call API 3.0 subscription.",
                "location": location,
            }
        elif response.status_code == 404:
            return {"error": f"Weather data not found for location '{location}'.", "location": location}
        elif response.status_code == 429:
            return {"error": "API rate limit exceeded. Please try again later.", "location": location}
        elif not response.ok:
            error_text = response.text[:200] if response.text else "Unknown error"
            return {"error": f"API returned error {response.status_code}: {error_text}", "location": location}

        response.raise_for_status()
        data = response.json()

        # Step 3: Parse One Call API 3.0 response structure
        current = data.get("current", {})

        if not current:
            return {"error": "Unexpected API response format: missing current weather data", "location": location}

        weather = current.get("weather", [])
        if not weather:
            return {"error": "Unexpected API response format: missing weather description", "location": location}

        return {
            "location": location,
            "temperature": current.get("temp"),
            "temperature_unit": "Fahrenheit",
            "description": weather[0].get("description", ""),
            "humidity": current.get("humidity"),
            "humidity_unit": "percent",
            "wind_speed": current.get("wind_speed", 0),
            "wind_speed_unit": "miles per hour",
        }

    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {str(e)}", "location": location}
    except KeyError as e:
        return {"error": f"Unexpected API response format: missing {str(e)}", "location": location}
    except Exception as e:
        return {"error": f"Failed to fetch weather: {str(e)}", "location": location}
