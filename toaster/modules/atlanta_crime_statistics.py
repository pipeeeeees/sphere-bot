"""Print Atlanta crime statistics for a requested occurrence-date range.

Data comes from the official City of Atlanta Crime Incidents Socrata dataset.
This module is intentionally standalone and is not connected to Toast.
"""

import argparse
from datetime import date
from typing import Optional

import requests


API_URL = "https://sharefulton.fultoncountyga.gov/resource/9w3w-ynjw.json"
SOURCE_URL = "https://sharefulton.fultoncountyga.gov/d/9w3w-ynjw"


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date {value!r}; use YYYY-MM-DD.") from exc


def get_atlanta_crime_statistics(
    start_date: date, end_date: Optional[date] = None
) -> str:
    """Return crime totals and type breakdown for an occurrence-date range."""
    end_date = end_date or date.today()
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")

    start_timestamp = f"{start_date.isoformat()}T00:00:00"
    end_timestamp = f"{end_date.isoformat()}T23:59:59"
    params = {
        "$select": "ucrliteral, count(*) as incidents",
        "$where": f'occurdate between "{start_timestamp}" and "{end_timestamp}"',
        "$group": "ucrliteral",
        "$order": "incidents DESC",
        "$limit": 5000,
    }

    try:
        response = requests.get(API_URL, params=params, timeout=20)
        response.raise_for_status()
        records = response.json()
    except requests.RequestException as exc:
        return f"Atlanta crime statistics are currently unavailable: {exc}"

    if not isinstance(records, list):
        return "Atlanta crime statistics are currently unavailable: invalid API response."

    breakdown = []
    total_incidents = 0
    for record in records:
        try:
            incidents = int(record.get("incidents", 0))
        except (AttributeError, TypeError, ValueError):
            continue
        if incidents <= 0:
            continue
        crime_type = str(record.get("ucrliteral") or "Unknown").strip() or "Unknown"
        breakdown.append((crime_type, incidents))
        total_incidents += incidents

    day_count = (end_date - start_date).days + 1
    lines = [
        "Atlanta Crime Statistics",
        f"Occurrence dates: {start_date.isoformat()} through {end_date.isoformat()}",
        f"Total reported incidents: {total_incidents:,}",
        f"Average incidents per day: {total_incidents / day_count:.2f}",
        "",
        "Top crime types:",
    ]
    if breakdown:
        lines.extend(
            f"  {crime_type}: {incidents:,}"
            for crime_type, incidents in breakdown[:10]
        )
    else:
        lines.append("  No incidents found for this date range.")
    lines.append(f"Source: {SOURCE_URL}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print Atlanta crime statistics from a start date through today."
    )
    parser.add_argument(
        "start_date",
        nargs="?",
        help="Start occurrence date, YYYY-MM-DD; defaults to 2025-01-01",
    )
    parser.add_argument(
        "end_date",
        nargs="?",
        help="Optional ending occurrence date, YYYY-MM-DD; defaults to 2025-12-31",
    )
    args = parser.parse_args()

    end_date = _parse_date(args.end_date) if args.end_date else date(2025, 12, 31)
    start_date = _parse_date(args.start_date) if args.start_date else date(2025, 1, 1)
    print(get_atlanta_crime_statistics(start_date, end_date))


if __name__ == "__main__":
    main()