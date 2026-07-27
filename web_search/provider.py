"""Seleção extensível do mecanismo de descoberta externa."""
from __future__ import annotations

import os

from .openai_provider import OpenAIProvider


def configured_provider():
    """Retorna o provider padrão OpenAI, ou ``None`` quando não há chave."""
    name = os.getenv("WEB_SEARCH_PROVIDER", "openai").strip().casefold() or "openai"
    if name == "openai":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        return OpenAIProvider(api_key=key) if key else None
    raise ValueError(f"WEB_SEARCH_PROVIDER não suportado: {name}")


def search_web(query: str, page: int = 1, limit: int = 10):
    provider = configured_provider()
    return provider.search(query, page=page, limit=limit) if provider else []
