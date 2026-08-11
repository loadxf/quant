"""Column mapping for arbitrary user trade-log CSVs.

A `ColumnMapping` names which CSV column feeds each canonical `Trade` field,
plus parsing options (timezone, datetime format, side-value vocabulary).
Mappings load from YAML, from `--map field=Column` CLI pairs, or are
auto-detected from headers via a synonym table.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from quantlab.errors import MappingError

CANONICAL_FIELDS = (
    "entry_time",
    "exit_time",
    "symbol",
    "side",
    "quantity",
    "pnl",
    "entry_price",
    "exit_price",
    "fees",
    "mae",
    "mfe",
)

# Header synonyms, matched case-insensitively after stripping non-alphanumerics.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "entry_time": ("entrytime", "entrydatetime", "opentime", "opened", "entrydate", "buytime"),
    "exit_time": (
        "exittime",
        "exitdatetime",
        "closetime",
        "closed",
        "exitdate",
        "selltime",
        "time",
        "datetime",
        "date",
    ),
    "symbol": ("symbol", "instrument", "ticker", "contract", "market", "product"),
    "side": ("side", "direction", "type", "buysell", "longshort", "position"),
    "quantity": ("quantity", "qty", "size", "contracts", "lots", "shares", "volume"),
    "pnl": (
        "pnl",
        "netpnl",
        "netpl",
        "profit",
        "profitloss",
        "pl",
        "netprofit",
        "realizedpnl",
        "gainloss",
        "result",
    ),
    "entry_price": ("entryprice", "openprice", "buyprice", "pricein", "avgentryprice"),
    "exit_price": ("exitprice", "closeprice", "sellprice", "priceout", "avgexitprice"),
    "fees": ("fees", "commission", "commissions", "cost", "costs"),
    "mae": ("mae", "maxadverseexcursion"),
    "mfe": ("mfe", "maxfavorableexcursion", "maxrunup", "runup"),
}

DEFAULT_LONG_VALUES = ("long", "buy", "b", "l", "bot", "bought", "1")
DEFAULT_SHORT_VALUES = ("short", "sell", "s", "sellshort", "sld", "sold", "-1")


class SideMapping(BaseModel):
    # extra="forbid": a typo'd key must fail loudly, not silently change
    # parsing semantics (e.g. `long_vals:` being ignored).
    model_config = ConfigDict(extra="forbid", strict=True)

    column: str
    long_values: list[str] = Field(default_factory=lambda: list(DEFAULT_LONG_VALUES))
    short_values: list[str] = Field(default_factory=lambda: list(DEFAULT_SHORT_VALUES))


class ColumnMapping(BaseModel):
    """Maps CSV columns to canonical Trade fields.

    Only `exit_time` and `pnl` are strictly required; everything else has a
    sensible default (entry_time falls back to exit_time, quantity to 1, ...).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    entry_time: str | None = None
    exit_time: str | None = None
    symbol: str | None = None
    side: SideMapping | None = None
    quantity: str | None = None
    pnl: str | None = None
    entry_price: str | None = None
    exit_price: str | None = None
    fees: str | None = None
    mae: str | None = None
    mfe: str | None = None

    # None = not declared: naive timestamps read as UTC, and the ingest
    # report says so. An explicit value (YAML or --map tz=...) is trusted
    # silently — the distinction is what makes the assumed-UTC warning
    # possible without nagging users who declared their zone.
    tz: str | None = None
    datetime_format: str | None = None  # strptime format; None = pandas inference
    default_symbol: str = "UNKNOWN"

    @classmethod
    def from_yaml(cls, path: Path | str) -> ColumnMapping:
        try:
            raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise MappingError(f"Could not read mapping file {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise MappingError(f"Mapping file {path} must contain a YAML mapping")
        if isinstance(raw.get("side"), str):
            raw["side"] = {"column": raw["side"]}
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise MappingError(f"Invalid mapping file {path}: {_format_validation(exc)}") from None

    @staticmethod
    def parse_pairs(pairs: list[str]) -> dict[str, object]:
        """`field=Column` CLI pairs -> a partial mapping dict (shared by
        from_pairs and the ingest overlay, so both agree on syntax)."""
        data: dict[str, object] = {}
        for pair in pairs:
            if "=" not in pair:
                raise MappingError(f"--map expects field=Column, got {pair!r}")
            field_name, column = pair.split("=", 1)
            field_name = field_name.strip()
            if field_name == "side":
                data["side"] = {"column": column.strip()}
            elif field_name in CANONICAL_FIELDS or field_name in ("tz", "datetime_format"):
                data[field_name] = column.strip()
            else:
                raise MappingError(
                    f"Unknown field {field_name!r}; expected one of {CANONICAL_FIELDS}"
                )
        return data

    @classmethod
    def from_pairs(cls, pairs: list[str], base: ColumnMapping | None = None) -> ColumnMapping:
        """Build/extend a mapping from CLI `field=Column` pairs."""
        data = base.model_dump() if base else {}
        data.update(cls.parse_pairs(pairs))
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise MappingError(f"Invalid --map pairs: {_format_validation(exc)}") from None

    def validate_against(self, headers: list[str]) -> None:
        missing = []
        for field_name in CANONICAL_FIELDS:
            value = getattr(self, field_name)
            column = value.column if isinstance(value, SideMapping) else value
            if column is not None and column not in headers:
                missing.append(f"{field_name} -> {column!r}")
        if missing:
            raise MappingError(
                f"Mapped columns not present in CSV: {', '.join(missing)}. "
                f"Available headers: {headers}"
            )
        missing_required = [f for f in ("exit_time", "pnl") if getattr(self, f) is None]
        if missing_required:
            raise MappingError(
                f"Mapping does not define {' or '.join(missing_required)} — "
                "`exit_time` and `pnl` columns are required"
            )


def _format_validation(exc: ValidationError) -> str:
    unknown = [
        ".".join(str(p) for p in err["loc"])
        for err in exc.errors()
        if err["type"] == "extra_forbidden"
    ]
    if unknown:
        return (
            f"unknown key(s) {unknown} — valid fields: "
            f"{(*CANONICAL_FIELDS, 'tz', 'datetime_format', 'default_symbol')}"
        )
    return str(exc)


def _normalize(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def autodetect_mapping(
    headers: list[str],
    skip_fields: frozenset[str] | set[str] = frozenset(),
    exclude_headers: frozenset[str] | set[str] = frozenset(),
    require: bool = True,
) -> ColumnMapping:
    """Best-effort mapping from CSV headers using the synonym table.

    Per field, synonyms are scanned twice: first skipping headers that
    contain '%' (a percent column must never shadow the absolute-money
    column it sits next to), then allowing them. When several distinct
    headers normalize to the same synonym and no other synonym resolves
    the field, that is genuine ambiguity — refuse loudly rather than
    pick one by column order and silently load wrong numbers.

    `skip_fields`/`exclude_headers` support --map overlays: fields the
    user bound explicitly are not re-detected, and their headers are
    off-limits to other fields.
    """
    normalized: dict[str, list[str]] = {}
    for header in headers:
        normalized.setdefault(_normalize(header), []).append(header)
    taken: set[str] = set(exclude_headers)
    found: dict[str, str] = {}
    for field_name, synonyms in _SYNONYMS.items():
        if field_name in skip_fields:
            continue
        ambiguous: list[str] = []
        for allow_pct in (False, True):
            for syn in synonyms:
                pool = [
                    h
                    for h in normalized.get(syn, ())
                    if h not in taken and (allow_pct or "%" not in h)
                ]
                if len(pool) == 1:
                    found[field_name] = pool[0]
                    taken.add(pool[0])
                    break
                if len(pool) > 1 and not ambiguous:
                    ambiguous = pool
            if field_name in found:
                break
        if field_name not in found and ambiguous:
            raise MappingError(
                f"Ambiguous columns for {field_name!r}: {ambiguous} all match the same "
                f"synonym — disambiguate with --map {field_name}=<column>"
            )

    if require and ("exit_time" not in found or "pnl" not in found):
        raise MappingError(
            "Could not auto-detect required columns (exit_time, pnl) from headers "
            f"{headers}. Provide a mapping YAML (--mapping) or --map pairs."
        )

    data: dict[str, object] = {k: v for k, v in found.items() if k != "side"}
    if "side" in found:
        data["side"] = {"column": found["side"]}
    return ColumnMapping.model_validate(data)
