#!/usr/bin/env python3
"""Coleta oportunidades com propostas abertas na API pública oficial do PNCP."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from zoneinfo import ZoneInfo

from normalizar_texto import corrigir_dados
from descobrir_licitacoes_openai import (
    UFS as VALID_UFS,
    comparable_url,
    collect_openai,
    is_auction,
    normalize_text,
    parse_date,
    write_report,
)


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "licitacoes.json"
STATUS = ROOT / "status_licitacoes.json"
TIMEZONE = ZoneInfo("America/Sao_Paulo")
BASE_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
PUBLICATION_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
SOURCE_NAME = "Portal Nacional de Contratações Públicas (PNCP)"
PUBLICATION_MODALITIES = tuple(range(2, 13))
PAGE_SIZE = int(os.environ.get("PNCP_TAMANHO_PAGINA", "50"))
MAX_PAGES = int(os.environ.get("PNCP_MAX_PAGINAS", "400"))
PNCP_WORKERS = max(1, int(os.environ.get("PNCP_WORKERS", "16")))
PUBLICATION_LOOKBACK_DAYS = int(os.environ.get("PNCP_PUBLICACAO_DIAS", "365"))
PUBLICATION_WINDOW_DAYS = max(1, int(os.environ.get("PNCP_PUBLICACAO_JANELA", "7")))
PUBLICATION_MAX_PAGES = int(os.environ.get("PNCP_PUBLICACAO_MAX_PAGINAS", "80"))
MAX_RECORDS = int(os.environ.get("PNCP_MAX_REGISTROS", "60000"))
REQUEST_TIMEOUT = int(os.environ.get("PNCP_TIMEOUT", "35"))
REQUEST_ATTEMPTS = max(1, int(os.environ.get("PNCP_TENTATIVAS", "3")))
TIME_BUDGET_SECONDS = int(os.environ.get("PNCP_TEMPO_MAXIMO", "600"))


def nested(row: dict, parent: str, key: str) -> str:
    value = row.get(parent)
    return str(value.get(key) or "").strip() if isinstance(value, dict) else ""


def pncp_link(numero_controle: str) -> str:
    """Converte 00000000000000-1-000001/2026 na página pública do edital."""
    match = re.fullmatch(r"(\d{14})-\d+-(\d+)/(\d{4})", numero_controle or "")
    if not match:
        return "https://pncp.gov.br/app/editais"
    cnpj, sequencial, ano = match.groups()
    return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{int(sequencial)}"


def normalize_datetime(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    # O PNCP usa ISO 8601, normalmente sem fuso. Mantemos o instante publicado.
    return text.replace(" ", "T", 1)


def map_contract(row: dict) -> dict:
    numero = str(row.get("numeroControlePNCP") or "").strip()
    mapped = {
        "id": numero,
        "numero": str(row.get("numeroCompra") or "").strip(),
        "processo": str(row.get("processo") or "").strip(),
        "orgao": nested(row, "orgaoEntidade", "razaoSocial"),
        "unidade": nested(row, "unidadeOrgao", "nomeUnidade"),
        "objeto": str(row.get("objetoCompra") or "").strip(),
        "informacao_complementar": str(row.get("informacaoComplementar") or "").strip(),
        "modalidade": str(row.get("modalidadeNome") or "").strip(),
        "modalidade_id": row.get("modalidadeId"),
        "modo_disputa": str(row.get("modoDisputaNome") or "").strip(),
        "situacao": str(row.get("situacaoCompraNome") or "").strip(),
        "data_publicacao": normalize_datetime(row.get("dataPublicacaoPncp")),
        "data_abertura": normalize_datetime(row.get("dataAberturaProposta")),
        "data_encerramento": normalize_datetime(row.get("dataEncerramentoProposta")),
        "valor_estimado": row.get("valorTotalEstimado"),
        "uf": nested(row, "unidadeOrgao", "ufSigla").upper(),
        "cidade": nested(row, "unidadeOrgao", "municipioNome"),
        "link": pncp_link(numero),
        "link_origem": str(row.get("linkSistemaOrigem") or "").strip(),
        "fonte": "PNCP",
    }
    return corrigir_dados(mapped)


def request_page(final_date: str, page: int) -> dict:
    query = urllib.parse.urlencode(
        {
            "dataFinal": final_date,
            "pagina": page,
            "tamanhoPagina": PAGE_SIZE,
        }
    )
    request = urllib.request.Request(
        f"{BASE_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "Radar-de-Oportunidades/1.0"},
    )
    last_error: Exception | None = None
    for attempt in range(REQUEST_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.load(response)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < REQUEST_ATTEMPTS:
                time.sleep(2**attempt)
    raise RuntimeError(f"Falha no PNCP para página {page}: {last_error}")


def request_publication_page(modality: int, initial_date: str, final_date: str, page: int) -> dict:
    query = urllib.parse.urlencode(
        {
            "dataInicial": initial_date,
            "dataFinal": final_date,
            "codigoModalidadeContratacao": modality,
            "pagina": page,
            "tamanhoPagina": PAGE_SIZE,
        }
    )
    request = urllib.request.Request(
        f"{PUBLICATION_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "Radar-de-Oportunidades/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Falha no PNCP/publicação modalidade {modality}, período {initial_date}-{final_date}, página {page}: {exc}"
        ) from exc


def rows_from_response(payload: dict) -> list[dict]:
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def has_more(payload: dict, page: int, row_count: int) -> bool:
    total_pages = payload.get("totalPaginas") if isinstance(payload, dict) else None
    if isinstance(total_pages, int):
        return page < total_pages
    remaining = payload.get("paginasRestantes") if isinstance(payload, dict) else None
    if isinstance(remaining, int):
        return remaining > 0
    return row_count >= PAGE_SIZE


def collect(now: dt.datetime | None = None) -> tuple[list[dict], list[str], bool]:
    now = now or dt.datetime.now(TIMEZONE)
    # Endpoint de propostas devolve apenas recebimentos ainda abertos até a data final.
    final_date = (now.date() + dt.timedelta(days=365)).strftime("%Y%m%d")
    selected: dict[str, dict] = {}
    errors: list[str] = []
    truncated = False
    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    def absorb(payload: dict) -> None:
        nonlocal truncated
        for raw in rows_from_response(payload):
            row = map_contract(raw)
            if is_auction(row):
                continue
            closing = parse_date(row.get("data_encerramento"))
            if closing is not None and closing < now.date():
                continue
            key = row.get("id") or f"{row.get('orgao')}|{row.get('numero')}|{row.get('data_encerramento')}"
            selected[str(key)] = row
            if len(selected) >= MAX_RECORDS:
                truncated = True
                return

    try:
        first = request_page(final_date, 1)
    except RuntimeError as exc:
        errors.append(f"{exc}; usando consulta por data de publicação.")
        first = None
    if first is None:
        start = now.date() - dt.timedelta(days=PUBLICATION_LOOKBACK_DAYS)
        windows: list[tuple[int, str, str]] = []
        while start <= now.date():
            end = min(start + dt.timedelta(days=PUBLICATION_WINDOW_DAYS - 1), now.date())
            for modality in PUBLICATION_MODALITIES:
                windows.append((modality, start.strftime("%Y%m%d"), end.strftime("%Y%m%d")))
            start = end + dt.timedelta(days=1)

        def fetch_window(modality: int, initial: str, final: str) -> tuple[list[dict], list[str], bool]:
            found: list[dict] = []
            local_errors: list[str] = []
            local_truncated = False
            for page in range(1, PUBLICATION_MAX_PAGES + 1):
                if time.monotonic() >= deadline:
                    local_truncated = True
                    break
                try:
                    payload = request_publication_page(modality, initial, final, page)
                except RuntimeError as window_error:
                    local_errors.append(str(window_error))
                    break
                page_rows = rows_from_response(payload)
                found.extend(page_rows)
                if not has_more(payload, page, len(page_rows)):
                    break
                if page == PUBLICATION_MAX_PAGES:
                    local_truncated = True
            return found, local_errors, local_truncated

        executor = ThreadPoolExecutor(max_workers=min(PNCP_WORKERS, len(windows) or 1))
        futures = {executor.submit(fetch_window, *window): window for window in windows}
        try:
            for future in as_completed(futures, timeout=max(1, deadline - time.monotonic())):
                raw_rows, window_errors, window_truncated = future.result()
                absorb({"data": raw_rows})
                if len(errors) < 50:
                    errors.extend(window_errors[: 50 - len(errors)])
                truncated = truncated or window_truncated
                if truncated and len(selected) >= MAX_RECORDS:
                    break
        except TimeoutError:
            truncated = True
            errors.append("Tempo máximo da coleta PNCP/publicação atingido; janelas restantes serão retomadas.")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        rows = sorted(
            selected.values(),
            key=lambda row: (row.get("data_encerramento") or "9999", row.get("uf") or "", row.get("orgao") or ""),
        )
        return rows, errors, truncated

    absorb(first)
    total_pages = first.get("totalPaginas") if isinstance(first, dict) else None
    if not isinstance(total_pages, int):
        total_pages = 2 if has_more(first, 1, len(rows_from_response(first))) else 1
    if total_pages > MAX_PAGES:
        truncated = True
        errors.append(f"PNCP informou {total_pages} páginas; limite desta execução: {MAX_PAGES}.")
    last_page = min(max(1, total_pages), MAX_PAGES)

    executor = ThreadPoolExecutor(max_workers=min(PNCP_WORKERS, max(1, last_page - 1)))
    futures = {executor.submit(request_page, final_date, page): page for page in range(2, last_page + 1)}
    try:
        for future in as_completed(futures, timeout=max(1, deadline - time.monotonic())):
            page = futures[future]
            try:
                absorb(future.result())
            except RuntimeError as exc:
                errors.append(str(exc))
            if truncated and len(selected) >= MAX_RECORDS:
                break
    except TimeoutError:
        truncated = True
        errors.append("Tempo máximo de coleta do PNCP atingido; páginas restantes serão retomadas na próxima atualização.")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    rows = sorted(
        selected.values(),
        key=lambda row: (row.get("data_encerramento") or "9999", row.get("uf") or "", row.get("orgao") or ""),
    )
    return rows, errors, truncated


def previous_payload() -> dict:
    try:
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def open_rows(rows: object, today: dt.date) -> list[dict]:
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if is_auction(row):
            continue
        deadline = parse_date(row.get("data_encerramento"))
        if deadline is not None and deadline >= today:
            result.append(row)
    return result


def merge_rows(*groups: list[dict]) -> list[dict]:
    """Mescla fontes preservando dados antigos e priorizando OpenAI e depois PNCP."""
    selected: list[dict] = []
    aliases: dict[str, int] = {}
    for rows in groups:
        for row in rows:
            identities = []
            if row.get("id"):
                identities.append(f"id:{normalize_text(row['id'])}")
            if comparable_url(row.get("link", "")):
                identities.append(f"url:{comparable_url(row['link'])}")
            fingerprint = "|".join(
                normalize_text(row.get(field)) for field in ("orgao", "objeto", "data_encerramento")
            )
            if fingerprint.replace("|", ""):
                identities.append(f"dados:{fingerprint}")
            index = next((aliases[key] for key in identities if key in aliases), None)
            if index is None:
                index = len(selected)
                selected.append(dict(row))
            current = selected[index]
            merged = {**current, **row}
            for field in current:
                if merged.get(field) in (None, ""):
                    merged[field] = current[field]
            selected[index] = merged
            for identity in identities:
                aliases[identity] = index
    return sorted(
        selected,
        key=lambda row: (row.get("data_encerramento") or "9999", row.get("uf") or "", row.get("orgao") or ""),
    )


def main() -> None:
    now = dt.datetime.now(TIMEZONE)
    previous = previous_payload()
    pncp_rows, pncp_errors, truncated = collect(now)
    openai_rows, openai_report = collect_openai(now)
    write_report(openai_report)
    previous_rows = open_rows(previous.get("licitacoes", []), now.date())
    rows = merge_rows(previous_rows, openai_rows, pncp_rows)
    sources = {
        "pncp": len(pncp_rows),
        "openai_web_search": len(openai_rows),
        "preservadas": max(0, len(rows) - len(pncp_rows) - len(openai_rows)),
    }
    openai_incomplete = (
        openai_report.get("configurada")
        and (
            openai_report.get("consultas_executadas", 0) < openai_report.get("consultas_planejadas", 0)
            or len(openai_report.get("ufs_consultadas", [])) < len(VALID_UFS)
            or bool(openai_report.get("erros"))
        )
    )
    partial = truncated or bool(pncp_errors) or not pncp_rows or bool(openai_incomplete)
    payload = {
        "atualizado_em": now.isoformat(timespec="seconds"),
        "fonte": f"{SOURCE_NAME} + OpenAI Web Search com fontes validadas",
        "fonte_url": "https://pncp.gov.br/app/editais",
        "criterio": "Contratações com recebimento de propostas aberto e encerramento em até 365 dias",
        "total": len(rows),
        "parcial": partial,
        "indisponivel": not rows,
        "fontes": sources,
        "cobertura": {
            "ufs_planejadas": len(VALID_UFS),
            "ufs_consultadas_openai": len(openai_report.get("ufs_consultadas", [])),
            "ufs_com_oportunidades": len({row.get("uf") for row in rows if row.get("uf")}),
        },
        "licitacoes": rows,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    status = {
        "status": "sem_dados" if not rows else ("ok_parcial" if payload["parcial"] else "ok"),
        "atualizado_em": payload["atualizado_em"],
        "total": payload["total"],
        "fontes": sources,
        "truncado": truncated,
        "erros_pncp": pncp_errors,
        "erros_openai": openai_report.get("erros", []),
        "openai_configurada": openai_report.get("configurada", False),
        "consultas_openai": openai_report.get("consultas_executadas", 0),
        "ufs_consultadas_openai": openai_report.get("ufs_consultadas", []),
    }
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
