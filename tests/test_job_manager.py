"""Tests for the JobManager. Real NARA API and file-pipeline are mocked."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from nara.config import Config
from nara.downloader import JobCancelled
from nara.jobs import ACTIVE_STATES, Job, JobManager


def _config(tmp_path: Path) -> Config:
    return Config(
        api_key="fake-key",
        api_base_url="https://example.test/api/v2/",
        default_rate=0.0,
        output_dir=tmp_path,
        server_host="127.0.0.1",
        server_port=8765,
        auto_open_browser=False,
        config_path=None,
        terms_acknowledged=True,
        acknowledged_at="2026-05-16T00:00:00Z",
    )


def _fixture_meta() -> dict:
    return {
        "source": {"parent_naid": "PARENT"},
        "file_units": [
            {"naid": "U1", "title": "Unit 1", "digital_object_count": 2,
             "digital_objects": [{"filename": "a.jpg"}, {"filename": "b.jpg"}]},
            {"naid": "U2", "title": "Unit 2", "digital_object_count": 1,
             "digital_objects": [{"filename": "c.jpg"}]},
        ],
    }


def _fake_runners(
    *,
    fail_at: str | None = None,
    pre_download_hook=None,
    download_ticks: int = 3,
    filter_matches: int = 1,
) -> dict:
    """Build a runners dict for a fast, fully-mocked pipeline."""

    def fetch_and_persist(parent_naid, paths, *, limit, client):
        if fail_at == "metadata":
            raise RuntimeError("boom: metadata")
        return _fixture_meta()

    def apply_filter(paths, *, name, query, metadata_file=None, force=False, fields=None):
        if fail_at == "filter":
            raise RuntimeError("boom: filter")
        meta = _fixture_meta()
        if filter_matches == 0:
            meta["file_units"] = []
        return (
            paths.root / f"metadata-{name}.json",
            {
                "filter": {
                    "total_source_count": 2,
                    "matched_count": filter_matches,
                    "name": name,
                    "query": query,
                },
                "file_units": meta["file_units"][:filter_matches],
            },
        )

    def download_all(paths, *, rate, client, metadata, progress_callback=None,
                     cancel_event=None, show_progress_bars=False):
        if pre_download_hook is not None:
            pre_download_hook()
        if fail_at == "download":
            raise RuntimeError("boom: download")
        for i in range(download_ticks):
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled("cancelled in download")
            if progress_callback is not None:
                progress_callback({
                    "phase": "downloading",
                    "current": i + 1,
                    "total": download_ticks,
                    "current_naid": f"U{i+1}",
                    "bytes_downloaded": (i + 1) * 1000,
                })
            time.sleep(0.005)
        return {"downloaded": download_ticks, "skipped": 0, "failed": 0}

    def build_pdfs(paths, *, metadata, force=False, progress_callback=None,
                   cancel_event=None, show_progress_bars=False):
        if fail_at == "build":
            raise RuntimeError("boom: build")
        units = metadata.get("file_units", [])
        results = []
        for i, u in enumerate(units, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled("cancelled in build")
            results.append({
                "naid": u["naid"],
                "status": "ok",
                "pdf_path": f"pdfs/{i:04d}-{u['naid']}.pdf",
                "pdf_size_bytes": 1234,
                "page_count": 2,
            })
            if progress_callback is not None:
                progress_callback({"phase": "building_pdfs", "current": i,
                                   "total": len(units), "current_naid": u["naid"]})
        return results

    def write_manifest(paths, *, metadata, build_results, out_path=None):
        return {}

    def make_client(cfg):
        return object()

    return {
        "fetch_and_persist": fetch_and_persist,
        "apply_filter": apply_filter,
        "download_all": download_all,
        "build_pdfs": build_pdfs,
        "write_manifest": write_manifest,
        "make_client": make_client,
    }


async def _wait_for(predicate, *, timeout: float = 3.0, interval: float = 0.02):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise TimeoutError("predicate never satisfied within timeout")


# ---------- happy path ----------

def test_create_runs_through_to_done(tmp_path):
    asyncio.run(_test_create_runs_through_to_done(tmp_path))


async def _test_create_runs_through_to_done(tmp_path):
    mgr = JobManager(config=_config(tmp_path), runners=_fake_runners())
    await mgr.startup()
    try:
        job = await mgr.create(parent_naid="7840517")
        assert job.status == "queued"
        await _wait_for(lambda: mgr.get(job.job_id).status == "done")
        finished = mgr.get(job.job_id)
        assert finished.status == "done"
        assert finished.completed_at is not None
        assert finished.result.successful_pdfs == 2
        assert finished.result.failed_pdfs == 0
    finally:
        await mgr.shutdown()


# ---------- filter path ----------

def test_filter_job_writes_subset_manifest(tmp_path):
    asyncio.run(_test_filter_job(tmp_path))


async def _test_filter_job(tmp_path):
    mgr = JobManager(config=_config(tmp_path), runners=_fake_runners(filter_matches=1))
    await mgr.startup()
    try:
        job = await mgr.create(parent_naid="P", name="igfarben",
                               filter_query=r"farben")
        await _wait_for(lambda: mgr.get(job.job_id).status == "done")
        finished = mgr.get(job.job_id)
        assert finished.status == "done"
        # manifest_path picks up the filter slug — manifest-igfarben.json.
        assert finished.result.manifest_path is not None
        assert finished.result.manifest_path.endswith("manifest-igfarben.json")
    finally:
        await mgr.shutdown()


def test_filter_with_zero_matches_fails_cleanly(tmp_path):
    asyncio.run(_test_filter_zero(tmp_path))


async def _test_filter_zero(tmp_path):
    mgr = JobManager(config=_config(tmp_path), runners=_fake_runners(filter_matches=0))
    await mgr.startup()
    try:
        job = await mgr.create(parent_naid="P", name="empty", filter_query="x")
        await _wait_for(lambda: mgr.get(job.job_id).status in ("failed", "cancelled"))
        finished = mgr.get(job.job_id)
        assert finished.status == "failed"
        assert any("0/" in e for e in finished.result.errors)
    finally:
        await mgr.shutdown()


def test_filter_query_without_name_is_rejected(tmp_path):
    asyncio.run(_test_filter_no_name(tmp_path))


async def _test_filter_no_name(tmp_path):
    mgr = JobManager(config=_config(tmp_path), runners=_fake_runners())
    await mgr.startup()
    try:
        with pytest.raises(ValueError):
            await mgr.create(parent_naid="P", filter_query="x")
    finally:
        await mgr.shutdown()


# ---------- failure ----------

def test_failure_in_download_phase(tmp_path):
    asyncio.run(_test_failure(tmp_path, "download"))


def test_failure_in_build_phase(tmp_path):
    asyncio.run(_test_failure(tmp_path, "build"))


async def _test_failure(tmp_path, phase):
    mgr = JobManager(config=_config(tmp_path),
                     runners=_fake_runners(fail_at=phase))
    await mgr.startup()
    try:
        job = await mgr.create(parent_naid="P")
        await _wait_for(lambda: mgr.get(job.job_id).status == "failed")
        finished = mgr.get(job.job_id)
        assert finished.status == "failed"
        assert any("boom" in e for e in finished.result.errors)
    finally:
        await mgr.shutdown()


# ---------- cancellation ----------

def test_cancel_before_start_marks_cancelled(tmp_path):
    asyncio.run(_test_cancel_before_start(tmp_path))


async def _test_cancel_before_start(tmp_path):
    # Block the worker on a runner that won't actually exit until we say so —
    # by then the second job has been queued and we can cancel it before it runs.
    block = asyncio.Event()

    def slow_metadata(parent_naid, paths, *, limit, client):
        # busy-loop briefly so the worker stays on this job
        while not block.is_set():
            time.sleep(0.01)
        return _fixture_meta()

    runners = _fake_runners()
    runners["fetch_and_persist"] = slow_metadata

    mgr = JobManager(config=_config(tmp_path), runners=runners)
    await mgr.startup()
    try:
        first = await mgr.create(parent_naid="A")
        second = await mgr.create(parent_naid="B")
        # Wait until the worker actually picked up the first job.
        await _wait_for(lambda: mgr.get(first.job_id).status == "fetching_metadata")

        cancelled = await mgr.cancel(second.job_id)
        assert cancelled.status == "cancelled"

        block.set()
        await _wait_for(lambda: mgr.get(first.job_id).status == "done")
    finally:
        block.set()
        await mgr.shutdown()


def test_cancel_during_download_stops_cleanly(tmp_path):
    asyncio.run(_test_cancel_during_download(tmp_path))


async def _test_cancel_during_download(tmp_path):
    # Long-running download that polls cancel_event ~once per ms.
    def long_download(paths, *, rate, client, metadata, progress_callback=None,
                      cancel_event=None, show_progress_bars=False):
        for i in range(1000):
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled("cancelled in download")
            if progress_callback is not None:
                progress_callback({"phase": "downloading", "current": i, "total": 1000})
            time.sleep(0.005)
        return {"downloaded": 1000, "skipped": 0, "failed": 0}

    runners = _fake_runners()
    runners["download_all"] = long_download

    mgr = JobManager(config=_config(tmp_path), runners=runners)
    await mgr.startup()
    try:
        job = await mgr.create(parent_naid="X")
        await _wait_for(lambda: mgr.get(job.job_id).status == "downloading")
        await mgr.cancel(job.job_id)
        await _wait_for(lambda: mgr.get(job.job_id).status == "cancelled")
        finished = mgr.get(job.job_id)
        assert finished.status == "cancelled"
        assert finished.completed_at is not None
    finally:
        await mgr.shutdown()


# ---------- persistence + startup recovery ----------

def test_persistence_roundtrip(tmp_path):
    asyncio.run(_test_persistence(tmp_path))


async def _test_persistence(tmp_path):
    cfg = _config(tmp_path)
    mgr1 = JobManager(config=cfg, runners=_fake_runners())
    await mgr1.startup()
    try:
        job = await mgr1.create(parent_naid="P", name="snap")
        await _wait_for(lambda: mgr1.get(job.job_id).status == "done")
    finally:
        await mgr1.shutdown()

    # New manager picks up the persisted finished job.
    mgr2 = JobManager(config=cfg, runners=_fake_runners())
    await mgr2.startup()
    try:
        loaded = mgr2.get(job.job_id)
        assert loaded is not None
        assert loaded.status == "done"
        assert loaded.name == "snap"
    finally:
        await mgr2.shutdown()


def test_active_jobs_marked_interrupted_on_restart(tmp_path):
    """A jobs.json with a running-state job → restored as interrupted."""
    cfg = _config(tmp_path)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    jobs_path = cfg.output_dir / "jobs.json"
    jobs_path.write_text(json.dumps({
        "schema_version": 1,
        "jobs": [{
            "job_id": "ghost",
            "parent_naid": "X",
            "name": None,
            "filter_query": None,
            "rate": 0.5,
            "status": "downloading",
            "created_at": "2026-05-16T00:00:00Z",
            "started_at": "2026-05-16T00:00:00Z",
            "completed_at": None,
            "progress": {"phase": "downloading", "current": 5, "total": 10,
                         "current_naid": "U1", "bytes_downloaded": 1234},
            "result": {"manifest_path": None, "successful_pdfs": None,
                       "failed_pdfs": None, "errors": []},
        }]
    }))
    asyncio.run(_assert_restored_as_interrupted(cfg, "ghost"))


async def _assert_restored_as_interrupted(cfg, job_id):
    mgr = JobManager(config=cfg, runners=_fake_runners())
    await mgr.startup()
    try:
        job = mgr.get(job_id)
        assert job is not None
        assert job.status == "interrupted"
        assert job.completed_at is not None
    finally:
        await mgr.shutdown()


# ---------- progress propagation ----------

def test_progress_events_update_job_progress(tmp_path):
    asyncio.run(_test_progress(tmp_path))


async def _test_progress(tmp_path):
    mgr = JobManager(config=_config(tmp_path), runners=_fake_runners(download_ticks=4))
    await mgr.startup()
    try:
        job = await mgr.create(parent_naid="P")
        await _wait_for(lambda: mgr.get(job.job_id).status == "done")
        # Final state reflects the build phase (which runs after downloading).
        finished = mgr.get(job.job_id)
        assert finished.progress.phase == "building_pdfs"
        # Either build_pdfs reaches total or the last download tick was honoured.
        assert finished.progress.current > 0
    finally:
        await mgr.shutdown()
