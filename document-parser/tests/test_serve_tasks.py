"""Docling Serve's task API: submit, wait, fetch (#349).

The client takes the conversion's `httpx.AsyncClient`, so the tests hand it
a mock and script its answers. `asyncio.sleep` is patched: the startup
backoff and the pause between polls must not slow the suite down.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from infra import serve_tasks
from infra.serve_tasks import ServeTaskError

BASE = "http://serve:5001"
HEADERS = {"X-Api-Key": "k"}


def _response(status_code: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = f"stub {status_code}"
    response.json.return_value = payload or {}
    if status_code >= 400:
        response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                str(status_code), request=MagicMock(), response=response
            )
        )
    else:
        response.raise_for_status = MagicMock()
    return response


def _client(*, post=(), get=()) -> AsyncMock:
    client = AsyncMock()
    client.post = AsyncMock(side_effect=list(post))
    client.get = AsyncMock(side_effect=list(get))
    return client


async def _submit(client: AsyncMock) -> str:
    return await serve_tasks.submit(
        client,
        BASE,
        headers=HEADERS,
        filename="a.pdf",
        content_type="application/pdf",
        file_bytes=b"%PDF",
        form_data={"do_ocr": "true"},
    )


class TestSubmit:
    async def test_queues_the_upload_and_returns_the_task_id(self):
        client = _client(post=[_response(200, {"task_id": "t-1", "task_status": "pending"})])

        assert await _submit(client) == "t-1"

        call = client.post.await_args
        assert call.args[0] == f"{BASE}/v1/convert/file/async"
        assert call.kwargs["data"] == {"do_ocr": "true"}
        assert call.kwargs["files"] == {"files": ("a.pdf", b"%PDF", "application/pdf")}
        assert call.kwargs["headers"] == HEADERS

    async def test_retries_while_docling_serve_starts(self):
        client = _client(post=[_response(404), _response(404), _response(200, {"task_id": "t-1"})])
        with patch("infra.serve_tasks.asyncio.sleep", new=AsyncMock()) as sleep:
            assert await _submit(client) == "t-1"

        assert [c.args[0] for c in sleep.await_args_list] == [2.0, 4.0]

    async def test_gives_up_after_five_404s(self):
        client = _client(post=[_response(404)] * 5)
        with (
            patch("infra.serve_tasks.asyncio.sleep", new=AsyncMock()) as sleep,
            pytest.raises(httpx.HTTPStatusError),
        ):
            await _submit(client)

        assert client.post.await_count == 5
        assert sleep.await_count == 4

    async def test_does_not_retry_another_error(self):
        client = _client(post=[_response(500)])
        with (
            patch("infra.serve_tasks.asyncio.sleep", new=AsyncMock()) as sleep,
            pytest.raises(httpx.HTTPStatusError),
        ):
            await _submit(client)

        sleep.assert_not_awaited()


class TestWaitForCompletion:
    async def test_polls_until_the_task_succeeds(self):
        client = _client(
            get=[
                _response(200, {"task_status": "pending", "task_position": 2}),
                _response(200, {"task_status": "started"}),
                _response(200, {"task_status": "success"}),
            ]
        )
        with patch("infra.serve_tasks.asyncio.sleep", new=AsyncMock()) as pause:
            await serve_tasks.wait_for_completion(client, BASE, "t-1", headers=HEADERS)

        assert client.get.await_count == 3
        call = client.get.await_args
        assert call.args[0] == f"{BASE}/v1/status/poll/t-1"
        assert call.kwargs["params"] == {"wait": 5.0}
        assert pause.await_count == 2

    async def test_fails_with_the_reason_docling_serve_gives(self):
        client = _client(
            get=[_response(200, {"task_status": "failure", "error_message": "Out of memory"})]
        )

        with pytest.raises(ServeTaskError, match="could not convert the document: Out of memory"):
            await serve_tasks.wait_for_completion(client, BASE, "t-1", headers=HEADERS)

    async def test_fails_when_docling_serve_lost_the_task(self):
        client = _client(get=[_response(404)])

        with pytest.raises(ServeTaskError, match="lost task t-1"):
            await serve_tasks.wait_for_completion(client, BASE, "t-1", headers=HEADERS)


class TestFetchResult:
    async def test_returns_the_conversion_response(self):
        client = _client(get=[_response(200, {"document": {"md_content": "# A"}})])

        data = await serve_tasks.fetch_result(client, BASE, "t-1", headers=HEADERS)

        assert data == {"document": {"md_content": "# A"}}
        assert client.get.await_args.args[0] == f"{BASE}/v1/result/t-1"

    async def test_retries_once_when_the_connection_breaks(self):
        client = _client(
            get=[httpx.ReadError("reset"), _response(200, {"document": {"md_content": "# A"}})]
        )

        data = await serve_tasks.fetch_result(client, BASE, "t-1", headers=HEADERS)

        assert data["document"]["md_content"] == "# A"
        assert client.get.await_count == 2
