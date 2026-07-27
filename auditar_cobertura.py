#!/usr/bin/env python3
"""Auditoria pequena e somente-leitura da cobertura da base de lotes."""
from __future__ import annotations

import json
import os
import sys
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


def audit(term: str, path: Path = ROOT / "lotes.json", search=search_web) -> dict:
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): payload = {}
    found = [row for row in payload.get("lotes", []) if isinstance(row, dict) and matches(row, term)]
    sources = sorted({str(row.get("fonte") or row.get("fonte_descoberta") or "") for row in found} - {""})
    domains = sorted({(urlsplit(str(row.get("link_lote") or row.get("link_evento") or "")).hostname or "").removeprefix("www.") for row in found} - {""})
    result = {"TERMO": term, "NA_BASE": len(found), "FONTES": sources, "DOMINIOS": domains}
    if os.getenv("WEB_SEARCH_PROVIDER") and os.getenv("WEB_SEARCH_API_KEY"):
        web = search(term + " leilão", 1, 10)
        result.update(WEB_ENCONTRADOS=len(web), BASE_ENCONTRADOS=len(found), POSSIVEIS_AUSENTES=max(0, len(web) - len(found)))
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Uso: {sys.argv[0]} TERMO", file=sys.stderr); return 2
    for key, value in audit(sys.argv[1]).items(): print(f"{key}: {value}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
