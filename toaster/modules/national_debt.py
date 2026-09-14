"""Print the latest U.S. national debt and a clearly labeled current estimate.

The official Treasury Debt to the Penny dataset is updated daily. When the
latest record is older than the current day, this module projects forward using
the most recent daily change; the projection is not an official live balance.
This module is standalone and is not connected to Toast.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

import requests


API_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
    "v2/accounting/od/debt_to_penny"
)
SOURCE_URL = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


def _decimal(record: dict, field: str) -> Decimal:
    try:
        return Decimal(str(record[field]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Treasury value for {field}") from exc


def get_national_debt_report(now: Optional[datetime] = None) -> str:
    """Return the latest official debt and a projected current estimate."""
    try:
        response = requests.get(
            API_URL,
            params={
                "sort": "-record_date",
                "page[size]": 2,
            },
            timeout=20,
        )
        response.raise_for_status()
        records = response.json().get("data", [])
    except (requests.RequestException, ValueError, AttributeError, TypeError) as exc:
        return f"U.S. national debt is currently unavailable: {exc}"

    if not isinstance(records, list) or not records:
        return "U.S. national debt is currently unavailable: no Treasury records returned."

    try:
        latest = records[0]
        latest_date = date.fromisoformat(latest["record_date"])
        latest_total = _decimal(latest, "tot_pub_debt_out_amt")
        public_debt = _decimal(latest, "debt_held_public_amt")
        intragov_debt = _decimal(latest, "intragov_hold_amt")
    except (KeyError, TypeError, ValueError) as exc:
        return f"U.S. national debt is currently unavailable: {exc}"

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    latest_timestamp = datetime.combine(latest_date, datetime.min.time(), tzinfo=timezone.utc)
    elapsed_days = max(0.0, (current_time - latest_timestamp).total_seconds() / 86400)

    projection_line = "Estimated current total: unavailable"
    daily_change_line = "Daily change: unavailable"
    if len(records) >= 2:
        try:
            previous_total = _decimal(records[1], "tot_pub_debt_out_amt")
            previous_date = date.fromisoformat(records[1]["record_date"])
            day_span = (latest_date - previous_date).days
            if day_span > 0:
                daily_change = (latest_total - previous_total) / day_span
                projected_total = latest_total + daily_change * Decimal(str(elapsed_days))
                daily_change_line = f"Recent average daily change: {_money(daily_change)}"
                projection_line = (
                    f"Estimated current total: {_money(projected_total)} "
                    f"(projected {elapsed_days:.1f} days from latest record)"
                )
        except (KeyError, TypeError, ValueError, InvalidOperation):
            pass

    return "\n".join(
        [
            "U.S. National Debt",
            f"Latest official total ({latest_date.isoformat()}): {_money(latest_total)}",
            projection_line,
            daily_change_line,
            f"Debt held by the public: {_money(public_debt)}",
            f"Intragovernmental holdings: {_money(intragov_debt)}",
            "Projection note: the Treasury publishes this dataset daily; the estimate is not an official live balance.",
            f"Source: {SOURCE_URL}",
        ]
    )


if __name__ == "__main__":
    print(get_national_debt_report())