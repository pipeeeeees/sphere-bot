import datetime

from modules import pollen
from modules import weather

def get_morning_report():
    """Generates the morning report."""
    morning_report_str = ""
    
    # initial message
    morning_report_str += f"Here is your **Atlanta Morning Report** for **{datetime.datetime.now().strftime('%A, %B %d, %Y')}**:"
    
    pollen_count = pollen.get_atl_pollen_count()
    if type(pollen_count) == int:
        morning_report_str += f"\n  🌼 Pollen count: **{pollen_count}**"
    #elif pollen_count == None:
    #    morning_report_str += "\n  🌼 Pollen count is yet reported"
        

    sunset = weather.get_sun_time(0, "sunset")
    sunset_string = f"\n  🌅 Sunset is at **{sunset}**"
    sunrise = weather.get_sun_time(1, "sunrise")
    sunrise_string = f"\n  🌅 Sunrise tomorrow is at **{sunrise}**"
    morning_report_str = morning_report_str + sunset_string
    morning_report_str = morning_report_str + sunrise_string


    return morning_report_str
    