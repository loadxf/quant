"""C007: lag-band reversal over the return from t-8 through t-6."""

SIGNAL_KIND = "lag_band_reversal"
ORIGIN = "G1"
HOLDOUT_END = "2026-01-31"
BAND_LAG = 6
BAND_LEN = 3
PERTURBATIONS = ("BAND_LAG", "BAND_LEN")
