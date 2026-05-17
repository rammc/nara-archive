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
    # Heuristic hint for the UI: "has_scans" | "has_children" | "likely_empty".
    # Computed from level + digital_object_count without an extra NARA round-trip.
    downloadability: str = "likely_empty"
    record_group_number: str | None = None


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
    recompress: bool = False


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
    recompress: bool = False
    progress: JobProgressDto = Field(default_factory=JobProgressDto)
    result: JobResultDto = Field(default_factory=JobResultDto)


class JobListResponse(BaseModel):
    jobs: list[JobDto]


# --- Library ---


class LibraryEntry(BaseModel):
    name: str
    parent_naid: str | None = None
    parent_title: str | None = None
    file_unit_count: int = 0
    pdf_count: int = 0
    total_size_bytes: int = 0
    generated_at: str | None = None


class LibraryListResponse(BaseModel):
    manifests: list[LibraryEntry]


class LibraryFileUnit(BaseModel):
    naid: str | None = None
    title: str | None = None
    slug: str | None = None
    scope_and_content_note: str | None = None
    inclusive_start_year: int | None = None
    inclusive_end_year: int | None = None
    pdf_path: str | None = None
    pdf_size_bytes: int = 0
    page_count: int = 0
    source_object_count: int = 0
    status: str = "ok"


class LibraryDetail(BaseModel):
    name: str
    schema_version: str | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)
    file_units: list[LibraryFileUnit]


class LibrarySearchResponse(BaseModel):
    name: str
    query: str
    total: int
    matches: list[LibraryFileUnit]


# --- Config ---


class ConfigDto(BaseModel):
    has_api_key: bool
    api_key_masked: str | None = None
    api_base_url: str
    default_rate: float
    output_dir: str
    server_host: str
    server_port: int
    auto_open_browser: bool
    terms_acknowledged: bool
    acknowledged_at: str | None = None
    config_path: str | None = None


class ConfigPatch(BaseModel):
    default_rate: float | None = Field(default=None, gt=0, le=60)
    auto_open_browser: bool | None = None


class RevealResponse(BaseModel):
    opened: str


# --- Presets ---


class PresetSearch(BaseModel):
    q: str
    record_group: list[str] | None = None
    level: list[str] | None = None
    year_from: int | None = None
    year_to: int | None = None
    has_digital_objects: bool | None = None


class Preset(BaseModel):
    id: str
    title: str
    description: str
    category: str
    search: PresetSearch | None = None
    direct_naid: str | None = None
    filter_regex_hint: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str | None = None  # "bundled" or "user"


class PresetListResponse(BaseModel):
    presets: list[Preset]
