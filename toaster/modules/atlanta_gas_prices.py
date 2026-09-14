"""Print the latest Atlanta-area gasoline price from the free EIA API.

The EIA publishes this series for the Lower Atlantic (PADD 1C) region,
which includes Georgia, rather than for individual Atlanta stations.
"""

from datetime import date

import requests


API_URL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
API_KEY = "DEMO_KEY"
AREA_CODE = "R1Z"
AREA_LABEL = "Lower Atlantic (includes Georgia)"
PRODUCT_CODE = "EPM0"
SOURCE_URL = "https://www.eia.gov/dnav/pet/pet_pri_gnd_dcus_r1z_w.htm"


def get_atlanta_gas_prices() -> str:
    """Return the latest available Atlanta-area gasoline price report."""
    try:
        response = requests.get(
            API_URL,
            params={
                "api_key": API_KEY,
                "frequency": "weekly",
                "data[0]": "value",
                "facets[duoarea][]": AREA_CODE,
                "facets[product][]": PRODUCT_CODE,
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "length": 1,
            },
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException:
        return "Atlanta-area gas prices are currently unavailable."
    records = response.json().get("response", {}).get("data", [])
    if not records:
        return "Atlanta-area gas prices are currently unavailable."

    record = records[0]
    period = record.get("period", "unknown date")
    value = record.get("value")
    try:
        price = float(value)
    except (TypeError, ValueError):
        return "Atlanta-area gas prices are currently unavailable."

    try:
        period_label = date.fromisoformat(period).strftime("%B %-d, %Y")
    except (TypeError, ValueError):
        period_label = str(period)

    return (
        f"Atlanta-area gasoline: ${price:.3f}/gal\n"
        f"Coverage: {AREA_LABEL}; all grades, weekly average\n"
        f"Updated: {period_label}\n"
        f"Source: {SOURCE_URL}"
    )


if __name__ == "__main__":
    print(get_atlanta_gas_prices())