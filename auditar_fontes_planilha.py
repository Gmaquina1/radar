#!/usr/bin/env python3
"""Confere o acesso às fontes catalogadas na planilha nacional."""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "fontes_planilha.json"
REPORT = ROOT / "auditoria_fontes_planilha.json"
TIMEOUT = max(1, int(os.getenv("AUDIT_TIMEOUT", "12")))
WORKERS = max(1, int(os.getenv("AUDIT_WORKERS", "24")))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check(item: dict) -> dict:
    started = time.monotonic()
    url = str(item.get("url") or "")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RadarLeiloes/1.0 (+https://radar.empaez.com)",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.5",
        },
    )
    code = 0
    final_url = url
    error = ""
    status = ""
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            code = int(response.status)
            final_url = response.geturl()
            response.read(65_536)
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
        final_url = exc.geturl()
        error = str(exc.reason or exc)
    except (TimeoutError, socket.timeout) as exc:
        error = str(exc)
        status = "timeout"
    except (OSError, ValueError, urllib.error.URLError) as exc:
        error = str(getattr(exc, "reason", exc))
        status = "erro"
    else:
        status = (
            "ok"
            if 200 <= code < 400
            else "bloqueado"
            if code in (401, 403)
            else "limitado"
            if code == 429
            else "erro_http"
        )
    if not status:
        status = (
            "bloqueado"
            if code in (401, 403)
            else "limitado"
            if code == 429
            else "erro_http"
        )
    return {
        "nome": item.get("nome", ""),
        "grupo": item.get("grupo", ""),
        "dominio": item.get("dominio", ""),
        "url": url,
        "url_final": final_url,
        "coletar_lotes": bool(item.get("coletar_lotes")),
        "status": status,
        "http_status": code,
        "erro": error,
        "duracao_segundos": round(time.monotonic() - started, 2),
    }


def run() -> dict:
    payload = json.loads(SOURCES.read_text(encoding="utf-8"))
    sources = [
        item
        for item in payload.get("fontes", [])
        if isinstance(item, dict) and item.get("url")
    ]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(WORKERS, len(sources) or 1)) as executor:
        futures = {executor.submit(check, item): item for item in sources}
        for position, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            print(
                f"[{position}/{len(sources)}] {result['status'].upper()} "
                f"{result['http_status']} {result['dominio']}",
                flush=True,
            )
    results.sort(key=lambda item: (item["grupo"], item["dominio"], item["url"]))
    counts = Counter(item["status"] for item in results)
    lot_results = [item for item in results if item["coletar_lotes"]]
    report = {
        "executado_em": now(),
        "timeout_segundos": TIMEOUT,
        "workers": WORKERS,
        "fontes_total": len(results),
        "fontes_de_lotes": len(lot_results),
        "fontes_acessiveis": counts["ok"],
        "fontes_de_lotes_acessiveis": sum(
            item["status"] == "ok" for item in lot_results
        ),
        "por_status": dict(sorted(counts.items())),
        "resultados": results,
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"[FIM] FONTES={len(results)} ACESSIVEIS={counts['ok']} "
        f"BLOQUEADAS={counts['bloqueado']} TIMEOUTS={counts['timeout']}",
        flush=True,
    )
    return report


if __name__ == "__main__":
    run()
