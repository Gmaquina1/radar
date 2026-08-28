#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import indexador_lotes as idx

ROOT = Path(__file__).resolve().parent
EVENTS_CSV = ROOT / "radar_leiloes_eventos_futuros.csv"
LOTS_JSON = ROOT / "lotes.json"
LOTS_CSV = ROOT / "lotes.csv"
REPORT_JSON = ROOT / "relatorio_complemento_lotes.json"
TZ = ZoneInfo("America/Sao_Paulo")

SUPERBID_COMPATIBLE = {
    "argonetworkleiloes.com.br",
    "eckertleiloes.com.br",
    "sold.com.br",
    "superbid.net",
    "superbid.com.br",
}

NAV_TITLE_RE = re.compile(
    r"^(?:esqueci(?: minha)? senha|lembrar senha|recuperar senha|login|entrar|cadastre-se|cadastro|"
    r"criar conta|minha conta|meus dados|contato|home|inicio|início|termos|politica de privacidade|"
    r"política de privacidade|whatsapp|facebook|instagram|linkedin|ver todos|voltar)$",
    re.I,
)
NAV_URL_RE = re.compile(
    r"/(?:login|entrar|cadastro|register|signup|lembrar-senha|recuperar-senha|forgot|password|contato|"
    r"politica-de-privacidade|termos)(?:/|$|\?)",
    re.I,
)
TOTAL_LOTS_RE = re.compile(r"\btotal\s+(\d{1,6})\s+lotes?\b", re.I)


def load_events() -> list[dict[str, str]]:
    with EVENTS_CSV.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_payload() -> dict:
    try:
        data = json.loads(LOTS_JSON.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {"lotes": data if isinstance(data, list) else []}


def event_key(row: dict[str, str]) -> str:
    return idx.event_date_key(str(row.get("evento") or row.get("nome") or ""), str(row.get("data") or ""))


def merge_key(row: dict[str, str]) -> str:
    number = idx.clean_text(row.get("lote", "")).casefold()
    key = event_key(row)
    if number and key:
        return f"evento:{key}|lote:{number}"
    return idx.stable_lot_key(row)


def is_real_lot(row: dict[str, str]) -> bool:
    title = idx.clean_text(row.get("titulo", ""))
    if not idx.valid_lot(row) or NAV_TITLE_RE.fullmatch(title):
        return False
    link = str(row.get("link_lote") or "")
    parsed = urllib.parse.urlparse(link)
    if NAV_URL_RE.search(parsed.path + "?" + parsed.query):
        return False
    number = idx.clean_text(row.get("lote", ""))
    price = idx.clean_text(row.get("lance_atual", ""))
    text = (title + " " + idx.clean_text(row.get("descricao", ""))).casefold()
    explicit_lot = bool(number or price or re.search(r"\blote\s*[:#º°-]?\s*\d+", text, re.I))
    lotish_path = bool(re.search(r"/(?:lote|lotes|oferta|item|produto|veiculo|maquina)(?:/|$)", parsed.path, re.I))
    return explicit_lot or (lotish_path and len(title) >= 8)


def official_variants(url: str) -> list[str]:
    variants = [url]
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if not any(k.casefold() == "page" for k, _ in query):
        variants.append(
            urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query + [("page", "1")]), parsed.fragment)
            )
        )
    if parsed.path.endswith("/lotes"):
        variants.append(url.rstrip("/") + "/?page=1")
    return list(dict.fromkeys(variants))


def decode(raw: bytes, content_type: str) -> str:
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if match:
        charset = match.group(1)
    return raw.decode(charset, errors="replace")


def reader_url(url: str) -> str:
    return "https://r.jina.ai/" + url


def parse_reader(event: dict[str, str], official_url: str) -> tuple[list[dict[str, str]], int]:
    code, raw, content_type, _ = idx.fetch_bytes(
        reader_url(official_url), timeout=max(20, idx.REQUEST_TIMEOUT), max_bytes=idx.PDF_MAX_BYTES
    )
    text = decode(raw, content_type)
    if code != 200 or not text.strip():
        return [], code
    rows = idx.lot_rows_from_text(event, official_url, official_url, text, "reader_oficial_ok", maximum=3000)
    for row in rows:
        row["fonte"] = official_url
        row["link_evento"] = official_url
        row["status_captura"] = "reader_oficial_ok"
    return rows, code


def extract_total(page: str) -> int:
    match = TOTAL_LOTS_RE.search(idx.clean_text(page))
    return int(match.group(1)) if match else 0


def collect_html_pages(event: dict[str, str], official_url: str) -> tuple[list[dict[str, str]], list[dict]]:
    attempts: list[dict] = []
    rows: list[dict[str, str]] = []
    first_page_text = ""
    first_working_url = official_url

    for candidate in official_variants(official_url):
        code, raw, content_type, final_url = idx.fetch_bytes(candidate)
        page = decode(raw, content_type)
        status = idx.capture_status(code, page)
        parsed = idx.extract_lots_from_page(event, official_url, page, final_url or candidate, status) if code == 200 else []
        attempts.append({"url": candidate, "http": code, "status": status, "lotes": len(parsed)})
        if code == 200:
            first_page_text = page
            first_working_url = final_url or candidate
        if parsed:
            rows.extend(parsed)
            break

    total = extract_total(first_page_text)
    if total and len(rows) < total:
        page_size_guess = max(10, len(rows) or 20)
        max_pages = min(60, max(2, math.ceil(total / page_size_guess) + 3))
        empty_streak = 0
        for page_number in range(2, max_pages + 1):
            parsed_url = urllib.parse.urlsplit(first_working_url)
            query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed_url.query, keep_blank_values=True) if k.casefold() != "page"]
            query.append(("page", str(page_number)))
            page_url = urllib.parse.urlunsplit(
                (parsed_url.scheme, parsed_url.netloc, parsed_url.path, urllib.parse.urlencode(query), parsed_url.fragment)
            )
            code, raw, content_type, final_url = idx.fetch_bytes(page_url)
            page = decode(raw, content_type)
            status = idx.capture_status(code, page)
            parsed_rows = idx.extract_lots_from_page(event, official_url, page, final_url or page_url, status) if code == 200 else []
            attempts.append({"url": page_url, "http": code, "status": status, "lotes": len(parsed_rows)})
            if parsed_rows:
                rows.extend(parsed_rows)
                empty_streak = 0
            else:
                empty_streak += 1
            if len({merge_key(r) for r in rows if merge_key(r)}) >= total or empty_streak >= 2:
                break
    return rows, attempts


def collect_event(event: dict[str, str]) -> tuple[list[dict[str, str]], dict]:
    urls = idx.event_urls(event, maximum=8)
    if not urls:
        return [], {"evento": event.get("nome", ""), "status": "sem_link", "tentativas": []}

    collected: list[dict[str, str]] = []
    attempts: list[dict] = []
    for official_url in urls:
        host = idx.domain(official_url)
        event_id = idx.parse_event_id(official_url)

        if event_id and (host in SUPERBID_COMPATIBLE or "/evento/" in urllib.parse.urlparse(official_url).path):
            api_rows, api_status = idx.extract_superbid_lots(event, official_url, official_url, max_pages=50)
            attempts.append({"url": official_url, "status": api_status, "lotes": len(api_rows), "modo": "api"})
            if api_rows:
                collected.extend(api_rows)

        html_rows, html_attempts = collect_html_pages(event, official_url)
        attempts.extend(html_attempts)
        if html_rows:
            collected.extend(html_rows)

        if not collected or any(int(a.get("http") or 0) in {0, 401, 403, 429} for a in html_attempts):
            reader_rows, reader_code = parse_reader(event, official_url)
            attempts.append(
                {"url": official_url, "http": reader_code, "status": "reader_oficial", "lotes": len(reader_rows), "modo": "fallback"}
            )
            if reader_rows:
                collected.extend(reader_rows)
        if collected:
            break

    unique: dict[str, dict[str, str]] = {}
    for row in collected:
        if not is_real_lot(row):
            continue
        key = merge_key(row)
        if key and key not in unique:
            unique[key] = row
    return list(unique.values()), {
        "evento": event.get("nome", ""),
        "data": event.get("data", ""),
        "status": "ok" if unique else "sem_lotes",
        "lotes": len(unique),
        "tentativas": attempts,
    }


def write_csv(rows: list[dict[str, str]]) -> None:
    with LOTS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=idx.FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in idx.FIELDS})


def main() -> None:
    events = load_events()
    payload = load_payload()
    existing = [dict(row) for row in payload.get("lotes", []) if isinstance(row, dict)]
    cleaned_existing = [row for row in existing if is_real_lot(row)]
    by_key: dict[str, dict[str, str]] = {}
    for row in cleaned_existing:
        key = merge_key(row)
        if key:
            by_key[key] = row

    logs: list[dict] = []
    added = 0
    for event in events:
        rows, log = collect_event(event)
        logs.append(log)
        for row in rows:
            key = merge_key(row)
            if not key:
                continue
            if key not in by_key:
                by_key[key] = row
                added += 1
            else:
                current = by_key[key]
                merged = {**row, **current}
                if len(idx.clean_text(row.get("titulo", ""))) > len(idx.clean_text(current.get("titulo", ""))):
                    merged["titulo"] = row.get("titulo", "")
                for field in ("descricao", "lance_atual", "foto_lote", "link_lote", "link_evento", "link_edital"):
                    merged[field] = current.get(field) or row.get(field) or ""
                by_key[key] = merged

    final_rows = list(by_key.values())
    final_rows.sort(
        key=lambda row: (
            row.get("data") or "9999-99-99",
            row.get("hora") or "23:59",
            row.get("uf") or "",
            row.get("evento") or "",
            row.get("lote") or "",
        )
    )
    final_event_keys = {event_key(row) for row in final_rows if event_key(row)}
    all_event_keys = {idx.event_date_key(e.get("nome", ""), e.get("data", "")) for e in events}
    now = datetime.now(TZ).isoformat(timespec="seconds")

    payload.update(
        {
            "atualizado_em": now,
            "total_eventos_lidos": len(events),
            "total_lotes": len(final_rows),
            "eventos_com_lotes": len(final_event_keys),
            "eventos_sem_lotes": max(0, len(all_event_keys) - len(final_event_keys)),
            "fonte_eventos": "google_my_maps",
            "somente_eventos_do_mapa": True,
            "complementacao_oficial": {
                "executado_em": now,
                "lotes_antes": len(existing),
                "falsos_positivos_removidos": len(existing) - len(cleaned_existing),
                "lotes_adicionados": added,
                "lotes_depois": len(final_rows),
                "eventos_processados": len(events),
                "eventos_com_lotes_apos_complemento": len(final_event_keys),
                "regra": "somente links oficiais dos eventos cadastrados no Google My Maps",
            },
            "lotes": final_rows,
        }
    )
    LOTS_JSON.write_text(json.dumps(idx.corrigir_dados(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(final_rows)
    REPORT_JSON.write_text(
        json.dumps(
            {
                "executado_em": now,
                "lotes_antes": len(existing),
                "falsos_positivos_removidos": len(existing) - len(cleaned_existing),
                "lotes_adicionados": added,
                "lotes_depois": len(final_rows),
                "eventos_processados": len(events),
                "eventos_com_lotes": len(final_event_keys),
                "logs": logs,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "lotes_antes": len(existing),
                "falsos_positivos_removidos": len(existing) - len(cleaned_existing),
                "lotes_adicionados": added,
                "lotes_depois": len(final_rows),
                "eventos_com_lotes": len(final_event_keys),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
