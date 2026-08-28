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
    "telefone", "whatsapp", "facebook", "instagram", "linkedin", "twitter", "youtube",
    "e-mail", "email", "site", "endereço", "endereco", "mapa", "política de privacidade",
    "politica de privacidade", "receba nosso informativo", "dê seu lance", "de seu lance",
}
IMAGE_RE = re.compile(r"\.(?:jpe?g|png|gif|webp|svg)(?:$|\?)", re.I)
ZERO_ITEMS_RE = re.compile(r"\b0\s+itens?\b", re.I)
ITEM_DETAIL_RE = re.compile(r"/item/\d+/(?:detalhes)?", re.I)
LOT_ID_RE = re.compile(r"/lote_id/\d+", re.I)
LOT_URL_RE = re.compile(r"/(?:leilao/)?lote/\d+|/lotes/lotes/|/oferta/", re.I)
NAV_PATH_RE = re.compile(
    r"/(?:login|entrar|cadastro|cadastre-se|register|signup|forgot|password|contato|fale-conosco|"
    r"quero-vender|quero-comprar|indique-nos|pagina-inicial|termos|politica-de-privacidade)(?:/|$)",
    re.I,
)
SOCIAL_HOST_RE = re.compile(r"(?:facebook\.com|instagram\.com|twitter\.com|x\.com|whatsapp\.com|youtube\.com)$", re.I)
LEGAL_PDF_RE = re.compile(r"presente edital|termo de consentimento|assinatura do arrematante|modelo\s+[ivx]+", re.I)
PHONE_RE = re.compile(r"^\(?\d{2}\)?\s*9?\d{4}[-\s]?\d{4}$")


def clean(value: object) -> str:
    return idx.clean_text(str(value or ""))


def simplify_js_title(title: str) -> str:
    if "$(" not in title or "LOTE" not in title.upper():
        return title
    pos = title.upper().find("LOTE")
    text = title[pos:]
    match = re.match(r"(LOTE\s+\d+\s*[-–—:]\s*.+?)(?=\s+LOTE\s+\d+\s*[-–—:]|$)", text, re.I)
    return clean(match.group(1) if match else text)[:400]


def canonical_event(row: dict) -> str:
    return idx.canonical_event_url(str(row.get("link_evento") or row.get("fonte") or ""))


def same_event_url(row: dict) -> bool:
    a = canonical_event(row)
    b = idx.canonical_event_url(str(row.get("link_lote") or ""))
    return bool(a and b and a == b)


def normalize_number(row: dict) -> None:
    number = clean(row.get("lote"))
    text = clean(row.get("titulo")) + " " + clean(row.get("descricao"))
    # Capturadores genéricos às vezes interpretam "Lote Urbano" como número URBANO.
    if number and not re.search(r"\d", number):
        number = ""
    # Prefere padrões explícitos próximos ao número de lote exibido no card.
    candidates = [
        r"[•|]\s*Lote\s+(\d+(?:[-./]\d+)*)\b",
        r"\bLote\s+(\d+(?:[-./]\d+)*)\b",
        r"\bLOTE\s*[:#º°-]?\s*(\d+(?:[-./]\d+)*)\b",
    ]
    for pattern in candidates:
        match = re.search(pattern, text, re.I)
        if match:
            number = match.group(1)
            break
    row["lote"] = number


def is_real(row: dict) -> bool:
    title = clean(row.get("titulo"))
    if not title:
        return False
    folded = title.casefold()
    if folded in NAV_TITLES or ZERO_ITEMS_RE.search(title):
        return False
    if folded.startswith("envie seu lance") and not re.search(r"\b(?:veículo|veiculo|caminh|trator|máquina|maquina|lote)\b", folded):
        return False

    link = str(row.get("link_lote") or "")
    parsed = urllib.parse.urlsplit(link)
    path = parsed.path
    host = parsed.netloc.casefold().removeprefix("www.")
    source = str(row.get("fonte") or "").casefold()
    if "style.config.json" in source or "siteconfig.superbid.net" in source:
        return False
    if IMAGE_RE.search(path) or NAV_PATH_RE.search(path) or SOCIAL_HOST_RE.search(host):
        return False

    if LEGAL_PDF_RE.search(title + " " + clean(row.get("descricao"))):
        return False

    number = clean(row.get("lote"))
    if PHONE_RE.fullmatch(number):
        return False
    price = clean(row.get("lance_atual"))
    explicit = bool(number or price or re.search(r"\bLOTE\s*[:#º°-]?\s*\d+", title, re.I))
    item_path = bool(ITEM_DETAIL_RE.search(path) or LOT_ID_RE.search(path) or LOT_URL_RE.search(path))

    if same_event_url(row) and not explicit:
        return False
    if title.casefold() == "detalhes do lote":
        return bool(ITEM_DETAIL_RE.search(path))
    return explicit or item_path


def quality(row: dict) -> tuple[int, int, int, int, int]:
    title = clean(row.get("titulo"))
    generic = title.casefold() in {"detalhes do lote", "lote"} or bool(re.fullmatch(r"LOTE\s+\d+", title, re.I))
    return (
        0 if generic else 1,
        1 if clean(row.get("lote")) else 0,
        1 if clean(row.get("descricao")) else 0,
        1 if clean(row.get("lance_atual")) else 0,
        len(title),
    )


def dedupe_key(row: dict) -> str:
    event = canonical_event(row)
    link = str(row.get("link_lote") or "")
    try:
        p = urllib.parse.urlsplit(link)
        host = p.netloc.casefold().removeprefix("www.")
        path = p.path.rstrip("/")
        for pattern, label in (
            (r"/item/(\d+)", "item"),
            (r"/leilao/lote/(\d+)", "lote"),
            (r"/lote_id/(\d+)", "lote"),
            (r"/oferta/.+-(\d+)$", "oferta"),
        ):
            match = re.search(pattern, path, re.I)
            if match:
                return f"{host}:{label}:{match.group(1)}"
        # Alliance usa /lotes/<slug> e /lotes/lotes/<slug> para o mesmo bem.
        match = re.search(r"/lotes/(?:lotes/)?([^/]+)$", path, re.I)
        if match and match.group(1) not in {"login", "cadastro", "pagina-inicial"}:
            return f"{host}:slug:{match.group(1).casefold()}"
        query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if k.casefold() not in {"page", "utm_source", "utm_medium", "utm_campaign"}]
        normalized = urllib.parse.urlunsplit((p.scheme.casefold(), host, path, urllib.parse.urlencode(query), ""))
        if normalized:
            return "url:" + normalized
    except Exception:
        pass
    number = clean(row.get("lote")).casefold()
    if event and number and re.search(r"\d", number):
        return f"event:{event}|lot:{number}"
    return idx.stable_lot_key(row)


def merge_rows(current: dict, candidate: dict) -> dict:
    best, other = (candidate, current) if quality(candidate) > quality(current) else (current, candidate)
    merged = dict(best)
    for field in idx.FIELDS:
        if not merged.get(field) and other.get(field):
            merged[field] = other[field]
    if len(clean(other.get("descricao"))) > len(clean(merged.get("descricao"))):
        merged["descricao"] = other.get("descricao", "")
    return merged


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
    for row in source:
        row["titulo"] = simplify_js_title(clean(row.get("titulo")))
        normalize_number(row)
        if not is_real(row):
            continue
        key = dedupe_key(row)
        if not key:
            continue
        current = kept.get(key)
        kept[key] = row if current is None else merge_rows(current, row)

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
