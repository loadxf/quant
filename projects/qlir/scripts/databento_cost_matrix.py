"""Databento GLBX.MDP3 cost matrix for the Q-LIR data decision — METADATA ONLY.

Prices the three candidate packages (P1 flow discovery, P2 TBBO
executable approximation, P3 definitive MBP-1) per calendar year
2021-2024 using only free endpoints:

    metadata.get_cost, metadata.get_record_count,
    metadata.get_billable_size, metadata.get_dataset_range,
    metadata.get_dataset_condition, symbology.resolve

It deliberately contains NO call to timeseries.get_range or
batch.submit_job — duplicate streams can be charged repeatedly; the
eventual purchase will be one manifest-controlled batch request.

Auth: reads DATABENTO_API_KEY from the environment (existence checked,
value never printed/logged/serialized). Refuses to run without it.

Usage:
    python projects/qlir/scripts/databento_cost_matrix.py
Output:
    projects/qlir/output/databento_cost_matrix.json  (+ a stdout table)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

DATASET = "GLBX.MDP3"
STYPE_IN = "continuous"
STYPE_OUT = "raw_symbol"

# Package -> list of (symbols, schema) legs. Sol/Fable round 2, section 5.2.
PACKAGES: dict[str, list[tuple[list[str], str]]] = {
    "P1_flow_discovery": [
        (["ES.v.0", "NQ.v.0"], "trades"),
        (["ES.v.0", "NQ.v.0"], "bbo-1s"),
        (["RTY.v.0", "YM.v.0"], "trades"),
    ],
    "P2_tbbo_executable": [
        (["ES.v.0", "NQ.v.0"], "tbbo"),
        (["RTY.v.0", "YM.v.0"], "trades"),
    ],
    "P3_definitive_mbp1": [
        (["ES.v.0", "NQ.v.0"], "mbp-1"),
        (["RTY.v.0", "YM.v.0"], "trades"),
    ],
}

# 2025+ is the locked test period: deliberately NOT priced or acquired
# until validation decisions are frozen.
YEARS: list[tuple[str, str, str]] = [
    ("2021", "2021-01-01", "2022-01-01"),
    ("2022", "2022-01-01", "2023-01-01"),
    ("2023", "2023-01-01", "2024-01-01"),
    ("2024", "2024-01-01", "2025-01-01"),
]

OUTPUT = Path(__file__).resolve().parent.parent / "output" / "databento_cost_matrix.json"


def main() -> int:
    if not os.environ.get("DATABENTO_API_KEY"):
        print(
            "BLOCKED: DATABENTO_API_KEY is not set in the environment.\n"
            "Set it (never commit it) and re-run. This script makes only\n"
            "free metadata/symbology calls — no time-series data is billed."
        )
        return 2
    try:
        import databento as db
    except ImportError:
        print(
            "BLOCKED: the databento client is not installed.\n"
            "Install with: pip install databento  (then re-run)"
        )
        return 2

    client = db.Historical()  # reads DATABENTO_API_KEY from the environment
    results: dict[str, Any] = {
        "dataset": DATASET,
        "stype_in": STYPE_IN,
        "client_version": getattr(db, "__version__", "unknown"),
        "dataset_range": None,
        "dataset_condition_summary": None,
        "symbology": {},
        "packages": {},
        "notes": "metadata-only; no timeseries/batch calls; 2025+ locked, unpriced",
    }

    def safe(label: str, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            print(f"  [warn] {label}: {type(exc).__name__}: {exc}")
            return {"error": f"{type(exc).__name__}: {exc}"}

    print(f"dataset range for {DATASET}:")
    rng = safe("get_dataset_range", client.metadata.get_dataset_range, dataset=DATASET)
    results["dataset_range"] = rng if isinstance(rng, dict) else str(rng)
    print(f"  {results['dataset_range']}")

    cond = safe(
        "get_dataset_condition",
        client.metadata.get_dataset_condition,
        dataset=DATASET,
        start_date="2021-01-01",
        end_date="2024-12-31",
    )
    if isinstance(cond, list):
        # DATED conditions are the audit record — retained in full, with
        # a state-count summary only as a convenience view (round 3 #9).
        results["dataset_condition_by_date"] = cond
        by_state: dict[str, int] = {}
        non_available: list[str] = []
        for day in cond:
            state = day.get("condition", "unknown") if isinstance(day, dict) else "unknown"
            by_state[state] = by_state.get(state, 0) + 1
            if isinstance(day, dict) and state != "available":
                non_available.append(f"{day.get('date', '?')}={state}")
        results["dataset_condition_summary"] = by_state
        print(f"dataset condition by day-state 2021-2024: {by_state}")
        if non_available:
            print(
                f"  non-available dates ({len(non_available)}): {non_available[:20]}"
                + (" …" if len(non_available) > 20 else "")
            )
    else:
        results["dataset_condition_by_date"] = cond
        results["dataset_condition_summary"] = cond

    all_symbols = sorted({s for legs in PACKAGES.values() for syms, _ in legs for s in syms})
    resolution = safe(
        "symbology.resolve",
        client.symbology.resolve,
        dataset=DATASET,
        symbols=all_symbols,
        stype_in=STYPE_IN,
        stype_out=STYPE_OUT,
        start_date="2021-01-01",
        end_date="2024-12-31",
    )
    if isinstance(resolution, dict) and "error" not in resolution:
        mappings = resolution.get("result", resolution)
        counts = {
            sym: (len(mappings.get(sym, [])) if isinstance(mappings, dict) else None)
            for sym in all_symbols
        }
        results["symbology"] = {"mapping_interval_counts": counts}
        unresolved = [s for s, n in counts.items() if not n]
        results["symbology"]["unresolved"] = unresolved
        print(f"symbology: mapping intervals per symbol {counts}; unresolved: {unresolved}")
    else:
        results["symbology"] = {"error": resolution}

    def fmt_money(value: float | None) -> str:
        return "n/a" if value is None else f"{value:,.2f}"

    def fmt_count(value: float | None) -> str:
        return "n/a" if value is None else f"{value:,.0f}"

    def fmt_gb(value: float | None) -> str:
        return "n/a" if value is None else f"{value / 1e9:,.2f}"

    header = f"{'package':<22} {'year':<10} {'cost $':>14} {'records':>18} {'GB':>10}"
    print("\n" + header)
    print("-" * len(header))
    for package, legs in PACKAGES.items():
        pkg: dict[str, Any] = {"legs": [], "by_year": {}, "total": {}}
        total_cost: float | None = 0.0
        total_records: float | None = 0.0
        total_bytes: float | None = 0.0
        for year, start, end in YEARS:
            # A failed leg makes the whole year UNAVAILABLE — never a $0
            # that reads as "free" (round 3 #9).
            y_cost: float | None = 0.0
            y_records: float | None = 0.0
            y_bytes: float | None = 0.0
            for symbols, schema in legs:
                kwargs = dict(
                    dataset=DATASET,
                    symbols=symbols,
                    schema=schema,
                    start=start,
                    end=end,
                    stype_in=STYPE_IN,
                )
                cost = safe(f"{package}/{year}/{schema} cost", client.metadata.get_cost, **kwargs)
                count = safe(
                    f"{package}/{year}/{schema} count", client.metadata.get_record_count, **kwargs
                )
                size = safe(
                    f"{package}/{year}/{schema} size", client.metadata.get_billable_size, **kwargs
                )
                leg_ok = all(isinstance(v, (int, float)) for v in (cost, count, size))
                pkg["legs"].append(
                    {
                        "year": year,
                        "symbols": symbols,
                        "schema": schema,
                        "available": leg_ok,
                        "cost_usd": cost if leg_ok else None,
                        "record_count": count if leg_ok else None,
                        "billable_bytes": size if leg_ok else None,
                        "error": None if leg_ok else {"cost": cost, "count": count, "size": size},
                    }
                )
                if leg_ok and y_cost is not None:
                    assert y_records is not None and y_bytes is not None
                    y_cost += float(cost)
                    y_records += float(count)
                    y_bytes += float(size)
                else:
                    y_cost = y_records = y_bytes = None
            pkg["by_year"][year] = {
                "cost_usd": y_cost,
                "record_count": y_records,
                "billable_bytes": y_bytes,
                "available": y_cost is not None,
            }
            if y_cost is None or total_cost is None:
                total_cost = total_records = total_bytes = None
            else:
                assert total_records is not None and total_bytes is not None
                assert y_records is not None and y_bytes is not None
                total_cost += y_cost
                total_records += y_records
                total_bytes += y_bytes
            print(
                f"{package:<22} {year:<10} {fmt_money(y_cost):>14} "
                f"{fmt_count(y_records):>18} {fmt_gb(y_bytes):>10}"
            )
        pkg["total"] = {
            "cost_usd": total_cost,
            "record_count": total_records,
            "billable_bytes": total_bytes,
            "available": total_cost is not None,
        }
        results["packages"][package] = pkg
        print(
            f"{package:<22} {'2021-2024':<10} {fmt_money(total_cost):>14} "
            f"{fmt_count(total_records):>18} {fmt_gb(total_bytes):>10}\n"
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"written: {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
