# loadx-quant

QuantPad-style **backtesting + prop-firm challenge simulation**, built on
QuantConnect Cloud, that runs on data **you** provide.

Two independent halves:

- **Pure-Python core** — prop-firm Monte Carlo simulator, strategy metrics,
  A–F "Verdict" scorecard, overfit checks, self-contained HTML reports.
  Works anywhere from a trade-log CSV. No QuantConnect account, no Docker.
- **QuantConnect Cloud integration** — push LEAN strategies, run cloud
  backtests (Docker-free), pull closed trades (with MAE/MFE) straight into
  the simulator. Needs a QC account.

```
pip install -e .          # core
pip install -e .[qc]      # + the lean CLI for QuantConnect Cloud
```

## Flow 1 — I have a trade log

Any broker/platform CSV export works; columns are auto-detected (or mapped
via `--mapping`/`--map`):

```bash
quant ingest trades my_trades.csv -o trades.parquet
quant metrics  trades.parquet --equity 50000
quant verdict  trades.parquet                      # A-F scorecard + overfit flags
quant prop firms list                              # 18 verified firm presets
quant prop evaluate trades.parquet --firm topstep_50k    # deterministic replay
quant prop simulate trades.parquet --firm topstep_50k    # Monte Carlo
quant report   trades.parquet --firm topstep_50k -o report.html   # everything
```

`quant prop simulate` answers the questions that matter before buying a
challenge: pass probability (with CI), expected fees, expected payout value,
**net EV per attempt and per retry campaign**, VaR/CVaR, risk of ruin,
days-to-pass and days-to-first-payout distributions.

Include MAE/MFE columns in your export if you can — without them,
intraday-sensitive rules (Apex-style real-time trailing, daily loss limits)
are checked at trade-close fidelity and results are **optimistic** (every
report states which fidelity was used).

No trade log at all? Explore risk geometry synthetically:

```bash
quant prop geometry --firm topstep_50k --win-rate 0.5 --rr 1.0 --trades-per-day 3
```

## Flow 2 — I have market data (or want QC's)

Cloud backtests run on QuantConnect's servers — **no Docker anywhere**.
Set credentials once (create the token at quantconnect.com → account):

```bash
export QC_USER_ID=123456 QC_API_TOKEN=your-token
```

Using QC's built-in data (ES/NQ futures, full US equities, FX — free for
cloud backtesting):

```bash
quant cloud backtest cloud/strategies/sma_cross_futures --push
quant cloud results --project-id <id> --backtest-id <id> -o trades.parquet
quant report trades.parquet --firm apex40_50k_eod -o report.html
```

Using your own bars via the QC Object Store:

```bash
quant ingest ohlcv my_bars.csv --symbol demo --tz America/Chicago --upload
# then point cloud/strategies/custom_data_demo at the printed key and:
quant cloud backtest cloud/strategies/custom_data_demo --push
```

QC cost notes (verified July 2026): the free tier allows 200 backtests/day
(single node, 20s launch delay) and 50 MB of Object Store that free orgs
cannot expand; a realistic paid entry is ~$24/mo ($10 Researcher seat +
$14 B2-8 node). The lean CLI itself requires membership in a paid-tier org.

## Firm presets

18 presets with rule parameters **verified against official firm sources on
2026-07-19** (citations in each YAML): `topstep_{50k,100k,150k}`,
`apex40_{25k,50k,100k,150k}_{intraday,eod}` (the 4.0 product line sold since
2026-03-01), `tpt_{25k,50k,75k,100k,150k}`, `ftmo_{2step,1step}_100k`.
Custom firms: copy any preset YAML and pass its path to `--firm`.

Encoded mechanics include: EOD vs intraday high-water ratchets with
always-real-time breach tests and threshold locks; pause-not-fail daily
loss lockouts; FTMO's midnight-re-anchoring daily loss and refundable fee;
consistency rules that raise targets or gate payouts; Apex 4.0's 30-day
expiry, payout cap ladders, and 6-payout lifetime account closure.

**Prop firms change rules constantly** (Apex replaced its entire product
line in March 2026; Topstep, TPT, and FTMO all changed 2024–2026). Check
the `verified_as_of` date and re-verify before relying on EV numbers.

## How the simulation works

Trading **days** are resampled with a stationary block bootstrap
(preserving streaks/volatility clustering; IID modes available), then each
day replays its trades step-by-step against the rule set, vectorized
across paths. A scalar evaluator implements identical semantics and a
golden-equivalence test forces exact agreement. 10k paths × 250 days runs
in ~1 s.

Validation anchors (zero-EV synthetic strategies):
- static floor/target hit gambler's-ruin `D/(T+D)` exactly;
- an uncapped trailing drawdown hits `exp(-target/drawdown)` — and is
  **geometry-independent** (Brownian scale invariance). Sensitivity to
  win-rate/RR geometry appears only through rules with absolute day-scale
  parameters (daily loss limits, consistency, time limits) — a refinement
  of the popular claim that low-RR/high-win-rate always passes trailing
  challenges more often.

## Development

```bash
pip install -e .[dev]
ruff check . && ruff format --check . && mypy && pytest
```

CI runs the same on Python 3.11/3.12 — no Docker, no network.
