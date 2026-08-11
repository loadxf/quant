"""C011: gap volatility minus monthly return."""

SIGNAL_KIND = "expression_minus_return"
ORIGIN = "G2"
HOLDOUT_END = "2030-01-01"
EXPR = ("roll_std", "gap", 63)
RETURN_WINDOW = 21
PERTURBATIONS = ("EXPR", "RETURN_WINDOW")
