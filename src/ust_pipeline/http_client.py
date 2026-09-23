from __future__ import annotations

import logging
import random
import ssl
import time
from collections.abc import Callable

import httpx
import truststore


LOG = logging.getLogger(__name__)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class TreasuryHttpClient:
    """Synchronous HTTP client with bounded exponential retry and Retry-After."""

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 30,
        max_retries: int = 4,
        backoff_base_seconds: float = 0.5,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        ca_bundle: str | None = None,
        allowed_hosts: set[str] | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.sleeper = sleeper
        verify: ssl.SSLContext | str = ca_bundle or truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        def check_scope(request: httpx.Request) -> None:
            if allowed_hosts and (request.url.scheme != 'https' or request.url.host not in allowed_hosts):
                raise ValueError('HTTP redirect/request left the configured official source scope')
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "*/*"},
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            transport=transport,
            verify=verify,
            event_hooks={'request': [check_scope]},
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "TreasuryHttpClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get(
        self,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.get(url, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt >= self.max_retries:
                    raise
                self._sleep(attempt, None)
                continue
            if response.status_code not in RETRYABLE_STATUS:
                if response.status_code == 304:
                    return response
                response.raise_for_status()
                return response
            if attempt >= self.max_retries:
                response.raise_for_status()
            self._sleep(attempt, response.headers.get("Retry-After"))
        raise AssertionError("retry loop exhausted")

    def _sleep(self, attempt: int, retry_after: str | None) -> None:
        try:
            delay = float(retry_after) if retry_after else None
        except ValueError:
            delay = None
        if delay is None:
            delay = self.backoff_base_seconds * (2**attempt) + random.uniform(0, 0.1)
        LOG.warning("retrying Treasury request", extra={"status": "RETRY", "delay": delay})
        self.sleeper(delay)
