import requests
from datetime import datetime, timedelta
import pytz

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

def get_today_temperatures(gridpoint="FFC/52,88"):
    """
    Fetch today's high and low temperatures for a given NWS gridpoint.
    
    Args:
        gridpoint (str): NWS gridpoint in the format "OFFICE/X,Y" (default: Atlanta, GA).
    
    Returns:
        tuple: (high_temp, low_temp) in Fahrenheit, or (None, None) if not found.
    
    Raises:
        requests.RequestException: If the API request fails.
    """
    # NWS API endpoint
    url = f"https://api.weather.gov/gridpoints/{gridpoint}/forecast"
    headers = {"User-Agent": "Mozilla/5.0"}  # Required by NWS API
    
    # Make the API request
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise error for bad status codes
    except requests.RequestException as e:
        raise requests.RequestException(f"Failed to fetch weather data: {e}")

    # Parse the response
    data = response.json()
    periods = data["properties"]["periods"]

    # Get today's date
    today = datetime.now().date()  # March 10, 2025, as of now
    high_temp = None
    low_temp = None

    # Loop through periods to find today's high and low
    for period in periods:
        period_start = datetime.fromisoformat(period["startTime"]).date()
        if period_start == today:
            temp = period["temperature"]
            if period["isDaytime"]:  # Use the API's daytime flag for accuracy
                high_temp = temp
            else:
                low_temp = temp

    return high_temp, low_temp

def get_hourly_temperatures_ascii_plot(gridpoint="FFC/52,88"):
    """
    Fetch hourly temperatures and return a 9-hour ASCII temperature graph as a formatted string.
    
    Args:
        gridpoint (str): NWS gridpoint in the format "OFFICE/X,Y" (default: Atlanta, GA).
    
    Returns:
        str: ASCII temperature graph as a formatted string.
    """
    url = f"https://api.weather.gov/gridpoints/{gridpoint}/forecast/hourly"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        return f"Error fetching data: {e}"

    data = response.json()
    periods = data["properties"]["periods"]

    tz = pytz.timezone("America/New_York")
    now = datetime.now(tz)  # Directly use timezone-aware datetime
    next_9_hours = []

    # Collect the next 9 hours
    for period in periods:
        period_start = datetime.fromisoformat(period["startTime"])
        temp = period["temperature"]

        if now <= period_start < now + timedelta(hours=9):  # Now limited to 9 hours
            next_9_hours.append((period_start.strftime("%H:%M"), temp))

    if not next_9_hours:
        return "No temperature data available for the next 9 hours."

    temps = [temp for _, temp in next_9_hours]
    times = [time for time, _ in next_9_hours]
    max_temp = max(temps)
    min_temp = min(temps)
    temp_range = max_temp - min_temp + 1 if max_temp != min_temp else 10
    graph_height = 10

    # Scale the graph (max height of 10 lines)
    scaled_temps = [
        int(((temp - min_temp) / temp_range) * (graph_height - 1)) if temp_range > 1 else 5
        for temp in temps
    ]

    # Build the ASCII graph as a string
    ascii_graph = "Atlanta 9-Hour Temperature Forecast:\n"
    for row in range(graph_height - 1, -1, -1):
        line = f"{min_temp + int((row / (graph_height - 1)) * temp_range):3d}°F | "
        for temp in scaled_temps:
            line += " * " if temp == row else "   "
        ascii_graph += line + "\n"

    # Time labels
    time_line = "      | " + " ".join(f"{t[:2]}" for t in times)
    ascii_graph += time_line

    return f"```\n{ascii_graph}\n```"  # Format for Discord code block


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