"""Exception hierarchy for quantlab."""


class QuantLabError(Exception):
    """Base class for all quantlab errors."""


class MappingError(QuantLabError):
    """A trade-log or OHLCV column mapping could not be resolved or applied."""


class ConfigError(QuantLabError):
    """A firm config / preset is invalid."""


class CloudUnavailableError(QuantLabError):
    """An optional QuantConnect API, CLI, or Object Store operation is unavailable.

    Browser-downloaded results and everything that consumes a trade log still work:
    `quant prop simulate trades.parquet --firm ...`
    """
