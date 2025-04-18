import datetime

from modules import pollen
from modules import weather

def get_morning_report():
    """Generates the morning report."""
    morning_report_str = ""
    
    # initial message
    morning_report_str += f"Here is your **Atlanta Morning Report** for **{datetime.datetime.now().strftime('%A, %B %d, %Y')}**:"
    
    # get today's temperatures
    #high_temp, low_temp = weather.get_today_temperatures()
    #if high_temp != None and low_temp != None:
    #    morning_report_str += f"\n  🌡️ Today's temperature range: **{low_temp}°F → {high_temp}°F**"

    pollen_count = pollen.get_atl_pollen_count()
    if type(pollen_count) == int:
        morning_report_str += f"\n  🌼 Pollen count: **{pollen_count}**"
    elif pollen_count == None:
        morning_report_str += "\n  🌼 Pollen count is not yet reported"
    
    # get current weather
    current_weather = weather.get_current_weather()
    if current_weather != None:
    #    morning_report_str += "\n\nHere are the **Current Weather Conditions**:"
    #    morning_report_str += f"\n  🌡️ Temperature: **{current_weather['temperature']}°F**"
    #    morning_report_str += f"\n  💧 Humidity: **{current_weather['humidity']}%**"
    #    morning_report_str += f"\n  💨 Wind speed: **{current_weather['wind_speed']} mph**"
        morning_report_str += f"\n  🌦️ Conditions: **{current_weather['conditions']}**"

    sunset = weather.get_sun_time(0, "sunset")
    sunset_string = f"\n  🌅 Sunset is at **{sunset}**"
    sunrise = weather.get_sun_time(1, "sunrise")
    sunrise_string = f"\n  🌅 Sunrise tomorrow is at **{sunrise}**"
    morning_report_str = morning_report_str + sunset_string
    morning_report_str = morning_report_str + sunrise_string

    ascii_plot = weather.get_hourly_temperatures_ascii_plot()
    if ascii_plot:
        if "Error" not in ascii_plot:
            morning_report_str += f"\n{ascii_plot}"

    return morning_report_str

def get_weather_alerts():
    """Gets the weather alerts for Atlanta."""
    report_str = "## Here are the Current Weather Alerts for Atlanta:" 
    alerts = weather.get_weather_alerts()
    
    if alerts:
        for alert in alerts:
            report_str += f"\n  🚨 {alert['event']}:"
            description = alert["description"]
            
            # Check if description contains bullet points
            if any(bullet in description for bullet in ["* ", " - "]):
                lines = description.split("*")
                cleaned_lines = []
                for line in lines:
                    if line.strip():  # Keep non-empty lines
                        cleaned_lines.append('- ' + line.replace('\n', '').strip())
                description = "\n".join(cleaned_lines)  # Rejoin with newlines
            
            report_str += f"\n{description}\n"
        
        return report_str
    else:
        return None