"""Upload normalized data files to the QuantConnect Cloud Object Store.

Primary route: `lean cloud object-store set KEY PATH` (the verified cloud
upload command — plain `lean object-store set` only opens a local folder).
Fallback: REST POST /api/v2/object/set (needs QC_ORGANIZATION_ID).

Free-tier budget (verified): 50 MB / 1,000 files per organization; keep
individual objects under 50 MB.
"""

from __future__ import annotations

import os
from pathlib import Path

from quantlab.errors import CloudUnavailableError
from quantlab.qc import runner
from quantlab.qc.api import QCClient

ENV_ORG = "QC_ORGANIZATION_ID"
DEFAULT_PREFIX = "quantlab"


def default_key(symbol: str) -> str:
    return f"{DEFAULT_PREFIX}/{symbol.lower()}.csv"


def upload(path: Path, key: str) -> str:
    size_mb = path.stat().st_size / 1e6
    if size_mb > 45:
        raise CloudUnavailableError(
            f"{path.name} is {size_mb:.0f} MB — keep Object Store files under "
            "~45 MB (QC recommends <50 MB per object; free tier totals 50 MB)."
        )
    try:
        runner.object_store_upload(key, path)
        return key
    except CloudUnavailableError:
        organization = os.environ.get(ENV_ORG, "").strip()
        if not organization:
            raise
        QCClient().object_store_set(organization, key, path.read_bytes())
        return key
