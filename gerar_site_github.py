#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "site_template.html"
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
        return list(csv.DictReader(handle))


def read_lotes() -> list[dict[str, str]]:
    path = ROOT / "lotes.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = data.get("lotes", []) if isinstance(data, dict) else data
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


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


def generic_title(value: str) -> bool:
    return bool(re.fullmatch(r"(?:lote\s*[\d.\-/a-z]*|efetuar lance|ver lote|detalhes)", (value or "").strip(), re.I))


def quality(row: dict[str, str]) -> float:
    title = row.get("titulo", "")
    return (0 if generic_title(title) else len(title)) + len(row.get("descricao", "")) / 20


def canonical_link(row: dict[str, str]) -> str:
    link = row.get("link_lote") or row.get("link_evento") or ""
    return re.sub(r"#.*$", "", link).strip()


def enrich_and_dedupe_lots(
    lots: list[dict[str, str]],
    events: list[dict[str, str]],
    now: dt.datetime,
) -> list[dict[str, str]]:
    event_lookup = {event_key(row.get("nome", ""), row.get("data", "")): row for row in events}
    selected: dict[str, dict[str, str]] = {}
    for raw in lots:
        row = dict(raw)
        if not is_upcoming(row, now):
            continue
        if row.get("uf") not in VALID_UFS:
            row["uf"] = ""
        event = event_lookup.get(event_key(row.get("evento", ""), row.get("data", "")), {})
        row["link_edital"] = row.get("link_edital") or event.get("link_edital", "")
        row["resumo_edital"] = row.get("resumo_edital") or event.get("resumo_edital", "")
        row["link_evento"] = row.get("link_evento") or event.get("link", "")
        key = canonical_link(row) or "|".join(
            (row.get("evento", ""), row.get("lote", ""), row.get("titulo", ""))
        ).casefold()
        current = selected.get(key)
        if not current:
            selected[key] = row
            continue
        preferred, other = (row, current) if quality(row) > quality(current) else (current, row)
        merged = {**other, **preferred}
        for field in ("lote", "link_edital", "resumo_edital", "link_evento", "lance_atual"):
            merged[field] = preferred.get(field) or other.get(field, "")
        selected[key] = merged
    return sorted(
        selected.values(),
        key=lambda row: (row.get("data") or "9999-99-99", row.get("hora") or "23:59", row.get("uf") or ""),
    )


def main() -> None:
    if not TEMPLATE.exists():
        raise SystemExit(f"Template nao encontrado: {TEMPLATE}")

    now = dt.datetime.now(TIMEZONE)
    events = [row for row in read_csv("radar_leiloes_eventos_futuros.csv") if is_upcoming(row, now)]
    for event in events:
        if event.get("uf") not in VALID_UFS:
            event["uf"] = ""
    lots = enrich_and_dedupe_lots(read_lotes(), events, now)
    patios = read_csv("radar_leiloes_patios.csv")
    app_version = os.environ.get("RADAR_VERSION") or now.strftime("v%Y.%m.%d.%H%M")
    edital_events = sum(1 for row in events if row.get("link_edital"))
    edital_lots = sum(1 for row in lots if row.get("link_edital"))

    payload = {
        "eventos": events,
        "patios": patios,
        "lotes": lots,
        "gerado_em": now.isoformat(timespec="seconds"),
        "proxima_atualizacao": "Diariamente às 16h (horário de Brasília)",
        "mapa": MAP_EMBED_URL,
        "versao": app_version,
        "editais_eventos": edital_events,
        "lotes_com_edital": edital_lots,
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = TEMPLATE.read_text(encoding="utf-8")
    if "__RADAR_DATA__" not in template:
        raise SystemExit("O marcador __RADAR_DATA__ nao existe no template.")
    html = template.replace("__RADAR_DATA__", data)
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    (ROOT / "radar-leiloes.html").write_text(
        "<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\">"
        "<meta http-equiv=\"refresh\" content=\"0;url=./\">"
        "<title>Radar de Leilões G MAQUINA</title>"
        "<p>Abrindo o <a href=\"./\">Radar de Leilões</a>...</p></html>\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "gerado_em": payload["gerado_em"],
                "eventos_futuros": len(events),
                "lotes_futuros": len(lots),
                "lotes_com_edital": edital_lots,
                "versao": app_version,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
