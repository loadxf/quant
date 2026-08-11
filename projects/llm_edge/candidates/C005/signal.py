"""C005 control: low-volume-conditioned reversal."""

SIGNAL_KIND = "volume_weighted_reversal"
ORIGIN = "G4"
HOLDOUT_END = "2030-01-01"
RETURN_WINDOW = 5
VOL_WINDOW = 63
PERTURBATIONS = ("RETURN_WINDOW", "VOL_WINDOW")
