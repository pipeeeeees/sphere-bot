"""Generate a five-year U.S. inflation-rate plot from public FRED data.

The plotted values are year-over-year percentage changes in the CPI, core CPI,
PCE, and core PCE price indexes.
"""

import argparse
import csv
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib
import requests

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt


FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SERIES = {
    "CPIAUCSL": "CPI",
    "CPILFESL": "Core CPI",
    "PCEPI": "PCE",
    "PCEPILFE": "Core PCE",
}
DEFAULT_OUTPUT = Path("inflation_rates.png")
LOOKBACK_MONTHS = 120


def _months_before(day: date, months: int) -> date:
    month_index = day.year * 12 + day.month - 1 - months
    year, month_zero_indexed = divmod(month_index, 12)
    month = month_zero_indexed + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def _fetch_index_series(
    series_id: str, start_date: date, end_date: date
) -> List[Tuple[date, float]]:
    response = requests.get(
        FRED_CSV_URL,
        params={
            "id": series_id,
            "cosd": start_date.isoformat(),
            "coed": end_date.isoformat(),
        },
        timeout=20,
    )
    response.raise_for_status()
    rows = csv.DictReader(response.text.replace("\x00", "").splitlines())
    observations = []
    for row in rows:
        raw_value = row.get(series_id, "")
        if not raw_value or raw_value == ".":
            continue
        try:
            observed_date = datetime.strptime(row["observation_date"], "%Y-%m-%d").date()
            observations.append((observed_date, float(raw_value)))
        except (KeyError, TypeError, ValueError):
            continue
    return observations


def fetch_inflation_rates(
    start_date: date, end_date: date
) -> Dict[str, List[Tuple[date, float]]]:
    """Fetch year-over-year inflation rates for the selected FRED indexes."""
    index_start = _months_before(start_date, 12)
    inflation_rates = {}
    for series_id in SERIES:
        observations = _fetch_index_series(series_id, index_start, end_date)
        by_month = {(observed_date.year, observed_date.month): value for observed_date, value in observations}
        rates = []
        for observed_date, value in observations:
            prior_value = by_month.get((observed_date.year - 1, observed_date.month))
            if prior_value is not None and prior_value != 0:
                rates.append((observed_date, ((value / prior_value) - 1.0) * 100.0))
        inflation_rates[series_id] = [
            (observed_date, value)
            for observed_date, value in rates
            if start_date <= observed_date <= end_date
        ]
    return inflation_rates


def create_inflation_plot(
    rates: Dict[str, List[Tuple[date, float]]],
    start_date: date,
    end_date: date,
    output_path: Path = DEFAULT_OUTPUT,
) -> Path:
    """Create and save the five-year year-over-year inflation PNG."""
    figure, axis = plt.subplots(figsize=(11, 6), facecolor="#111827")
    axis.set_facecolor("#1f2937")
    colors = {
        "CPIAUCSL": "#fbbf24",
        "CPILFESL": "#60a5fa",
        "PCEPI": "#f87171",
        "PCEPILFE": "#c084fc",
    }

    for year in range(start_date.year, end_date.year + 1):
        if year % 2 == 0:
            axis.axvspan(
                max(start_date, date(year, 1, 1)),
                min(end_date, date(year + 1, 1, 1)),
                color="#475569",
                alpha=0.22,
                zorder=0,
            )

    plotted = False
    for series_id, label in SERIES.items():
        observations = rates.get(series_id, [])
        if not observations:
            continue
        dates, values = zip(*observations)
        axis.plot(dates, values, color=colors[series_id], linewidth=2.2, label=label)
        axis.scatter([dates[-1]], [values[-1]], color=colors[series_id], s=34, zorder=3)
        axis.annotate(
            f"{values[-1]:.2f}%",
            (dates[-1], values[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            color=colors[series_id],
            va="center",
        )
        plotted = True

    if not plotted:
        plt.close(figure)
        raise ValueError("FRED returned no inflation observations")

    axis.axhline(0, color="#cbd5e1", linewidth=1, alpha=0.5)
    axis.set_title("U.S. Inflation Rates: Year-over-Year Change", color="#f8fafc")
    axis.set_ylabel("12-month change (%)", color="#e5e7eb")
    axis.set_xlim(start_date, end_date)
    axis.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    axis.tick_params(colors="#e5e7eb")
    axis.grid(axis="both", linestyle="--", color="#cbd5e1", alpha=0.2)
    for spine in axis.spines.values():
        spine.set_color("#64748b")
    legend = axis.legend(facecolor="#1f2937", edgecolor="#64748b")
    for text in legend.get_texts():
        text.set_color("#f8fafc")
    figure.autofmt_xdate()
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

    end_date = date.today()
    start_date = _months_before(end_date, LOOKBACK_MONTHS)
    rates = fetch_inflation_rates(start_date, end_date)
    output_path = create_inflation_plot(rates, start_date, end_date, args.output)
    print(f"Saved inflation plot to {output_path}")


if __name__ == "__main__":
    main()