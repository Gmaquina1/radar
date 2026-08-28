#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from normalizar_texto import corrigir_dados
from personalizar_site import apply_date_highlights


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "site_template.html"
PORTAL_TEMPLATE = ROOT / "portal_template.html"
LICITACOES_TEMPLATE = ROOT / "licitacoes_template.html"
LICITACOES_DATA = ROOT / "licitacoes.json"
MUNICIPALITIES = ROOT / "municipios_coordenadas.json"
MAP_EMBED_URL = "https://www.google.com/maps/d/u/0/embed?mid=1fYo8R4P75VxKA3TqsiuLsWIqIDEO27U&ehbc=2E312F"
TIMEZONE = ZoneInfo("America/Sao_Paulo")
VALID_UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def read_csv(name: str) -> list[dict[str, str]]:
    path = ROOT / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return corrigir_dados(list(csv.DictReader(handle)))


def read_lot_file(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = data.get("lotes", []) if isinstance(data, dict) else data
    return corrigir_dados([row for row in rows if isinstance(row, dict)]) if isinstance(rows, list) else []


def read_lotes() -> list[dict[str, str]]:
    return read_lot_file(ROOT / "lotes.json")


def read_municipalities() -> list[list]:
    try:
        data = json.loads(MUNICIPALITIES.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = data.get("municipios", []) if isinstance(data, dict) else []
    return [row for row in rows if isinstance(row, list) and len(row) == 4]


def normalize_place(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", text).casefold().strip()


def municipality_index(rows: list[list]) -> dict[str, list[tuple[str, str, float, float]]]:
    by_uf: dict[str, list[tuple[str, str, float, float]]] = {}
    for name, uf, latitude, longitude in rows:
        by_uf.setdefault(str(uf), []).append(
            (normalize_place(name), str(name), float(latitude), float(longitude))
        )
    for values in by_uf.values():
        values.sort(key=lambda item: len(item[0]), reverse=True)
    return by_uf


def add_municipality_coordinates(
    row: dict[str, str],
    event: dict[str, str],
    municipalities: dict[str, list[tuple[str, str, float, float]]],
) -> None:
    uf = row.get("uf") or event.get("uf") or ""
    if uf not in municipalities:
        return
    location = " | ".join(
        str(value or "")
        for value in (
            row.get("cidade"),
            row.get("local"),
            event.get("endereco_ou_localizacao"),
            row.get("evento"),
        )
    )
    normalized = normalize_place(location)
    for city_key, city, latitude, longitude in municipalities[uf]:
        if re.search(rf"(?<!\w){re.escape(city_key)}(?!\w)", normalized):
            row["cidade"] = city
            row["latitude"] = latitude
            row["longitude"] = longitude
            if not row.get("local"):
                row["local"] = f"{city} - {uf}"
            return


def infer_uf(*values: str) -> str:
    text = " | ".join(str(value or "") for value in values)
    matches = re.findall(r"(?:-|/)\s*([A-Z]{2})(?=\b|,)", text.upper())
    return next((uf for uf in reversed(matches) if uf in VALID_UFS), "")


def parse_hour(value: str) -> tuple[int, int] | None:
    match = re.search(r"(\d{1,2})[:h](\d{2})?", value or "", re.I)
    if not match:
        return None
    return min(23, int(match.group(1))), min(59, int(match.group(2) or 0))


def is_upcoming(row: dict[str, str], now: dt.datetime) -> bool:
    value = (row.get("data") or "").strip()
    if not value:
        return False
    try:
        day = dt.date.fromisoformat(value)
    except ValueError:
        return False
    if day > now.date():
        return True
    if day < now.date():
        return False
    parsed_hour = parse_hour(row.get("hora") or row.get("hora_marcador") or "")
    if not parsed_hour:
        return True
    hour, minute = parsed_hour
    starts_at = dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=TIMEZONE)
    return starts_at > now


def event_key(name: str, event_date: str) -> str:
    normalized = re.sub(r"\s+", " ", (name or "").strip()).casefold()
    return f"{normalized}|{event_date or ''}"


def canonical_event_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return ""
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
    ]
    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            parts.path.rstrip("/") or "/",
            urlencode(query),
            "",
        )
    )


def event_urls(row: dict[str, str]) -> list[str]:
    urls: list[str] = []
    for field in ("site_leiloeiro", "link", "link_edital", "link_evento"):
        for value in str(row.get(field, "") or "").split("|"):
            url = canonical_event_url(value.strip())
            if url and url not in urls:
                urls.append(url)
    return urls


def event_identity(row: dict[str, str]) -> str:
    urls = event_urls(row)
    parts = [
        urls[0] if urls else "",
        normalize_place(row.get("nome") or row.get("evento") or ""),
        str(row.get("data") or ""),
        normalize_place(row.get("endereco_ou_localizacao") or row.get("local") or ""),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"evento-{digest}"


def prepare_events(events: list[dict[str, str]]) -> list[dict[str, str]]:
    prepared: list[dict[str, str]] = []
    for raw in events:
        row = dict(raw)
        urls = event_urls(row)
        primary_url = urls[0] if urls else ""
        host = urlsplit(primary_url).netloc.casefold().removeprefix("www.") if primary_url else ""
        row["evento_id"] = row.get("evento_id") or event_identity(row)
        row["evento"] = row.get("evento") or row.get("nome", "")
        row["titulo"] = row.get("titulo") or row.get("nome", "")
        row["hora"] = row.get("hora") or row.get("hora_marcador", "")
        row["local"] = row.get("local") or row.get("endereco_ou_localizacao", "")
        row["link_evento"] = row.get("link_evento") or primary_url
        row["leiloeiro"] = row.get("leiloeiro") or host or row.get("site_leiloeiro", "")
        prepared.append(row)
    return prepared


def generic_title(value: str) -> bool:
    return bool(re.fullmatch(r"(?:lote\s*[\d.\-/a-z]*|efetuar lance|ver lote|detalhes)", (value or "").strip(), re.I))


def quality(row: dict[str, str]) -> float:
    title = row.get("titulo", "")
    return (0 if generic_title(title) else len(title)) + len(row.get("descricao", "")) / 20


def canonical_link(row: dict[str, str]) -> str:
    link = row.get("link_lote") or row.get("link_evento") or ""
    return re.sub(r"#.*$", "", link).strip()


def lot_key(row: dict[str, str]) -> str:
    link = canonical_link(row)
    event = re.sub(r"\s+", " ", row.get("evento", "").strip()).casefold()
    lot_number = re.sub(r"\s+", " ", row.get("lote", "").strip()).casefold()
    title = re.sub(r"\s+", " ", row.get("titulo", "").strip()).casefold()
    base = link or event
    if lot_number:
        return f"{base}|lote:{lot_number}"
    if title:
        return f"{base}|titulo:{title}"
    return base


def enrich_and_dedupe_lots(
    lots: list[dict[str, str]],
    events: list[dict[str, str]],
    now: dt.datetime,
) -> list[dict[str, str]]:
    events = prepare_events(events)
    event_lookup = {event_key(row.get("nome", ""), row.get("data", "")): row for row in events}
    event_url_lookup: dict[str, dict[str, str]] = {}
    for event in events:
        for url in event_urls(event):
            event_url_lookup[url] = event
    municipalities = municipality_index(read_municipalities())
    selected: dict[str, dict[str, str]] = {}
    for raw in lots:
        row = dict(raw)
        if not is_upcoming(row, now):
            continue
        if row.get("uf") not in VALID_UFS:
            row["uf"] = ""
        event = event_lookup.get(
            event_key(row.get("evento", ""), row.get("data", ""))
        )
        if not event:
            event = next(
                (
                    event_url_lookup[url]
                    for url in (
                        canonical_event_url(row.get("link_evento", "")),
                        canonical_event_url(row.get("fonte", "")),
                    )
                    if url in event_url_lookup
                ),
                None,
            )
        if not event:
            continue
        row["uf"] = row.get("uf") or event.get("uf") or infer_uf(
            row.get("local", ""),
            event.get("endereco_ou_localizacao", ""),
            row.get("evento", ""),
        )
        row["link_edital"] = row.get("link_edital") or event.get("link_edital", "")
        row["resumo_edital"] = row.get("resumo_edital") or event.get("resumo_edital", "")
        linked_event_urls = event_urls(event)
        row["link_evento"] = row.get("link_evento") or (
            linked_event_urls[0] if linked_event_urls else ""
        )
        row["evento_id"] = event.get("evento_id") or event_identity(event)
        add_municipality_coordinates(row, event, municipalities)
        key = lot_key(row)
        current = selected.get(key)
        if not current:
            selected[key] = row
            continue
        preferred, other = (row, current) if quality(row) > quality(current) else (current, row)
        merged = {**other, **preferred}
        for field in ("lote", "foto_lote", "link_edital", "resumo_edital", "link_evento", "lance_atual"):
            merged[field] = preferred.get(field) or other.get(field, "")
        selected[key] = merged
    return sorted(
        selected.values(),
        key=lambda row: (row.get("data") or "9999-99-99", row.get("hora") or "23:59", row.get("uf") or ""),
    )


def main() -> None:
    required_templates = (TEMPLATE, PORTAL_TEMPLATE, LICITACOES_TEMPLATE)
    missing = [str(path) for path in required_templates if not path.exists()]
    if missing:
        raise SystemExit(f"Template nao encontrado: {', '.join(missing)}")

    now = dt.datetime.now(TIMEZONE)
    events = prepare_events(
        [row for row in read_csv("radar_leiloes_eventos_futuros.csv") if is_upcoming(row, now)]
    )
    for event in events:
        if event.get("uf") not in VALID_UFS:
            event["uf"] = ""
    # lotes.json e gerado exclusivamente a partir dos eventos do Google My
    # Maps. Nenhuma base paralela e acrescentada na pagina publicada.
    lots = enrich_and_dedupe_lots(read_lotes(), events, now)
    patios = read_csv("radar_leiloes_patios.csv")
    municipalities = read_municipalities()
    app_version = os.environ.get("RADAR_VERSION") or now.strftime("v%Y.%m.%d.%H%M")
    edital_events = sum(1 for row in events if row.get("link_edital"))
    edital_lots = sum(1 for row in lots if row.get("link_edital"))

    payload = {
        "eventos": events,
        "patios": patios,
        "lotes": lots,
        "municipios": municipalities,
        "geodados": {"fonte": "municipios-br 3.2.1", "licenca": "CC0-1.0"},
        "fonte_eventos": "Google My Maps",
        "somente_eventos_do_mapa": True,
        "gerado_em": now.isoformat(timespec="seconds"),
        "proxima_atualizacao": "Atualização a cada 6 horas",
        "mapa": MAP_EMBED_URL,
        "versao": app_version,
        "editais_eventos": edital_events,
        "lotes_com_edital": edital_lots,
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = apply_date_highlights(TEMPLATE.read_text(encoding="utf-8"))
    if "__RADAR_DATA__" not in template:
        raise SystemExit("O marcador __RADAR_DATA__ nao existe no template.")
    html = template.replace("__RADAR_DATA__", data)
    (ROOT / "leiloes.html").write_text(html, encoding="utf-8")
    portal = PORTAL_TEMPLATE.read_text(encoding="utf-8")
    (ROOT / "index.html").write_text(portal, encoding="utf-8")

    try:
        licitacoes_payload = json.loads(LICITACOES_DATA.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        licitacoes_payload = {
            "atualizado_em": now.isoformat(timespec="seconds"),
            "fonte": "Portal Nacional de Contratações Públicas (PNCP)",
            "total": 0,
            "licitacoes": [],
        }
    licitacoes_data = json.dumps(
        corrigir_dados(licitacoes_payload), ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")
    licitacoes_template = LICITACOES_TEMPLATE.read_text(encoding="utf-8")
    if "__LICITACOES_DATA__" not in licitacoes_template:
        raise SystemExit("O marcador __LICITACOES_DATA__ nao existe no template de licitacoes.")
    (ROOT / "licitacoes.html").write_text(
        licitacoes_template.replace("__LICITACOES_DATA__", licitacoes_data),
        encoding="utf-8",
    )
    (ROOT / "radar-leiloes.html").write_text(
        "<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\">"
        "<meta http-equiv=\"refresh\" content=\"0;url=./leiloes.html\">"
        "<title>Radar de Leilões</title>"
        "<p>Abrindo o <a href=\"./leiloes.html\">Radar de Leilões</a>...</p></html>\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "gerado_em": payload["gerado_em"],
                "eventos_futuros": len(events),
                "lotes_futuros": len(lots),
                "lotes_com_edital": edital_lots,
                "licitacoes": len(licitacoes_payload.get("licitacoes", [])),
                "versao": app_version,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
