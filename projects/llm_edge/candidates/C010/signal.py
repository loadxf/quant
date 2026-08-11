"""C010: 63-day volatility of the daily range fraction."""

SIGNAL_KIND = "expression"
ORIGIN = "G2"
HOLDOUT_END = "2030-01-01"
EXPR = ("roll_std", "rng", 63)
PERTURBATIONS = ("EXPR",)
