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