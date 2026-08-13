"""QC backtest result -> canonical TradeLog + EquityCurve.

Field names verified against QC docs and LEAN source (July 2026):
`backtest.totalPerformance.closedTrades[]` carries per-trade
symbols (or symbol in older serializers), entryTime, entryPrice,
exitTime, exitPrice, quantity,
direction (0=Long/1=Short), profitLoss, totalFees, mae, mfe.
LEAN's `Trade.ProfitLoss` is documented as "The GROSS profit/loss of the
trade" with fees accumulated separately in TotalFees — the canonical
Trade.pnl contract is NET, so pnl = profitLoss - totalFees here.
MAE/MFE flow straight into the intraday rule fidelity.

Malformed entries are dropped with a reason (mirroring the CSV
ingester's contract) instead of aborting the whole download.

The equity curve can come from either the ``charts`` object in the JSON
downloaded from the Cloud backtest results page or the separate API chart
endpoint. Series values arrive as [t, value] pairs or [t, o, h, l, c]
candles (close used). Timestamps without timezone are treated as UTC —
documented assumption. ``equityMarks`` remains supported for older files
created by quantlab's retired Object Store export block.
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
_MISSING = object()


def _field(mapping: dict[str, Any], name: str, default: Any = _MISSING) -> Any:
    """Read a JSON field case-insensitively for UI/API serializer variants."""
    if name in mapping:
        return mapping[name]
    wanted = name.casefold()
    for key, value in mapping.items():
        if isinstance(key, str) and key.casefold() == wanted:
            return value
    if default is not _MISSING:
        return default
    raise KeyError(name)


def _parse_time(value: Any) -> dt.datetime:
    stamp = pd.to_datetime(value)
    if pd.isna(stamp):
        raise ValueError(f"unparseable timestamp {value!r}")
    py = stamp.to_pydatetime()
    return py.replace(tzinfo=UTC) if py.tzinfo is None else py.astimezone(UTC)


def _symbol_text(raw: Any) -> str:
    if isinstance(raw, dict):
        raw = _field(raw, "value", None) or _field(raw, "id", None)
    if raw is None or not str(raw).strip():
        raise ValueError("closed trade has no symbol")
    return str(raw).strip()


def _closed_trade_symbol(raw: dict[str, Any]) -> str:
    """Normalize LEAN's current ``symbols[]`` and legacy ``symbol`` fields."""
    singular = _field(raw, "symbol", None)
    if singular is not None:
        return _symbol_text(singular)
    symbols = _field(raw, "symbols", None)
    if not isinstance(symbols, list) or not symbols:
        raise ValueError("closed trade has no symbol")
    if len(symbols) != 1:
        raise ValueError(
            f"closed trade has {len(symbols)} symbols; multi-symbol trades are unsupported"
        )
    return _symbol_text(symbols[0])


def parse_closed_trades(backtest: object) -> tuple[TradeLog, list[str]]:
    """Returns (log, skipped_reasons). One malformed trade must not abort a
    500-trade download."""
    if not isinstance(backtest, dict):
        raise QuantLabError("Backtest result must be a JSON object")
    performance = _field(backtest, "totalPerformance", None)
    if performance is None:
        performance = {}
    if not isinstance(performance, dict):
        raise QuantLabError("Backtest totalPerformance must be a JSON object")
    closed = _field(performance, "closedTrades", None)
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
            quantity = abs(float(_field(raw, "quantity")))
            if not math.isfinite(quantity) or quantity <= 0:
                raise ValueError(f"quantity must be finite and positive (got {quantity})")
            fees = abs(float(_field(raw, "totalFees", 0.0)))
            gross = float(_field(raw, "profitLoss", 0.0))
            if not math.isfinite(fees) or not math.isfinite(gross):
                raise ValueError("profitLoss and totalFees must be finite")
            raw_direction = float(_field(raw, "direction"))
            if not math.isfinite(raw_direction) or raw_direction not in (0.0, 1.0):
                raise ValueError(f"unsupported direction {raw_direction!r}")
            direction = int(raw_direction)
            mae = _field(raw, "mae", None)
            mfe = _field(raw, "mfe", None)
            entry_price = _field(raw, "entryPrice", None)
            exit_price = _field(raw, "exitPrice", None)
            trades.append(
                Trade(
                    entry_time=_parse_time(_field(raw, "entryTime")),
                    exit_time=_parse_time(_field(raw, "exitTime")),
                    symbol=_closed_trade_symbol(raw),
                    side=Side.LONG if direction == 0 else Side.SHORT,
                    quantity=quantity,
                    # LEAN profitLoss is GROSS; canonical pnl is NET of fees.
                    pnl=gross - fees,
                    entry_price=float(entry_price) if entry_price is not None else None,
                    exit_price=float(exit_price) if exit_price is not None else None,
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


def parse_equity_marks(backtest: object) -> EquityCurve | None:
    """Legacy equity marks embedded by the old quantlab export block.
    (`"equityMarks": [[iso-utc, value], ...]`).

    Returns None when the payload carries no marks at all (e.g. an API
    download or a pre-marks export) so callers can distinguish "absent"
    from "present but unreadable" (which raises)."""
    if not isinstance(backtest, dict):
        raise QuantLabError("Backtest result must be a JSON object")
    marks = _field(backtest, "equityMarks", None)
    if marks is None:
        return None
    if not isinstance(marks, list):
        raise QuantLabError("equityMarks must be a JSON array")
    points: list[tuple[dt.datetime, float]] = []
    for raw in marks:
        if not isinstance(raw, list | tuple) or len(raw) < 2:
            continue
        try:
            when = _parse_time(raw[0])
            value = float(raw[1])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        points.append((when, value))
    if not points:
        raise QuantLabError("equityMarks contained no readable points")
    frame = pd.Series([v for _, v in points], index=pd.DatetimeIndex([t for t, _ in points]))
    frame = frame.sort_index(kind="stable")
    frame = frame[~frame.index.duplicated(keep="last")]
    return EquityCurve.from_series(frame)


def parse_embedded_equity(backtest: object) -> EquityCurve | None:
    """Read Strategy Equity embedded in a Cloud ``Download Results`` JSON.

    QuantConnect currently serializes ``charts`` as a name-keyed object. A
    list form is accepted as well so files remain importable if the UI uses
    the same chart-array representation as other LEAN result serializers.
    Legacy ``equityMarks`` are a final compatibility fallback.
    """
    if not isinstance(backtest, dict):
        raise QuantLabError("Backtest result must be a JSON object")
    charts = _field(backtest, "charts", None)
    candidates: list[object] = []
    if isinstance(charts, dict):
        preferred = charts.get("Strategy Equity")
        if preferred is not None:
            candidates.append(preferred)
        candidates.extend(
            chart
            for name, chart in charts.items()
            if name != "Strategy Equity"
            and isinstance(name, str)
            and name.casefold() == "strategy equity"
        )
    elif isinstance(charts, list):
        candidates.extend(
            chart
            for chart in charts
            if isinstance(chart, dict)
            and str(_field(chart, "name", "")).casefold() == "strategy equity"
        )
    elif charts is not None:
        raise QuantLabError("Backtest charts must be a JSON object or array")
    for chart in candidates:
        if isinstance(chart, dict):
            # Name-keyed chart objects may omit their redundant name field.
            normalized = (
                chart if _field(chart, "name", None) else {"name": "Strategy Equity", **chart}
            )
            return parse_equity_chart(normalized)
    return parse_equity_marks(backtest)


def parse_equity_chart(chart: object) -> EquityCurve:
    if not isinstance(chart, dict):
        raise QuantLabError("Equity chart must be a JSON object")
    series_map = _field(chart, "series", None)
    if series_map is None:
        series_map = {}
    if not isinstance(series_map, dict):
        raise QuantLabError("Equity chart series must be a JSON object")
    series = _field(series_map, "Equity", None) or next(iter(series_map.values()), None)
    if series is None:
        raise QuantLabError(f"Chart {_field(chart, 'name', None)!r} has no series")
    if not isinstance(series, dict):
        raise QuantLabError("Equity chart series entry must be a JSON object")
    values = _field(series, "values", [])
    if not isinstance(values, list):
        raise QuantLabError("Equity chart series values must be a JSON array")
    points: list[tuple[dt.datetime, float]] = []
    for raw in values:
        if isinstance(raw, dict):  # {"x": ts, "y": v}
            ts, value = _field(raw, "x", None), _field(raw, "y", None)
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
    """Read a Cloud Download Results JSON or saved API response wrapper."""

    def reject_constant(value: str):
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise QuantLabError(f"Could not read saved backtest result {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise QuantLabError("Saved backtest result must contain a JSON object")
    backtest = _field(raw, "backtest", raw)
    if not isinstance(backtest, dict):
        raise QuantLabError("Saved backtest field must contain a JSON object")
    return backtest
