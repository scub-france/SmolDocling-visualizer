"""Analyses wait for their turn instead of failing inside the engine (#349).

The service never hands an engine more conversions than it runs at once:
one for the in-process converter, the setting for Docling Serve, which
queues the rest itself. The analyses beyond that wait in the service's
semaphore, still PENDING, and start in order of creation.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock, patch

from services.analysis_service import AnalysisService, _engine_capacity


class _Engine:
    """Just enough of a DocumentConverter for the service to size its queue."""

    supports_page_batching = False

    def __init__(self, max_parallel_conversions: int | None) -> None:
        self.max_parallel_conversions = max_parallel_conversions


class TestEngineCapacity:
    def test_caps_the_setting_with_the_engine_capacity(self):
        assert _engine_capacity(_Engine(1), max_concurrent=3) == 1

    def test_keeps_the_setting_when_the_engine_queues_itself(self):
        assert _engine_capacity(_Engine(None), max_concurrent=3) == 3

    def test_keeps_the_setting_when_it_is_the_lower_bound(self):
        assert _engine_capacity(_Engine(8), max_concurrent=3) == 3

    def test_ignores_an_engine_that_does_not_say(self):
        assert _engine_capacity(MagicMock(), max_concurrent=3) == 3


def _service(engine: _Engine, max_concurrent: int = 3) -> AnalysisService:
    return AnalysisService(
        converter=engine,
        analysis_repo=MagicMock(),
        document_repo=MagicMock(),
        max_concurrent=max_concurrent,
    )


class TestQueue:
    async def test_a_local_engine_converts_one_analysis_at_a_time_in_order(self, caplog):
        service = _service(_Engine(1))
        started: list[str] = []
        done = {job: asyncio.Event() for job in ("job-1", "job-2", "job-3")}

        async def inner(job_id, *_args):
            started.append(job_id)
            await done[job_id].wait()

        with (
            caplog.at_level(logging.INFO),
            patch.object(service, "_run_analysis_inner", side_effect=inner),
        ):
            tasks = [
                asyncio.create_task(service._run_analysis(job, f"/{job}.pdf", f"{job}.pdf"))
                for job in done
            ]
            await asyncio.sleep(0)
            # The first converts; the others wait, so they have not run
            # `_run_analysis_inner`, where the job turns RUNNING.
            assert started == ["job-1"]

            done["job-1"].set()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert started == ["job-1", "job-2"]

            done["job-2"].set()
            done["job-3"].set()
            await asyncio.gather(*tasks)

        assert started == ["job-1", "job-2", "job-3"]
        assert "Analysis queued: job-2 (the engine runs 1 at a time)" in caplog.text

    async def test_docling_serve_takes_as_many_as_the_setting(self):
        service = _service(_Engine(None), max_concurrent=3)
        started: list[str] = []
        release = asyncio.Event()

        async def inner(job_id, *_args):
            started.append(job_id)
            await release.wait()

        with patch.object(service, "_run_analysis_inner", side_effect=inner):
            tasks = [
                asyncio.create_task(service._run_analysis(job, f"/{job}.pdf", f"{job}.pdf"))
                for job in ("job-1", "job-2", "job-3")
            ]
            await asyncio.sleep(0)
            assert started == ["job-1", "job-2", "job-3"]

            release.set()
            await asyncio.gather(*tasks)
