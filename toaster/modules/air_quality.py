"""Atlanta air-quality report using the free Open-Meteo API."""

from datetime import datetime

import requests


ATLANTA_LATITUDE = 33.7490
ATLANTA_LONGITUDE = -84.3880
TIMEZONE = "America/New_York"
API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def _aqi_category(aqi: float) -> str:
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"


def _format_measurement(value, unit: str) -> str:
    return f"{value:.1f} {unit}" if isinstance(value, (int, float)) else "unavailable"


def get_atlanta_aqi_report() -> str:
    response = requests.get(
        API_URL,
        params={
            "latitude": ATLANTA_LATITUDE,
            "longitude": ATLANTA_LONGITUDE,
            "current": "us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide,carbon_monoxide",
            "timezone": TIMEZONE,
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    current = data.get("current", {})
    units = data.get("current_units", {})
    aqi = current.get("us_aqi")
    if not isinstance(aqi, (int, float)):
        return "Atlanta AQI is currently unavailable."

    observed_at = current.get("time")
    try:
        observed_label = datetime.fromisoformat(observed_at).strftime("%I:%M %p")
    except (TypeError, ValueError):
        observed_label = "the latest reading"

    return (
        f"Air quality in Atlanta is currently **US AQI {round(aqi)} ({_aqi_category(aqi)})**"
    )