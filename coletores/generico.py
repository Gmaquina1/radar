"""Coletor genérico conservador para páginas públicas de leilões."""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import urllib.parse
from html.parser import HTMLParser

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid", "gclid"}
WORDS = ("leilao", "leilão", "leiloes", "leilões", "auction", "evento", "lote", "oferta", "item", "catalogo", "catálogo")


def public_date_time(value: object) -> tuple[str, str]:
    """Extrai encerramento/data pública em formatos brasileiros ou ISO."""
    text = html.unescape(str(value or ""))
    date_match = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", text)
    if date_match:
        day, month, year = map(int, date_match.groups())
    else:
        date_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if not date_match:
            return "", ""
        year, month, day = map(int, date_match.groups())
    try:
        parsed_date = dt.date(year, month, day).isoformat()
    except ValueError:
        return "", ""
    tail = text[date_match.end():]
    hour_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?\b", tail)
    hour = f"{int(hour_match.group(1)):02d}:{hour_match.group(2)}" if hour_match else ""
    return parsed_date, hour


def _scalar_url(value) -> str:
    """Return the first usable URL from permissive schema.org values."""
    if isinstance(value, dict):
        for key in ("url", "@id", "contentUrl", "href"):
            found = _scalar_url(value.get(key))
            if found:
                return found
        return ""
    if isinstance(value, (list, tuple)):
        return next((found for item in value if (found := _scalar_url(item))), "")
    if not isinstance(value, str):
        return ""
    value = html.unescape(value).strip()
    # Bad feeds sometimes concatenate URLs with whitespace.
    match = re.search(r"https?://[^\s<>\"']+", value, re.I)
    return match.group(0).rstrip(".,;)") if match else value


def canonicalize_url(url, base: str = "") -> str:
    raw = _scalar_url(url)
    if not raw or any(ch in raw for ch in "\r\n\t"):
        return ""
    try:
        absolute = urllib.parse.urljoin(base, raw) if base else raw
        parts = urllib.parse.urlsplit(absolute)
        host = (parts.hostname or "").casefold()
        port = parts.port  # validates malformed ports
    except (TypeError, ValueError, UnicodeError):
        return ""
    if parts.scheme.casefold() not in {"http", "https"} or not host:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if port:
        host += f":{port}"
    query = urllib.parse.urlencode([(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k.casefold() not in TRACKING])
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    try:
        return urllib.parse.urlunsplit(("https", host, urllib.parse.quote(urllib.parse.unquote(path), safe="/%:@!$&'()*+,;=-._~"), query, ""))
    except (TypeError, ValueError, UnicodeError):
        return ""


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links, self.meta, self.images, self.jsonld = [], {}, [], []
        self._json = False
        self._buffer: list[str] = []
        self.title, self._title = "", False

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "a" and data.get("href"):
            self.links.append(data["href"])
        if tag == "meta":
            key = data.get("property") or data.get("name")
            if key and data.get("content"):
                self.meta[key.casefold()] = data["content"]
        if tag == "img" and (data.get("src") or data.get("data-src")):
            self.images.append(data.get("src") or data.get("data-src"))
        if tag == "script" and data.get("type", "").casefold() == "application/ld+json":
            self._json, self._buffer = True, []
        if tag == "title":
            self._title, self._buffer = True, []

    def handle_data(self, data):
        if self._json or self._title:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._json:
            try:
                self.jsonld.append(json.loads("".join(self._buffer)))
            except (ValueError, TypeError):
                pass
            self._json = False
        if tag == "title" and self._title:
            self.title, self._title = " ".join("".join(self._buffer).split()), False


def _nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from _nodes(item)
    elif isinstance(value, dict):
        yield value
        if "@graph" in value:
            yield from _nodes(value["@graph"])
        if "itemListElement" in value:
            yield from _nodes(value["itemListElement"])
        if "item" in value:
            yield from _nodes(value["item"])


class GenericCollector:
    def parse_html(self, url: str, content: str) -> tuple[list[dict], list[str]]:
        parser = PageParser(); parser.feed(content)
        meta_description = parser.meta.get("og:description", "") or parser.meta.get("description", "")
        meta_date, meta_hour = public_date_time(meta_description)
        lots = []
        for root in parser.jsonld:
            for node in _nodes(root):
                kinds = node.get("@type", "")
                kinds = kinds if isinstance(kinds, list) else [kinds]
                if not any(str(kind).casefold() in {"product", "offer", "event"} for kind in kinds):
                    continue
                offers = node.get("offers")
                offer = next(_nodes(offers), {})
                image = _scalar_url(node.get("image"))
                link = canonicalize_url(node.get("url") or node.get("@id"), url) or canonicalize_url(url)
                structured_date, structured_hour = public_date_time(
                    node.get("endDate")
                    or offer.get("priceValidUntil")
                    or node.get("startDate")
                    or ""
                )
                lots.append({"titulo": str(node.get("name") or ""), "descricao": str(node.get("description") or meta_description or ""), "lance_atual": offer.get("price", node.get("price", "")), "data": structured_date or meta_date, "hora": structured_hour or meta_hour, "link_lote": link, "foto_lote": canonicalize_url(image, url) if image else "", "status_evento": node.get("eventStatus", "desconhecido"), "fonte_descoberta": "json_ld", "confianca_dados": "alta"})
        if not lots and (parser.meta.get("og:title") or parser.title):
            lots.append({"titulo": parser.meta.get("og:title", parser.title), "descricao": meta_description, "data": meta_date, "hora": meta_hour, "link_lote": urllib.parse.urljoin(url, parser.meta.get("og:url", url)), "foto_lote": urllib.parse.urljoin(url, parser.meta.get("og:image", "")) if parser.meta.get("og:image") else "", "status_evento": "desconhecido", "fonte_descoberta": "link_interno", "confianca_dados": "media"})
        links = []
        for link in parser.links:
            absolute = canonicalize_url(link, url)
            if any(word in urllib.parse.unquote(absolute).casefold() for word in WORDS):
                links.append(absolute)
        return lots, list(dict.fromkeys(links))

    def discover_events(self, url: str) -> list[dict]:
        return [{"link": canonicalize_url(url)}]

    def discover_lots(self, event: dict) -> list[dict]:
        return []

    def parse_lot(self, url: str) -> dict:
        return {"link_lote": canonicalize_url(url)}
