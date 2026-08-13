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
src/qlir/                          data-integrity package (tested)
  store.py      immutable raw files + sha256 manifest (identity survives
                deletion; atomic installs)
  manifest.py   hash-chained append-only acquisition ledger (JSONL)
  loader.py     schema-aware trades/tbbo/mbp-1 loading (BBO preserved,
                signed flow restricted to action='T')
  mapping.py    two-step symbology composition + roll validation
  windows.py    half-open event windows (canonical; notebook mirrors)
scripts/databento_cost_matrix.py   metadata-ONLY cost matrix (P1/P2/P3)
scripts/timing_smoke_stats.py      local stats on the QC event export
qc/qlir_timing_smoke.py            paste into a QC Research notebook
data/q_lir/raw/<dataset>/<schema>/<symbol>/<date>.dbn.zst   (immutable)
data/q_lir/derived/<version>/*.parquet                      (regenerable)
data/q_lir/manifests/acquisition.jsonl
data/q_lir/manifests/files.sha256
```

`data/` is gitignored. Raw identities are immutable even across file
deletion (the hash manifest is the record); derived Parquet may be
regenerated, never silently amended.

## Symbology contract (round 4)

Databento resolves CONTINUOUS symbols to **instrument_id only**. The
dated raw contract requires a SECOND resolution step:

```
step 1: stype_in=continuous     -> stype_out=instrument_id
step 2: stype_in=instrument_id  -> stype_out=raw_symbol
```

`qlir.mapping.parse_two_step` composes both; losing the raw-contract
mapping fails closed.

## Acquisition ledger (`manifests/acquisition.jsonl`)

Hash-chained JSONL — one line per batch request:

```json
{"prev_hash": "…", "record_hash": "…", "record": {
  "dataset": "GLBX.MDP3",
  "schema": "trades",
  "requested_symbols": ["ES.v.0", "NQ.v.0"],
  "stype_in": "continuous",
  "stype_out": "instrument_id",
  "resolved_contracts": {"ES.v.0": [{"instrument_id": 4916, "raw_symbol": "ESH2"}]},
  "start_utc": "2022-01-01T00:00:00Z",
  "end_utc": "2023-01-01T00:00:00Z",
  "request_cost_usd": 0.0,
  "record_count": 0,
  "billable_size_bytes": 0,
  "client_version": "",
  "file_hashes": "manifests/files.sha256",
  "dataset_conditions": {},
  "derivation_code_commit": "",
  "split": "development | validation"
}}
```

Appends are O_APPEND single-line writes under an exclusive lock; any
edit, reorder, or deletion of a prior line breaks the chain and reads
fail closed. The **locked period is date-derived**: any range touching
2025-01-01+ is refused regardless of the split label, and labels must
match the date-derived classification.

## Rules of engagement

- `metadata.*` and `symbology.resolve` calls only until a purchase is
  authorized. **Never** `timeseries.get_range` or `batch.submit_job`.
- `DATABENTO_API_KEY` is checked for existence only — never printed,
  logged, serialized, or committed.
- Once authorized: one manifest-controlled **batch** request (charged
  once, redownloadable), never exploratory streams.
- 2025–2026 data are the locked test set: the ledger refuses them by
  DATE until the validation protocol is frozen.
