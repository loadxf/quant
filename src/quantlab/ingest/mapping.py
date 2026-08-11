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

    tz: str = "UTC"  # timezone applied to naive timestamps
    datetime_format: str | None = None  # strptime format; None = pandas inference
    default_symbol: str = "UNKNOWN"

    @classmethod
    def from_yaml(cls, path: Path | str) -> ColumnMapping:
        try:
            raw = yaml.safe_load(Path(path).read_text())
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise MappingError(f"Could not read mapping file {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise MappingError(f"Mapping file {path} must contain a YAML mapping")
        if isinstance(raw.get("side"), str):
            raw["side"] = {"column": raw["side"]}
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise MappingError(f"Invalid mapping file {path}: {exc}") from exc

    @classmethod
    def from_pairs(cls, pairs: list[str], base: ColumnMapping | None = None) -> ColumnMapping:
        """Build/extend a mapping from CLI `field=Column` pairs."""
        data = base.model_dump() if base else {}
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
        return cls.model_validate(data)

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
        if self.exit_time is None or self.pnl is None:
            raise MappingError("Mapping must define at least `exit_time` and `pnl` columns")


def _normalize(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def autodetect_mapping(headers: list[str]) -> ColumnMapping:
    """Best-effort mapping from CSV headers using the synonym table.

    First exact-synonym match wins per field; a header is only assigned once.
    Raises MappingError when the required fields can't be found.
    """
    normalized = {_normalize(h): h for h in headers}
    taken: set[str] = set()
    found: dict[str, str] = {}
    for field_name, synonyms in _SYNONYMS.items():
        for syn in synonyms:
            header = normalized.get(syn)
            if header is not None and header not in taken:
                found[field_name] = header
                taken.add(header)
                break

    if "exit_time" not in found or "pnl" not in found:
        raise MappingError(
            "Could not auto-detect required columns (exit_time, pnl) from headers "
            f"{headers}. Provide a mapping YAML (--mapping) or --map pairs."
        )

    data: dict[str, object] = {k: v for k, v in found.items() if k != "side"}
    if "side" in found:
        data["side"] = {"column": found["side"]}
    return ColumnMapping.model_validate(data)
