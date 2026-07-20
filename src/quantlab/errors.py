"""Exception hierarchy for quantlab."""


class QuantLabError(Exception):
    """Base class for all quantlab errors."""


class MappingError(QuantLabError):
    """A trade-log or OHLCV column mapping could not be resolved or applied."""


class ConfigError(QuantLabError):
    """A firm config / preset is invalid."""


class CloudUnavailableError(QuantLabError):
    """QuantConnect Cloud integration is unavailable (missing CLI or credentials).

    Everything that consumes a trade log still works:
    `quant prop simulate trades.parquet --firm ...`
    """
