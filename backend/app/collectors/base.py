"""Base class all collectors inherit from.

A collector is a stateless adapter: `Source` in, `list[SourceItem]` out.
It does NOT touch the database, does NOT see the tenant context, and
does NOT decide whether an item is a signal. Those responsibilities sit
in the service and detector layers respectively.

Failure policy: a collector should never raise for routine network
errors. It logs and returns `[]` (or skips the offending item). Raising
is reserved for programmer errors (misconfiguration, unsupported source
type) that the pipeline run should mark as FAILED.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import Source
from app.domain.types import SourceItem

__all__ = ["BaseCollector", "SourceItem"]


class BaseCollector(ABC):
    source_type: str  # the SourceType value this collector handles

    @abstractmethod
    def collect(self, source: Source) -> list[SourceItem]:
        ...
