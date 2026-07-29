from __future__ import annotations

from datetime import datetime
from typing import Protocol

from finalboss.models import CollectionResult


class SourceAdapter(Protocol):
    async def collect(self, *, since: datetime) -> CollectionResult: ...
