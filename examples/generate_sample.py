"""Regenerate examples/trades_sample.csv (deterministic).

A ~6-month synthetic MNQ/MES futures log with slightly positive expectancy,
realistic RTH session times, MAE/MFE columns, and deliberately messy
formatting ($ signs, commas, parenthesized negatives) to exercise the
ingestion parser. Run: python examples/generate_sample.py
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

OUT = Path(__file__).parent / "trades_sample.csv"
CT = ZoneInfo("America/Chicago")


def money(value: float) -> str:
    return f"(${abs(value):,.2f})" if value < 0 else f"${value:,.2f}"


def main() -> None:
    rng = np.random.default_rng(42)
    start = dt.date(2026, 1, 5)
    rows = []
    day = start
    while len(rows) < 400:
        if day.weekday() < 5 and rng.random() > 0.08:  # skip weekends + odd days off
            for _ in range(int(rng.integers(1, 6))):
                minute = int(rng.integers(0, 300))  # 08:30-13:30 CT window
                entry = dt.datetime.combine(day, dt.time(8, 30), tzinfo=CT) + dt.timedelta(
                    minutes=minute
                )
                hold = int(rng.integers(2, 90))
                exit_ = entry + dt.timedelta(minutes=hold)
                symbol = "MNQ" if rng.random() < 0.7 else "MES"
                side = "Buy" if rng.random() < 0.55 else "Sell"
                qty = int(rng.integers(1, 4))
                win = rng.random() < 0.52
                base = float(rng.gamma(2.0, 60.0)) if win else -float(rng.gamma(2.0, 55.0))
                pnl = round(base * qty / 2, 2)
                mae = round(-abs(min(pnl, 0)) - float(rng.gamma(1.5, 25.0)), 2)
                mfe = round(abs(max(pnl, 0)) + float(rng.gamma(1.5, 25.0)), 2)
                fees = round(0.62 * qty * 2, 2)
                rows.append(
                    {
                        "Entry DateTime": entry.strftime("%Y-%m-%d %H:%M:%S"),
                        "Exit DateTime": exit_.strftime("%Y-%m-%d %H:%M:%S"),
                        "Symbol": symbol,
                        "Type": side,
                        "Qty": qty,
                        "Net P/L": money(pnl),
                        "Fees": money(fees),
                        "MAE": money(mae),
                        "MFE": money(mfe),
                    }
                )
        day += dt.timedelta(days=1)

    rows = rows[:400]
    with OUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} trades -> {OUT}")


if __name__ == "__main__":
    main()
