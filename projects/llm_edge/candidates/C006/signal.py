"""C006 control: intraday-component five-day reversal."""

SIGNAL_KIND = "intraday_reversal"
ORIGIN = "G4"
HOLDOUT_END = "2030-01-01"
REVERSAL_WINDOW = 5
MIN_PERIODS = 3
PERTURBATIONS = ("REVERSAL_WINDOW", "MIN_PERIODS")
