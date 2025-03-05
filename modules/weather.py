import requests
from datetime import datetime, timedelta

def is_dst(date):
    """Determines if a given date is during Daylight Saving Time (DST) in the US."""
    # Second Sunday in March
    dst_start = datetime(date.year, 3, 8)
    while dst_start.weekday() != 6:  # Find the next Sunday
        dst_start += timedelta(days=1)
    
    # First Sunday in November
    dst_end = datetime(date.year, 11, 1)
    while dst_end.weekday() != 6:  # Find the next Sunday
        dst_end += timedelta(days=1)
    
    # Return True if the date is within the DST period
    return dst_start <= date < dst_end

def get_sun_time(delta_days=0, event="sunset"):
    """
    Fetches and returns the local sunrise or sunset time for Atlanta, handling DST.
    
    Args:
        delta_days (int): Number of days from today to calculate the event time. 
                          0 for today, 1 for tomorrow, -1 for yesterday, etc.
        event (str): The event to fetch, either 'sunrise' or 'sunset'. Defaults to 'sunset'.
                          
    Returns:
        str: Event time in HH:MM AM/PM format with leading zeros stripped.
    """
    # Calculate the target date
    target_date = datetime.now() + timedelta(days=delta_days)
    
    # API endpoint for sunrise/sunset data
    url = "https://api.sunrise-sunset.org/json"
    
    # Parameters for Atlanta (latitude and longitude)
    params = {
        "lat": 33.7490,  # Atlanta latitude
        "lng": -84.3880,  # Atlanta longitude
        "date": target_date.strftime("%Y-%m-%d"),  # Pass the target date in YYYY-MM-DD format
        "formatted": 0   # Return times in UTC (24-hour format for easier conversion)
    }
    
    # Make the API request
    response = requests.get(url, params=params)
    data = response.json()
    
    # Check API response status
    if data["status"] != "OK":
        raise Exception("Failed to fetch event time. API status: " + data["status"])
    
    # Extract the specified event time (sunrise or sunset) in UTC
    event_utc = data["results"].get(event)
    if event_utc is None:
        raise Exception(f"Invalid event: {event}. Please use 'sunrise' or 'sunset'.")
    
    event_utc_datetime = datetime.strptime(event_utc, "%Y-%m-%dT%H:%M:%S+00:00")
    
    # Determine the current offset based on DST
    if is_dst(target_date):
        offset = timedelta(hours=4)  # EDT (UTC-4)
    else:
        offset = timedelta(hours=5)  # EST (UTC-5)
    
    # Convert UTC to local time
    event_local_datetime = event_utc_datetime - offset
    
    # Return the local event time as a string in HH:MM AM/PM format
    return event_local_datetime.strftime("%I:%M %p").lstrip("0")

def get_today_temperatures():
    # NWS API endpoint for Atlanta, GA (gridpoint: FFC/52,88)
    url = "https://api.weather.gov/gridpoints/FFC/52,88/forecast"

    headers = {"User-Agent": "Mozilla/5.0"}  # Required by NWS API
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # Raise error if request fails

    data = response.json()
    periods = data["properties"]["periods"]

    high_temp = None
    low_temp = None

    for period in periods:
        if "day" in period["name"].lower():  # Look for daytime period (high temp)
            high_temp = period["temperature"]
        elif "night" in period["name"].lower():  # Look for nighttime period (low temp)
            low_temp = period["temperature"]

    return high_temp, low_temp

def get_current_weather():
    url = "https://api.weather.gov/stations/KATL/observations/latest"  # KATL = Atlanta Airport station
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()["properties"]

    weather = {
        "temperature": round(data["temperature"]["value"] * 9/5 + 32, 2) if data["temperature"]["value"] is not None else None,  # Convert C to F
        "humidity": round(data["relativeHumidity"]["value"], 2),
        "wind_speed": round((data["windSpeed"]["value"] * 0.621371) if data["windSpeed"]["value"] is not None else 0, 2),  # Convert km/h to mph, default to 0
        "conditions": data["textDescription"]
    }
    
    return weather

def get_hourly_forecast():
    url = "https://api.weather.gov/gridpoints/FFC/52,88/forecast/hourly"
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()["properties"]["periods"]

    forecast = []
    for period in data[:12]:  # Next 12 hours
        forecast.append({
            "time": period["startTime"][:16],  # Keep only YYYY-MM-DDTHH:MM
            "temp": period["temperature"],
            "conditions": period["shortForecast"]
        })

    return forecast

def get_weekly_forecast():
    url = "https://api.weather.gov/gridpoints/FFC/52,88/forecast"
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()["properties"]["periods"]

    forecast = []
    for period in data:
        forecast.append({
            "day": period["name"],
            "temp": period["temperature"],
            "conditions": period["shortForecast"]
        })

    return forecast


def get_weather_alerts():
    url = "https://api.weather.gov/alerts/active?zone=GAZ021"  # Atlanta Zone
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()["features"]

    alerts = []
    for alert in data:
        alerts.append({
            "event": alert["properties"]["event"],
            "description": alert["properties"]["description"]
        })

    return alerts



if __name__ == "__main__":
    # Example usage
    print("EXAMPLE 1:")
    high_temp, low_temp = get_today_temperatures()
    if high_temp is not None and low_temp is not None:
        print(f"Today's high temperature in Atlanta: {high_temp}°F")
        print(f"Tonight's low temperature in Atlanta: {low_temp}°F")
    else:
        print("Temperature data unavailable.")


    # Example usage
    print("\n\n\nEXAMPLE 2:")
    current_weather = get_current_weather()
    print(f"Current Temp: {current_weather['temperature']:.1f}°F")
    print(f"Humidity: {current_weather['humidity']}%")
    print(f"Wind Speed: {current_weather['wind_speed']:.1f} mph")
    print(f"Conditions: {current_weather['conditions']}")




    # Example usage
    print("\n\n\nEXAMPLE 3:")
    hourly_forecast = get_hourly_forecast()
    for hour in hourly_forecast:
        print(f"{hour['time']}: {hour['temp']}°F - {hour['conditions']}")


    # Example usage
    print("\n\n\nEXAMPLE 4:")
    weekly_forecast = get_weekly_forecast()
    for day in weekly_forecast:
        print(f"{day['day']}: {day['temp']}°F - {day['conditions']}")


    # Example usage
    print("\n\n\nEXAMPLE 5:")
    alerts = get_weather_alerts()
    if alerts:
        for alert in alerts:
            print(f"ALERT: {alert['event']}\n{alert['description']}\n")
    else:
        print("No active weather alerts.")