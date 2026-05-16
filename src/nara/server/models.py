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
