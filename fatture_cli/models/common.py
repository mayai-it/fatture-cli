"""Common Pydantic schemas shared by resource models."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard Fatture in Cloud list-endpoint envelope.

    FiC paginates list responses with ``data``, ``current_page``, ``last_page``,
    ``per_page``, ``total``. Other envelope keys may be added over time — kept
    permissive via ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow")

    data: list[T] = Field(default_factory=list)
    current_page: int | None = None
    last_page: int | None = None
    per_page: int | None = None
    total: int | None = None
