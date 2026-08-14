"""The ONE quarantined Databento calibration request (round 8, item 4).

PREPARED, NOT EXECUTED. Default invocation is a DRY RUN that prints the
exact frozen request and exits. Executing the billable batch requires
ALL of:

    DATABENTO_API_KEY in the environment
    --authorized-by "<name>"          (the human who approved the spend)
    --i-understand-this-is-billable
    --max-cost-usd <ceiling>          (abort if the estimate exceeds it)

Purpose (Sol, round 8): validate the REAL server artifacts — response
envelopes, batch manifest, DBN metadata, symbol/range coverage, and the
derived receipt — against everything the fixtures encoded. The
observations are PERMANENTLY EXCLUDED from research:

  - data lands under data/q_lir/calibration/ (research loaders never
    read this root);
  - the receipt goes to the calibration ledger, not the research ledger;
  - dataset_conditions carries an explicit exclusion marker.

One batch job (charged once, redownloadable) — never timeseries
streaming. The request is deliberately tiny: five development-period ES
sessions in 2021, before the March roll, trades schema only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qlir.spec import AcquisitionSpec  # noqa: E402

# ---- the frozen calibration request (do not widen) -----------------------
CALIBRATION_SPEC = AcquisitionSpec(
    dataset="GLBX.MDP3",
    schema="trades",
    symbols=("ES.v.0",),
    start_utc=dt.datetime(2021, 3, 1, tzinfo=dt.UTC),
    end_utc=dt.datetime(2021, 3, 6, tzinfo=dt.UTC),  # exclusive; Mon-Fri sessions
)
CALIBRATION_ROOT = PROJECT_ROOT / "data" / "q_lir" / "calibration"
CALIBRATION_LEDGER = CALIBRATION_ROOT / "manifests" / "acquisition.jsonl"
EXCLUSION_MARKER = "calibration-excluded-from-research"


def describe() -> dict:
    return {
        "dataset": CALIBRATION_SPEC.dataset,
        "schema": CALIBRATION_SPEC.schema,
        "symbols": list(CALIBRATION_SPEC.symbols),
        "stype_in": CALIBRATION_SPEC.stype_in,
        "start": CALIBRATION_SPEC.start_utc.isoformat(),
        "end": CALIBRATION_SPEC.end_utc.isoformat(),
        "delivery": "batch.submit_job (charged once, redownloadable)",
        "quarantine_root": str(CALIBRATION_ROOT),
        "ledger": str(CALIBRATION_LEDGER),
        "exclusion": EXCLUSION_MARKER,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-by", default="", help="Human who approved the spend.")
    parser.add_argument("--i-understand-this-is-billable", action="store_true", dest="billable_ack")
    parser.add_argument("--max-cost-usd", type=float, default=0.0)
    args = parser.parse_args(argv)

    print("QUARANTINED CALIBRATION REQUEST (frozen):")
    print(json.dumps(describe(), indent=2))

    if not (args.authorized_by and args.billable_ack and args.max_cost_usd > 0):
        print(
            "\nDRY RUN — nothing was requested. Executing requires "
            "--authorized-by, --i-understand-this-is-billable, and "
            "--max-cost-usd, plus DATABENTO_API_KEY."
        )
        return 0
    if not os.environ.get("DATABENTO_API_KEY"):
        print("BLOCKED: DATABENTO_API_KEY is not set.")
        return 2

    import databento as db
    from qlir.acquire import build_verified_receipt, compose_contract_map
    from qlir.manifest import append_acquisition
    from qlir.store import RawStore

    client = db.Historical()
    spec = CALIBRATION_SPEC
    kwargs = dict(
        dataset=spec.dataset,
        symbols=list(spec.symbols),
        schema=spec.schema,
        start=spec.start_utc,
        end=spec.end_utc,
        stype_in=spec.stype_in,
    )
    estimate = float(client.metadata.get_cost(**kwargs))
    print(f"metadata.get_cost estimate: ${estimate:,.2f} (ceiling ${args.max_cost_usd:,.2f})")
    if estimate > args.max_cost_usd:
        print("ABORT: estimate exceeds the authorized ceiling; nothing was requested.")
        return 3

    # --- two-step symbology, strict envelopes -------------------------
    step_one = client.symbology.resolve(
        dataset=spec.dataset,
        symbols=list(spec.symbols),
        stype_in="continuous",
        stype_out="instrument_id",
        start_date=spec.start_date.isoformat(),
        end_date=spec.end_date_exclusive.isoformat(),
    )
    ids = sorted(
        {
            str(interval["s"])
            for intervals in step_one.get("result", {}).values()
            for interval in intervals
        }
    )
    step_two = client.symbology.resolve(
        dataset=spec.dataset,
        symbols=ids,
        stype_in="instrument_id",
        stype_out="raw_symbol",
        start_date=spec.start_date.isoformat(),
        end_date=spec.end_date_exclusive.isoformat(),
    )
    contract_map = compose_contract_map(spec, step_one, step_two)
    print("symbology composed:", sorted(contract_map.symbols()))

    # --- ONE batch job (never streaming) ------------------------------
    job = client.batch.submit_job(
        **kwargs, encoding="dbn", compression="zstd", split_duration="day"
    )
    job_id = job["id"] if isinstance(job, dict) else str(job)
    print(
        f"batch job submitted: {job_id} — poll batch.list_jobs until done, then rerun "
        "download via batch.list_files/download (redownloadable; no second charge)."
    )
    conditions = client.metadata.get_dataset_condition(
        dataset=spec.dataset,
        start_date=spec.start_date.isoformat(),
        end_date=(spec.end_date_exclusive - dt.timedelta(days=1)).isoformat(),  # inclusive
    )
    store = RawStore(CALIBRATION_ROOT)
    files_dir_note = store.raw_dir
    print(
        f"\nWhen the job completes: download every listed file, store via RawStore "
        f"under {files_dir_note}, then build the receipt with build_verified_receipt "
        f"(server_manifest = batch.list_files sizes/hashes) and append to "
        f"{CALIBRATION_LEDGER} with dataset_conditions "
        f"{{'purpose': '{EXCLUSION_MARKER}', ...}}. build_verified_receipt and "
        "append_acquisition are imported above and are the ONLY sanctioned path."
    )
    # Persist the exact request + responses beside the future data.
    audit_dir = CALIBRATION_ROOT / "manifests"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "calibration_request_audit.json").write_text(
        json.dumps(
            {
                "request": {**{k: str(v) for k, v in kwargs.items()}},
                "estimate_usd": estimate,
                "authorized_by": args.authorized_by,
                "job_id": job_id,
                "step_one_response": step_one,
                "step_two_response": step_two,
                "dataset_conditions": conditions,
                "exclusion": EXCLUSION_MARKER,
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"audit written: {audit_dir / 'calibration_request_audit.json'}")
    _ = build_verified_receipt, append_acquisition  # bound at download time
    return 0


if __name__ == "__main__":
    sys.exit(main())
