#!/usr/bin/env python3
"""Coleta completa e resiliente das licitações abertas do PNCP.

A rotina usa paginação sequencial, espera progressiva para HTTP 429/5xx e
preserva oportunidades ainda abertas de execuções anteriores. O objetivo é
não perder registros quando a API oficial estiver instável ou aplicar limite
de requisições.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import atualizar_licitacoes as base

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "licitacoes.json"
STATUS = ROOT / "status_licitacoes.json"
TIMEZONE = ZoneInfo("America/Sao_Paulo")
BASE_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"

REQUEST_TIMEOUT = max(15, int(os.environ.get("PNCP_TIMEOUT", "60")))
REQUEST_ATTEMPTS = max(3, int(os.environ.get("PNCP_TENTATIVAS", "8")))
REQUEST_INTERVAL = max(0.2, float(os.environ.get("PNCP_INTERVALO", "0.8")))
RATE_LIMIT_WAIT = max(10, int(os.environ.get("PNCP_ESPERA_429", "30")))
MAX_WAIT = max(RATE_LIMIT_WAIT, int(os.environ.get("PNCP_ESPERA_MAXIMA", "180")))
MAX_PAGES = max(1, int(os.environ.get("PNCP_MAX_PAGINAS", "1000")))
MAX_RECORDS = max(1, int(os.environ.get("PNCP_MAX_REGISTROS", "60000")))
PREFERRED_PAGE_SIZE = max(10, int(os.environ.get("PNCP_TAMANHO_PAGINA", "500")))
PAGE_SIZE_CANDIDATES = tuple(
    dict.fromkeys(size for size in (PREFERRED_PAGE_SIZE, 200, 100, 50) if size > 0)
)


def retry_after_seconds(headers: object, fallback: float) -> float:
    """Lê Retry-After em segundos ou data HTTP, respeitando um teto."""
    value = headers.get("Retry-After") if hasattr(headers, "get") else None
    if value:
        text = str(value).strip()
        if text.isdigit():
            return min(MAX_WAIT, max(1.0, float(text)))
        try:
            parsed = email.utils.parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            seconds = (parsed - dt.datetime.now(dt.timezone.utc)).total_seconds()
            if seconds > 0:
                return min(MAX_WAIT, seconds)
        except (TypeError, ValueError, OverflowError):
            pass
    return min(MAX_WAIT, max(1.0, fallback))


def response_is_json(response: object) -> bool:
    content_type = response.headers.get("Content-Type", "") if hasattr(response, "headers") else ""
    return "json" in str(content_type).lower()


def request_page(final_date: str, page: int, page_size: int) -> dict:
    query = urllib.parse.urlencode(
        {"dataFinal": final_date, "pagina": page, "tamanhoPagina": page_size}
    )
    request = urllib.request.Request(
        f"{BASE_URL}?{query}",
        headers={
            "Accept": "application/json",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (compatible; Radar-de-Oportunidades/2.0; +https://radar.empaez.com)",
        },
    )
    last_error: Exception | None = None

    for attempt in range(REQUEST_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                if not response_is_json(response):
                    sample = response.read(300).decode("utf-8", errors="replace")
                    raise RuntimeError(f"PNCP retornou conteúdo não JSON: {sample[:120]!r}")
                payload = json.load(response)
                if not isinstance(payload, dict):
                    raise RuntimeError("PNCP retornou um JSON em formato inesperado")
                return payload
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in {400, 422} and page == 1:
                raise
            if exc.code == 429:
                fallback = RATE_LIMIT_WAIT * (2 ** min(attempt, 3))
                wait = retry_after_seconds(exc.headers, fallback) + random.uniform(0.2, 1.5)
            elif 500 <= exc.code < 600:
                wait = min(MAX_WAIT, 3 * (2**attempt)) + random.uniform(0.2, 1.0)
            else:
                raise RuntimeError(f"Falha HTTP {exc.code} no PNCP, página {page}") from exc
            print(f"PNCP página {page}: HTTP {exc.code}; nova tentativa em {wait:.1f}s", flush=True)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            wait = min(MAX_WAIT, 3 * (2**attempt)) + random.uniform(0.2, 1.0)
            print(f"PNCP página {page}: {type(exc).__name__}; nova tentativa em {wait:.1f}s", flush=True)
            time.sleep(wait)

    raise RuntimeError(f"PNCP indisponível na página {page} após {REQUEST_ATTEMPTS} tentativas: {last_error}")


def choose_page_size(final_date: str) -> tuple[int, dict]:
    errors: list[str] = []
    for size in PAGE_SIZE_CANDIDATES:
        try:
            payload = request_page(final_date, 1, size)
            return size, payload
        except urllib.error.HTTPError as exc:
            errors.append(f"{size}: HTTP {exc.code}")
            if exc.code not in {400, 422}:
                raise
        except RuntimeError as exc:
            errors.append(f"{size}: {exc}")
            raise
    raise RuntimeError("Nenhum tamanho de página foi aceito pelo PNCP: " + "; ".join(errors))


def rows_from_payload(payload: dict) -> list[dict]:
    rows = payload.get("data", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def collect_pncp(now: dt.datetime) -> tuple[list[dict], list[str], bool, int, int]:
    final_date = (now.date() + dt.timedelta(days=365)).strftime("%Y%m%d")
    selected: dict[str, dict] = {}
    errors: list[str] = []
    truncated = False

    page_size, first = choose_page_size(final_date)
    total_pages = first.get("totalPaginas")
    if not isinstance(total_pages, int) or total_pages < 1:
        total_pages = 1
    target_pages = min(total_pages, MAX_PAGES)
    if total_pages > MAX_PAGES:
        truncated = True
        errors.append(f"PNCP informou {total_pages} páginas; limite configurado: {MAX_PAGES}.")

    def absorb(payload: dict) -> None:
        nonlocal truncated
        for raw in rows_from_payload(payload):
            row = base.map_contract(raw)
            if base.is_auction(row):
                continue
            closing = base.parse_date(row.get("data_encerramento"))
            if closing is not None and closing < now.date():
                continue
            key = row.get("id") or f"{row.get('orgao')}|{row.get('numero')}|{row.get('data_encerramento')}"
            selected[str(key)] = row
            if len(selected) >= MAX_RECORDS:
                truncated = True
                return

    absorb(first)
    print(
        f"PNCP: {total_pages} páginas, tamanho {page_size}, "
        f"primeira página com {len(rows_from_payload(first))} registros.",
        flush=True,
    )

    for page in range(2, target_pages + 1):
        if len(selected) >= MAX_RECORDS:
            errors.append(f"Limite de {MAX_RECORDS} registros atingido.")
            break
        time.sleep(REQUEST_INTERVAL)
        try:
            payload = request_page(final_date, page, page_size)
            absorb(payload)
        except RuntimeError as exc:
            errors.append(str(exc))
        if page % 10 == 0 or page == target_pages:
            print(f"PNCP: página {page}/{target_pages}; {len(selected)} oportunidades abertas.", flush=True)

    rows = sorted(
        selected.values(),
        key=lambda row: (row.get("data_encerramento") or "9999", row.get("uf") or "", row.get("orgao") or ""),
    )
    return rows, errors, truncated, total_pages, page_size


def main() -> None:
    now = dt.datetime.now(TIMEZONE)
    previous = base.previous_payload()
    previous_rows = base.open_rows(previous.get("licitacoes", []), now.date())

    pncp_rows: list[dict] = []
    pncp_errors: list[str] = []
    pncp_truncated = False
    pncp_total_pages = 0
    pncp_page_size = 0
    try:
        pncp_rows, pncp_errors, pncp_truncated, pncp_total_pages, pncp_page_size = collect_pncp(now)
    except Exception as exc:
        pncp_errors = [f"Coleta completa do PNCP falhou: {type(exc).__name__}: {exc}"]

    compras_rows: list[dict] = []
    compras_errors: list[str] = []
    compras_truncated = False
    try:
        compras_rows, compras_errors, compras_truncated = base.collect_compras_gov(now)
    except Exception as exc:
        compras_errors = [f"Coleta do Compras.gov.br falhou: {type(exc).__name__}: {exc}"]

    rows = base.merge_rows(previous_rows, compras_rows, pncp_rows)
    sources = {
        "pncp": len(pncp_rows),
        "compras_gov": len(compras_rows),
        "preservadas": max(0, len(rows) - len(pncp_rows) - len(compras_rows)),
    }
    partial = (
        not pncp_rows
        or pncp_truncated
        or compras_truncated
        or bool(pncp_errors)
        or bool(compras_errors)
    )

    payload = {
        "atualizado_em": now.isoformat(timespec="seconds"),
        "fonte": "Portal Nacional de Contratações Públicas (PNCP) + Compras.gov.br",
        "fonte_url": "https://pncp.gov.br/app/editais",
        "criterio": "Contratações com recebimento de propostas aberto e encerramento em até 365 dias",
        "total": len(rows),
        "parcial": partial,
        "indisponivel": not rows,
        "fontes": sources,
        "cobertura": {
            "ufs_com_oportunidades": len({row.get("uf") for row in rows if row.get("uf")}),
            "paginas_pncp_informadas": pncp_total_pages,
            "tamanho_pagina_pncp": pncp_page_size,
        },
        "licitacoes": rows,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    status = {
        "status": "sem_dados" if not rows else ("ok_parcial" if partial else "ok"),
        "atualizado_em": payload["atualizado_em"],
        "total": len(rows),
        "fontes": sources,
        "paginas_pncp_informadas": pncp_total_pages,
        "tamanho_pagina_pncp": pncp_page_size,
        "truncado": pncp_truncated or compras_truncated,
        "erros_pncp": pncp_errors[:100],
        "erros_compras_gov": compras_errors[:100],
    }
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False), flush=True)

    if not rows:
        raise SystemExit("Nenhuma licitação disponível após a coleta; a publicação foi interrompida.")


if __name__ == "__main__":
    main()
