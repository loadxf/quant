"""Thin QuantConnect REST API v2 client.

Auth (verified against QC docs, July 2026): HTTP Basic where username is
the user id and password is sha256("{api_token}:{unix_timestamp}"), with
the same timestamp sent in a `Timestamp` header. Credentials come from
the QC_USER_ID / QC_API_TOKEN environment variables (the lean CLI itself
does NOT read env vars — see runner.py).

Endpoints used:
- POST /api/v2/backtests/read          (statistics + totalPerformance.closedTrades)
- POST /api/v2/backtests/chart/read    (equity curve; returns a loading
  state while QC assembles the chart — poll until ready)
- POST /api/v2/object/set              (Object Store upload, multipart)
"""

from __future__ import annotations

import base64
import hashlib
import os
import time
from typing import Any

import requests

from quantlab.errors import CloudUnavailableError, QuantLabError

API_BASE = "https://www.quantconnect.com/api/v2"
ENV_USER = "QC_USER_ID"
ENV_TOKEN = "QC_API_TOKEN"


def credentials_from_env() -> tuple[str, str]:
    user_id = os.environ.get(ENV_USER, "").strip()
    token = os.environ.get(ENV_TOKEN, "").strip()
    if not user_id or not token:
        raise CloudUnavailableError(
            f"QuantConnect credentials missing: set {ENV_USER} and {ENV_TOKEN} "
            "(from quantconnect.com account settings). The prop-firm simulator "
            "works without them: `quant prop simulate trades.parquet --firm ...`"
        )
    return user_id, token


class QCClient:
    def __init__(
        self,
        user_id: str | None = None,
        api_token: str | None = None,
        base_url: str = API_BASE,
        session: requests.Session | None = None,
    ) -> None:
        if user_id is None or api_token is None:
            user_id, api_token = credentials_from_env()
        self.user_id = user_id
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        timestamp = str(int(time.time()))
        hashed = hashlib.sha256(f"{self.api_token}:{timestamp}".encode()).hexdigest()
        basic = base64.b64encode(f"{self.user_id}:{hashed}".encode()).decode()
        return {"Authorization": f"Basic {basic}", "Timestamp": timestamp}

    def _post(
        self,
        endpoint: str,
        data: dict | None = None,
        files: dict | None = None,
        retries: int = 2,
    ) -> dict:
        """POST with clean errors: transient 429/5xx and connection blips
        retry briefly (uploads too — QC's object/set is idempotent per
        key), then every failure surfaces as a QuantLabError the CLI
        renders as one line, never a raw requests traceback."""
        last_error = ""
        for attempt in range(retries + 1):
            try:
                response = self.session.post(
                    f"{self.base_url}/{endpoint.lstrip('/')}",
                    headers=self._headers(),
                    data=data,
                    files=files,
                    timeout=60,
                )
            except requests.RequestException as exc:
                last_error = f"network error ({exc.__class__.__name__}: {exc})"
                if attempt < retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                break
            if response.status_code == 401:
                raise CloudUnavailableError(
                    f"QuantConnect rejected the credentials (401) — check {ENV_USER}/{ENV_TOKEN}."
                )
            if response.status_code == 429 or response.status_code >= 500:
                last_error = f"HTTP {response.status_code}: {response.text[:200].strip()}"
                if attempt < retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                break
            if response.status_code >= 400:
                raise QuantLabError(
                    f"QuantConnect API error on {endpoint} "
                    f"(HTTP {response.status_code}): {response.text[:300].strip()}"
                )
            try:
                payload = response.json()
            except ValueError:
                # Maintenance/CDN pages return 200 with HTML bodies.
                raise QuantLabError(
                    f"QuantConnect returned a non-JSON response on {endpoint} "
                    f"(HTTP {response.status_code}): {response.text[:200].strip()!r}"
                ) from None
            if not payload.get("success", False):
                raise QuantLabError(
                    f"QuantConnect API error on {endpoint}: {payload.get('errors', payload)}"
                )
            return payload
        raise QuantLabError(
            f"QuantConnect API unreachable on {endpoint} after {retries + 1} attempts — "
            f"last: {last_error}"
        )

    def read_backtest(self, project_id: int, backtest_id: str) -> dict[str, Any]:
        payload = self._post(
            "backtests/read", data={"projectId": project_id, "backtestId": backtest_id}
        )
        return payload["backtest"]

    def read_backtest_chart(
        self,
        project_id: int,
        backtest_id: str,
        name: str = "Strategy Equity",
        count: int = 5000,
        start: int = 0,
        end: int | None = None,
        poll_seconds: float = 2.0,
        max_polls: int = 30,
    ) -> dict[str, Any]:
        data = {
            "projectId": project_id,
            "backtestId": backtest_id,
            "name": name,
            "count": count,
            "start": start,
            "end": end if end is not None else int(time.time()),
        }
        for _ in range(max_polls):
            payload = self._post("backtests/chart/read", data=data)
            if "chart" in payload:
                return payload["chart"]
            time.sleep(poll_seconds)  # documented LoadingResponse state
        raise QuantLabError(f"Chart {name!r} still loading after {max_polls} polls")

    def object_store_set(self, organization_id: str, key: str, data: bytes) -> None:
        self._post(
            "object/set",
            data={"organizationId": organization_id, "key": key},
            files={"objectData": data},
        )
