"""C008: gap-intraday coherence premium."""

SIGNAL_KIND = "gap_intraday_coherence"
ORIGIN = "G1"
HOLDOUT_END = "2026-01-31"
SMOOTH = 3
MIN_PERIODS = 2
PERTURBATIONS = ("SMOOTH", "MIN_PERIODS")
