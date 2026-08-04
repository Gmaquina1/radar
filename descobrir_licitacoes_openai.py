#!/usr/bin/env python3
"""Descoberta complementar de licitações com OpenAI Responses + Web Search."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from normalizar_texto import corrigir_dados
from web_search.openai_provider import response_sources


ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "relatorio_licitacoes_openai.json"
UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
)
UF_NAMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
    "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}
MAX_RESULTS_PER_QUERY = int(os.environ.get("OPENAI_LICITACOES_RESULTADOS", "25"))
MAX_QUERIES = int(os.environ.get("OPENAI_LICITACOES_CONSULTAS", "30"))
TIME_BUDGET = int(os.environ.get("OPENAI_LICITACOES_TEMPO_MAXIMO", "1200"))


LICITACOES_SCHEMA = {
    "type": "object",
    "properties": {
        "licitacoes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": ["string", "null"]},
                    "numero": {"type": ["string", "null"]},
                    "processo": {"type": ["string", "null"]},
                    "orgao": {"type": "string"},
                    "unidade": {"type": ["string", "null"]},
                    "objeto": {"type": "string"},
                    "modalidade": {"type": ["string", "null"]},
                    "data_publicacao": {"type": ["string", "null"]},
                    "data_abertura": {"type": ["string", "null"]},
                    "data_encerramento": {"type": "string"},
                    "valor_estimado": {"type": ["number", "null"]},
                    "uf": {"type": "string", "enum": list(UFS)},
                    "cidade": {"type": ["string", "null"]},
                    "link": {"type": "string"},
                },
                "required": [
                    "id", "numero", "processo", "orgao", "unidade", "objeto", "modalidade",
                    "data_publicacao", "data_abertura", "data_encerramento", "valor_estimado",
                    "uf", "cidade", "link",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["licitacoes"],
    "additionalProperties": False,
}


def normalize_url(value: str) -> str:
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    path = re.sub(r"/{2,}", "/", parsed.path or "/").rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, parsed.query, ""))


def comparable_url(value: str) -> str:
    normalized = normalize_url(value)
    if not normalized:
        return ""
    parsed = urlsplit(normalized)
    return urlunsplit(("https", (parsed.hostname or "").removeprefix("www."), parsed.path.rstrip("/"), "", ""))


def parse_date(value: object) -> dt.date | None:
    text = str(value or "").strip()
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return None
    try:
        return dt.date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(char for char in text if unicodedata.category(char) != "Mn").casefold().strip()


def row_key(row: dict) -> str:
    if row.get("id"):
        return f"id:{normalize_text(row['id'])}"
    link = comparable_url(row.get("link", ""))
    if link:
        return f"url:{link}"
    return "|".join(normalize_text(row.get(field)) for field in ("orgao", "objeto", "data_encerramento"))


def query_for_uf(uf: str, today: dt.date) -> str:
    return (
        f"Licitações públicas e avisos de contratação com propostas abertas em {UF_NAMES[uf]} ({uf}), "
        f"com encerramento a partir de {today.isoformat()}. Procure PNCP, Compras.gov.br, portais estaduais, "
        "municipais e plataformas oficiais de disputa. Inclua compras, serviços, obras, locações, máquinas, "
        "veículos e demais segmentos. Retorne somente oportunidades reais cujo edital ou página oficial você "
        f"tenha aberto, no máximo {MAX_RESULTS_PER_QUERY}. Use no campo link exatamente uma URL consultada."
    )


def national_queries(today: dt.date) -> list[tuple[str, str]]:
    items = [(uf, query_for_uf(uf, today)) for uf in UFS]
    items.extend(
        [
            ("BR-FEDERAL", f"Licitações federais brasileiras com propostas abertas e encerramento a partir de {today.isoformat()}, somente com página oficial ou PNCP consultada."),
            ("BR-MAQUINAS", f"Licitações brasileiras abertas para locação ou compra de máquinas pesadas, terraplenagem, transporte e serviços de máquinas, encerramento a partir de {today.isoformat()}, somente com página oficial consultada."),
            ("BR-OBRAS", f"Licitações brasileiras abertas de obras, manutenção, pavimentação e serviços de engenharia, encerramento a partir de {today.isoformat()}, somente com página oficial consultada."),
        ]
    )
    return items[:MAX_QUERIES]


def response_payload(response) -> dict:
    text = getattr(response, "output_text", None)
    if text is None and isinstance(response, dict):
        text = response.get("output_text")
    try:
        value = json.loads(str(text or ""))
    except json.JSONDecodeError:
        return {"licitacoes": []}
    return value if isinstance(value, dict) else {"licitacoes": []}


def validate_rows(raw_rows: object, sources: list[dict], today: dt.date) -> tuple[list[dict], int]:
    if not isinstance(raw_rows, list):
        return [], 0
    source_by_url = {comparable_url(item.get("url", "")): item for item in sources}
    accepted: list[dict] = []
    rejected = 0
    for raw in raw_rows:
        if not isinstance(raw, dict):
            rejected += 1
            continue
        link_key = comparable_url(raw.get("link", ""))
        deadline = parse_date(raw.get("data_encerramento"))
        uf = str(raw.get("uf") or "").upper()
        if (
            not link_key
            or link_key not in source_by_url
            or deadline is None
            or deadline < today
            or uf not in UFS
            or len(str(raw.get("orgao") or "").strip()) < 3
            or len(str(raw.get("objeto") or "").strip()) < 8
        ):
            rejected += 1
            continue
        source = source_by_url[link_key]
        row = {
            "id": str(raw.get("id") or "").strip(),
            "numero": str(raw.get("numero") or "").strip(),
            "processo": str(raw.get("processo") or "").strip(),
            "orgao": str(raw.get("orgao") or "").strip(),
            "unidade": str(raw.get("unidade") or "").strip(),
            "objeto": str(raw.get("objeto") or "").strip(),
            "informacao_complementar": "",
            "modalidade": str(raw.get("modalidade") or "").strip(),
            "modalidade_id": None,
            "modo_disputa": "",
            "situacao": "Recebendo propostas",
            "data_publicacao": str(raw.get("data_publicacao") or "").strip(),
            "data_abertura": str(raw.get("data_abertura") or "").strip(),
            "data_encerramento": str(raw.get("data_encerramento") or "").strip(),
            "valor_estimado": raw.get("valor_estimado"),
            "uf": uf,
            "cidade": str(raw.get("cidade") or "").strip(),
            "link": source.get("url") or raw.get("link"),
            "link_origem": source.get("url") or raw.get("link"),
            "fonte": "OpenAI Web Search",
            "fonte_titulo": str(source.get("title") or "").strip(),
            "origem_validada": True,
        }
        accepted.append(corrigir_dados(row))
    return accepted, rejected


def collect_openai(now: dt.datetime, client=None) -> tuple[list[dict], dict]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_LICITACOES_MODEL", "").strip() or os.getenv("OPENAI_SEARCH_MODEL", "").strip() or "gpt-5-mini"
    report = {
        "configurada": bool(api_key or client),
        "modelo": model,
        "consultas_planejadas": 0,
        "consultas_executadas": 0,
        "fontes_consultadas": 0,
        "registros_aceitos": 0,
        "registros_rejeitados": 0,
        "ufs_consultadas": [],
        "ufs_com_resultados": [],
        "erros": [],
    }
    if not api_key and client is None:
        return [], report
    if client is None:
        from openai import OpenAI

        timeout = float(os.getenv("OPENAI_LICITACOES_TIMEOUT", "120"))
        client = OpenAI(api_key=api_key, timeout=timeout, max_retries=1)
    queries = national_queries(now.date())
    report["consultas_planejadas"] = len(queries)
    deadline = time.monotonic() + TIME_BUDGET
    selected: dict[str, dict] = {}
    for scope, query in queries:
        if time.monotonic() >= deadline:
            report["erros"].append("Tempo máximo da busca OpenAI atingido.")
            break
        try:
            response = client.responses.create(
                model=model,
                tools=[{"type": "web_search"}],
                tool_choice="required",
                include=["web_search_call.action.sources"],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "licitacoes_abertas",
                        "strict": True,
                        "schema": LICITACOES_SCHEMA,
                    }
                },
                input=(
                    "Extraia os resultados no esquema solicitado. Use datas em ISO 8601 (AAAA-MM-DD ou "
                    "AAAA-MM-DDTHH:MM:SS), valor como número ou null e o link exato de uma fonte aberta "
                    "pela busca. Não complete campos por suposição e não inclua oportunidade sem prazo futuro.\n\n"
                    + query
                ),
                store=False,
            )
        except Exception as exc:  # O relatório preserva falhas isoladas sem perder as demais UFs.
            report["erros"].append(f"{scope}: {type(exc).__name__}: {exc}")
            continue
        report["consultas_executadas"] += 1
        if scope in UFS:
            report["ufs_consultadas"].append(scope)
        sources = response_sources(response)
        report["fontes_consultadas"] += len(sources)
        payload = response_payload(response)
        rows, rejected = validate_rows(payload.get("licitacoes"), sources, now.date())
        report["registros_rejeitados"] += rejected
        if rows and scope in UFS:
            report["ufs_com_resultados"].append(scope)
        for row in rows:
            selected[row_key(row)] = row
    result = sorted(
        selected.values(),
        key=lambda row: (row.get("data_encerramento") or "9999", row.get("uf") or "", row.get("orgao") or ""),
    )
    report["registros_aceitos"] = len(result)
    report["ufs_consultadas"] = sorted(set(report["ufs_consultadas"]))
    report["ufs_com_resultados"] = sorted(set(report["ufs_com_resultados"]))
    return result, report


def write_report(report: dict, path: Path = REPORT) -> None:
    path.write_text(json.dumps(corrigir_dados(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    from zoneinfo import ZoneInfo

    rows, report = collect_openai(dt.datetime.now(ZoneInfo("America/Sao_Paulo")))
    write_report(report)
    print(json.dumps({"licitacoes": len(rows), **report}, ensure_ascii=False))
