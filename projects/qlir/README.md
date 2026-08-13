# Q-LIR — Quarter-Hour Latent Impact Release (research project)

Infrastructure for the Sol/Fable Q-LIR study. Research log:
`docs/sol-fable-edge-lab.md` (append-only). Nothing here is a strategy;
nothing here has evidence behind it yet.

## Gates (frozen 2026-08-13)

- **Gate I** — infrastructure correctness: Topstep rule fixes D1–D5 +
  tests green + det/MC parity + provenance explained.
- **Gate II** — free QC timing smoke test: reproducible quarter-hour
  structure vs five-minute placebos in development/validation. A null
  here does NOT kill the flow-conditioned hypothesis (coarse data, no
  aggressor side).
- **Gate III** — definitive Databento development evidence (see the lab
  log for the full criteria list). 2025+ stays unpurchased until the
  validation decisions are frozen.

## Layout

```
scripts/databento_cost_matrix.py   metadata-ONLY cost matrix (P1/P2/P3)
scripts/timing_smoke_stats.py      local stats on the QC event export
qc/qlir_timing_smoke.py            paste into a QC Research notebook
data/q_lir/raw/<dataset>/<schema>/<symbol>/<date>.dbn.zst   (immutable)
data/q_lir/derived/<version>/*.parquet                      (regenerable)
data/q_lir/manifests/acquisition.json
data/q_lir/manifests/files.sha256
```

`data/` is gitignored. Raw DBN files are immutable once written; derived
Parquet may be regenerated, never silently amended.

## Acquisition manifest (`manifests/acquisition.json`)

One record per batch request:

```json
{
  "dataset": "GLBX.MDP3",
  "schema": "trades",
  "requested_symbols": ["ES.v.0", "NQ.v.0"],
  "stype_in": "continuous",
  "stype_out": "raw_symbol",
  "resolved_contracts": {"ES.v.0": ["ESH1", "..."]},
  "start_utc": "2021-01-01T00:00:00Z",
  "end_utc": "2025-01-01T00:00:00Z",
  "request_cost_usd": 0.0,
  "record_count": 0,
  "billable_size_bytes": 0,
  "client_version": "",
  "file_hashes": "manifests/files.sha256",
  "dataset_conditions": {},
  "derivation_code_commit": "",
  "split": "development | validation | locked_test"
}
```

## Rules of engagement

- `metadata.*` and `symbology.resolve` calls only until a purchase is
  authorized. **Never** `timeseries.get_range` or `batch.submit_job`.
- `DATABENTO_API_KEY` is checked for existence only — never printed,
  logged, serialized, or committed.
- Once authorized: one manifest-controlled **batch** request (charged
  once, redownloadable), never exploratory streams.
- 2025–2026 data are the locked test set: do not acquire until the
  validation protocol is frozen.
