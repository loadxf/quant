"""C013: volume-recession-conditioned monthly reversal."""

SIGNAL_KIND = "volume_recession_monthly_reversal"
ORIGIN = "G3"
HOLDOUT_END = "2030-01-01"
SPIKE_Z = 1.5
POST_DAYS = 5
WINDOW = 252
MIN_SPIKES = 3
HOLD = 21
VOL_WINDOW = 63
RETURN_WINDOW = 21
PERTURBATIONS = (
    "SPIKE_Z",
    "POST_DAYS",
    "WINDOW",
    "MIN_SPIKES",
    "VOL_WINDOW",
    "RETURN_WINDOW",
    "HOLD",
)
