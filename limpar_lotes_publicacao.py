#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import urllib.parse
from pathlib import Path

import indexador_lotes as idx

ROOT = Path(__file__).resolve().parent
JSON_PATH = ROOT / "lotes.json"
CSV_PATH = ROOT / "lotes.csv"

NAV_TITLES = {
    "clique aqui", "pessoa fisica", "pessoa física", "pessoa juridica", "pessoa jurídica",
    "alliance leiloes", "alliance leilões", "quem somos", "indique-nos", "fale conosco",
    "impressao", "impressão", "termos de uso", "como participar", "quero vender",
    "quero comprar", "catalogo", "catálogo", "pagina inicial", "página inicial",
    "esqueci minha senha", "lembrar senha", "recuperar senha", "login", "entrar",
    "cadastre-se", "cadastro", "minha conta", "contato", "home", "inicio", "início",
}
IMAGE_RE = re.compile(r"\.(?:jpe?g|png|gif|webp|svg)(?:$|\?)", re.I)
ZERO_ITEMS_RE = re.compile(r"\b0\s+itens?\b", re.I)
ITEM_DETAIL_RE = re.compile(r"/item/\d+/detalhes", re.I)
LOT_ID_RE = re.compile(r"/lote_id/\d+", re.I)
LOT_URL_RE = re.compile(r"/(?:leilao/)?lote/\d+|/lotes/lotes/|/oferta/", re.I)
LEGAL_PDF_RE = re.compile(r"presente edital|termo de consentimento|assinatura do arrematante|modelo\s+[ivx]+", re.I)


def clean(value: object) -> str:
    return idx.clean_text(str(value or ""))


def simplify_js_title(title: str) -> str:
    if "$(" not in title or "LOTE" not in title.upper():
        return title
    pos = title.upper().find("LOTE")
    text = title[pos:]
    # Portais podem repetir o mesmo título 2 ou 3 vezes no HTML.
    match = re.match(r"(LOTE\s+\d+\s*[-–—:]\s*.+?)(?=\s+LOTE\s+\d+\s*[-–—:]|$)", text, re.I)
    return clean(match.group(1) if match else text)[:240]


def same_event_url(row: dict) -> bool:
    a = idx.canonical_event_url(str(row.get("link_evento") or ""))
    b = idx.canonical_event_url(str(row.get("link_lote") or ""))
    return bool(a and b and a == b)


def is_real(row: dict) -> bool:
    title = clean(row.get("titulo"))
    if not title:
        return False
    folded = title.casefold()
    if folded in NAV_TITLES or ZERO_ITEMS_RE.search(title):
        return False

    link = str(row.get("link_lote") or "")
    parsed = urllib.parse.urlsplit(link)
    path = parsed.path
    if IMAGE_RE.search(path):
        return False

    # Trechos jurídicos de edital que começam com "Lote 4" não são bens.
    if LEGAL_PDF_RE.search(title + " " + clean(row.get("descricao"))):
        return False

    number = clean(row.get("lote"))
    price = clean(row.get("lance_atual"))
    explicit = bool(number or price or re.search(r"\bLOTE\s*[:#º°-]?\s*\d+", title, re.I))
    item_path = bool(ITEM_DETAIL_RE.search(path) or LOT_ID_RE.search(path) or LOT_URL_RE.search(path))

    if same_event_url(row) and not explicit:
        return False
    if title.casefold() == "detalhes do lote":
        return bool(ITEM_DETAIL_RE.search(path))
    return explicit or item_path


def quality(row: dict) -> tuple[int, int, int, int]:
    title = clean(row.get("titulo"))
    generic = title.casefold() in {"detalhes do lote", "lote"} or bool(re.fullmatch(r"LOTE\s+\d+", title, re.I))
    return (
        0 if generic else 1,
        1 if clean(row.get("descricao")) else 0,
        1 if clean(row.get("lance_atual")) else 0,
        len(title),
    )


def dedupe_key(row: dict) -> str:
    link = str(row.get("link_lote") or "")
    if link:
        try:
            p = urllib.parse.urlsplit(link)
            query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if k.casefold() not in {"page", "utm_source", "utm_medium", "utm_campaign"}]
            normalized = urllib.parse.urlunsplit((p.scheme.casefold(), p.netloc.casefold(), p.path.rstrip("/"), urllib.parse.urlencode(query), p.fragment))
            return "url:" + normalized
        except Exception:
            pass
    return idx.stable_lot_key(row)


def write_csv(rows: list[dict]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=idx.FIELDS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in idx.FIELDS})


def main() -> None:
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    source = payload.get("lotes", []) if isinstance(payload, dict) else []
    source = [dict(row) for row in source if isinstance(row, dict)]

    kept: dict[str, dict] = {}
    removed = 0
    for row in source:
        row["titulo"] = simplify_js_title(clean(row.get("titulo")))
        if not is_real(row):
            removed += 1
            continue
        key = dedupe_key(row)
        if not key:
            removed += 1
            continue
        current = kept.get(key)
        if current is None or quality(row) > quality(current):
            kept[key] = row

    rows = list(kept.values())
    rows.sort(key=lambda r: (str(r.get("data") or "9999"), str(r.get("hora") or ""), str(r.get("evento") or ""), str(r.get("lote") or ""), str(r.get("titulo") or "")))
    event_keys = {idx.event_date_key(str(r.get("evento") or ""), str(r.get("data") or "")) for r in rows}
    event_keys.discard("|")

    payload["lotes"] = rows
    payload["total_lotes"] = len(rows)
    payload["eventos_com_lotes"] = len(event_keys)
    payload["eventos_sem_lotes"] = max(0, int(payload.get("total_eventos_lidos") or 0) - len(event_keys))
    payload["limpeza_publicacao"] = {
        "registros_entrada": len(source),
        "falsos_positivos_ou_duplicados_removidos": len(source) - len(rows),
        "registros_publicados": len(rows),
        "eventos_com_lotes": len(event_keys),
    }

    JSON_PATH.write_text(json.dumps(idx.corrigir_dados(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(rows)
    print(json.dumps(payload["limpeza_publicacao"], ensure_ascii=False))


if __name__ == "__main__":
    main()
