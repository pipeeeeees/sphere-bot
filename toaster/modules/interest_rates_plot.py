"""Generate a six-month U.S. interest-rate change plot from public FRED data."""

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
    "DFF": "Effective Federal Funds",
    "DGS2": "2-Year Treasury",
    "DGS10": "10-Year Treasury",
}
DEFAULT_OUTPUT = Path("interest_rates_6_months.png")


def _months_before(day: date, months: int) -> date:
    month_index = day.year * 12 + day.month - 1 - months
    year, month_zero_indexed = divmod(month_index, 12)
    month = month_zero_indexed + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def fetch_interest_rates(
    start_date: date, end_date: date
) -> Dict[str, List[Tuple[date, float]]]:
    """Fetch selected FRED rate series for an inclusive date range."""
    rates = {series_id: [] for series_id in SERIES}
    for series_id in SERIES:
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
        clean_csv = response.text.replace("\x00", "")
        rows = csv.DictReader(clean_csv.splitlines())
        for row in rows:
            try:
                observed_date = datetime.strptime(row["observation_date"], "%Y-%m-%d").date()
            except (KeyError, TypeError, ValueError):
                continue
            raw_value = row.get(series_id, "")
            if not raw_value or raw_value == ".":
                continue
            try:
                rates[series_id].append((observed_date, float(raw_value)))
            except ValueError:
                continue
    return rates


def create_interest_rates_plot(
    rates: Dict[str, List[Tuple[date, float]]],
    start_date: date,
    end_date: date,
    output_path: Path = DEFAULT_OUTPUT,
) -> Path:
    """Create and save the six-month interest-rate PNG."""
    figure, axis = plt.subplots(figsize=(11, 6), facecolor="#111827")
    axis.set_facecolor("#1f2937")
    colors = {"DFF": "#fbbf24", "DGS2": "#60a5fa", "DGS10": "#f87171"}

    plotted = False
    for series_id, label in SERIES.items():
        observations = rates.get(series_id, [])
        if not observations:
            continue
        dates, values = zip(*observations)
        axis.plot(
            dates,
            values,
            color=colors[series_id],
            linewidth=2.2,
            label=label,
        )
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
        raise ValueError("FRED returned no interest-rate observations")

    axis.set_title("U.S. Interest Rates: Last Six Months", color="#f8fafc")
    axis.set_ylabel("Rate (%)", color="#e5e7eb")
    axis.set_xlim(start_date, end_date)
    axis.xaxis.set_major_locator(mdates.MonthLocator())
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
    start_date = _months_before(end_date, 6)
    rates = fetch_interest_rates(start_date, end_date)
    output_path = create_interest_rates_plot(rates, start_date, end_date, args.output)
    print(f"Saved interest-rate plot to {output_path}")


if __name__ == "__main__":
    main()