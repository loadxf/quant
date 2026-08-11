"""B003 baseline: spike-entry five-day reversal held ten days."""

SIGNAL_KIND = "spike_reversal"
ORIGIN = "baseline"
EPISODE_Z = 2.0
RETURN_WINDOW = 5
VOL_WINDOW = 63
HOLD = 10
MIN_NAMES = 4
QUANTILE = 0.5
PERTURBATIONS = (
    "EPISODE_Z",
    "RETURN_WINDOW",
    "VOL_WINDOW",
    "HOLD",
    "MIN_NAMES",
    "QUANTILE",
)
