"""Thin HTTP client for the NARA Catalog API v2."""
from __future__ import annotations

from typing import Any

import requests
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .config import DEFAULT_API_BASE_URL, resolve_config

# Kept for back-compat with code that imports API_BASE from .api.
API_BASE = DEFAULT_API_BASE_URL
USER_AGENT = "nara-archive/0.1 (+https://github.com/rammc/nara-archive)"


class NaraApiError(RuntimeError):
    """Any unrecoverable problem talking to the NARA API."""


class NaraUpstreamDown(requests.exceptions.RequestException):
    """API origin is unreachable — CloudFront served HTML or a non-JSON body.

    Symptom seen in the wild: ``200 OK`` with ``content-type: text/html`` and
    ``x-cache: Error from cloudfront`` — the static SPA fallback. Treated as
    retryable so transient origin blips don't kill the run.
    """


def _is_retryable(exc: BaseException) -> bool:
    """Retry on network errors and 5xx — never on 4xx or HTML-fallback responses.

    ``NaraUpstreamDown`` is *not* retried because the symptom (CloudFront's
    origin-fetch failing on the local PoP) tends to persist for minutes or
    longer — usually a geo-specific NARA origin issue. Fail fast instead.
    """
    if isinstance(exc, NaraUpstreamDown):
        return False
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, requests.exceptions.JSONDecodeError):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else 0
        return 500 <= status < 600
    return False


class NaraClient:
    """Minimal client. Caller is responsible for rate-limiting between calls."""

    def __init__(self, api_key: str | None = None, *, base: str | None = None, timeout: float = 30.0):
        cfg = resolve_config()
        key = api_key or cfg.api_key
        base_url = base or cfg.api_base_url
        if not key:
            raise NaraApiError(
                "NARA_API_KEY is not set. Run `nara init`, or export "
                "NARA_API_KEY in your shell, or put it in a project-local .env."
            )
        self._key = key
        self._base = base_url.rstrip("/") + "/"
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {"x-api-key": self._key, "User-Agent": USER_AGENT, "Accept": "application/json"}
        )

    @retry(
        reraise=True,
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=2, min=2, max=32),
        stop=stop_after_attempt(3),
    )
    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._session.get(url, params=params, timeout=self._timeout)
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        if "json" not in ctype:
            head = resp.content[:32].lstrip().lower()
            if head.startswith(b"<!doctype") or head.startswith(b"<html") or "html" in ctype:
                raise NaraUpstreamDown(
                    f"Upstream returned HTML instead of JSON "
                    f"(content-type={ctype!r}, x-cache={resp.headers.get('x-cache')!r}). "
                    f"Likely a NARA origin outage — try again later."
                )
        return resp.json()

    def get_children(self, parent_naid: str, *, limit: int = 300) -> dict[str, Any]:
        """Return the raw JSON for ``GET /records/parentNaId/{naId}``."""
        url = f"{self._base}records/parentNaId/{parent_naid}"
        try:
            return self._get_json(url, params={"limit": limit})
        except NaraUpstreamDown as e:
            raise NaraApiError(
                f"NARA API is currently unreachable while fetching children of "
                f"{parent_naid}: {e}"
            ) from e
        except RetryError as e:
            raise NaraApiError(f"Exhausted retries fetching children of {parent_naid}: {e}") from e
        except requests.exceptions.HTTPError as e:
            raise NaraApiError(
                f"HTTP {e.response.status_code if e.response else '?'} fetching children "
                f"of {parent_naid}: {e}"
            ) from e

    def get_record(self, naid: str) -> dict[str, Any] | None:
        """Return raw JSON for a single record, or ``None`` if not findable.

        Uses the documented ``/records/search?naIds={naid}`` endpoint; there is
        no direct ``/records/{naid}`` route (CloudFront serves the SPA HTML
        fallback for it, which is why early versions of this code mistook a
        bad route for a NARA outage).
        """
        url = f"{self._base}records/search"
        try:
            return self._get_json(url, params={"naId": naid, "limit": 1})
        except NaraUpstreamDown:
            # Treat HTML fallbacks here as "not found" — the lookup is best-effort.
            return None
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise NaraApiError(f"HTTP error fetching record {naid}: {e}") from e
        except RetryError as e:
            raise NaraApiError(f"Exhausted retries fetching record {naid}: {e}") from e

    @retry(
        reraise=True,
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=2, min=2, max=32),
        stop=stop_after_attempt(3),
    )
    def stream_download(self, url: str, dest_tmp, *, chunk: int = 65536) -> int:
        """Stream ``url`` to ``dest_tmp`` (binary file handle). Returns bytes written.

        The caller controls the destination handle and the eventual rename to the
        final path — this keeps retry semantics clean (we re-stream from scratch
        on retry by truncating the handle).
        """
        dest_tmp.seek(0)
        dest_tmp.truncate(0)
        written = 0
        with self._session.get(url, stream=True, timeout=self._timeout) as resp:
            resp.raise_for_status()
            for block in resp.iter_content(chunk_size=chunk):
                if not block:
                    continue
                dest_tmp.write(block)
                written += len(block)
        return written
