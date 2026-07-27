#!/usr/bin/env python3
"""Auditoria pequena e somente-leitura da cobertura da base de lotes."""
from __future__ import annotations

import json
import argparse
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from web_search import search_web

ROOT = Path(__file__).resolve().parent


def tokens(value) -> set[str]:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    words = "".join(ch if ch.isalnum() else " " for ch in text if not unicodedata.combining(ch)).split()
    return {word[:-3] + "al" if len(word) > 5 and word.endswith("ais") else word[:-1] if len(word) > 3 and word.endswith("s") else word for word in words}


def matches(row: dict, term: str) -> bool:
    haystack = " ".join(str(value or "") for value in row.values())
    return tokens(term) <= tokens(haystack)


def audit(term: str, path: Path = ROOT / "lotes.json", search=search_web, web: bool = False) -> dict:
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): payload = {}
    found = [row for row in payload.get("lotes", []) if isinstance(row, dict) and matches(row, term)]
    sources = sorted({str(row.get("fonte") or row.get("fonte_descoberta") or "") for row in found} - {""})
    domains = sorted({(urlsplit(str(row.get("link_lote") or row.get("link_evento") or "")).hostname or "").removeprefix("www.") for row in found} - {""})
    result = {"TERMO": term, "RESULTADOS_NA_BASE": len(found), "NA_BASE": len(found), "FONTES": sources, "DOMINIOS": domains}
    if web:
        results = []
        for query in (term + " leilão", term + " lote leilão"):
            results.extend(search(query, 1, 10))
        urls = {item.url for item in results}
        base_urls = {str(row.get("link_lote") or row.get("link_evento") or "") for row in found}
        result.update(RESULTADOS_WEB=len(urls), POSSIVEIS_AUSENTES=len(urls - base_urls))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("termo"); parser.add_argument("--web", action="store_true"); args = parser.parse_args()
    for key, value in audit(args.termo, web=args.web).items(): print(f"{key}: {value}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
