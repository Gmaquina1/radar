from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""


class SearchProvider(Protocol):
    def search(self, query: str, page: int = 1, limit: int = 10) -> list[SearchResult]: ...
