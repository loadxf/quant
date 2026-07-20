"""QuantConnect Cloud integration (REST API v2 + lean CLI cloud commands).

Everything here degrades gracefully: without credentials or the lean CLI
this package raises CloudUnavailableError with an actionable message —
the prop-firm simulator and reporting run from trade logs regardless.
"""
