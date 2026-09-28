"""Docling Serve's task API: submit a conversion, wait for it, fetch its result (#349).

Docling Serve queues conversions behind its workers. Its synchronous route
(`POST /v1/convert/file`) gives up after `DOCLING_SERVE_MAX_SYNC_WAIT` (120 s
by default) with a 504 while the task keeps running. The asynchronous routes
have no such limit: the task is submitted, its status followed with a
long-poll, then its result fetched.

Each call takes the `httpx.AsyncClient` of the conversion, so one connection
serves the whole exchange.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_API_PREFIX = "/v1"

# Docling Serve registers the `/v1/convert/*` route decorators at FastAPI
# import time but returns 404 from the actual handler until its lifespan
# startup has wired up the converter pipeline (~30s after first launch).
# Neither `/version` nor `/openapi.json` nor an empty upload (which validates
# the form schema and answers 422) detects this — only a real multipart
# upload triggers it. We retry the upload up to 5 times with exponential
# backoff to absorb that startup window. The retry is scoped tight (only 404
# from the submit route) so a real "route gone" regression still surfaces
# once the backoff is exhausted.
_STARTUP_RETRY_ATTEMPTS = 5
_STARTUP_RETRY_BASE_DELAY = 2.0  # 2, 4, 8, 16, 32s — total ~62s max

# Docling Serve holds a status request open up to this long, and answers as
# soon as the task ends: few requests, and the result is fetched right away,
# well within the 300 s Docling Serve keeps a single-use result.
_POLL_WAIT_SECONDS = 5.0
# Pause between two status requests, for a Docling Serve that answers without
# waiting: it must not be polled in a tight loop.
_POLL_PAUSE_SECONDS = 1.0


class ServeTaskError(RuntimeError):
    """A Docling Serve task failed, or Docling Serve lost track of it."""


async def submit(
    client: httpx.AsyncClient,
    base_url: str,
    *,
    headers: dict[str, str],
    filename: str,
    content_type: str,
    file_bytes: bytes,
    form_data: dict[str, str | list[str]],
) -> str:
    """Queue a conversion in Docling Serve and return its task id."""
    url = f"{base_url}{_API_PREFIX}/convert/file/async"
    files = {"files": (filename, file_bytes, content_type)}
    response = await _post_with_startup_retry(
        client, url, headers=headers, files=files, form_data=form_data
    )
    if response.status_code >= 400:
        logger.error(
            "Docling Serve error %d: %s (form_data=%s)",
            response.status_code,
            response.text[:500],
            form_data,
        )
    response.raise_for_status()
    task_id = str(response.json()["task_id"])
    logger.info("Docling Serve task submitted: %s", task_id)
    return task_id


async def wait_for_completion(
    client: httpx.AsyncClient,
    base_url: str,
    task_id: str,
    *,
    headers: dict[str, str],
) -> None:
    """Return once the task succeeded. Raise if it failed or was lost."""
    url = f"{base_url}{_API_PREFIX}/status/poll/{task_id}"
    while True:
        response = await client.get(url, params={"wait": _POLL_WAIT_SECONDS}, headers=headers)
        if response.status_code == 404:
            raise ServeTaskError(
                f"Docling Serve lost task {task_id}: it may have restarted during the conversion"
            )
        response.raise_for_status()
        status = response.json()
        state = status.get("task_status")
        if state == "success":
            logger.info("Docling Serve task succeeded: %s", task_id)
            return
        if state == "failure":
            reason = status.get("error_message") or "no reason given"
            raise ServeTaskError(f"Docling Serve could not convert the document: {reason}")
        await asyncio.sleep(_POLL_PAUSE_SECONDS)


async def fetch_result(
    client: httpx.AsyncClient,
    base_url: str,
    task_id: str,
    *,
    headers: dict[str, str],
) -> dict:
    """The task's `ConvertDocumentResponse`, as the synchronous route returned it.

    Docling Serve serves a result once by default, then drops it: one retry
    covers a connection that broke before the answer came back.
    """
    url = f"{base_url}{_API_PREFIX}/result/{task_id}"
    try:
        response = await client.get(url, headers=headers)
    except httpx.TransportError:
        logger.warning("Fetching the result of Docling Serve task %s failed, retrying", task_id)
        response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


async def _post_with_startup_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    files: dict,
    form_data: dict[str, str | list[str]],
) -> httpx.Response:
    """POST the multipart upload, retrying on 404 to absorb Docling Serve's startup."""
    for attempt in range(1, _STARTUP_RETRY_ATTEMPTS + 1):
        response = await client.post(url, files=files, data=form_data, headers=headers)
        if response.status_code != 404 or attempt == _STARTUP_RETRY_ATTEMPTS:
            if response.status_code == 404:
                logger.error(
                    "Docling Serve still returning 404 after %d attempts at %s — giving up. "
                    "Either the route really is gone or startup took longer than ~62s.",
                    attempt,
                    url,
                )
            return response
        delay = _STARTUP_RETRY_BASE_DELAY * (2 ** (attempt - 1))
        logger.warning(
            "Docling Serve returned 404 for %s (attempt %d/%d) — "
            "likely startup race, retrying in %.0fs",
            url,
            attempt,
            _STARTUP_RETRY_ATTEMPTS,
            delay,
        )
        await asyncio.sleep(delay)
    raise AssertionError("unreachable: the last attempt always returns")
