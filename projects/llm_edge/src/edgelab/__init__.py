"""edgelab: empirical harness for the LLM-novelty trading-edge experiment.

All backtests route through backtest.run_backtest, which writes every evaluation
to a concurrency-safe, git-audited trials ledger (candidates/trials_ledger.csv).
Retrospective deviation D5 records why the historical mixed-window ledger cannot
currently supply a calibrated Deflated Sharpe Ratio; promotion fails closed.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
CANDIDATES_DIR = REPO_ROOT / "candidates"
LEDGER_PATH = CANDIDATES_DIR / "trials_ledger.csv"
REGISTRY_PATH = CANDIDATES_DIR / "registry.json"

# Pre-registered split boundaries (protocol.md section 4). Do not modify.
TRAIN_START = "2005-01-01"
TRAIN_END = "2018-12-31"
VALIDATION_START = "2019-01-01"
VALIDATION_END = "2023-12-31"
HOLDOUT_START = "2024-01-01"
POST_CUTOFF_START = "2026-02-01"  # provably outside model training data
# The data actually shown to the model during G1 generation.  This must never
# drift with wall-clock time: later observations are evaluation/audit data, not
# part of the historical hypothesis provenance.
G1_GENERATION_END = "2026-07-17"
