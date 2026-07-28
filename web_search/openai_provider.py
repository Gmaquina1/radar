"""Descoberta de URLs com a ferramenta nativa Web Search da Responses API."""
from __future__ import annotations

import os
from collections.abc import Iterable
from urllib.parse import urlsplit

from .base import SearchResult

DEFAULT_MODEL = "gpt-5-mini"


def _value(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _items(value) -> Iterable:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return value
    return (value,)


def _valid_url(value) -> bool:
    try:
        parsed = urlsplit(str(value or ""))
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


def response_sources(response) -> list[dict]:
    """Extrai somente URLs atribuídas a fontes/citações retornadas pela API."""
    found: list[dict] = []
    seen: set[str] = set()

    def add(source):
        url = _value(source, "url")
        if not _valid_url(url) or url in seen:
            return
        seen.add(url)
        found.append({
            "url": url,
            "title": str(_value(source, "title", "") or ""),
            "description": str(_value(source, "description", _value(source, "text", "")) or ""),
        })

    for output in _items(_value(response, "output", [])):
        # web_search_call.action.sources é a origem preferencial.
        action = _value(output, "action")
        for source in _items(_value(action, "sources", [])):
            add(source)
        for source in _items(_value(output, "sources", [])):
            add(source)
        for content in _items(_value(output, "content", [])):
            for annotation in _items(_value(content, "annotations", [])):
                citation = _value(annotation, "url_citation", annotation)
                add(citation)
    return found


class OpenAIProvider:
    def __init__(self, api_key: str | None = None, client=None, model: str | None = None, timeout: float | None = None):
        self.model = model or os.getenv("OPENAI_SEARCH_MODEL", "").strip() or DEFAULT_MODEL
        timeout = timeout or float(
            os.getenv(
                "OPENAI_REQUEST_TIMEOUT",
                os.getenv("REQUEST_TIMEOUT", "15"),
            )
        )
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, timeout=timeout, max_retries=1)
        self.client = client

    def search(self, query: str, page: int = 1, limit: int = 10) -> list[SearchResult]:
        del page  # Web Search não expõe paginação tradicional.
        response = self.client.responses.create(
            model=self.model,
            tools=[{"type": "web_search"}],
            input=("Pesquise amplamente na web brasileira. Retorne fontes relevantes para: " + query),
            tool_choice="auto",
            include=["web_search_call.action.sources"],
        )
        return [SearchResult(item["url"], item["title"], item["description"]) for item in response_sources(response)[:max(0, limit)]]


def search_web(query: str, limit: int = 10) -> list[dict]:
    """Interface pública estruturada solicitada para integrações independentes."""
    return [{"title": r.title, "url": r.url, "description": r.snippet, "query": query}
            for r in OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY")).search(query, limit=limit)]
