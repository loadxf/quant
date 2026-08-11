"""B002 baseline: ungated one-day reversal held five days."""

SIGNAL_KIND = "plain_reversal"
ORIGIN = "baseline"
RETURN_WINDOW = 1
HOLD = 5
PERTURBATIONS = ("RETURN_WINDOW", "HOLD")
