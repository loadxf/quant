"""Trusted causal signal registry for promotable research candidates.

Candidate ``signal.py`` files are declarations, not executable programs.  A
literal ``SIGNAL_KIND`` selects one of the handlers below and a strict schema
defines every consumed parameter.  This keeps candidate code from becoming a
second, gameable execution boundary while retaining explicit, sealed strategy
definitions for registration and holdout evaluation.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping

import numpy as np
import pandas as pd

from .grammar import (
    BINARY,
    MAX_DEPTH,
    MAX_NODES,
    ROLLING,
    TERMINALS,
    UNARY,
    build_terminals,
    count_nodes,
    depth,
    evaluate,
    parse_expr,
    to_string,
)
from .market_calendar import nyse_sessions

Frame = pd.DataFrame
Fields = dict[str, object]

SECTOR_TO_ETF = {
    "Materials": "XLB",
    "Communication Services": "XLC",
    "Energy": "XLE",
    "Financials": "XLF",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Consumer Staples": "XLP",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Health Care": "XLV",
    "Consumer Discretionary": "XLY",
}

_EXECUTION_PARAMETERS = {"HOLD", "MIN_NAMES", "QUANTILE"}
_COMMON_PARAMETERS = {
    "SIGNAL_KIND",
    "ORIGIN",
    "HOLDOUT_END",
    "PERTURBATIONS",
    "HOLD",
    "MIN_NAMES",
    "QUANTILE",
    "UNIVERSE",
}

_KIND_PARAMETERS: dict[str, frozenset[str]] = {
    "plain_reversal": frozenset({"RETURN_WINDOW"}),
    "spike_reversal": frozenset({"EPISODE_Z", "RETURN_WINDOW", "VOL_WINDOW"}),
    "volume_recession_reversal": frozenset(
        {
            "SPIKE_Z",
            "POST_DAYS",
            "WINDOW",
            "MIN_SPIKES",
            "VOL_WINDOW",
            "REVERSAL_WINDOW",
        }
    ),
    "turn_of_month_reversal": frozenset({"FIRST_DAYS", "LAST_DAYS", "RETURN_WINDOW"}),
    "episode_reversal": frozenset(
        {
            "EPISODE_Z",
            "LOOKBACK",
            "VOL_WINDOW",
            "RETURN_WINDOW",
            "BREADTH_THRESHOLD",
            "BROAD_TAIL",
            "THIN_TAIL",
        }
    ),
    "volume_weighted_reversal": frozenset({"RETURN_WINDOW", "VOL_WINDOW"}),
    "intraday_reversal": frozenset({"REVERSAL_WINDOW", "MIN_PERIODS"}),
    "lag_band_reversal": frozenset({"BAND_LAG", "BAND_LEN"}),
    "gap_intraday_coherence": frozenset({"SMOOTH", "MIN_PERIODS"}),
    "sector_etf_reversal": frozenset({"RETURN_WINDOW"}),
    "expression": frozenset({"EXPR"}),
    "expression_minus_return": frozenset({"EXPR", "RETURN_WINDOW"}),
    "volume_recession_monthly_reversal": frozenset(
        {"SPIKE_Z", "POST_DAYS", "WINDOW", "MIN_SPIKES", "VOL_WINDOW", "RETURN_WINDOW"}
    ),
    "smoothed_volume_z": frozenset({"SMOOTH", "MIN_PERIODS", "VOL_WINDOW"}),
    "range_volatility": frozenset({"WINDOW"}),
    "volume_rank_skew_expression": frozenset({"EXPR", "VOL_WINDOW"}),
}

_FLOAT_PARAMETERS = {"EPISODE_Z", "SPIKE_Z", "BROAD_TAIL", "THIN_TAIL", "QUANTILE"}


def _positive_int(name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise RuntimeError(f"signal parameter {name} must be a positive integer")
    return value


def _positive_number(name: str, value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RuntimeError(f"signal parameter {name} must be a positive finite number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise RuntimeError(f"signal parameter {name} must be a positive finite number")
    return number


def _validate_runtime_expr(expr: object) -> None:
    if isinstance(expr, str):
        if expr not in TERMINALS:
            raise RuntimeError(f"unknown signal expression terminal {expr!r}")
        return
    if not isinstance(expr, tuple) or not expr or not isinstance(expr[0], str):
        raise RuntimeError(f"invalid signal expression node {expr!r}")
    op = expr[0]
    if op in UNARY:
        if len(expr) != 2:
            raise RuntimeError(f"signal expression {op} expects one operand")
        _validate_runtime_expr(expr[1])
        return
    if op in ROLLING:
        if len(expr) != 3:
            raise RuntimeError(f"signal expression {op} expects an operand and window")
        _positive_int("EXPR window", expr[2])
        _validate_runtime_expr(expr[1])
        return
    if op in BINARY:
        if len(expr) != 3:
            raise RuntimeError(f"signal expression {op} expects two operands")
        _validate_runtime_expr(expr[1])
        _validate_runtime_expr(expr[2])
        return
    raise RuntimeError(f"unknown signal expression operation {op!r}")


def _expression_windows(expr: object) -> list[int]:
    if isinstance(expr, str):
        return []
    if not isinstance(expr, tuple):
        return []
    windows = [expr[2]] if expr and expr[0] in ROLLING and len(expr) == 3 else []
    for child in expr[1:]:
        if isinstance(child, tuple):
            windows.extend(_expression_windows(child))
    return windows


def validate_declaration(
    values: Mapping[str, object], *, relaxed_expression_window: bool = False
) -> dict[str, object]:
    """Validate and normalize a declaration without executing candidate code."""
    kind = values.get("SIGNAL_KIND")
    if not isinstance(kind, str) or kind not in _KIND_PARAMETERS:
        raise RuntimeError(f"unknown or missing literal SIGNAL_KIND: {kind!r}")
    origin = values.get("ORIGIN")
    if origin not in {"G1", "G2", "G3", "G4", "baseline"}:
        raise RuntimeError(f"unknown or missing literal ORIGIN: {origin!r}")
    required = _KIND_PARAMETERS[kind]
    allowed = _COMMON_PARAMETERS | set(required)
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise RuntimeError(f"unknown signal declaration constants: {', '.join(unknown)}")
    missing = sorted(required - set(values))
    if missing:
        raise RuntimeError(f"missing signal declaration parameters: {', '.join(missing)}")

    normalized = dict(values)
    for name in required:
        value = normalized[name]
        if name == "EXPR":
            _validate_runtime_expr(value)
            if depth(value) > MAX_DEPTH or count_nodes(value) > MAX_NODES:
                raise RuntimeError("signal expression exceeds the grammar complexity bounds")
            if relaxed_expression_window:
                for node in _expression_windows(value):
                    if node > 512:
                        raise RuntimeError("perturbed signal expression window is too large")
            else:
                try:
                    parse_expr(to_string(value))
                except ValueError as exc:
                    raise RuntimeError(
                        f"base signal expression is outside the frozen grammar: {exc}"
                    ) from exc
        elif name in _FLOAT_PARAMETERS:
            _positive_number(name, value)
        else:
            _positive_int(name, value)

    if "HOLD" in normalized:
        _positive_int("HOLD", normalized["HOLD"])
    if "MIN_NAMES" in normalized:
        _positive_int("MIN_NAMES", normalized["MIN_NAMES"])
    if "QUANTILE" in normalized:
        quantile = _positive_number("QUANTILE", normalized["QUANTILE"])
        if quantile > 0.5:
            raise RuntimeError("signal parameter QUANTILE must be at most 0.5")
    if "UNIVERSE" in normalized and normalized["UNIVERSE"] not in {"equities", "etfs"}:
        raise RuntimeError("signal parameter UNIVERSE must be 'equities' or 'etfs'")
    if "HOLDOUT_END" in normalized:
        try:
            end = pd.Timestamp(normalized["HOLDOUT_END"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("HOLDOUT_END must be an ISO date string") from exc
        if (
            not isinstance(normalized["HOLDOUT_END"], str)
            or end.time() != pd.Timestamp(end.date()).time()
        ):
            raise RuntimeError("HOLDOUT_END must be an ISO date string")

    perturbations = normalized.get("PERTURBATIONS")
    if not isinstance(perturbations, tuple) or not all(
        isinstance(name, str) and name for name in perturbations
    ):
        raise RuntimeError("candidate must declare PERTURBATIONS as a tuple of names")
    if len(set(perturbations)) != len(perturbations):
        raise RuntimeError("candidate PERTURBATIONS contains duplicate names")
    consumable = set(required) | (_EXECUTION_PARAMETERS & set(normalized))
    undeclared = sorted(set(perturbations) - consumable)
    if undeclared:
        raise RuntimeError(
            "PERTURBATIONS names parameters not consumed by the signal/backtest: "
            + ", ".join(undeclared)
        )
    missing_robustness = sorted(consumable - set(perturbations))
    if missing_robustness:
        raise RuntimeError(
            "numeric signal/backtest parameters missing from PERTURBATIONS: "
            + ", ".join(missing_robustness)
        )
    return normalized


def _terminals(fields: Fields) -> dict[str, Frame]:
    return build_terminals(
        fields["open"],
        fields["high"],
        fields["low"],
        fields["close"],
        fields["adjclose"],
        fields["volume"],
    )


def _volume_z(fields: Fields, window: int) -> Frame:
    volume = fields["volume"]
    if not isinstance(volume, pd.DataFrame):
        raise RuntimeError("candidate fields must include a volume DataFrame")
    logvol = np.log(volume.where(volume > 0))
    return (logvol - logvol.rolling(window).mean()) / logvol.rolling(window).std()


def _episode_log_return(logret: Frame, spike: Frame, lookback: int) -> Frame:
    """Inclusive return from the earliest spike through the preceding day."""
    episode_ret = pd.DataFrame(np.nan, index=logret.index, columns=logret.columns)
    for k in range(1, lookback + 1):
        spiked_k_ago = spike.shift(k, fill_value=False)
        inclusive = logret.shift(1).rolling(k, min_periods=k).sum()
        episode_ret = episode_ret.mask(spiked_k_ago, inclusive)
    return episode_ret


def _recession_speed(fields: Fields, params: Mapping[str, object]) -> Frame:
    volz = _volume_z(fields, int(params["VOL_WINDOW"]))
    post_days = int(params["POST_DAYS"])
    window = int(params["WINDOW"])
    min_spikes = int(params["MIN_SPIKES"])
    spike_known = volz.shift(post_days)
    post_mean = sum(volz.shift(k) for k in range(post_days)) / post_days
    recession = (spike_known - post_mean).where(spike_known > float(params["SPIKE_Z"]))
    speed = recession.rolling(window, min_periods=min_spikes).mean()
    count = recession.notna().rolling(window, min_periods=1).sum()
    return speed.where(count >= min_spikes)


def _plain_reversal(fields: Fields, p: Mapping[str, object]) -> Frame:
    return -fields["adjclose"].pct_change(int(p["RETURN_WINDOW"]), fill_method=None)


def _spike_reversal(fields: Fields, p: Mapping[str, object]) -> Frame:
    volz = _volume_z(fields, int(p["VOL_WINDOW"]))
    ret = fields["adjclose"].pct_change(int(p["RETURN_WINDOW"]), fill_method=None)
    return (-ret).where(volz > float(p["EPISODE_Z"]))


def _volume_recession_reversal(fields: Fields, p: Mapping[str, object]) -> Frame:
    reversal = -fields["adjclose"].pct_change(int(p["REVERSAL_WINDOW"]), fill_method=None)
    return reversal * _recession_speed(fields, p).rank(axis=1, pct=True)


def _turn_of_month_reversal(fields: Fields, p: Mapping[str, object]) -> Frame:
    ret = fields["adjclose"].pct_change(int(p["RETURN_WINDOW"]), fill_method=None)
    selected: set[pd.Timestamp] = set()
    for period in ret.index.to_period("M").unique():
        sessions = nyse_sessions(period.start_time, period.end_time)
        selected.update(sessions[: int(p["FIRST_DAYS"])])
        selected.update(sessions[-int(p["LAST_DAYS"]) :])
    mask = pd.Series(ret.index.normalize().isin(selected).astype(float), index=ret.index)
    return (-ret).mul(mask, axis=0)


def _episode_reversal(fields: Fields, p: Mapping[str, object]) -> Frame:
    volz = _volume_z(fields, int(p["VOL_WINDOW"]))
    ret = fields["adjclose"].pct_change(int(p["RETURN_WINDOW"]), fill_method=None)
    spike = (volz > float(p["EPISODE_Z"])).fillna(False)
    lookback = int(p["LOOKBACK"])
    live = spike.shift(1, fill_value=False).rolling(lookback, min_periods=1).max() == 1.0
    trigger = live & (volz < 0) & (volz.shift(1) >= 0)
    episode = _episode_log_return(np.log1p(ret), spike, lookback)
    raw = (-np.expm1(episode)).where(trigger)
    breadth = raw.notna().sum(axis=1)
    tail = pd.Series(
        np.where(
            breadth < int(p["BREADTH_THRESHOLD"]),
            float(p["THIN_TAIL"]),
            float(p["BROAD_TAIL"]),
        ),
        index=raw.index,
    )
    ranks = raw.rank(axis=1, pct=True)
    return raw.where(ranks.le(tail, axis=0) | ranks.gt(1.0 - tail, axis=0))


def _volume_weighted_reversal(fields: Fields, p: Mapping[str, object]) -> Frame:
    weight = 1.0 - _volume_z(fields, int(p["VOL_WINDOW"])).rank(axis=1, pct=True)
    reversal = fields["adjclose"].pct_change(int(p["RETURN_WINDOW"]), fill_method=None)
    return -reversal * weight


def _intraday_reversal(fields: Fields, p: Mapping[str, object]) -> Frame:
    intraday = fields["close"] / fields["open"] - 1.0
    return -intraday.rolling(int(p["REVERSAL_WINDOW"]), min_periods=int(p["MIN_PERIODS"])).sum()


def _lag_band_reversal(fields: Fields, p: Mapping[str, object]) -> Frame:
    return (
        -fields["adjclose"]
        .pct_change(int(p["BAND_LEN"]) - 1, fill_method=None)
        .shift(int(p["BAND_LAG"]))
    )


def _gap_intraday_coherence(fields: Fields, p: Mapping[str, object]) -> Frame:
    terms = _terminals(fields)
    return (
        (terms["gap"] * terms["intraday"])
        .rolling(int(p["SMOOTH"]), min_periods=int(p["MIN_PERIODS"]))
        .mean()
    )


def _sector_etf_reversal(fields: Fields, p: Mapping[str, object]) -> Frame:
    adj = fields["adjclose"]
    etf = fields.get("etf_adjclose")
    sectors = fields.get("sectors")
    if not isinstance(adj, pd.DataFrame) or not isinstance(etf, pd.DataFrame):
        raise RuntimeError("sector ETF signal requires adjclose and etf_adjclose panels")
    if not isinstance(sectors, dict):
        raise RuntimeError("sector ETF signal requires an equity sector mapping")
    etf_ret = etf.pct_change(int(p["RETURN_WINDOW"]), fill_method=None).reindex(adj.index)
    signal = pd.DataFrame(index=adj.index, columns=adj.columns, dtype=float)
    for ticker in adj.columns:
        etf_ticker = SECTOR_TO_ETF.get(sectors.get(ticker, ""))
        if etf_ticker is not None and etf_ticker in etf_ret.columns:
            signal[ticker] = -etf_ret[etf_ticker]
    return signal


def _expression(fields: Fields, p: Mapping[str, object]) -> Frame:
    return evaluate(p["EXPR"], _terminals(fields))


def _expression_minus_return(fields: Fields, p: Mapping[str, object]) -> Frame:
    return _expression(fields, p) - fields["adjclose"].pct_change(
        int(p["RETURN_WINDOW"]), fill_method=None
    )


def _volume_recession_monthly_reversal(fields: Fields, p: Mapping[str, object]) -> Frame:
    reversal = -fields["adjclose"].pct_change(int(p["RETURN_WINDOW"]), fill_method=None)
    return reversal * _recession_speed(fields, p).rank(axis=1, pct=True)


def _smoothed_volume_z(fields: Fields, p: Mapping[str, object]) -> Frame:
    return (
        _volume_z(fields, int(p["VOL_WINDOW"]))
        .rolling(int(p["SMOOTH"]), min_periods=int(p["MIN_PERIODS"]))
        .mean()
    )


def _range_volatility(fields: Fields, p: Mapping[str, object]) -> Frame:
    fraction = (fields["high"] - fields["low"]) / fields["close"]
    window = int(p["WINDOW"])
    return fraction.rolling(window, min_periods=window // 2).std()


def _volume_rank_skew_expression(fields: Fields, p: Mapping[str, object]) -> Frame:
    terms = _terminals(fields)
    terms["volz"] = _volume_z(fields, int(p["VOL_WINDOW"]))
    return evaluate(p["EXPR"], terms)


_HANDLERS: dict[str, Callable[[Fields, Mapping[str, object]], Frame]] = {
    "plain_reversal": _plain_reversal,
    "spike_reversal": _spike_reversal,
    "volume_recession_reversal": _volume_recession_reversal,
    "turn_of_month_reversal": _turn_of_month_reversal,
    "episode_reversal": _episode_reversal,
    "volume_weighted_reversal": _volume_weighted_reversal,
    "intraday_reversal": _intraday_reversal,
    "lag_band_reversal": _lag_band_reversal,
    "gap_intraday_coherence": _gap_intraday_coherence,
    "sector_etf_reversal": _sector_etf_reversal,
    "expression": _expression,
    "expression_minus_return": _expression_minus_return,
    "volume_recession_monthly_reversal": _volume_recession_monthly_reversal,
    "smoothed_volume_z": _smoothed_volume_z,
    "range_volatility": _range_volatility,
    "volume_rank_skew_expression": _volume_rank_skew_expression,
}


def compute_declared_signal(
    fields: Fields,
    declaration: Mapping[str, object],
    overrides: Mapping[str, object] | None = None,
) -> Frame:
    """Evaluate one strict declaration through its trusted causal handler."""
    validate_declaration(declaration)
    override_values = dict(overrides or {})
    allowed_overrides = set(declaration["PERTURBATIONS"]) - _EXECUTION_PARAMETERS
    forbidden = sorted(set(override_values) - allowed_overrides)
    if forbidden:
        raise RuntimeError(
            "signal overrides are undeclared, routing, or backtest-only parameters: "
            + ", ".join(forbidden)
        )
    values = dict(declaration)
    values.update(override_values)
    values = validate_declaration(
        values, relaxed_expression_window="EXPR" in override_values
    )
    reference = fields.get("adjclose")
    if not isinstance(reference, pd.DataFrame):
        raise RuntimeError("candidate fields must include an adjclose DataFrame")
    signal = _HANDLERS[str(values["SIGNAL_KIND"])](fields, values)
    if type(signal) is not pd.DataFrame or type(signal.index) is not pd.DatetimeIndex:
        raise RuntimeError("trusted signal handler returned an invalid frame")
    if signal.index.tz is not None:
        raise RuntimeError("trusted signal index must be timezone-naive")
    if not signal.index.equals(reference.index) or not signal.columns.equals(reference.columns):
        raise RuntimeError("trusted signal must match the selected price panel")
    try:
        numeric = signal.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("trusted signal contains non-numeric values") from exc
    if np.isinf(numeric).any():
        raise RuntimeError("trusted signal contains infinite values")
    return signal
