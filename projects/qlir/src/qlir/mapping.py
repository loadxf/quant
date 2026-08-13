"""Continuous-symbol mapping validation (two-step contract, round 4).

Databento's supported symbology matrix resolves CONTINUOUS symbols to
INSTRUMENT_ID only; the dated raw contract requires a SECOND resolution
step (instrument_id -> raw_symbol). `symbology.resolve` returns, per
requested symbol, intervals ``{"d0": start_date, "d1": end_date, "s":
<output symbol>}`` (d0 inclusive, d1 exclusive) — for step one, ``s`` is
the instrument id as a string. A mapping CHANGE instant is midnight UTC
of each interval's d0 after the first. Per the frozen protocol (Sol
round 2 §4.1): any 60-second feature window, 5-second confirmation
window, or 120-second outcome window that crosses a mapping change is
invalid, and roll-transition SESSIONS are a prespecified stratum, never
silently discarded.
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
    instrument_id: int  # PRIMARY identity (step one: continuous -> id)
    raw_symbol: str  # dated contract (step two: id -> raw)
    start_date: dt.date  # inclusive
    end_date: dt.date  # exclusive


def _parse_intervals(symbol: str, intervals: list[dict]) -> list[tuple[dt.date, dt.date, str]]:
    parsed: list[tuple[dt.date, dt.date, str]] = []
    for item in intervals:
        try:
            start = dt.date.fromisoformat(str(item["d0"]))
            end = dt.date.fromisoformat(str(item["d1"]))
            out_symbol = str(item["s"])
        except (KeyError, ValueError) as exc:
            raise QlirError(f"malformed mapping interval for {symbol}: {item!r}") from exc
        if end <= start:
            raise QlirError(f"mapping interval for {symbol} has d1 <= d0: {item!r}")
        parsed.append((start, end, out_symbol))
    parsed.sort(key=lambda interval: interval[0])
    for previous, current in itertools.pairwise(parsed):
        if current[0] < previous[1]:
            raise QlirError(
                f"overlapping mapping intervals for {symbol}: {previous[2]} and {current[2]}"
            )
    return parsed


def parse_two_step(
    symbol: str,
    continuous_to_id: list[dict],
    id_to_raw: dict[str, str] | dict[int, str],
) -> list[MappingInterval]:
    """Compose the two supported resolution steps into dated intervals.

    `continuous_to_id`: symbology.resolve(stype_in=continuous,
    stype_out=instrument_id) intervals for one symbol — ``s`` is the
    instrument id (as a string). `id_to_raw`: the second resolution
    (stype_in=instrument_id, stype_out=raw_symbol), id -> dated contract.
    Missing ids fail closed — a lost raw-contract mapping is the round-4
    failure mode.
    """
    normalized: dict[str, str] = {str(key): str(value) for key, value in id_to_raw.items()}
    result: list[MappingInterval] = []
    for start, end, id_str in _parse_intervals(symbol, continuous_to_id):
        try:
            instrument_id = int(id_str)
        except ValueError:
            raise QlirError(
                f"step-one output for {symbol} is not an instrument id: {id_str!r} "
                "(continuous resolves to instrument_id; raw symbols need step two)"
            ) from None
        raw = normalized.get(id_str)
        if raw is None:
            raise QlirError(
                f"instrument_id {id_str} for {symbol} has no raw_symbol in the "
                "second resolution step — refusing to lose the contract mapping"
            )
        result.append(MappingInterval(symbol, instrument_id, raw, start, end))
    return result


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
