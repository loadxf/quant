"""Continuous-symbol mapping validation.

Databento's `symbology.resolve` returns, per requested continuous symbol,
a list of intervals ``{"d0": start_date, "d1": end_date, "s": raw_symbol}``
(d0 inclusive, d1 exclusive). A mapping CHANGE instant is midnight UTC of
each interval's d0 after the first. Per the frozen protocol (Sol round 2
§4.1): any 60-second feature window, 5-second confirmation window, or
120-second outcome window that crosses a mapping change is invalid, and
roll-transition SESSIONS are a prespecified stratum, never silently
discarded.
"""

from __future__ import annotations

import datetime as dt
import itertools
from dataclasses import dataclass

import pandas as pd

from qlir import QlirError


@dataclass(frozen=True)
class MappingInterval:
    symbol: str  # requested continuous symbol (ES.v.0)
    raw_symbol: str  # resolved contract (ESH1)
    start_date: dt.date  # inclusive
    end_date: dt.date  # exclusive


def parse_resolution(symbol: str, intervals: list[dict]) -> list[MappingInterval]:
    """Parse one symbol's entry from a symbology.resolve result."""
    parsed: list[MappingInterval] = []
    for item in intervals:
        try:
            start = dt.date.fromisoformat(str(item["d0"]))
            end = dt.date.fromisoformat(str(item["d1"]))
            raw = str(item["s"])
        except (KeyError, ValueError) as exc:
            raise QlirError(f"malformed mapping interval for {symbol}: {item!r}") from exc
        if end <= start:
            raise QlirError(f"mapping interval for {symbol} has d1 <= d0: {item!r}")
        parsed.append(MappingInterval(symbol, raw, start, end))
    parsed.sort(key=lambda interval: interval.start_date)
    for previous, current in itertools.pairwise(parsed):
        if current.start_date < previous.end_date:
            raise QlirError(
                f"overlapping mapping intervals for {symbol}: "
                f"{previous.raw_symbol} and {current.raw_symbol}"
            )
    return parsed


def change_instants(intervals: list[MappingInterval]) -> list[pd.Timestamp]:
    """Midnight-UTC instants at which the mapped contract changes
    (every interval start after the first)."""
    return [
        pd.Timestamp(interval.start_date, tz="UTC")
        for interval in sorted(intervals, key=lambda i: i.start_date)[1:]
    ]


def window_crosses_mapping(
    window_start: pd.Timestamp, window_end: pd.Timestamp, instants: list[pd.Timestamp]
) -> bool:
    """True when a mapping-change instant falls inside (start, end].

    CONSERVATIVE closed-end convention: a window ending exactly at the
    change instant is treated as crossing (data at the instant already
    belongs to the new contract), so it is invalid. A window starting
    exactly at the instant is entirely post-change and valid.
    """
    if window_end <= window_start:
        raise QlirError("window_end must be after window_start")
    return any(window_start < instant <= window_end for instant in instants)


def roll_transition_sessions(intervals: list[MappingInterval]) -> set[str]:
    """ISO dates of sessions containing a mapping change — the
    prespecified roll-transition stratum (reported, never discarded)."""
    return {instant.date().isoformat() for instant in change_instants(intervals)}
