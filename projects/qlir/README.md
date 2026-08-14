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
scripts/build_macro_calendar.py    rebuild frozen release calendar from sources
scripts/timing_smoke_stats.py      local stats on the QC event export
qc/qlir_timing_smoke.py            paste into a QC Research notebook
qc/qlir_gate2_free_template.ipynb   compact free-tier end-to-end QC template
qc/qlir_gate2_free_paste.py         one-cell free-tier QC template
qc/qlir_macro_exclusion_audit.py   no-returns QC exclusion audit cell
qc/qlir_export_locked.py            deterministic post-exclusion QC export cell
qc/qlir_gate2_analysis.py           free-tier in-notebook frozen analysis cell
calendars/macro_events_v2.csv      frozen dated release calendar (complete v2)
data/q_lir/raw/<dataset>/<schema>/<symbol>/<date>.dbn.zst   (immutable)
data/q_lir/derived/<version>/*.parquet                      (regenerable)
data/q_lir/manifests/acquisition.jsonl
data/q_lir/manifests/files.sha256
```

`data/` is gitignored. Raw identities are immutable even across file
deletion (the hash manifest is the record); derived Parquet may be
regenerated, never silently amended.

## Free-tier QuantConnect notebook template

`qc/qlir_gate2_free_template.ipynb` is the compact, output-free notebook to
reuse for the complete Gate II workflow. It contains setup, timezone probing,
2021-2024 extraction, full-cash-session filtering, integrity checks, the
embedded macro calendar, symmetric exclusions, and the frozen analysis. Failed
download experiments and duplicated recovery cells are intentionally absent.

For the simplest browser-only workflow, open `qc/qlir_gate2_free_paste.py`,
copy the entire file, paste it into one fresh QuantConnect Research code cell,
and run that cell. Never paste `scripts/build_qc_free_template.py` into
QuantConnect; the builder is local repository tooling and uses `__file__`,
which a notebook cell does not define.
The generated notebook is tested to remain below QC's observed 64,000-character
limit. Rebuild it after changing a component with:

```text
python projects/qlir/scripts/build_qc_free_template.py
```

## Symbology contract (round 4)

Databento resolves CONTINUOUS symbols to **instrument_id only**. The
dated raw contract requires a SECOND resolution step:

```
step 1: stype_in=continuous     -> stype_out=instrument_id
step 2: stype_in=instrument_id  -> stype_out=raw_symbol
```

`qlir.mapping.ContractMap.compose_many` (spec-validated via
`qlir.acquire.compose_contract_map`) composes both interval-valued
responses date-aware; losing the raw-contract mapping fails closed.

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
  "files": [{"relative_path": "raw/GLBX.MDP3/trades/ES.v.0/2022-03-01.dbn.zst",
             "sha256": "…", "size_bytes": 123, "record_count": 456}],
  "dataset_conditions": {},
  "derivation_code_commit": "",
  "split": "development | validation"
}}
```

Appends are O_APPEND single-line writes under an exclusive lock; a
sibling ANCHOR file (`acquisition.jsonl.anchor`, count + terminal hash,
updated in the same locked transaction) makes tail truncation and
whole-file deletion detectable; records are REVALIDATED on every read
(supported stype pairs only — the invalid continuous→raw_symbol pairing
can never be attested — and `resolved_contracts` must round-trip the
typed ContractMap structure). Stated exactly: the pair is tamper-EVIDENT
unless BOTH files are rewritten consistently; against a fully local
adversary, mirror the anchor off-host (operational step). The **locked
period is date-derived**: any range touching 2025-01-01+ is refused
regardless of the split label, and labels must match the date-derived
classification.

## Acquisition pipeline (`qlir.acquire`)

```
spec  = AcquisitionSpec(dataset, schema, symbols, start_utc, end_utc)
step_one = symbology.resolve(continuous -> instrument_id)
step_two = symbology.resolve(instrument_id -> raw_symbol)   # ALSO interval-valued
contract_map = compose_contract_map(spec, step_one, step_two)  # envelopes bound to spec
frame = load_acquired_file(path, spec, contract_map)  # DBN metadata + per-record binding
files = attest_files(data_root, [(relpath, n_records), ...])  # frozen hashes NOW
append_acquisition(ledger, build_acquisition_record(spec=spec, contract_map=...,
                   files=files, ...), data_root=data_root)    # disk-verified receipt
```

ONE spec binds every boundary: the response envelopes, the DBN metadata
(dataset/schema/stypes/symbols/interval — an XNAS file can never pass a
GLBX spec), per-record raw AND continuous-symbol identity, and the
receipt (symbol sets equal, date coverage complete, per-file hashes
verified on disk before the append).

Raw identity is a function of (instrument_id, event_date) — some
publishers remap ids daily. The Gate II stats script excludes release
windows from a DATED, versioned macro-event calendar
(`calendars/macro_events_v2.csv`). V2 contains 1,482 source rows and
1,156 unique timestamps for the frozen 2021-2024 taxonomy. Coincident
release rows remain in the source artifact; the mask deduplicates only
`(date, time_ct)` and applies the same inclusive ±10-minute rule to both
instruments and every boundary class. Source definitions and pinned URLs
are recorded in `calendars/macro_events_v2_sources.md`.

Before any effect calculation in QuantConnect, paste and run
`qc/macro_events_v2_embedded.py` as a notebook cell. This compressed Python
representation works on free accounts and requires neither the Object Store
nor a Research-node restart. Then paste and run
`qc/qlir_macro_exclusion_audit.py`. The audit verifies the embedded calendar
checksum and reads only `date`,
`boundary_ct`, `instrument`, and `boundary_class`; it prints the before,
excluded, and retained counts without touching return, price, volume, or
volatility columns.

## Rules of engagement

- `metadata.*` and `symbology.resolve` calls only until a purchase is
  authorized. **Never** `timeseries.get_range` or `batch.submit_job`.
- `DATABENTO_API_KEY` is checked for existence only — never printed,
  logged, serialized, or committed.
- Once authorized: one manifest-controlled **batch** request (charged
  once, redownloadable), never exploratory streams.
- 2025–2026 data are the locked test set: the ledger refuses them by
  DATE until the validation protocol is frozen.
