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
from pathlib import Path
from zoneinfo import ZoneInfo

from normalizar_texto import corrigir_dados


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "licitacoes.json"
STATUS = ROOT / "status_licitacoes.json"
TIMEZONE = ZoneInfo("America/Sao_Paulo")
BASE_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
SOURCE_NAME = "Portal Nacional de Contratações Públicas (PNCP)"
MODALIDADES = tuple(range(2, 13))  # Exclui apenas as modalidades de leilão.
PAGE_SIZE = 500
MAX_PAGES_PER_MODALITY = int(os.environ.get("PNCP_MAX_PAGINAS_MODALIDADE", "80"))
MAX_RECORDS = int(os.environ.get("PNCP_MAX_REGISTROS", "60000"))
REQUEST_TIMEOUT = int(os.environ.get("PNCP_TIMEOUT", "35"))
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


def request_page(modality: int, final_date: str, page: int) -> dict:
    query = urllib.parse.urlencode(
        {
            "dataFinal": final_date,
            "codigoModalidadeContratacao": modality,
            "pagina": page,
            "tamanhoPagina": PAGE_SIZE,
        }
    )
    request = urllib.request.Request(
        f"{BASE_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "Radar-de-Oportunidades/1.0"},
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.load(response)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"Falha no PNCP para modalidade {modality}, página {page}: {last_error}")


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
    for modality in MODALIDADES:
        for page in range(1, MAX_PAGES_PER_MODALITY + 1):
            if time.monotonic() >= deadline:
                errors.append("Tempo máximo de coleta do PNCP atingido; nova tentativa será feita na próxima atualização.")
                truncated = True
                break
            try:
                payload = request_page(modality, final_date, page)
            except RuntimeError as exc:
                errors.append(str(exc))
                break
            raw_rows = rows_from_response(payload)
            for raw in raw_rows:
                row = map_contract(raw)
                key = row.get("id") or f"{row.get('orgao')}|{row.get('numero')}|{row.get('data_encerramento')}"
                selected[str(key)] = row
                if len(selected) >= MAX_RECORDS:
                    truncated = True
                    break
            if truncated or not has_more(payload, page, len(raw_rows)):
                break
            time.sleep(0.15)
        if truncated:
            break
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


def main() -> None:
    now = dt.datetime.now(TIMEZONE)
    rows, errors, truncated = collect(now)
    previous = previous_payload()
    if not rows and previous.get("licitacoes"):
        status = {
            "status": "base_anterior_preservada",
            "atualizado_em": now.isoformat(timespec="seconds"),
            "total_preservado": len(previous.get("licitacoes", [])),
            "erros": errors or ["A API do PNCP não devolveu registros."],
        }
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(status, ensure_ascii=False))
        return
    if not rows:
        raise SystemExit("A API do PNCP não devolveu licitações e não existe base anterior válida.")
    payload = {
        "atualizado_em": now.isoformat(timespec="seconds"),
        "fonte": SOURCE_NAME,
        "fonte_url": "https://pncp.gov.br/app/editais",
        "criterio": "Contratações com recebimento de propostas aberto e encerramento em até 365 dias",
        "total": len(rows),
        "parcial": truncated or bool(errors),
        "licitacoes": rows,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    status = {
        "status": "ok_parcial" if payload["parcial"] else "ok",
        "atualizado_em": payload["atualizado_em"],
        "total": payload["total"],
        "truncado": truncated,
        "erros": errors,
    }
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
