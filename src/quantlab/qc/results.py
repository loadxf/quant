"""QC backtest result -> canonical TradeLog + EquityCurve.

Field names verified against QC docs and LEAN source (July 2026):
`backtest.totalPerformance.closedTrades[]` carries per-trade
symbol, entryTime, entryPrice, exitTime, exitPrice, quantity,
direction (0=Long/1=Short), profitLoss, totalFees, mae, mfe.
LEAN's `Trade.ProfitLoss` is documented as "The GROSS profit/loss of the
trade" with fees accumulated separately in TotalFees — the canonical
Trade.pnl contract is NET, so pnl = profitLoss - totalFees here.
MAE/MFE flow straight into the intraday rule fidelity.

Malformed entries are dropped with a reason (mirroring the CSV
ingester's contract) instead of aborting the whole download.

The equity curve comes from the separate chart endpoint ("Strategy
Equity"); series values arrive as [t, value] pairs or [t, o, h, l, c]
candles (close used). Timestamps without timezone are treated as UTC —
documented assumption.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pandas as pd

from quantlab.errors import QuantLabError
from quantlab.schema.equity import EquityCurve
from quantlab.schema.trade import Side, Trade, TradeLog

UTC = dt.UTC


def _parse_time(value: Any) -> dt.datetime:
    stamp = pd.to_datetime(value)
    if pd.isna(stamp):
        raise ValueError(f"unparseable timestamp {value!r}")
    py = stamp.to_pydatetime()
    return py.replace(tzinfo=UTC) if py.tzinfo is None else py.astimezone(UTC)


def _symbol_text(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("value") or raw.get("Value") or raw.get("id") or "UNKNOWN")
    return str(raw)


def parse_closed_trades(backtest: dict[str, Any]) -> tuple[TradeLog, list[str]]:
    """Returns (log, skipped_reasons). One malformed trade must not abort a
    500-trade download."""
    performance = backtest.get("totalPerformance") or {}
    closed = performance.get("closedTrades") or []
    if not closed:
        raise QuantLabError(
            "Backtest result has no totalPerformance.closedTrades — the "
            "algorithm may not have closed any round-trip trades."
        )
    trades: list[Trade] = []
    skipped: list[str] = []
    for position, raw in enumerate(closed):
        try:
            quantity = abs(float(raw.get("quantity", 0)) or 1.0)
            fees = abs(float(raw.get("totalFees", 0.0)))
            gross = float(raw.get("profitLoss", 0.0))
            mae = raw.get("mae")
            mfe = raw.get("mfe")
            trades.append(
                Trade(
                    entry_time=_parse_time(raw["entryTime"]),
                    exit_time=_parse_time(raw["exitTime"]),
                    symbol=_symbol_text(raw.get("symbol", "UNKNOWN")),
                    side=Side.LONG if int(raw.get("direction", 0)) == 0 else Side.SHORT,
                    quantity=quantity,
                    # LEAN profitLoss is GROSS; canonical pnl is NET of fees.
                    pnl=gross - fees,
                    entry_price=(
                        float(raw["entryPrice"]) if raw.get("entryPrice") is not None else None
                    ),
                    exit_price=(
                        float(raw["exitPrice"]) if raw.get("exitPrice") is not None else None
                    ),
                    fees=fees,
                    mae=-abs(float(mae)) if mae is not None else None,
                    mfe=abs(float(mfe)) if mfe is not None else None,
                )
            )
        except Exception as exc:
            skipped.append(f"closedTrades[{position}]: {type(exc).__name__}: {exc}")
    if not trades:
        raise QuantLabError(
            f"No usable trades in closedTrades ({len(skipped)} skipped; first reason: {skipped[0]})"
        )
    return TradeLog(trades=trades, source="lean-cloud"), skipped


def parse_equity_chart(chart: dict[str, Any]) -> EquityCurve:
    series_map = chart.get("series") or {}
    series = series_map.get("Equity") or next(iter(series_map.values()), None)
    if not series:
        raise QuantLabError(f"Chart {chart.get('name')!r} has no series")
    points: list[tuple[dt.datetime, float]] = []
    for raw in series.get("values", []):
        if isinstance(raw, dict):  # {"x": ts, "y": v}
            ts, value = raw.get("x"), raw.get("y")
        elif isinstance(raw, list | tuple) and len(raw) >= 2:
            ts = raw[0]
            value = raw[4] if len(raw) >= 5 else raw[1]  # candle -> close
        else:
            continue
        if ts is None or value is None:
            continue
        when = dt.datetime.fromtimestamp(float(ts), tz=UTC)
        points.append((when, float(value)))
    if not points:
        raise QuantLabError("Equity chart contained no readable points")
    frame = pd.Series([v for _, v in points], index=pd.DatetimeIndex([t for t, _ in points]))
    return EquityCurve.from_series(frame)


def load_result_file(path: Path) -> dict[str, Any]:
    """Read a saved backtests/read response (or its `backtest` object)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return raw.get("backtest", raw)
