"""Two-step symbology composition with DATE-AWARE raw identity (round 5).

Databento returns EVERY resolution — including step two,
instrument_id → raw_symbol — as interval-valued lists:

    step one:  {"ES.v.0": [{"d0": "2022-01-01", "d1": "2022-03-14", "s": "4916"}, …]}
    step two:  {"4916":   [{"d0": "2022-01-01", "d1": "2022-03-14", "s": "ESH2"}, …]}

(d0 inclusive, d1 exclusive). Some publishers remap instrument ids
DAILY, so the date dimension of step two is material: raw identity is a
function of (instrument_id, event_date), never of the id alone. The
round-4 flat `dict[id, str]` shape does not exist in the API and
serialized whole interval lists into the symbol field — the exact
corruption this module now makes unrepresentable.

`ContractMap.compose` intersects both interval sets, requires COMPLETE
and UNAMBIGUOUS date coverage of every step-one interval by step-two
intervals, and resolves `raw_for(instrument_id, event_date)`.
`flat_map_for_date` produces a validated single-date map for per-date
raw files. `to_record`/`from_record` give the typed structure the
acquisition ledger validates.

A mapping CHANGE instant is midnight UTC of each composed interval's d0
after the first — id changes AND raw remaps both count. Per the frozen
protocol: any feature/confirmation/outcome window crossing a change is
invalid, and roll-transition SESSIONS are a prespecified stratum.
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
    instrument_id: int  # PRIMARY identity (step one)
    raw_symbol: str  # dated contract for THIS date range (step two)
    start_date: dt.date  # inclusive
    end_date: dt.date  # exclusive


def _parse_intervals(owner: str, intervals: object) -> list[tuple[dt.date, dt.date, str]]:
    if not isinstance(intervals, list) or not intervals:
        raise QlirError(f"mapping intervals for {owner} must be a non-empty list")
    parsed: list[tuple[dt.date, dt.date, str]] = []
    for item in intervals:
        if not isinstance(item, dict):
            raise QlirError(f"malformed mapping interval for {owner}: {item!r}")
        try:
            start = dt.date.fromisoformat(str(item["d0"]))
            end = dt.date.fromisoformat(str(item["d1"]))
            out_symbol = str(item["s"])
        except (KeyError, ValueError) as exc:
            raise QlirError(f"malformed mapping interval for {owner}: {item!r}") from exc
        if end <= start:
            raise QlirError(f"mapping interval for {owner} has d1 <= d0: {item!r}")
        if not out_symbol or out_symbol.startswith("[") or out_symbol.startswith("{"):
            raise QlirError(
                f"mapping output for {owner} looks like a serialized structure, "
                f"not a symbol: {out_symbol[:40]!r}"
            )
        parsed.append((start, end, out_symbol))
    parsed.sort(key=lambda interval: interval[0])
    for previous, current in itertools.pairwise(parsed):
        if current[0] < previous[1]:
            raise QlirError(
                f"overlapping mapping intervals for {owner}: {previous[2]} and {current[2]}"
            )
    return parsed


class ContractMap:
    """Composed, validated (instrument_id, date) → raw_symbol mapping."""

    def __init__(self, intervals: list[MappingInterval]) -> None:
        if not intervals:
            raise QlirError("ContractMap needs at least one interval")
        by_id: dict[int, list[MappingInterval]] = {}
        for interval in intervals:
            by_id.setdefault(interval.instrument_id, []).append(interval)
        for instrument_id, group in by_id.items():
            group.sort(key=lambda i: i.start_date)
            for previous, current in itertools.pairwise(group):
                if current.start_date < previous.end_date and (
                    current.raw_symbol != previous.raw_symbol or current.symbol != previous.symbol
                ):
                    raise QlirError(
                        f"ambiguous raw mapping for instrument_id {instrument_id}: "
                        f"{previous.raw_symbol} and {current.raw_symbol} overlap in time"
                    )
        self.intervals = sorted(intervals, key=lambda i: (i.symbol, i.start_date))

    # -- composition ------------------------------------------------------
    @classmethod
    def compose(
        cls,
        symbol: str,
        continuous_to_id: list[dict],
        id_to_raw: dict[str, list[dict]] | dict[int, list[dict]],
    ) -> ContractMap:
        """Compose ONE continuous symbol's step-one intervals with the
        interval-valued step-two response. Fails closed on: non-integer
        step-one output (the invalid direct pairing), missing step-two
        entries, coverage gaps, and ambiguity."""
        normalized: dict[str, list[dict]] = {}
        for key, value in id_to_raw.items():
            if not isinstance(value, list):
                raise QlirError(
                    f"step-two mapping for instrument_id {key} must be a LIST of "
                    f"dated intervals (the documented response shape), got "
                    f"{type(value).__name__} — a flat id→str map does not exist "
                    "in the API"
                )
            normalized[str(key)] = value
        composed: list[MappingInterval] = []
        for a_start, a_end, id_str in _parse_intervals(symbol, continuous_to_id):
            try:
                instrument_id = int(id_str)
            except ValueError:
                raise QlirError(
                    f"step-one output for {symbol} is not an instrument id: {id_str!r} "
                    "(continuous resolves to instrument_id; raw symbols need step two)"
                ) from None
            if id_str not in normalized:
                raise QlirError(
                    f"instrument_id {id_str} for {symbol} has no step-two entry — "
                    "refusing to lose the contract mapping"
                )
            raw_intervals = _parse_intervals(f"instrument_id {id_str}", normalized[id_str])
            cursor = a_start
            for b_start, b_end, raw in raw_intervals:
                clip_start = max(a_start, b_start)
                clip_end = min(a_end, b_end)
                if clip_end <= clip_start:
                    continue
                if clip_start > cursor:
                    raise QlirError(
                        f"step-two coverage GAP for instrument_id {id_str} "
                        f"({symbol}): [{cursor} .. {clip_start}) has no raw symbol"
                    )
                composed.append(MappingInterval(symbol, instrument_id, raw, clip_start, clip_end))
                cursor = max(cursor, clip_end)
            if cursor < a_end:
                raise QlirError(
                    f"step-two coverage GAP for instrument_id {id_str} ({symbol}): "
                    f"[{cursor} .. {a_end}) has no raw symbol — the composed mapping "
                    "must cover every step-one date"
                )
        return cls(composed)

    @classmethod
    def compose_many(
        cls,
        step_one_result: dict[str, list[dict]],
        step_two_result: dict[str, list[dict]],
    ) -> ContractMap:
        """Compose every requested continuous symbol against one shared
        step-two response (the exact `result` payloads of the two
        symbology.resolve calls)."""
        if not isinstance(step_one_result, dict) or not step_one_result:
            raise QlirError("step-one result must be a non-empty dict of symbol -> intervals")
        intervals: list[MappingInterval] = []
        for symbol, cont_intervals in step_one_result.items():
            intervals.extend(cls.compose(symbol, cont_intervals, step_two_result).intervals)
        return cls(intervals)

    # -- resolution -------------------------------------------------------
    def raw_for(self, instrument_id: int, event_date: dt.date) -> str:
        """Raw identity by (instrument_id, event_date) — the ONLY valid
        lookup; ids may remap across dates."""
        matches = {
            interval.raw_symbol
            for interval in self.intervals
            if interval.instrument_id == instrument_id
            and interval.start_date <= event_date < interval.end_date
        }
        if not matches:
            raise QlirError(
                f"no raw_symbol for instrument_id {instrument_id} on {event_date} — "
                "outside the composed mapping's coverage"
            )
        if len(matches) > 1:
            raise QlirError(
                f"ambiguous raw_symbol for instrument_id {instrument_id} on "
                f"{event_date}: {sorted(matches)}"
            )
        return next(iter(matches))

    def symbol_for(self, instrument_id: int, event_date: dt.date) -> str:
        """Requested continuous symbol by (instrument_id, event_date) —
        the per-record identity binding for multi-symbol files ('<multi>'
        is not an analyzable identity; round 6, finding 2)."""
        matches = {
            interval.symbol
            for interval in self.intervals
            if interval.instrument_id == instrument_id
            and interval.start_date <= event_date < interval.end_date
        }
        if not matches:
            raise QlirError(
                f"no continuous symbol for instrument_id {instrument_id} on "
                f"{event_date} — outside the composed mapping's coverage"
            )
        if len(matches) > 1:
            raise QlirError(
                f"ambiguous continuous symbol for instrument_id {instrument_id} on "
                f"{event_date}: {sorted(matches)}"
            )
        return next(iter(matches))

    def assert_covers(self, symbol: str, start_date: dt.date, end_date_exclusive: dt.date) -> None:
        """Require gap-free coverage of [start_date, end_date_exclusive)
        for one requested symbol (round 6, finding 1: a receipt must not
        attest a request interval its mapping does not cover)."""
        spans = sorted(
            (interval.start_date, interval.end_date)
            for interval in self.intervals
            if interval.symbol == symbol
        )
        if not spans:
            raise QlirError(f"contract map has no intervals for symbol {symbol!r}")
        cursor = start_date
        for span_start, span_end in spans:
            if span_start > cursor:
                if cursor >= end_date_exclusive:
                    break
                raise QlirError(
                    f"contract map for {symbol!r} has a coverage gap at "
                    f"[{cursor} .. {min(span_start, end_date_exclusive)}) inside the "
                    f"attested range [{start_date} .. {end_date_exclusive})"
                )
            cursor = max(cursor, span_end)
        if cursor < end_date_exclusive:
            raise QlirError(
                f"contract map for {symbol!r} ends {cursor}, short of the attested "
                f"range end {end_date_exclusive}"
            )
        if spans[0][0] > start_date:
            raise QlirError(
                f"contract map for {symbol!r} starts {spans[0][0]}, after the "
                f"attested range start {start_date}"
            )

    def symbols(self) -> set[str]:
        return {interval.symbol for interval in self.intervals}

    def flat_map_for_date(self, event_date: dt.date) -> dict[int, str]:
        """Validated SINGLE-DATE id → raw map (for one per-date raw file)."""
        flat: dict[int, str] = {}
        for interval in self.intervals:
            if interval.start_date <= event_date < interval.end_date:
                existing = flat.get(interval.instrument_id)
                if existing is not None and existing != interval.raw_symbol:
                    raise QlirError(
                        f"ambiguous raw_symbol for instrument_id "
                        f"{interval.instrument_id} on {event_date}"
                    )
                flat[interval.instrument_id] = interval.raw_symbol
        if not flat:
            raise QlirError(f"no instruments active on {event_date} in the composed mapping")
        return flat

    # -- ledger round-trip ------------------------------------------------
    def to_record(self) -> dict[str, list[dict]]:
        """The typed `resolved_contracts` structure the ledger validates."""
        record: dict[str, list[dict]] = {}
        for interval in self.intervals:
            record.setdefault(interval.symbol, []).append(
                {
                    "instrument_id": interval.instrument_id,
                    "raw_symbol": interval.raw_symbol,
                    "d0": interval.start_date.isoformat(),
                    "d1": interval.end_date.isoformat(),
                }
            )
        return record

    @classmethod
    def from_record(cls, record: object) -> ContractMap:
        if not isinstance(record, dict) or not record:
            raise QlirError(
                "resolved_contracts must be a non-empty dict of "
                "symbol -> [{instrument_id, raw_symbol, d0, d1}]"
            )
        intervals: list[MappingInterval] = []
        for symbol, items in record.items():
            if not isinstance(items, list) or not items:
                raise QlirError(f"resolved_contracts[{symbol!r}] must be a non-empty list")
            for item in items:
                if not isinstance(item, dict):
                    raise QlirError(f"resolved_contracts[{symbol!r}] entry is not a dict")
                try:
                    instrument_id = int(item["instrument_id"])
                    raw = str(item["raw_symbol"])
                    start = dt.date.fromisoformat(str(item["d0"]))
                    end = dt.date.fromisoformat(str(item["d1"]))
                except (KeyError, TypeError, ValueError) as exc:
                    raise QlirError(
                        f"resolved_contracts[{symbol!r}] entry malformed: {item!r}"
                    ) from exc
                if end <= start:
                    raise QlirError(f"resolved_contracts[{symbol!r}] has d1 <= d0: {item!r}")
                if not raw or raw.startswith("[") or raw.startswith("{"):
                    raise QlirError(
                        f"resolved_contracts[{symbol!r}] raw_symbol looks like a "
                        f"serialized structure: {raw[:40]!r}"
                    )
                intervals.append(MappingInterval(str(symbol), instrument_id, raw, start, end))
        return cls(intervals)


def change_instants(intervals: list[MappingInterval]) -> list[pd.Timestamp]:
    """Midnight-UTC instants at which any symbol's mapped contract
    changes (id change OR raw remap) — every interval start after that
    symbol's first."""
    instants: set[pd.Timestamp] = set()
    by_symbol: dict[str, list[MappingInterval]] = {}
    for interval in intervals:
        by_symbol.setdefault(interval.symbol, []).append(interval)
    for group in by_symbol.values():
        group.sort(key=lambda i: i.start_date)
        for interval in group[1:]:
            instants.add(pd.Timestamp(interval.start_date, tz="UTC"))
    return sorted(instants)


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
