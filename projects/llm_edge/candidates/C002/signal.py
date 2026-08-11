"""C002: turn-of-month phase-gated one-day reversal, held five days."""

SIGNAL_KIND = "turn_of_month_reversal"
ORIGIN = "G3"
HOLDOUT_END = "2030-01-01"
HOLD = 5
FIRST_DAYS = 3
LAST_DAYS = 2
RETURN_WINDOW = 1
PERTURBATIONS = ("FIRST_DAYS", "LAST_DAYS", "RETURN_WINDOW", "HOLD")
