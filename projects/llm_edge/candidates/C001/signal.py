"""C001: reversal conditioned on volume-shock recession speed."""

SIGNAL_KIND = "volume_recession_reversal"
ORIGIN = "G3"
HOLDOUT_END = "2030-01-01"
SPIKE_Z = 1.5
POST_DAYS = 5
WINDOW = 252
MIN_SPIKES = 3
VOL_WINDOW = 63
REVERSAL_WINDOW = 5
PERTURBATIONS = (
    "SPIKE_Z",
    "POST_DAYS",
    "WINDOW",
    "MIN_SPIKES",
    "VOL_WINDOW",
    "REVERSAL_WINDOW",
)
