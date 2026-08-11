"""C014: sustained-volume premium, held 21 days."""

SIGNAL_KIND = "smoothed_volume_z"
ORIGIN = "G1"
HOLDOUT_END = "2026-01-31"
SMOOTH = 5
MIN_PERIODS = 3
VOL_WINDOW = 63
HOLD = 21
PERTURBATIONS = ("SMOOTH", "MIN_PERIODS", "VOL_WINDOW", "HOLD")
