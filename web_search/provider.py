"""Busca configurável, sem scraping de páginas de resultados."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from .base import SearchResult


class BraveProvider:
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, key: str, timeout: float = 15) -> None:
        self.key, self.timeout = key, timeout

    def search(self, query: str, page: int = 1, limit: int = 10) -> list[SearchResult]:
        count = max(1, min(limit, 20))
        params = urllib.parse.urlencode({"q": query, "count": count, "offset": (page - 1) * count, "country": "br"})
        request = urllib.request.Request(f"{self.endpoint}?{params}", headers={"X-Subscription-Token": self.key, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.load(response)
        return [SearchResult(item.get("url", ""), item.get("title", ""), item.get("description", "")) for item in payload.get("web", {}).get("results", []) if item.get("url")]


def configured_provider():
    name = os.getenv("WEB_SEARCH_PROVIDER", "").strip().casefold()
    key = os.getenv("WEB_SEARCH_API_KEY", "").strip()
    if not name or not key:
        return None
    if name == "brave":
        return BraveProvider(key, float(os.getenv("REQUEST_TIMEOUT", "15")))
    raise ValueError(f"WEB_SEARCH_PROVIDER não suportado: {name}")


def search_web(query: str, page: int = 1, limit: int = 10) -> list[SearchResult]:
    provider = configured_provider()
    return provider.search(query, page, limit) if provider else []
