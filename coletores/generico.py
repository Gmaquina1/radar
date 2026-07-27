"""Coletor genérico conservador para páginas públicas de leilões."""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from html.parser import HTMLParser

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid", "gclid"}
WORDS = ("leilao", "leilão", "leiloes", "leilões", "auction", "evento", "lote", "oferta", "item", "catalogo", "catálogo")


def canonicalize_url(url: str) -> str:
    parts = urllib.parse.urlsplit(html.unescape(url.strip()))
    host = parts.hostname.casefold() if parts.hostname else ""
    if host.startswith("www."):
        host = host[4:]
    if parts.port:
        host += f":{parts.port}"
    query = urllib.parse.urlencode([(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k.casefold() not in TRACKING])
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urllib.parse.urlunsplit(("https" if parts.scheme in {"http", "https"} else parts.scheme, host, path, query, ""))


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
        if "item" in value and isinstance(value["item"], dict):
            yield from _nodes(value["item"])


class GenericCollector:
    def parse_html(self, url: str, content: str) -> tuple[list[dict], list[str]]:
        parser = PageParser(); parser.feed(content)
        lots = []
        for root in parser.jsonld:
            for node in _nodes(root):
                kind = str(node.get("@type", "")).casefold()
                if kind not in {"product", "offer", "event"}:
                    continue
                offer = node.get("offers", {}) if isinstance(node.get("offers"), dict) else {}
                image = node.get("image", "")
                if isinstance(image, list): image = image[0] if image else ""
                if isinstance(image, dict): image = image.get("url", "")
                lots.append({"titulo": node.get("name", ""), "descricao": node.get("description", ""), "lance_atual": offer.get("price", node.get("price", "")), "data": node.get("startDate", ""), "link_lote": urllib.parse.urljoin(url, node.get("url", "")) or url, "foto_lote": urllib.parse.urljoin(url, str(image)) if image else "", "status_evento": node.get("eventStatus", "desconhecido"), "fonte_descoberta": "json_ld", "confianca_dados": "alta"})
        if not lots and (parser.meta.get("og:title") or parser.title):
            lots.append({"titulo": parser.meta.get("og:title", parser.title), "descricao": parser.meta.get("og:description", ""), "link_lote": urllib.parse.urljoin(url, parser.meta.get("og:url", url)), "foto_lote": urllib.parse.urljoin(url, parser.meta.get("og:image", "")) if parser.meta.get("og:image") else "", "status_evento": "desconhecido", "fonte_descoberta": "link_interno", "confianca_dados": "media"})
        links = []
        for link in parser.links:
            absolute = canonicalize_url(urllib.parse.urljoin(url, link))
            if any(word in urllib.parse.unquote(absolute).casefold() for word in WORDS):
                links.append(absolute)
        return lots, list(dict.fromkeys(links))

    def discover_events(self, url: str) -> list[dict]:
        return [{"link": canonicalize_url(url)}]

    def discover_lots(self, event: dict) -> list[dict]:
        return []

    def parse_lot(self, url: str) -> dict:
        return {"link_lote": canonicalize_url(url)}
