"""QuantConnect Cloud result import and optional automation helpers.

The primary path imports ``Download Results`` JSON from the Cloud web IDE
and needs no API credentials or lean CLI. REST, CLI, and Object Store upload
helpers are optional automation paths and raise CloudUnavailableError with
actionable guidance when their paid-tier prerequisites are unavailable.
"""
