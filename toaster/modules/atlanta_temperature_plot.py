"""Generate a seven-day Atlanta high/low temperature plot from Open-Meteo."""

import argparse
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib
import requests

matplotlib.use("Agg")
from matplotlib.colors import to_rgba
import matplotlib.pyplot as plt


ATLANTA_LATITUDE = 33.7490
ATLANTA_LONGITUDE = -84.3880
TIMEZONE = "America/New_York"
API_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_OUTPUT = Path("atlanta_7_day_temperatures.png")


def get_atlanta_forecast() -> dict[str, Any]:
    """Fetch the next seven days of Atlanta high and low temperatures."""
    response = requests.get(
        API_URL,
        params={
            "latitude": ATLANTA_LATITUDE,
            "longitude": ATLANTA_LONGITUDE,
            "daily": "temperature_2m_max,temperature_2m_min",
            "temperature_unit": "fahrenheit",
            "timezone": TIMEZONE,
            "forecast_days": 7,
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    daily = data.get("daily")
    if not isinstance(daily, dict):
        raise ValueError("Open-Meteo response did not include daily forecast data")

    dates = daily.get("time")
    highs = daily.get("temperature_2m_max")
    lows = daily.get("temperature_2m_min")
    if not isinstance(dates, list) or not isinstance(highs, list) or not isinstance(lows, list):
        raise ValueError("Open-Meteo response is missing temperature series")
    if len(dates) != 7 or len(highs) != 7 or len(lows) != 7:
        raise ValueError("Open-Meteo did not return exactly seven forecast days")

    return {"dates": dates, "highs": highs, "lows": lows}


def create_temperature_plot(forecast: dict[str, Any], output_path: Path = DEFAULT_OUTPUT) -> Path:
    """Create and save a high/low temperature plot as a PNG."""
    dates = [date.fromisoformat(value) for value in forecast["dates"]]
    highs = [float(value) for value in forecast["highs"]]
    lows = [float(value) for value in forecast["lows"]]
    labels = [day.strftime("%a\n%b %-d") for day in dates]
    positions = list(range(len(labels)))
    temperature_min = min(lows) - 2
    temperature_max = max(highs) + 2
    gradient_min = 0.0
    gradient_max = 110.0
    temperature_transition = 70.0

    figure, axis = plt.subplots(figsize=(10, 5.5), facecolor="#111827")
    axis.set_facecolor("#1f2937")
    axis.set_ylim(temperature_min, temperature_max)
    maximum_opacity = 0.45
    gradient_rows = []
    for row in range(256):
        temperature = gradient_min + (row / 255) * (gradient_max - gradient_min)
        if temperature < temperature_transition:
            color = "#3b82f6"
            opacity = maximum_opacity * (
                (temperature_transition - temperature) / temperature_transition
            )
        else:
            color = "#ef4444"
            opacity = maximum_opacity * (
                (temperature - temperature_transition)
                / (gradient_max - temperature_transition)
            )
        gradient_rows.append([to_rgba(color, opacity)])
    axis.imshow(
        gradient_rows,
        origin="lower",
        aspect="auto",
        extent=(-0.5, len(labels) - 0.5, gradient_min, gradient_max),
        interpolation="bilinear",
        zorder=0,
    )
    for position, forecast_date in zip(positions, dates):
        if forecast_date.weekday() >= 5:
            axis.axvspan(
                position - 0.5,
                position + 0.5,
                color="#334155",
                alpha=0.45,
                zorder=1,
            )
    axis.plot(
        positions,
        highs,
        color="#ff6b6b",
        marker="o",
        linewidth=2.5,
        label="Daily high",
        zorder=2,
    )
    axis.plot(
        positions,
        lows,
        color="#60a5fa",
        marker="o",
        linewidth=2.5,
        label="Daily low",
        zorder=2,
    )
    axis.set_title("Atlanta 7-Day Temperature Forecast", color="#f8fafc")
    axis.set_xlabel("Day", color="#e5e7eb")
    axis.set_ylabel("Temperature (°F)", color="#e5e7eb")
    axis.set_xticks(positions, labels)
    axis.tick_params(colors="#e5e7eb")
    axis.grid(axis="y", linestyle="--", color="#cbd5e1", alpha=0.25)
    for spine in axis.spines.values():
        spine.set_color("#64748b")
    legend = axis.legend(facecolor="#1f2937", edgecolor="#64748b")
    for text in legend.get_texts():
        text.set_color("#f8fafc")
    figure.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, format="png", dpi=150, facecolor=figure.get_facecolor())
    plt.close(figure)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"PNG output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    forecast = get_atlanta_forecast()
    output_path = create_temperature_plot(forecast, args.output)
    print(f"Saved Atlanta temperature plot to {output_path}")


if __name__ == "__main__":
    main()
