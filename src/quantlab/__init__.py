"""quantlab: empirical harness for the LLM-novelty trading-edge experiment.

All backtests route through backtest.run_backtest, which writes every evaluation
to the append-only trials ledger (candidates/trials_ledger.csv). The Deflated
Sharpe Ratio of any final claim is computed against the FULL ledger, so no
evaluation escapes multiple-testing accounting.
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
