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
import contextlib
import datetime as dt
import hashlib
import ipaddress
import math
import os
import time
from email.utils import parsedate_to_datetime
from numbers import Integral, Real
from typing import Any
from urllib.parse import urlsplit

import requests

from quantlab.errors import CloudUnavailableError, QuantLabError

API_BASE = "https://www.quantconnect.com/api/v2"
ENV_USER = "QC_USER_ID"
ENV_TOKEN = "QC_API_TOKEN"


def _retry_delay(value: str | None, fallback: float) -> float:
    if value is None:
        return fallback
    try:
        delay = float(value)
        if math.isfinite(delay) and delay >= 0:
            return delay
    except (TypeError, ValueError):
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=dt.UTC)
        return max(0.0, (retry_at - dt.datetime.now(dt.UTC)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return fallback


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
        max_retries: int = 3,
    ) -> None:
        if user_id is None or api_token is None:
            user_id, api_token = credentials_from_env()
        if not str(user_id).strip() or not str(api_token).strip():
            raise CloudUnavailableError("QuantConnect user id and API token must be non-empty")
        if not isinstance(base_url, str):
            raise QuantLabError("QuantConnect API base_url must be a URL string")
        try:
            parsed = urlsplit(base_url)
        except ValueError as exc:
            raise QuantLabError("QuantConnect API base_url is malformed") from exc
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise QuantLabError("QuantConnect API base_url is malformed")
        loopback = parsed.hostname == "localhost"
        with contextlib.suppress(ValueError):
            loopback = loopback or ipaddress.ip_address(parsed.hostname).is_loopback
        if parsed.scheme != "https" and not loopback:
            raise QuantLabError(
                "QuantConnect API base_url must use HTTPS except for loopback test servers"
            )
        if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 0:
            raise QuantLabError("QuantConnect max_retries must be a non-negative integer")
        self.user_id = user_id
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.max_retries = max_retries

    def _headers(self) -> dict[str, str]:
        timestamp = str(int(time.time()))
        hashed = hashlib.sha256(f"{self.api_token}:{timestamp}".encode()).hexdigest()
        basic = base64.b64encode(f"{self.user_id}:{hashed}".encode()).decode()
        return {"Authorization": f"Basic {basic}", "Timestamp": timestamp}

    def _post(self, endpoint: str, data: dict | None = None, files: dict | None = None) -> dict:
        response = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    f"{self.base_url}/{endpoint.lstrip('/')}",
                    headers=self._headers(),
                    data=data,
                    files=files,
                    timeout=60,
                )
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise CloudUnavailableError(
                        f"QuantConnect API request failed on {endpoint}: {exc}"
                    ) from None
                time.sleep(min(2**attempt, 30))
                continue
            if response.status_code not in (429, 500, 502, 503, 504) or attempt >= self.max_retries:
                break
            retry_after = getattr(response, "headers", {}).get("Retry-After")
            delay = _retry_delay(retry_after, float(2**attempt))
            time.sleep(min(max(delay, 0.0), 30.0))
        assert response is not None
        if response.status_code == 401:
            raise CloudUnavailableError(
                f"QuantConnect rejected the credentials (401) — check {ENV_USER}/{ENV_TOKEN}."
            )
        try:
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise CloudUnavailableError(
                f"QuantConnect API returned HTTP {response.status_code} on {endpoint}: {exc}"
            ) from exc
        except ValueError as exc:
            raise QuantLabError(f"QuantConnect API returned invalid JSON on {endpoint}") from exc
        if not isinstance(payload, dict):
            raise QuantLabError(f"QuantConnect API returned a non-object payload on {endpoint}")
        if not payload.get("success", False):
            raise QuantLabError(
                f"QuantConnect API error on {endpoint}: {payload.get('errors', payload)}"
            )
        return payload

    def read_backtest(self, project_id: int, backtest_id: str) -> dict[str, Any]:
        payload = self._post(
            "backtests/read", data={"projectId": project_id, "backtestId": backtest_id}
        )
        backtest = payload.get("backtest")
        if not isinstance(backtest, dict):
            raise QuantLabError("QuantConnect backtests/read response had no backtest object")
        return backtest

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
        if (
            not isinstance(count, Integral)
            or isinstance(count, bool)
            or count <= 0
            or not isinstance(max_polls, Integral)
            or isinstance(max_polls, bool)
            or max_polls <= 0
            or not isinstance(poll_seconds, Real)
            or isinstance(poll_seconds, bool)
            or not math.isfinite(float(poll_seconds))
            or poll_seconds < 0
        ):
            raise QuantLabError("count/max_polls must be positive and poll_seconds non-negative")
        if not isinstance(start, Integral) or isinstance(start, bool) or start < 0:
            raise QuantLabError("chart start must be a non-negative integer timestamp")
        if end is not None and (
            not isinstance(end, Integral) or isinstance(end, bool) or end < start
        ):
            raise QuantLabError("chart end must be an integer timestamp at or after start")
        for _ in range(max_polls):
            payload = self._post("backtests/chart/read", data=data)
            if isinstance(payload.get("chart"), dict):
                return payload["chart"]
            time.sleep(poll_seconds)  # documented LoadingResponse state
        raise QuantLabError(f"Chart {name!r} still loading after {max_polls} polls")

    def object_store_set(self, organization_id: str, key: str, data: bytes) -> None:
        self._post(
            "object/set",
            data={"organizationId": organization_id, "key": key},
            files={"objectData": data},
        )
