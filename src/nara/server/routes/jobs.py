"""Routes for the JobManager: create / list / get / cancel / restart."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, Response

from ...jobs import TERMINAL_STATES, JobManager
from ..models import JobCreate, JobDto, JobListResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _manager(request: Request) -> JobManager:
    mgr = getattr(request.app.state, "jobs", None)
    if mgr is None:
        raise HTTPException(503, "job manager not running")
    return mgr


def _to_dto(job) -> JobDto:  # type: ignore[no-untyped-def]
    return JobDto.model_validate(asdict(job))


@router.post("", response_model=JobDto, status_code=201)
async def create_job(body: JobCreate, request: Request) -> JobDto:
    mgr = _manager(request)
    try:
        job = await mgr.create(
            parent_naid=body.parent_naid,
            name=body.name,
            filter_query=body.filter_query,
            rate=body.rate,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _to_dto(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(request: Request) -> JobListResponse:
    mgr = _manager(request)
    return JobListResponse(jobs=[_to_dto(j) for j in mgr.list()])


@router.get("/{job_id}", response_model=JobDto)
async def get_job(job_id: str, request: Request) -> JobDto:
    mgr = _manager(request)
    job = mgr.get(job_id)
    if job is None:
        raise HTTPException(404, f"job {job_id} not found")
    return _to_dto(job)


@router.delete("/{job_id}")
async def delete_job(job_id: str, request: Request):
    """Smart DELETE: active jobs are cancelled (200 + DTO); terminal jobs
    are purged from history (204 No Content)."""
    mgr = _manager(request)
    job = mgr.get(job_id)
    if job is None:
        raise HTTPException(404, f"job {job_id} not found")
    if job.status in TERMINAL_STATES:
        await mgr.remove(job_id)
        return Response(status_code=204)
    try:
        cancelled = await mgr.cancel(job_id)
    except KeyError as e:
        raise HTTPException(404, f"job {job_id} not found") from e
    return _to_dto(cancelled)


@router.post("/{job_id}/restart", response_model=JobDto, status_code=201)
async def restart_job(job_id: str, request: Request) -> JobDto:
    """Queue a new job that reuses the original parameters."""
    mgr = _manager(request)
    try:
        new = await mgr.restart(job_id)
    except KeyError as e:
        raise HTTPException(404, f"job {job_id} not found") from e
    return _to_dto(new)
