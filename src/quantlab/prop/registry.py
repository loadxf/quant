"""Load firm presets (package data) or user-supplied firm YAML files."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml
from pydantic import ValidationError

from quantlab.errors import ConfigError
from quantlab.prop.config import FirmConfig

_PACKAGE = "quantlab.prop.firms"


def list_firms() -> list[str]:
    names = []
    for entry in resources.files(_PACKAGE).iterdir():
        if entry.name.endswith(".yaml"):
            names.append(entry.name.removesuffix(".yaml"))
    return sorted(names)


def load_firm(name_or_path: str | Path) -> FirmConfig:
    """Load a preset by name (`topstep_50k`) or any firm YAML by path."""
    path = Path(name_or_path)
    if path.suffix in (".yaml", ".yml") and path.exists():
        raw_text = path.read_text()
    else:
        resource = resources.files(_PACKAGE) / f"{name_or_path}.yaml"
        if not resource.is_file():
            raise ConfigError(
                f"Unknown firm {name_or_path!r}. Presets: {', '.join(list_firms())} — "
                "or pass a path to your own firm YAML."
            )
        raw_text = resource.read_text()

    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ConfigError(f"Firm config {name_or_path} must be a YAML mapping")
    try:
        return FirmConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid firm config {name_or_path}: {exc}") from exc
