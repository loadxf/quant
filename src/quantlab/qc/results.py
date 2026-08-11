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
import math
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
        raw = raw.get("value") or raw.get("Value") or raw.get("id")
    if raw is None or not str(raw).strip():
        raise ValueError("closed trade has no symbol")
    return str(raw).strip()


def parse_closed_trades(backtest: object) -> tuple[TradeLog, list[str]]:
    """Returns (log, skipped_reasons). One malformed trade must not abort a
    500-trade download."""
    if not isinstance(backtest, dict):
        raise QuantLabError("Backtest result must be a JSON object")
    performance = backtest.get("totalPerformance")
    if performance is None:
        performance = {}
    if not isinstance(performance, dict):
        raise QuantLabError("Backtest totalPerformance must be a JSON object")
    closed = performance.get("closedTrades")
    if closed is None:
        closed = []
    if not isinstance(closed, list):
        raise QuantLabError("Backtest totalPerformance.closedTrades must be a JSON array")
    if not closed:
        raise QuantLabError(
            "Backtest result has no totalPerformance.closedTrades — the "
            "algorithm may not have closed any round-trip trades."
        )
    trades: list[Trade] = []
    skipped: list[str] = []
    for position, raw in enumerate(closed):
        try:
            quantity = abs(float(raw["quantity"]))
            if not math.isfinite(quantity) or quantity <= 0:
                raise ValueError(f"quantity must be finite and positive (got {quantity})")
            fees = abs(float(raw.get("totalFees", 0.0)))
            gross = float(raw.get("profitLoss", 0.0))
            if not math.isfinite(fees) or not math.isfinite(gross):
                raise ValueError("profitLoss and totalFees must be finite")
            raw_direction = float(raw["direction"])
            if not math.isfinite(raw_direction) or raw_direction not in (0.0, 1.0):
                raise ValueError(f"unsupported direction {raw_direction!r}")
            direction = int(raw_direction)
            mae = raw.get("mae")
            mfe = raw.get("mfe")
            trades.append(
                Trade(
                    entry_time=_parse_time(raw["entryTime"]),
                    exit_time=_parse_time(raw["exitTime"]),
                    symbol=_symbol_text(raw.get("symbol")),
                    side=Side.LONG if direction == 0 else Side.SHORT,
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


def parse_equity_chart(chart: object) -> EquityCurve:
    if not isinstance(chart, dict):
        raise QuantLabError("Equity chart must be a JSON object")
    series_map = chart.get("series")
    if series_map is None:
        series_map = {}
    if not isinstance(series_map, dict):
        raise QuantLabError("Equity chart series must be a JSON object")
    series = series_map.get("Equity") or next(iter(series_map.values()), None)
    if series is None:
        raise QuantLabError(f"Chart {chart.get('name')!r} has no series")
    if not isinstance(series, dict):
        raise QuantLabError("Equity chart series entry must be a JSON object")
    values = series.get("values", [])
    if not isinstance(values, list):
        raise QuantLabError("Equity chart series values must be a JSON array")
    points: list[tuple[dt.datetime, float]] = []
    for raw in values:
        if isinstance(raw, dict):  # {"x": ts, "y": v}
            ts, value = raw.get("x"), raw.get("y")
        elif isinstance(raw, list | tuple) and len(raw) >= 2:
            ts = raw[0]
            value = raw[4] if len(raw) >= 5 else raw[1]  # candle -> close
        else:
            continue
        if ts is None or value is None:
            continue
        try:
            numeric_value = float(value)
            if not math.isfinite(numeric_value):
                continue
            if isinstance(ts, str) and not ts.strip().replace(".", "", 1).isdigit():
                when = _parse_time(ts)
            else:
                epoch = float(ts)
                if abs(epoch) >= 1e11:  # QC exports can use milliseconds.
                    epoch /= 1000
                when = dt.datetime.fromtimestamp(epoch, tz=UTC)
            points.append((when, numeric_value))
        except (OverflowError, OSError, TypeError, ValueError):
            continue
    if not points:
        raise QuantLabError("Equity chart contained no readable points")
    frame = pd.Series([v for _, v in points], index=pd.DatetimeIndex([t for t, _ in points]))
    frame = frame.sort_index(kind="stable")
    frame = frame[~frame.index.duplicated(keep="last")]
    return EquityCurve.from_series(frame)


def load_result_file(path: Path) -> dict[str, Any]:
    """Read a saved backtests/read response (or its `backtest` object)."""
    def reject_constant(value: str):
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        raw = json.loads(Path(path).read_text(), parse_constant=reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise QuantLabError(f"Could not read saved backtest result {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise QuantLabError("Saved backtest result must contain a JSON object")
    backtest = raw.get("backtest", raw)
    if not isinstance(backtest, dict):
        raise QuantLabError("Saved backtest field must contain a JSON object")
    return backtest
