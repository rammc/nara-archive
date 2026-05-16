"""Pydantic request/response models for the web API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    """One row in a search-results page — flattened for easy frontend rendering."""

    naid: str
    title: str | None = None
    level: str | None = None
    scope_and_content_note: str | None = None
    inclusive_start_year: int | None = None
    inclusive_end_year: int | None = None
    digital_object_count: int = 0
    thumbnail_url: str | None = None


class SearchResponse(BaseModel):
    hits: list[SearchHit]
    total: int
    page: int
    page_size: int


class RecordDetail(BaseModel):
    """A single record's full details. Returns ``record`` as raw NARA shape."""

    naid: str
    title: str | None = None
    level: str | None = None
    record: dict[str, Any] = Field(default_factory=dict)
    digital_objects: list[dict[str, Any]] = Field(default_factory=list)


class ChildrenResponse(BaseModel):
    parent_naid: str
    total: int
    hits: list[SearchHit]


# --- Jobs ---

class JobCreate(BaseModel):
    parent_naid: str = Field(..., min_length=1)
    name: str | None = None
    filter_query: str | None = None
    rate: float | None = Field(default=None, gt=0, le=60)


class JobProgressDto(BaseModel):
    phase: str = ""
    current: int = 0
    total: int = 0
    current_naid: str | None = None
    bytes_downloaded: int = 0


class JobResultDto(BaseModel):
    manifest_path: str | None = None
    successful_pdfs: int | None = None
    failed_pdfs: int | None = None
    errors: list[str] = Field(default_factory=list)


class JobDto(BaseModel):
    job_id: str
    parent_naid: str
    name: str | None = None
    filter_query: str | None = None
    rate: float
    status: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    progress: JobProgressDto = Field(default_factory=JobProgressDto)
    result: JobResultDto = Field(default_factory=JobResultDto)


class JobListResponse(BaseModel):
    jobs: list[JobDto]
