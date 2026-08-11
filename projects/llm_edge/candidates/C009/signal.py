"""C009: sector-ETF next-day member reversal."""

SIGNAL_KIND = "sector_etf_reversal"
ORIGIN = "G1"
HOLDOUT_END = "2026-01-31"
RETURN_WINDOW = 1
PERTURBATIONS = ("RETURN_WINDOW",)
