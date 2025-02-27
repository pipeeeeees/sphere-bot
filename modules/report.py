import datetime

from modules import pollen
from modules import weather

def get_morning_report():
    """Generates the morning report."""
    morning_report_str = ""
    
    # initial message
    morning_report_str += f"Here is you **Atlanta Morning Report** for {datetime.datetime.now().strftime('%A, %B %d, %Y')}:\n"
    
    pollen_count = pollen.get_atl_pollen_count()
    if type(pollen_count) == int:
        morning_report_str += f"🌼 Pollen count: **{pollen_count}**"
        

    sunset = weather.get_sun_time(0, "sunset")
    sunset_string = f"\n🌅 Sunset is at {sunset}**"
    sunrise = weather.get_sun_time(1, "sunrise")
    sunrise_string = f"\n🌅 Sunrise tomorrow is at **{sunrise}**"
    message_string = message_string + sunset_string
    message_string = message_string + sunrise_string
    