"""Background job manager for full bulk-download runs.

A ``Job`` represents one metadata-fetch → download → PDF-build pipeline against
a NARA parent NAID, optionally filtered. The :class:`JobManager` exposes a
queue-style API to the FastAPI server: create, list, get, cancel.

Architecture: one asyncio worker task processes jobs FIFO. Heavy phases run
inside ``asyncio.to_thread`` because they're synchronous I/O. Progress
callbacks marshal updates back onto the event loop via
``loop.call_soon_threadsafe`` so that all mutations of :class:`Job` happen on
the asyncio thread — no locks needed.

Cancellation: the user signals with DELETE, we set a ``threading.Event`` that
the phase code polls between files / units. The current file (or unit) runs
to completion to keep on-disk state clean; resume semantics handle the rest.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Awaitable, Callable

from .api import NaraApiError, NaraClient
from .config import Config
from .downloader import JobCancelled, download_all
from .filter import apply_filter, validate_filter_name
from .manifest import write_manifest
from .metadata import fetch_and_persist
from .pdfbuild import build_pdfs
from .utils import OutputPaths, atomic_write_text, manifest_path_for, utc_now_iso

log = logging.getLogger("nara")

SCHEMA_VERSION = 1

# Terminal states have no follow-up automation.
TERMINAL_STATES = {"done", "failed", "cancelled", "interrupted"}
# Active states are the ones we mark as "interrupted" on server restart.
ACTIVE_STATES = {"fetching_metadata", "downloading", "building_pdfs"}

# Throttle progress persistence so 255k file events don't trigger 255k disk writes.
PERSIST_EVERY_N_EVENTS = 25


@dataclass
class JobProgress:
    phase: str = ""
    current: int = 0
    total: int = 0
    current_naid: str | None = None
    bytes_downloaded: int = 0


@dataclass
class JobResult:
    manifest_path: str | None = None
    successful_pdfs: int | None = None
    failed_pdfs: int | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class Job:
    job_id: str
    parent_naid: str
    name: str | None
    filter_query: str | None
    rate: float
    status: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    progress: JobProgress = field(default_factory=JobProgress)
    result: JobResult = field(default_factory=JobResult)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Job":
        progress = JobProgress(**(d.get("progress") or {}))
        result = JobResult(**(d.get("result") or {}))
        return cls(
            job_id=d["job_id"],
            parent_naid=d["parent_naid"],
            name=d.get("name"),
            filter_query=d.get("filter_query"),
            rate=float(d.get("rate", 1.0)),
            status=d.get("status", "queued"),
            created_at=d["created_at"],
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            progress=progress,
            result=result,
        )


# Phase callables — overridable for tests. Real defaults bound to the production code.
PhaseRunners = dict[str, Callable[..., Any]]
DEFAULT_RUNNERS: PhaseRunners = {
    "fetch_and_persist": fetch_and_persist,
    "apply_filter": apply_filter,
    "download_all": download_all,
    "build_pdfs": build_pdfs,
    "write_manifest": write_manifest,
    "make_client": lambda cfg: NaraClient(api_key=cfg.api_key, base=cfg.api_base_url),
}


class JobManager:
    """Single-job-at-a-time worker queue with on-disk persistence."""

    def __init__(
        self,
        *,
        config: Config,
        persistence_path: Path | None = None,
        runners: PhaseRunners | None = None,
    ) -> None:
        self._config = config
        self._persistence_path = (
            persistence_path or config.output_dir / "jobs.json"
        )
        self._runners: PhaseRunners = {**DEFAULT_RUNNERS, **(runners or {})}

        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._cancel_events: dict[str, threading.Event] = {}
        self._worker_task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._shutting_down = False

    # ----- public API -----

    @property
    def persistence_path(self) -> Path:
        return self._persistence_path

    def list(self) -> list[Job]:
        """Most recent first."""
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def startup(self) -> None:
        """Load persisted jobs, mark active ones as interrupted, start the worker."""
        self._loop = asyncio.get_running_loop()
        self._load()
        requeued: list[str] = []
        for job in list(self._jobs.values()):
            if job.status in ACTIVE_STATES:
                job.status = "interrupted"
                job.completed_at = utc_now_iso()
                log.info("job=%s marked interrupted on startup", job.job_id)
            elif job.status == "queued":
                requeued.append(job.job_id)
        self._persist()
        for jid in requeued:
            self._queue.put_nowait(jid)
        self._worker_task = asyncio.create_task(self._worker_loop(), name="nara-job-worker")

    async def shutdown(self) -> None:
        """Cancel the worker and any in-flight job; jobs.json is left intact."""
        self._shutting_down = True
        for ev in self._cancel_events.values():
            ev.set()
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self._persist()

    async def create(
        self,
        *,
        parent_naid: str,
        name: str | None = None,
        filter_query: str | None = None,
        rate: float | None = None,
    ) -> Job:
        if filter_query and not name:
            raise ValueError("name is required when filter_query is set")
        if name:
            validate_filter_name(name)
        job = Job(
            job_id=uuid.uuid4().hex,
            parent_naid=str(parent_naid).strip(),
            name=name,
            filter_query=filter_query,
            rate=float(rate) if rate is not None else self._config.default_rate,
            status="queued",
            created_at=utc_now_iso(),
        )
        if not job.parent_naid:
            raise ValueError("parent_naid is required")
        self._jobs[job.job_id] = job
        self._persist()
        await self._queue.put(job.job_id)
        return job

    async def cancel(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status in TERMINAL_STATES:
            return job  # already finished — no-op
        ev = self._cancel_events.get(job_id)
        if ev is not None:
            ev.set()  # worker will observe between files
        else:
            # Job was queued but not yet started.
            job.status = "cancelled"
            job.completed_at = utc_now_iso()
            self._persist()
        return job

    # ----- worker -----

    async def _worker_loop(self) -> None:
        while not self._shutting_down:
            try:
                job_id = await self._queue.get()
            except asyncio.CancelledError:
                return
            job = self._jobs.get(job_id)
            if job is None or job.status in TERMINAL_STATES:
                continue
            try:
                await self._run_one(job)
            except Exception:  # noqa: BLE001 — never let the worker die
                log.exception("worker crashed on job=%s; continuing", job_id)

    async def _run_one(self, job: Job) -> None:
        job.started_at = utc_now_iso()
        cancel_event = threading.Event()
        self._cancel_events[job.job_id] = cancel_event

        loop = self._loop
        assert loop is not None
        event_counter = {"n": 0}

        def progress(event: dict[str, Any]) -> None:
            """Called from the worker thread; marshalled back to the loop."""
            loop.call_soon_threadsafe(self._apply_progress, job.job_id, event, event_counter)

        try:
            cfg = self._config
            paths = OutputPaths(root=cfg.output_dir)
            paths.ensure()
            client = self._runners["make_client"](cfg)

            # Phase 1
            job.status = "fetching_metadata"
            job.progress = JobProgress(phase="fetching_metadata")
            self._persist()
            meta = await asyncio.to_thread(
                self._runners["fetch_and_persist"],
                job.parent_naid, paths, limit=300, client=client,
            )

            # Optional filter step
            metadata_for_phases = meta
            manifest_target = paths.manifest
            if job.filter_query and job.name:
                out_path, sub_doc = await asyncio.to_thread(
                    self._runners["apply_filter"],
                    paths,
                    name=job.name,
                    query=job.filter_query,
                    metadata_file=paths.metadata,
                    force=True,
                )
                if not sub_doc["file_units"]:
                    raise RuntimeError(
                        f"filter matched 0/{sub_doc['filter']['total_source_count']} "
                        f"file units — nothing to download"
                    )
                metadata_for_phases = sub_doc
                manifest_target = manifest_path_for(out_path)

            # Phase 2
            self._check_cancelled(cancel_event)
            job.status = "downloading"
            job.progress = JobProgress(
                phase="downloading",
                total=sum(u.get("digital_object_count", 0)
                          for u in metadata_for_phases.get("file_units", [])),
            )
            self._persist()
            await asyncio.to_thread(
                self._runners["download_all"],
                paths,
                rate=job.rate,
                client=client,
                metadata=metadata_for_phases,
                progress_callback=progress,
                cancel_event=cancel_event,
                show_progress_bars=False,
            )

            # Phase 3
            self._check_cancelled(cancel_event)
            job.status = "building_pdfs"
            job.progress = JobProgress(
                phase="building_pdfs",
                total=len(metadata_for_phases.get("file_units", [])),
            )
            self._persist()
            results = await asyncio.to_thread(
                self._runners["build_pdfs"],
                paths,
                metadata=metadata_for_phases,
                progress_callback=progress,
                cancel_event=cancel_event,
                show_progress_bars=False,
            )

            # Manifest
            await asyncio.to_thread(
                self._runners["write_manifest"],
                paths,
                metadata=metadata_for_phases,
                build_results=results,
                out_path=manifest_target,
            )

            job.status = "done"
            ok = sum(1 for r in results if r.get("status") == "ok")
            failed = sum(1 for r in results if r.get("status") in ("failed", "missing"))
            job.result.manifest_path = str(manifest_target)
            job.result.successful_pdfs = ok
            job.result.failed_pdfs = failed
        except JobCancelled as e:
            job.status = "cancelled"
            job.result.errors.append(str(e))
            log.info("job=%s cancelled by user", job.job_id)
        except NaraApiError as e:
            job.status = "failed"
            job.result.errors.append(str(e))
            log.exception("job=%s NARA API failure", job.job_id)
        except Exception as e:  # noqa: BLE001
            job.status = "failed"
            job.result.errors.append(str(e))
            log.exception("job=%s unexpected failure", job.job_id)
        finally:
            job.completed_at = utc_now_iso()
            self._cancel_events.pop(job.job_id, None)
            self._persist()

    # ----- progress + persistence -----

    def _apply_progress(
        self,
        job_id: str,
        event: dict[str, Any],
        counter: dict[str, int],
    ) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        prog = job.progress
        prog.phase = event.get("phase", prog.phase)
        if "current" in event:
            prog.current = int(event["current"])
        if "total" in event:
            prog.total = int(event["total"])
        if event.get("current_naid"):
            prog.current_naid = str(event["current_naid"])
        if "bytes_downloaded" in event:
            prog.bytes_downloaded = int(event["bytes_downloaded"])
        counter["n"] += 1
        if counter["n"] % PERSIST_EVERY_N_EVENTS == 0:
            self._persist()

    def _check_cancelled(self, ev: threading.Event) -> None:
        if ev.is_set():
            raise JobCancelled("cancelled before next phase")

    # ----- on-disk -----

    def _persist(self) -> None:
        doc = {
            "schema_version": SCHEMA_VERSION,
            "jobs": [j.to_dict() for j in self._jobs.values()],
        }
        try:
            atomic_write_text(
                self._persistence_path,
                json.dumps(doc, indent=2, ensure_ascii=False),
            )
        except OSError:
            log.exception("could not persist jobs.json to %s", self._persistence_path)

    def _load(self) -> None:
        if not self._persistence_path.exists():
            return
        try:
            doc = json.loads(self._persistence_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("jobs.json is corrupt at %s — starting fresh",
                        self._persistence_path)
            return
        for d in doc.get("jobs", []):
            try:
                job = Job.from_dict(d)
                self._jobs[job.job_id] = job
            except (KeyError, ValueError, TypeError):
                log.warning("skipping malformed job entry: %r", d)
