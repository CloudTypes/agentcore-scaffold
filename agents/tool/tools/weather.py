"""Weather API tool for getting weather information."""

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
    
    Args:
        location: City name (e.g., "Denver, Colorado", "London, UK", "Denver")
        
    Returns:
        Tuple of (latitude, longitude) or None if not found
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
                GEOCODING_API_URL,
                params={
                    "q": loc_variant,
                    "limit": 1,
                    "appid": WEATHER_API_KEY
                },
                timeout=10
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
    
    Args:
        location: City name or location (e.g., "New York", "London, UK")
        
    Returns:
        Dictionary containing weather information with the following fields:
        - location: The location name
        - temperature: Temperature in Fahrenheit
        - temperature_unit: "Fahrenheit" (always)
        - description: Weather condition description (e.g., "clear sky", "partly cloudy")
        - humidity: Humidity percentage (0-100)
        - humidity_unit: "percent" (always)
        - wind_speed: Wind speed in miles per hour
        - wind_speed_unit: "miles per hour" (always)
        
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
    """
    if not WEATHER_API_KEY:
        return {
            "error": "Weather API key not configured",
            "location": location
        }
    
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
            "location": location
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
                "exclude": "minutely,hourly,daily,alerts"  # Only get current weather
            },
            timeout=10
        )
        
        # Check for HTTP errors
        if response.status_code == 401:
            return {
                "error": "Invalid API key or subscription issue. Please check your WEATHER_API_KEY and ensure you have an active One Call API 3.0 subscription.",
                "location": location
            }
        elif response.status_code == 404:
            return {
                "error": f"Weather data not found for location '{location}'.",
                "location": location
            }
        elif response.status_code == 429:
            return {
                "error": "API rate limit exceeded. Please try again later.",
                "location": location
            }
        elif not response.ok:
            error_text = response.text[:200] if response.text else "Unknown error"
            return {
                "error": f"API returned error {response.status_code}: {error_text}",
                "location": location
            }
        
        response.raise_for_status()
        data = response.json()
        
        # Step 3: Parse One Call API 3.0 response structure
        current = data.get("current", {})
        
        if not current:
            return {
                "error": "Unexpected API response format: missing current weather data",
                "location": location
            }
        
        weather = current.get("weather", [])
        if not weather:
            return {
                "error": "Unexpected API response format: missing weather description",
                "location": location
            }
        
        return {
            "location": location,
            "temperature": current.get("temp"),
            "temperature_unit": "Fahrenheit",
            "description": weather[0].get("description", ""),
            "humidity": current.get("humidity"),
            "humidity_unit": "percent",
            "wind_speed": current.get("wind_speed", 0),
            "wind_speed_unit": "miles per hour"
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "error": f"Network error: {str(e)}",
            "location": location
        }
    except KeyError as e:
        return {
            "error": f"Unexpected API response format: missing {str(e)}",
            "location": location
        }
    except Exception as e:
        return {
            "error": f"Failed to fetch weather: {str(e)}",
            "location": location
        }
