"""C016: skew of absolute cross-sectional volume-z rank, ETFs."""

SIGNAL_KIND = "volume_rank_skew_expression"
ORIGIN = "G2"
HOLDOUT_END = "2030-01-01"
EXPR = ("roll_skew", ("abs_", ("cs_rank", "volz")), 63)
HOLD = 5
QUANTILE = 0.2
MIN_NAMES = 30
UNIVERSE = "etfs"
VOL_WINDOW = 63
PERTURBATIONS = ("EXPR", "VOL_WINDOW", "HOLD", "QUANTILE", "MIN_NAMES")
