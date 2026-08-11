"""C015: 63-day volatility of daily range fraction, long high."""

SIGNAL_KIND = "range_volatility"
ORIGIN = "G2"
HOLDOUT_END = "2030-01-01"
WINDOW = 63
HOLD = 5
PERTURBATIONS = ("WINDOW", "HOLD")
