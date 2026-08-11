"""C004 control: plain five-day short-term reversal."""

SIGNAL_KIND = "plain_reversal"
ORIGIN = "G4"
HOLDOUT_END = "2030-01-01"
RETURN_WINDOW = 5
PERTURBATIONS = ("RETURN_WINDOW",)
