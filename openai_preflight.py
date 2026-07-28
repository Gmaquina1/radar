#!/usr/bin/env python3
"""Preflight seguro da Responses API; nunca registra a credencial."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass

from web_search.openai_provider import OpenAIProvider


@dataclass
class PreflightResult:
    configurada: bool
    modelo: str
    connection: str = "NAO_TESTADA"
    web_search: str = "NAO_TESTADA"
    fontes_teste: int = 0
    consulta_teste: str = "leilões de máquinas Brasil"
    http_status: int | None = None
    tipo_erro: str = ""
    mensagem: str = ""


def classify_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    text = f"{type(exc).__name__} {exc}".casefold()
    if any(x in text for x in ("quota", "billing", "insufficient_quota")):
        return "BILLING"
    if status in (401, 403) or any(x in text for x in ("authentication", "api key", "unauthorized")):
        return "AUTH"
    if status == 429 or "rate limit" in text:
        return "RATE_LIMIT"
    if "model" in text:
        return "MODEL"
    if any(x in text for x in ("web_search", "tool")):
        return "WEB_SEARCH_TOOL"
    if isinstance(exc, (TimeoutError, ConnectionError)) or any(x in text for x in ("timeout", "network", "connection")):
        return "NETWORK"
    return "API"


def check(client=None) -> PreflightResult:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_SEARCH_MODEL", "").strip() or "gpt-5-mini"
    result = PreflightResult(bool(key), model)
    if not key:
        result.tipo_erro, result.mensagem = "CONFIG", "OPENAI_API_KEY ausente"
        return result
    try:
        sources = OpenAIProvider(api_key=key, client=client, model=model).search("leilões de máquinas Brasil", limit=5)
        result.connection = "OK"
        result.fontes_teste = len(sources)
        result.web_search = "OK" if sources else "ERRO"
        if not sources:
            result.tipo_erro, result.mensagem = "SEM_FONTES", "A chamada funcionou, mas não retornou fontes atribuídas"
    except Exception as exc:
        result.connection = result.web_search = "ERRO"
        result.http_status = getattr(exc, "status_code", None)
        result.tipo_erro = classify_error(exc)
        result.mensagem = str(exc).replace(key, "***")[:500]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require", action="store_true")
    args = parser.parse_args()
    result = check()
    print(f"OPENAI_API_KEY_CONFIGURADA: {str(result.configurada).lower()}")
    print(f"OPENAI_SEARCH_MODEL: {result.modelo}")
    print(f"OPENAI_CONNECTION: {result.connection}")
    print(f"OPENAI_WEB_SEARCH: {result.web_search}")
    print(
        "OPENAI_TEST_RESULTS: "
        f"consulta={result.consulta_teste!r}; "
        f"fontes_validas={result.fontes_teste}"
    )
    print(f"OPENAI_ERROR_TYPE: {result.tipo_erro or 'NONE'}")
    if result.http_status is not None:
        print(f"OPENAI_HTTP_STATUS: {result.http_status}")
    if result.tipo_erro:
        print(f"OPENAI_ERROR: {result.mensagem}")
    with open("openai_preflight.json", "w", encoding="utf-8") as handle:
        json.dump(asdict(result), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return 1 if args.require and (result.connection != "OK" or result.web_search != "OK") else 0


if __name__ == "__main__":
    raise SystemExit(main())
