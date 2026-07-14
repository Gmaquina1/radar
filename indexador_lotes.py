#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - instalado pelo GitHub Actions
    PdfReader = None


ROOT = Path(__file__).resolve().parent
EVENTOS_CSV = ROOT / "radar_leiloes_eventos_futuros.csv"
LOTES_JSON = ROOT / "lotes.json"
LOTES_CSV = ROOT / "lotes.csv"
TIMEZONE = ZoneInfo("America/Sao_Paulo")

FIELDS = [
    "titulo",
    "descricao",
    "lance_atual",
    "lote",
    "leiloeiro",
    "evento",
    "data",
    "data_original",
    "hora",
    "uf",
    "local",
    "link_evento",
    "link_lote",
    "fonte",
    "capturado_em",
    "status_captura",
]

IGNORE_ANCHORS = {
    "entrar",
    "login",
    "cadastre-se",
    "cadastro",
    "contato",
    "home",
    "inicio",
    "início",
    "proximo",
    "próximo",
    "anterior",
    "termos",
    "politica de privacidade",
    "política de privacidade",
    "whatsapp",
    "facebook",
    "twitter",
    "instagram",
    "linkedin",
    "compartilhar",
    "copiar link",
}

BLOCKED_TITLES = (
    "just a moment",
    "attention required",
    "access denied",
    "403 forbidden",
    "verificando",
    "checking your browser",
)

PRICE_RE = re.compile(r"R\$\s?[\d\.\,]+", re.I)
LOT_RE = re.compile(r"\b(?:lote|lt\.?)\s*[:#º°-]?\s*(\d+[A-Za-z]?)", re.I)
URL_RE = re.compile(r"https?://[^\s<>'\"]+", re.I)
EVENT_ID_RE = re.compile(r"-(\d{5,})(?:[/?#]|$)")
PDF_RE = re.compile(r"\.pdf(?:$|[?#])", re.I)
PDF_LOT_RE = re.compile(
    r"(?im)(?:^|\n)\s*(?:lote|item)\s*(?:n\s*[.º°o]?\s*)?[:#º°\-]?\s*"
    r"(\d{1,5}(?:[.\-/][A-Za-z0-9]{1,5})?[A-Za-z]?)\b"
)
SUPERBID_API = "https://offer-query.superbid.net/offers/"
SUPERBID_LIKE_DOMAINS = (
    "sold.com.br",
    "superbid.net",
    "superbid.com.br",
    "eckertleiloes.com.br",
)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self.title = ""
        self._in_title = False
        self._title_text: list[str] = []
        self._ignored_depth = 0
        self.visible_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag.lower() == "a":
            attrs_dict = {k.lower(): v or "" for k, v in attrs}
            self._href = attrs_dict.get("href")
            self._text = []
        elif tag.lower() == "title":
            self._in_title = True
            self._title_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        if tag.lower() == "a" and self._href:
            text = clean_text(" ".join(self._text))
            if text:
                self.links.append((self._href, text))
            self._href = None
            self._text = []
        elif tag.lower() == "title":
            self._in_title = False
            self.title = clean_text(" ".join(self._title_text))

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)
        if self._in_title:
            self._title_text.append(data)
        if not self._ignored_depth:
            value = clean_text(data)
            if value:
                self.visible_text.append(value)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def slugify(value: str) -> str:
    value = strip_accents(clean_text(value)).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "lote"


def first_url(value: str) -> str:
    urls = URL_RE.findall(value or "")
    return urls[0].rstrip(").,;") if urls else ""


def all_urls(value: str) -> list[str]:
    return [item.rstrip(").,;]") for item in URL_RE.findall(value or "")]


def absolute_url(base: str, url: str) -> str:
    return urllib.parse.urljoin(base, html.unescape(url or ""))


def domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def unwrap_google_url(url: str) -> str:
    """Extrai o destino real de links de redirecionamento do Google."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc.endswith("google.com") and parsed.path == "/url":
            return urllib.parse.parse_qs(parsed.query).get("q", [url])[0]
    except Exception:
        pass
    return url


def event_urls(event: dict[str, str], maximum: int = 4) -> list[str]:
    """Prioriza a pagina do leilao, mas tambem usa editais/PDFs como fonte de lotes."""
    urls: list[str] = []
    for field in ("site_leiloeiro", "link", "link_edital", "descricao"):
        value = event.get(field, "")
        candidates = all_urls(value)
        if not candidates and value.strip().lower().startswith("www."):
            candidates = ["https://" + value.strip()]
        for candidate in candidates:
            candidate = unwrap_google_url(html.unescape(candidate))
            if candidate not in urls:
                urls.append(candidate)

    def priority(url: str) -> tuple[int, int]:
        host = domain(url)
        if is_superbid_like(url):
            return (0, len(url))
        if "drive.google.com" in host or PDF_RE.search(url):
            return (2, len(url))
        if host.endswith("google.com"):
            return (3, len(url))
        return (1, len(url))

    return sorted(urls, key=priority)[:maximum]


def parse_event_id(url: str) -> str:
    parsed = urllib.parse.urlparse(url or "")
    match = EVENT_ID_RE.search(parsed.path)
    if match:
        return match.group(1)
    for part in reversed(parsed.path.split("/")):
        if part.isdigit() and len(part) >= 5:
            return part
    return ""


def is_superbid_like(url: str) -> bool:
    host = domain(url)
    return any(host == item or host.endswith("." + item) for item in SUPERBID_LIKE_DOMAINS)


def read_events(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fetch_bytes(url: str, timeout: int = 12, max_bytes: int = 20_000_000) -> tuple[int, bytes, str, str]:
    if "drive.google.com" in domain(url):
        parsed = urllib.parse.urlparse(url)
        match = re.search(r"/file/d/([^/]+)", parsed.path)
        file_id = match.group(1) if match else urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
        if file_id:
            url = f"https://drive.google.com/uc?export=download&id={file_id}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)[:max_bytes]
            return response.status, raw, response.headers.get("content-type", ""), response.geturl()
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(500_000)
        except Exception:
            raw = b""
        return exc.code, raw, exc.headers.get("content-type", ""), url
    except Exception as exc:
        return 0, str(exc).encode("utf-8", errors="replace"), "", url


def fetch(url: str, timeout: int = 12) -> tuple[int, str, str]:
    status, raw, content_type, final_url = fetch_bytes(url, timeout=timeout)
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if match:
        charset = match.group(1)
    return status, raw.decode(charset, errors="replace"), final_url


def extract_json_blocks(page: str) -> list[object]:
    blocks: list[object] = []
    patterns = [
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, page, flags=re.I | re.S):
            raw = html.unescape(match.group(1)).strip()
            try:
                blocks.append(json.loads(raw))
            except Exception:
                continue
    return blocks


def walk_json(value: object):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk_json(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_json(item)


def text_from_dict(data: dict) -> str:
    keys = [
        "title",
        "titulo",
        "name",
        "nome",
        "description",
        "descricao",
        "shortDescription",
        "lotTitle",
        "productName",
    ]
    parts = [clean_text(str(data.get(key, ""))) for key in keys if data.get(key)]
    return " - ".join(dict.fromkeys(part for part in parts if part))


def price_from_dict(data: dict) -> str:
    for key in ("price", "currentBid", "lanceAtual", "minimumBid", "valor", "amount"):
        if key in data and data[key] not in ("", None):
            value = str(data[key])
            if value.startswith("R$"):
                return value
            if re.fullmatch(r"[\d\.,]+", value):
                return "R$ " + value
    text = json.dumps(data, ensure_ascii=False)
    match = PRICE_RE.search(text)
    return match.group(0) if match else ""


def url_from_dict(data: dict, base_url: str) -> str:
    for key in ("url", "link", "href", "permalink", "lotUrl"):
        if data.get(key):
            return absolute_url(base_url, str(data[key]))
    return ""


def lot_number(value: str) -> str:
    match = LOT_RE.search(value or "")
    return match.group(1) if match else ""


def parse_api_datetime(value: str) -> tuple[str, str]:
    match = re.search(r"(\d{4}-\d{2}-\d{2})[ T](\d{1,2}:\d{2})", value or "")
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def product_location(product: dict) -> str:
    location = product.get("location") or {}
    if not isinstance(location, dict):
        return ""
    parts = [
        location.get("address"),
        location.get("city"),
        location.get("stateCode"),
        location.get("state"),
    ]
    return clean_text(", ".join(str(part) for part in parts if part))


def offer_title(offer: dict) -> str:
    product = offer.get("product") or {}
    if not isinstance(product, dict):
        product = {}
    detail = offer.get("offerDetail") or {}
    if not isinstance(detail, dict):
        detail = {}
    for value in (
        product.get("shortDesc"),
        product.get("description"),
        offer.get("title"),
        detail.get("title"),
        detail.get("description"),
    ):
        title = clean_text(str(value or ""))
        if title:
            return title
    offer_id = str(offer.get("id") or "").strip()
    return f"Lote {offer_id}" if offer_id else ""


def offer_description(offer: dict) -> str:
    product = offer.get("product") or {}
    if not isinstance(product, dict):
        product = {}
    offer_desc = offer.get("offerDescription")
    if isinstance(offer_desc, dict):
        offer_desc = offer_desc.get("offerDescription") or offer_desc.get("description")
    parts = [
        offer_desc,
        product.get("description"),
        product.get("productTypeDescription"),
        product.get("categoryDescription"),
    ]
    return clean_text(" | ".join(str(part) for part in parts if part))[:600]


def offer_link(source_url: str, offer: dict, title: str) -> str:
    offer_id = str(offer.get("id") or "").strip()
    if not offer_id:
        return source_url
    parsed = urllib.parse.urlparse(source_url)
    host = parsed.netloc or "www.sold.com.br"
    scheme = parsed.scheme or "https"
    return f"{scheme}://{host}/oferta/{slugify(title)}-{offer_id}"


def lot_from_superbid_offer(
    event: dict[str, str],
    link_evento: str,
    source_url: str,
    offer: dict,
    status: str,
) -> dict[str, str] | None:
    title = offer_title(offer)
    if not title:
        return None
    product = offer.get("product") or {}
    if not isinstance(product, dict):
        product = {}
    auction = offer.get("auction") or {}
    if not isinstance(auction, dict):
        auction = {}

    api_date, api_hour = parse_api_datetime(str(offer.get("endDate") or ""))
    local = product_location(product) or event.get("endereco_ou_localizacao", "")
    event_name = event.get("nome", "") or clean_text(str(auction.get("desc") or ""))

    row = {
        **event_base(event, link_evento, source_url, status),
        "titulo": title[:240],
        "descricao": offer_description(offer),
        "lance_atual": clean_text(str(offer.get("priceFormatted") or offer.get("currentBidFormatted") or "")),
        "lote": clean_text(str(offer.get("lotNumberDesc") or offer.get("lotNumber") or "")),
        "evento": event_name,
        "data": api_date or event.get("data", ""),
        "data_original": event.get("data_original", ""),
        "hora": api_hour or event.get("hora_marcador", ""),
        "local": local,
        "link_lote": offer_link(source_url, offer, title),
    }
    return row


def extract_superbid_lots(
    event: dict[str, str],
    link_evento: str,
    source_url: str,
    max_pages: int = 5,
) -> tuple[list[dict[str, str]], str]:
    event_id = parse_event_id(link_evento) or parse_event_id(source_url)
    if not event_id:
        return [], "api_superbid_sem_id_evento"

    lots: list[dict[str, str]] = []
    status = "api_superbid_sem_lotes"
    for page_number in range(max_pages):
        params = {
            "locale": "pt_BR",
            "timeZoneId": "America/Sao_Paulo",
            "portalId": "[2,15]",
            "filter": f"auction.id:{event_id}",
            "searchType": "opened",
            "pageNumber": str(page_number),
            "pageSize": "60",
            "orderBy": "lotNumber:asc;subLotNumber:asc",
        }
        api_url = SUPERBID_API + "?" + urllib.parse.urlencode(params)
        status_code, raw, _ = fetch(api_url)
        status = f"api_superbid_http_{status_code}" if status_code else "api_superbid_erro"
        if status_code != 200:
            break
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            status = "api_superbid_json_invalido"
            break
        offers = data.get("offers") or []
        if not isinstance(offers, list) or not offers:
            break
        for offer in offers:
            if isinstance(offer, dict):
                row = lot_from_superbid_offer(event, link_evento, source_url, offer, status)
                if row:
                    lots.append(row)
        total = int(data.get("total") or 0)
        if len(lots) >= total or len(offers) < 60:
            break
    if lots:
        status = "api_superbid_ok"
        for row in lots:
            row["status_captura"] = status
    return lots, status


def looks_like_lot(text: str, url: str = "") -> bool:
    low = clean_text(text).casefold()
    path = urllib.parse.urlparse(url).path.casefold()
    query = urllib.parse.urlparse(url).query.casefold()
    if len(low) < 5:
        return False
    if low in IGNORE_ANCHORS:
        return False
    host = domain(url)
    if any(item in host for item in ("whatsapp.com", "facebook.com", "twitter.com", "x.com", "linkedin.com")):
        return False
    if LOT_RE.search(low) or PRICE_RE.search(text):
        return True
    if any(part in path for part in ("/lote", "/oferta", "/item", "/produto/", "/veiculo/", "/maquina/")):
        return True
    if "lot" in query and "evento" not in path:
        return True
    return False


def capture_status(status_code: int, page: str) -> str:
    status = f"http_{status_code}" if status_code else "erro"
    low = clean_text(page[:3000]).casefold()
    if status_code in {401, 403, 429}:
        return f"bloqueado_{status}"
    if any(title in low for title in BLOCKED_TITLES):
        return f"bloqueado_{status}"
    return status


def event_base(event: dict[str, str], link_evento: str, source_url: str, status: str) -> dict[str, str]:
    return {
        "leiloeiro": domain(source_url or link_evento),
        "evento": event.get("nome", ""),
        "data": event.get("data", ""),
        "data_original": event.get("data_original", ""),
        "hora": event.get("hora_marcador", ""),
        "uf": event.get("uf", ""),
        "local": event.get("endereco_ou_localizacao", ""),
        "link_evento": link_evento,
        "fonte": source_url or link_evento,
        "capturado_em": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        "status_captura": status,
    }


def pdf_text(raw: bytes) -> str:
    if not raw or PdfReader is None:
        return ""
    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [(page.extract_text() or "") for page in reader.pages[:120]]
        return "\n".join(pages)
    except Exception:
        return ""


def lot_rows_from_text(
    event: dict[str, str],
    link_evento: str,
    source_url: str,
    text: str,
    status: str,
    maximum: int = 1500,
) -> list[dict[str, str]]:
    """Transforma blocos iniciados por LOTE/ITEM em registros pesquisaveis."""
    normalized = html.unescape(text or "").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    matches = list(PDF_LOT_RE.finditer(normalized))
    if not matches:
        return []

    base = event_base(event, link_evento, source_url, status)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for position, match in enumerate(matches[:maximum]):
        number = clean_text(match.group(1)).upper()
        start = match.end()
        end = matches[position + 1].start() if position + 1 < len(matches) else min(len(normalized), start + 2500)
        segment = clean_text(normalized[start:end])[:1800]
        if not segment or number in seen:
            continue
        # Evita confundir clausulas de edital (ex.: "lote 9.19") com numero de bem.
        if re.fullmatch(r"\d+\.\d{2,}", number):
            continue
        seen.add(number)
        # Editais costumam trazer cabecalhos repetidos entre o numero e a descricao.
        segment = re.sub(r"^(?:[-–—:|]\s*)+", "", segment)
        title_piece = re.split(
            r"\b(?:avalia[cç][aã]o|lance\s+m[ií]nimo|valor\s+m[ií]nimo|localiza[cç][aã]o|observa[cç][oõ]es?)\b",
            segment,
            maxsplit=1,
            flags=re.I,
        )[0]
        title_piece = clean_text(title_piece)[:210]
        if len(title_piece) < 3:
            title_piece = segment[:210]
        price_match = PRICE_RE.search(segment)
        rows.append(
            {
                **base,
                "titulo": f"Lote {number} - {title_piece}"[:240],
                "descricao": segment[:600],
                "lance_atual": price_match.group(0) if price_match else "",
                "lote": number,
                "link_lote": source_url + ("&" if "#" in source_url else "#") + f"lote-{urllib.parse.quote(number)}",
            }
        )
    return rows


def extract_lots_from_pdf(
    event: dict[str, str], link_evento: str, source_url: str, raw: bytes
) -> list[dict[str, str]]:
    text = pdf_text(raw)
    return lot_rows_from_text(event, link_evento, source_url, text, "pdf_ok")


def pdf_links_from_html(page: str, base_url: str, maximum: int = 2) -> list[str]:
    found: list[str] = []
    for candidate in re.findall(r"(?:href|src)=[\"']([^\"']+)[\"']", page or "", flags=re.I):
        url = absolute_url(base_url, candidate)
        if (PDF_RE.search(url) or "drive.google.com" in domain(url)) and url not in found:
            found.append(url)
    return found[:maximum]


def extract_lots_from_page(event: dict[str, str], link_evento: str, page: str, final_url: str, status: str) -> list[dict[str, str]]:
    base = event_base(event, link_evento, final_url, status)
    lots: list[dict[str, str]] = []
    seen: set[str] = set()

    parser = LinkParser()
    try:
        parser.feed(page)
    except Exception:
        pass

    for block in extract_json_blocks(page):
        for item in walk_json(block):
            title = text_from_dict(item)
            if not title or not looks_like_lot(title, url_from_dict(item, final_url)):
                continue
            link_lote = url_from_dict(item, final_url) or final_url
            key = (title + "|" + link_lote).casefold()
            if key in seen:
                continue
            seen.add(key)
            lots.append(
                {
                    **base,
                    "titulo": title[:240],
                    "descricao": clean_text(str(item.get("description") or item.get("descricao") or ""))[:600],
                    "lance_atual": price_from_dict(item),
                    "lote": lot_number(title),
                    "link_lote": link_lote,
                }
            )

    for href, text in parser.links:
        link_lote = absolute_url(final_url, href)
        title = clean_text(text)
        if not looks_like_lot(title, link_lote):
            continue
        key = (title + "|" + link_lote).casefold()
        if key in seen:
            continue
        seen.add(key)
        nearby_price = PRICE_RE.search(title)
        lots.append(
            {
                **base,
                "titulo": title[:240],
                "descricao": "",
                "lance_atual": nearby_price.group(0) if nearby_price else "",
                "lote": lot_number(title),
                "link_lote": link_lote,
            }
        )

    # Alguns portais exibem os lotes apenas como texto, sem links individuais.
    if not lots:
        visible_lots = lot_rows_from_text(
            event,
            link_evento,
            final_url,
            "\n".join(parser.visible_text),
            "html_texto_ok",
        )
        for row in visible_lots:
            key = (row.get("lote", "") + "|" + row.get("titulo", "")).casefold()
            if key not in seen:
                seen.add(key)
                lots.append(row)

    return lots


def extract_one_event(index: int, event: dict[str, str], delay: float) -> tuple[int, list[dict[str, str]], dict]:
    urls = event_urls(event)
    if not urls:
        return index, [], {
            "n": index,
            "evento": event.get("nome", ""),
            "data": event.get("data", ""),
            "status": "sem_link",
            "lotes": 0,
        }

    extracted: list[dict[str, str]] = []
    attempts: list[dict[str, object]] = []
    final_status = "sem_lotes"
    final_url = urls[0]

    for source_url in urls:
        if is_superbid_like(source_url):
            api_lots, api_status = extract_superbid_lots(event, source_url, source_url)
            attempts.append({"url": source_url, "status": api_status, "lotes": len(api_lots)})
            if api_lots:
                extracted.extend(api_lots)
                final_status = api_status
                final_url = source_url
                break

        status_code, raw, content_type, fetched_url = fetch_bytes(source_url)
        final_url = fetched_url or source_url
        raw_is_pdf = raw[:4] == b"%PDF"
        is_pdf = bool(PDF_RE.search(final_url) or "pdf" in content_type.casefold() or raw_is_pdf)
        if is_pdf and status_code == 200:
            pdf_lots = extract_lots_from_pdf(event, source_url, final_url, raw)
            pdf_status = "pdf_ok" if pdf_lots else "pdf_sem_lotes"
            attempts.append({"url": source_url, "status": pdf_status, "http": status_code, "lotes": len(pdf_lots)})
            if pdf_lots:
                extracted.extend(pdf_lots)
                final_status = pdf_status
                break
            final_status = pdf_status
            continue

        charset = "utf-8"
        charset_match = re.search(r"charset=([\w-]+)", content_type or "", re.I)
        if charset_match:
            charset = charset_match.group(1)
        page = raw.decode(charset, errors="replace")
        status = capture_status(status_code, page)
        page_lots = extract_lots_from_page(event, source_url, page, final_url, status) if status_code == 200 else []
        attempts.append({"url": source_url, "status": status, "http": status_code, "lotes": len(page_lots)})
        if page_lots:
            extracted.extend(page_lots)
            final_status = "html_ok"
            break

        # Se a pagina do evento aponta para um edital, usa o PDF como segunda fonte.
        for pdf_url in pdf_links_from_html(page, final_url):
            pdf_code, pdf_raw, pdf_type, pdf_final = fetch_bytes(pdf_url)
            if pdf_code != 200 or not (pdf_raw[:4] == b"%PDF" or "pdf" in pdf_type.casefold()):
                continue
            pdf_lots = extract_lots_from_pdf(event, source_url, pdf_final or pdf_url, pdf_raw)
            attempts.append({"url": pdf_url, "status": "pdf_link_ok" if pdf_lots else "pdf_link_sem_lotes", "http": pdf_code, "lotes": len(pdf_lots)})
            if pdf_lots:
                extracted.extend(pdf_lots)
                final_status = "pdf_link_ok"
                final_url = pdf_final or pdf_url
                break
        if extracted:
            break
        final_status = status

    if delay:
        time.sleep(delay)

    log = {
        "n": index,
        "evento": event.get("nome", ""),
        "data": event.get("data", ""),
        "link": urls[0],
        "final_url": final_url,
        "status": final_status,
        "lotes": len(extracted),
        "fontes_tentadas": attempts,
    }
    return index, extracted, log


def extract_lots(
    events: list[dict[str, str]],
    limit: int,
    delay: float,
    workers: int,
) -> tuple[list[dict[str, str]], list[dict]]:
    lots: list[dict[str, str]] = []
    logs: list[dict] = []
    seen_global: set[str] = set()
    selected = events[:limit] if limit else events

    results: list[tuple[int, list[dict[str, str]], dict]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(extract_one_event, index, event, delay): (index, event)
            for index, event in enumerate(selected, 1)
        }
        for future in as_completed(futures):
            index, event = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    (
                        index,
                        [],
                        {
                            "n": index,
                            "evento": event.get("nome", ""),
                            "link": first_url(event.get("link", "")),
                            "status": "erro_execucao_evento",
                            "erro": repr(exc),
                            "lotes": 0,
                        },
                    )
                )

    for _, extracted, log in sorted(results, key=lambda item: item[0]):
        new_rows: list[dict[str, str]] = []
        for row in extracted:
            dedupe_key = (row.get("titulo", "") + "|" + row.get("link_lote", "")).casefold()
            if dedupe_key in seen_global:
                continue
            seen_global.add(dedupe_key)
            new_rows.append(row)
        lots.extend(new_rows)
        log["lotes"] = len(new_rows)
        logs.append(log)
    return lots, logs


def load_previous_lots(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data.get("lotes", []) if isinstance(data, dict) else data
    return [row for row in rows if isinstance(row, dict) and valid_lot(row)] if isinstance(rows, list) else []


def valid_lot(row: dict[str, str]) -> bool:
    number = clean_text(row.get("lote", ""))
    title = clean_text(row.get("titulo", ""))
    if not title or title.casefold() in IGNORE_ANCHORS:
        return False
    if re.fullmatch(r"\d+\.\d{2,}", number):
        return False
    return True


def clean_existing_outputs(json_path: Path, csv_path: Path) -> int:
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Nao foi possivel limpar {json_path}: {exc}")
    if not isinstance(payload, dict):
        raise SystemExit(f"Formato invalido em {json_path}")
    rows = [row for row in payload.get("lotes", []) if isinstance(row, dict) and valid_lot(row)]
    payload["lotes"] = rows
    payload["total_lotes"] = len(rows)
    payload["total_lotes_preservados"] = sum(
        1 for row in rows if str(row.get("status_captura", "")).startswith("preservado_apos_falha:")
    )
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, rows)
    return len(rows)


def event_key(value: str) -> str:
    return slugify(value or "").casefold()


def event_date_key(name: str, event_date: str) -> str:
    return event_key(name) + "|" + clean_text(event_date)


def preserve_unavailable_lots(
    events: list[dict[str, str]],
    fresh_lots: list[dict[str, str]],
    logs: list[dict],
    previous_lots: list[dict[str, str]],
) -> tuple[list[dict[str, str]], int]:
    """Mantem lotes do evento ativo quando a consulta atual foi bloqueada ou falhou."""
    fresh_event_keys = {event_date_key(row.get("evento", ""), row.get("data", "")) for row in fresh_lots}
    current_event_keys = {event_date_key(event.get("nome", ""), event.get("data", "")) for event in events}
    failed_event_keys = {
        event_date_key(str(log.get("evento", "")), str(log.get("data", "")))
        for log in logs
        if int(log.get("lotes") or 0) == 0
    }
    allowed = (current_event_keys & failed_event_keys) - fresh_event_keys

    carried: list[dict[str, str]] = []
    for old in previous_lots:
        key = event_date_key(old.get("evento", ""), old.get("data", ""))
        if key not in allowed:
            continue
        old_number = clean_text(old.get("lote", ""))
        old_title = clean_text(old.get("titulo", "")).casefold()
        if re.fullmatch(r"\d+\.\d{2,}", old_number) or old_title in IGNORE_ANCHORS:
            continue
        row = dict(old)
        old_status = row.get("status_captura", "")
        if str(old_status).startswith("preservado_apos_falha:"):
            row["status_captura"] = old_status
        else:
            row["status_captura"] = f"preservado_apos_falha:{old_status}"[:120]
        carried.append(row)
    return fresh_lots + carried, len(carried)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexa lotes a partir dos eventos do radar.")
    parser.add_argument("--eventos", default=str(EVENTOS_CSV))
    parser.add_argument("--saida", default=str(LOTES_JSON))
    parser.add_argument("--csv", default=str(LOTES_CSV))
    parser.add_argument("--limite", type=int, default=0, help="0 = todos os eventos")
    parser.add_argument("--delay", type=float, default=0.4)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--somente-limpeza", action="store_true", help="Remove resultados invalidos sem acessar a internet")
    args = parser.parse_args()

    if args.somente_limpeza:
        total = clean_existing_outputs(Path(args.saida), Path(args.csv))
        print(json.dumps({"total_lotes": total, "modo": "somente_limpeza"}, ensure_ascii=False))
        return

    events = read_events(Path(args.eventos))
    selected_events = events[: args.limite] if args.limite else events
    output_path = Path(args.saida)
    previous_lots = load_previous_lots(output_path)
    fresh_lots, logs = extract_lots(events, args.limite, args.delay, args.workers)
    lots, preserved_count = preserve_unavailable_lots(selected_events, fresh_lots, logs, previous_lots)

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in lots:
        if not valid_lot(row):
            continue
        key = "|".join(
            (
                event_key(row.get("evento", "")),
                clean_text(row.get("lote", "")).casefold(),
                clean_text(row.get("titulo", "")).casefold(),
                row.get("link_lote", "").casefold(),
            )
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    lots = deduped

    payload = {
        "atualizado_em": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        "total_eventos_lidos": len(selected_events),
        "total_lotes": len(lots),
        "total_lotes_capturados_agora": len(fresh_lots),
        "total_lotes_preservados": preserved_count,
        "eventos_com_lotes": sum(1 for log in logs if int(log.get("lotes") or 0) > 0),
        "eventos_sem_lotes": sum(1 for log in logs if int(log.get("lotes") or 0) == 0),
        "eventos_com_erro_ou_bloqueio": sum(
            1
            for log in logs
            if any(word in str(log.get("status", "")) for word in ("erro", "bloqueado", "http_0"))
        ),
        "lotes": lots,
        "logs": logs,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(Path(args.csv), lots)
    print(
        json.dumps(
            {
                key: payload[key]
                for key in (
                    "atualizado_em",
                    "total_eventos_lidos",
                    "total_lotes",
                    "total_lotes_capturados_agora",
                    "total_lotes_preservados",
                    "eventos_com_lotes",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
