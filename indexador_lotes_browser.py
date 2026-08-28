#!/usr/bin/env python3
from __future__ import annotations

import csv
import html
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

import indexador_lotes as idx

ROOT = Path(__file__).resolve().parent
EVENTS_CSV = ROOT / "radar_leiloes_eventos_futuros.csv"
LOTS_JSON = ROOT / "lotes.json"
LOTS_CSV = ROOT / "lotes.csv"
REPORT_JSON = ROOT / "relatorio_browser_lotes.json"
TZ = ZoneInfo("America/Sao_Paulo")

MAX_DESCRIPTION = 12000
MAX_BROWSER_EVENTS = 80
MAX_JSON_RESPONSES = 120

LOT_LINK_RE = re.compile(
    r"/(?:item/\d+/(?:detalhes)?|lote(?:s)?/[^?#]+|leilao/lote/\d+|oferta/[^?#]+|lote_id/\d+)(?:[/?#]|$)",
    re.I,
)
GENERIC_TITLE_RE = re.compile(r"^(?:detalhes do lote|lote|ver lote|saiba mais|abrir lote)$", re.I)
PRICE_RE = re.compile(r"R\$\s*[\d\.]+(?:,\d{2})?", re.I)
LOT_NUMBER_RE = re.compile(r"\bLote\s*(?:n[º°o.]?\s*)?[:#º°-]?\s*([A-Z0-9./-]+)", re.I)
DECLARED_TOTAL_RE = re.compile(r"\bTotal\s+(\d{1,6})\s+Lotes?\b", re.I)


def clean(value: object) -> str:
    return idx.clean_text(str(value or ""))


def load_events() -> list[dict[str, str]]:
    with EVENTS_CSV.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_payload() -> dict:
    try:
        data = json.loads(LOTS_JSON.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if isinstance(data, list):
        return {"lotes": data}
    return data if isinstance(data, dict) else {"lotes": []}


def canonical_event_url(url: str) -> str:
    url = html.unescape(str(url or "")).strip()
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
        query = [
            (k, v)
            for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if k.casefold() not in {
                "page", "pagenumber", "pagesize", "orderby", "preorderby", "searchtype",
                "utm_source", "utm_medium", "utm_campaign", "fbclid", "gclid",
            }
        ]
        return urllib.parse.urlunsplit(
            (parsed.scheme.casefold() or "https", parsed.netloc.casefold().removeprefix("www."), parsed.path.rstrip("/"), urllib.parse.urlencode(query), "")
        )
    except Exception:
        return url


def event_source(event: dict[str, str]) -> str:
    urls = idx.event_urls(event, maximum=8)
    return urls[0] if urls else ""


def lot_key(row: dict) -> str:
    link = str(row.get("link_lote") or "").strip()
    if link:
        try:
            parsed = urllib.parse.urlsplit(link)
            query = [
                (k, v)
                for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
                if k.casefold() not in {"page", "utm_source", "utm_medium", "utm_campaign"}
            ]
            fragment = parsed.fragment if parsed.fragment.casefold().startswith("lote-") else ""
            normalized = urllib.parse.urlunsplit(
                (parsed.scheme.casefold() or "https", parsed.netloc.casefold().removeprefix("www."), parsed.path.rstrip("/"), urllib.parse.urlencode(query), fragment)
            )
            if LOT_LINK_RE.search(parsed.path) or fragment:
                return "url:" + normalized
        except Exception:
            pass
    event_url = canonical_event_url(str(row.get("link_evento") or row.get("fonte") or ""))
    number = clean(row.get("lote")).casefold()
    title = clean(row.get("titulo")).casefold()
    return "fallback:" + "|".join((event_url, number, title[:180]))


def quality(row: dict) -> tuple[int, int, int, int, int]:
    title = clean(row.get("titulo"))
    desc = clean(row.get("descricao"))
    generic = bool(GENERIC_TITLE_RE.fullmatch(title)) or not title
    return (
        1 if clean(row.get("lote")) else 0,
        0 if generic else 1,
        1 if clean(row.get("lance_atual")) else 0,
        1 if clean(row.get("foto_lote")) else 0,
        len(desc) + len(title),
    )


def merge_row(current: dict | None, new: dict) -> dict:
    if current is None:
        return new
    best, other = (new, current) if quality(new) > quality(current) else (current, new)
    merged = dict(best)
    for field in idx.FIELDS:
        if not merged.get(field) and other.get(field):
            merged[field] = other[field]
    if len(clean(other.get("descricao"))) > len(clean(merged.get("descricao"))):
        merged["descricao"] = other.get("descricao", "")
    if GENERIC_TITLE_RE.fullmatch(clean(merged.get("titulo"))) and not GENERIC_TITLE_RE.fullmatch(clean(other.get("titulo"))):
        merged["titulo"] = other.get("titulo", "")
    return merged


def event_base(event: dict[str, str], source: str, status: str) -> dict[str, str]:
    return idx.event_base(event, source, source, status)


def extract_number(text: str) -> str:
    match = LOT_NUMBER_RE.search(text or "")
    return clean(match.group(1)).upper() if match else ""


def title_from_card(text: str, number: str) -> str:
    value = clean(text)
    if number:
        value = re.sub(rf"^.*?\bLote\s*(?:n[º°o.]?\s*)?[:#º°-]?\s*{re.escape(number)}\b", "", value, count=1, flags=re.I)
    value = re.sub(r"\b(?:Aberto para Lances|Em Andamento|Encerrado|Detalhes do Lote)\b.*$", "", value, flags=re.I)
    value = re.sub(r"\b(?:Maior Lance|Lance Inicial|Lance Atual)\b.*$", "", value, flags=re.I)
    value = clean(value)
    if "Descrição:" in value:
        value = clean(value.split("Descrição:", 1)[0])
    return value[:320]


def card_rows(event: dict[str, str], source: str, page: Page) -> list[dict[str, str]]:
    script = r"""
    () => {
      const out = [];
      const rx = /\/(?:item\/\d+|lote(?:s)?\/|leilao\/lote\/\d+|oferta\/|lote_id\/\d+)/i;
      const links = [...document.querySelectorAll('a[href]')].filter(a => rx.test(a.href));
      for (const a of links) {
        let node = a;
        let chosen = a.parentElement;
        for (let i = 0; i < 7 && node; i++, node = node.parentElement) {
          const text = (node.innerText || '').trim();
          if (text.length >= 20 && text.length <= 12000 && (/\blote\s*[#º°:-]?\s*[a-z0-9]/i.test(text) || /R\$\s*[\d.]+/i.test(text))) {
            chosen = node;
          }
        }
        const text = ((chosen && chosen.innerText) || a.innerText || '').trim();
        const img = chosen ? chosen.querySelector('img') : null;
        out.push({href: a.href, anchor: (a.innerText || '').trim(), text, img: img ? (img.currentSrc || img.src || '') : ''});
      }
      return out;
    }
    """
    try:
        cards = page.evaluate(script)
    except Exception:
        return []
    if not isinstance(cards, list):
        return []
    base = event_base(event, source, "browser_dom_ok")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        href = str(card.get("href") or "")
        if not href or not LOT_LINK_RE.search(urllib.parse.urlsplit(href).path):
            continue
        text = clean(card.get("text"))
        anchor = clean(card.get("anchor"))
        if len(text) < 8:
            text = anchor
        number = extract_number(text) or extract_number(anchor)
        title = title_from_card(text, number)
        if not title or GENERIC_TITLE_RE.fullmatch(title):
            title = clean(anchor)
        if not title or GENERIC_TITLE_RE.fullmatch(title):
            # Mantém a linha; a rotina de merge pode enriquecê-la com outra fonte.
            title = f"Lote {number}" if number else "Detalhes do Lote"
        price = PRICE_RE.search(text)
        row = {
            **base,
            "titulo": title[:320],
            "descricao": text[:MAX_DESCRIPTION],
            "lance_atual": price.group(0) if price else "",
            "lote": number,
            "link_lote": href,
            "foto_lote": idx.valid_image_url(str(card.get("img") or ""), source),
        }
        key = lot_key(row)
        if key not in seen:
            seen.add(key)
            rows.append(row)
    return rows


def text_rows(event: dict[str, str], source: str, page: Page) -> list[dict[str, str]]:
    try:
        text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        return []
    rows = idx.lot_rows_from_text(event, source, source, text, "browser_texto_ok", maximum=5000)
    for row in rows:
        row["descricao"] = clean(row.get("descricao"))[:MAX_DESCRIPTION]
    return rows


def number_from_dict(item: dict) -> str:
    for key in ("lotNumberDesc", "lotNumber", "numeroLote", "numero_lote", "lot", "lote", "number", "numero"):
        value = item.get(key)
        if value not in (None, "", []):
            return clean(value).upper()
    return ""


def description_from_dict(item: dict) -> str:
    parts: list[str] = []
    for key in (
        "description", "descricao", "shortDescription", "longDescription", "lotDescription",
        "productDescription", "details", "observacao", "observacoes", "additionalInfo",
    ):
        value = item.get(key)
        if isinstance(value, (str, int, float)) and clean(value):
            parts.append(clean(value))
    return clean(" | ".join(dict.fromkeys(parts)))[:MAX_DESCRIPTION]


def json_rows(event: dict[str, str], source: str, captured: list[tuple[str, object]]) -> list[dict[str, str]]:
    base = event_base(event, source, "browser_json_ok")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for response_url, data in captured:
        for item in idx.walk_json(data):
            if not isinstance(item, dict):
                continue
            title = idx.text_from_dict(item)
            number = number_from_dict(item) or idx.lot_number(title)
            link = idx.url_from_dict(item, source)
            path = urllib.parse.urlsplit(link).path if link else ""
            if not title:
                continue
            if not number and not (link and LOT_LINK_RE.search(path)):
                continue
            price = idx.price_from_dict(item)
            row = {
                **base,
                "titulo": clean(title)[:320],
                "descricao": description_from_dict(item),
                "lance_atual": price,
                "lote": number,
                "link_lote": link or source,
                "foto_lote": idx.image_from_dict(item, response_url or source),
                "fonte": response_url or source,
            }
            key = lot_key(row)
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def capture_page(context: BrowserContext, event: dict[str, str], source: str) -> tuple[list[dict[str, str]], dict]:
    captured_json: list[tuple[str, object]] = []
    page = context.new_page()

    def on_response(response) -> None:
        if len(captured_json) >= MAX_JSON_RESPONSES or response.status != 200:
            return
        ctype = (response.headers.get("content-type") or "").casefold()
        url_low = response.url.casefold()
        if "json" not in ctype and not any(token in url_low for token in ("api", "offer", "lote", "lot", "item", "auction")):
            return
        try:
            data = response.json()
        except Exception:
            return
        if isinstance(data, (dict, list)):
            captured_json.append((response.url, data))

    page.on("response", on_response)
    status = 0
    error = ""
    declared_total = 0
    try:
        response = page.goto(source, wait_until="domcontentloaded", timeout=45000)
        status = response.status if response else 0
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except PlaywrightTimeoutError:
            pass
        # Dispara lazy-loading e paginações/infinite scroll que dependem do viewport.
        for _ in range(5):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(650)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(400)

        body_text = ""
        try:
            body_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            pass
        declared = DECLARED_TOTAL_RE.search(body_text)
        declared_total = int(declared.group(1)) if declared else 0

        html_text = page.content()
        rows = idx.extract_lots_from_page(event, source, html_text, page.url, "browser_html_ok")
        rows.extend(card_rows(event, source, page))
        rows.extend(text_rows(event, source, page))
        rows.extend(json_rows(event, source, captured_json))
    except Exception as exc:
        rows = []
        error = clean(exc)[:500]
    finally:
        page.close()

    merged: dict[str, dict] = {}
    for row in rows:
        row["descricao"] = clean(row.get("descricao"))[:MAX_DESCRIPTION]
        key = lot_key(row)
        if key:
            merged[key] = merge_row(merged.get(key), row)
    return list(merged.values()), {
        "url": source,
        "http": status,
        "lotes_browser": len(merged),
        "total_declarado_na_pagina": declared_total,
        "json_responses": len(captured_json),
        "erro": error,
    }


def direct_pdf_rows(event: dict[str, str], source: str) -> tuple[list[dict[str, str]], dict]:
    code, raw, ctype, final_url = idx.fetch_bytes(source, timeout=max(20, idx.REQUEST_TIMEOUT), max_bytes=max(idx.PDF_MAX_BYTES, 50_000_000))
    is_pdf = raw.startswith(b"%PDF-") or "pdf" in (ctype or "").casefold()
    rows: list[dict[str, str]] = []
    error = ""
    if code == 200 and is_pdf:
        try:
            rows = idx.extract_lots_from_pdf(event, source, final_url or source, raw)
        except Exception as exc:
            error = clean(exc)[:500]
    return rows, {
        "url": source,
        "http": code,
        "pdf": is_pdf,
        "lotes_pdf": len(rows),
        "erro": error,
    }


def write_csv(rows: list[dict]) -> None:
    with LOTS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=idx.FIELDS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in idx.FIELDS})


def main() -> None:
    events = load_events()
    payload = load_payload()
    existing = [dict(row) for row in payload.get("lotes", []) if isinstance(row, dict)]
    merged: dict[str, dict] = {}
    for row in existing:
        key = lot_key(row)
        if key:
            merged[key] = merge_row(merged.get(key), row)

    # Um mesmo leilão pode aparecer em mais de um marcador/pátio. Navega uma única vez
    # por URL/data, sem deixar de manter todos os registros do mapa no frontend.
    unique_events: list[tuple[dict[str, str], str]] = []
    seen_events: set[str] = set()
    for event in events:
        source = event_source(event)
        if not source:
            continue
        key = canonical_event_url(source) + "|" + clean(event.get("data"))
        if key in seen_events:
            continue
        seen_events.add(key)
        unique_events.append((event, source))

    logs: list[dict] = []
    before = len(merged)
    browser_candidates = [(event, source) for event, source in unique_events if "drive.google.com" not in idx.domain(source) and not idx.PDF_RE.search(source)]
    pdf_candidates = [(event, source) for event, source in unique_events if "drive.google.com" in idx.domain(source) or idx.PDF_RE.search(source)]

    # PDFs/Google Drive primeiro: não precisam do Chromium.
    for event, source in pdf_candidates:
        rows, log = direct_pdf_rows(event, source)
        log.update({"evento": event.get("nome", ""), "data": event.get("data", ""), "modo": "pdf"})
        logs.append(log)
        for row in rows:
            key = lot_key(row)
            if key:
                merged[key] = merge_row(merged.get(key), row)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1440, "height": 1100},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "DNT": "1",
            },
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        for event, source in browser_candidates[:MAX_BROWSER_EVENTS]:
            rows, log = capture_page(context, event, source)
            log.update({"evento": event.get("nome", ""), "data": event.get("data", ""), "modo": "browser"})
            logs.append(log)
            for row in rows:
                key = lot_key(row)
                if key:
                    merged[key] = merge_row(merged.get(key), row)
        context.close()
        browser.close()

    rows = list(merged.values())
    rows.sort(
        key=lambda row: (
            str(row.get("data") or "9999-99-99"),
            str(row.get("hora") or "23:59"),
            str(row.get("evento") or ""),
            str(row.get("lote") or ""),
            str(row.get("titulo") or ""),
        )
    )

    event_keys = {
        idx.event_date_key(str(row.get("evento") or ""), str(row.get("data") or ""))
        for row in rows
        if idx.event_date_key(str(row.get("evento") or ""), str(row.get("data") or ""))
    }
    now = datetime.now(TZ).isoformat(timespec="seconds")
    declared_shortfalls = [
        log for log in logs
        if int(log.get("total_declarado_na_pagina") or 0) > 0
        and int(log.get("lotes_browser") or 0) < int(log.get("total_declarado_na_pagina") or 0)
    ]

    payload.update(
        {
            "atualizado_em": now,
            "total_lotes": len(rows),
            "eventos_com_lotes": len(event_keys),
            "captura_browser": {
                "executado_em": now,
                "lotes_antes": before,
                "lotes_depois": len(rows),
                "lotes_adicionados_ou_enriquecidos": max(0, len(rows) - before),
                "eventos_unicos_processados": len(unique_events),
                "paginas_browser": len(browser_candidates[:MAX_BROWSER_EVENTS]),
                "fontes_pdf": len(pdf_candidates),
                "paginas_com_total_declarado_incompleto": len(declared_shortfalls),
            },
            "lotes": rows,
        }
    )
    LOTS_JSON.write_text(json.dumps(idx.corrigir_dados(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(rows)
    REPORT_JSON.write_text(
        json.dumps(
            {
                "executado_em": now,
                "lotes_antes": before,
                "lotes_depois": len(rows),
                "eventos_unicos": len(unique_events),
                "shortfalls": declared_shortfalls,
                "logs": logs,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["captura_browser"], ensure_ascii=False))


if __name__ == "__main__":
    main()
