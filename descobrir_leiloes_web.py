#!/usr/bin/env python3
"""Descoberta incremental de leilões públicos independente do Google My Maps."""
from __future__ import annotations

import argparse
import csv
import email.utils
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from coletores.generico import GenericCollector, canonicalize_url
from web_search import search_web

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "portais_leiloes.json"
NEW_CATALOG = ROOT / "novos_portais_descobertos.json"
STATE = ROOT / ".discovery_state.json"
EVENTS = ROOT / "eventos_descobertos_web.json"
CONSOLIDATED = ROOT / "eventos_consolidados.csv"
REPORT = ROOT / "relatorio_descoberta_web.json"
COVERAGE = ROOT / "relatorio_cobertura_radar.json"
KEYWORDS = ("leilao", "leilão", "leiloes", "leilões", "auction", "evento", "lote", "oferta", "edital")
UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")
TERMS = ("máquinas", "veículos", "imóveis", "equipamentos", "tratores", "caminhões", "sucatas", "prefeitura", "tribunal", "DETRAN", "banco", "fazendas")


def env_int(name: str, default: int) -> int:
    try: return max(0, int(os.getenv(name, default)))
    except ValueError: return default


CONFIG = {"MAX_SEARCH_QUERIES": env_int("MAX_SEARCH_QUERIES", 8), "MAX_RESULTS_PER_QUERY": env_int("MAX_RESULTS_PER_QUERY", 10), "MAX_NEW_DOMAINS": env_int("MAX_NEW_DOMAINS", 10), "MAX_PAGES_PER_DOMAIN": env_int("MAX_PAGES_PER_DOMAIN", 12), "MAX_URLS_PER_DOMAIN": env_int("MAX_URLS_PER_DOMAIN", 50), "MAX_DEPTH": env_int("MAX_DEPTH", 2), "MAX_LOTS_PER_DOMAIN": env_int("MAX_LOTS_PER_DOMAIN", 250), "REQUEST_TIMEOUT": env_int("REQUEST_TIMEOUT", 15), "REQUEST_RETRIES": env_int("REQUEST_RETRIES", 2), "GLOBAL_WORKERS": env_int("GLOBAL_WORKERS", 6), "PER_DOMAIN_WORKERS": env_int("PER_DOMAIN_WORKERS", 1), "CACHE_TTL": env_int("CACHE_TTL", 21600)}


def now() -> str: return datetime.now(timezone.utc).isoformat(timespec="seconds")
def read_json(path: Path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return default
def write_json(path: Path, value) -> None: path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def host(url: str) -> str: return (urllib.parse.urlsplit(url).hostname or "").removeprefix("www.").casefold()


def query_group(state_path: Path = STATE, deep: bool = False) -> tuple[str, list[str]]:
    state = read_json(state_path, {})
    index = int(state.get("next_group", 0)) % 4
    groups = [UFS[i::4] for i in range(4)]
    queries = [f"leilão {TERMS[(index + n) % len(TERMS)]} {uf}" for n, uf in enumerate(groups[index])]
    queries += ["leilões online abertos", "edital de leilão público"]
    limit = CONFIG["MAX_SEARCH_QUERIES"] * (3 if deep else 1)
    write_json(state_path, {"last_group": chr(65 + index), "next_group": (index + 1) % 4, "executado_em": now()})
    return chr(65 + index), queries[:limit]


class HttpClient:
    def __init__(self, sleep=time.sleep): self.sleep, self.attempts = sleep, []
    def get(self, url: str) -> tuple[str, str, int, dict]:
        for attempt in range(CONFIG["REQUEST_RETRIES"] + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "RadarLeiloes/1.0 (+https://radar.empaez.com)"})
                with urllib.request.urlopen(req, timeout=CONFIG["REQUEST_TIMEOUT"]) as response:
                    body = response.read(3_000_000).decode(response.headers.get_content_charset() or "utf-8", "replace")
                    return body, response.geturl(), response.status, dict(response.headers)
            except urllib.error.HTTPError as exc:
                retry = exc.headers.get("Retry-After", "")
                self.attempts.append({"url": url, "http_status": exc.code, "retry_after": retry})
                if exc.code == 403: return "", url, 403, dict(exc.headers)
                if exc.code != 429 and exc.code < 500: return "", url, exc.code, dict(exc.headers)
                if attempt == CONFIG["REQUEST_RETRIES"]: return "", url, exc.code, dict(exc.headers)
                delay = retry_seconds(retry) or (2 ** attempt + random.random())
                self.sleep(min(delay, 30))
            except (OSError, TimeoutError):
                if attempt == CONFIG["REQUEST_RETRIES"]: return "", url, 0, {}
                self.sleep(2 ** attempt + random.random())
        return "", url, 0, {}


def retry_seconds(value: str) -> float:
    if str(value).isdigit(): return float(value)
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return max(0, (parsed - datetime.now(parsed.tzinfo)).total_seconds())
    except (TypeError, ValueError): return 0


def sitemap_urls(xml: str, limit: int = 100) -> tuple[list[str], list[str]]:
    try: root = ET.fromstring(xml)
    except ET.ParseError: return [], []
    locations = [node.text.strip() for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "loc" and node.text]
    if root.tag.rsplit("}", 1)[-1] == "sitemapindex": return [], locations[:limit]
    return [url for url in locations if any(k in urllib.parse.unquote(url).casefold() for k in KEYWORDS)][:limit], []


def robots_sitemaps(text: str) -> list[str]:
    return [line.split(":", 1)[1].strip() for line in text.splitlines() if line.casefold().startswith("sitemap:")]


def load_map_events(path: Path) -> list[dict]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle: return [dict(row, fonte_descoberta="mapa") for row in csv.DictReader(handle)]
    except OSError: return []


def consolidate(map_events: list[dict], web_events: list[dict], output: Path = CONSOLIDATED) -> None:
    rows, seen = [], set()
    for row in map_events + web_events:
        url = row.get("site_leiloeiro") or row.get("link") or row.get("link_evento") or row.get("url_descoberta", "")
        key = canonicalize_url(url) if url else "|".join((row.get("nome", ""), row.get("data", "")))
        if not key or key in seen: continue
        seen.add(key); item = dict(row)
        item.setdefault("nome", item.get("titulo") or f"Leilão descoberto em {host(url)}")
        item.setdefault("link", url); item.setdefault("site_leiloeiro", url)
        rows.append(item)
    fields = list(dict.fromkeys([key for row in rows for key in row] or ["nome", "link", "fonte_descoberta"]))
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)


def run(deep: bool = False, client: HttpClient | None = None, search=search_web, map_path: Path | None = None) -> dict:
    client, collector = client or HttpClient(), GenericCollector()
    group, queries = query_group(deep=deep)
    catalog = read_json(CATALOG, []); known = {entry["dominio"]: entry for entry in catalog if isinstance(entry, dict) and entry.get("dominio")}
    new_entries = read_json(NEW_CATALOG, []); candidates: list[tuple[str, str]] = []
    map_events = load_map_events(map_path or ROOT / "radar_leiloes_eventos_futuros.csv")
    errors, results = [], 0
    configured = bool(os.getenv("WEB_SEARCH_PROVIDER") and os.getenv("WEB_SEARCH_API_KEY"))
    if configured:
        for query in queries:
            try:
                found = search(query, 1, CONFIG["MAX_RESULTS_PER_QUERY"]); results += len(found)
                candidates.extend((item.url, query) for item in found)
            except Exception as exc: errors.append({"consulta": query, "erro": type(exc).__name__})
    candidates.extend((entry.get("url_exemplo") or f"https://{entry['dominio']}/", "catalogo") for entry in catalog if entry.get("ativo", True))
    candidates.extend(((entry.get("site_leiloeiro") or entry.get("link")), "mapa") for entry in map_events if entry.get("site_leiloeiro") or entry.get("link"))
    discovered, lots, diagnostics, visited, new_count = [], [], {}, set(), 0
    for seed, query in candidates:
        domain = host(seed)
        if not domain: continue
        is_new = domain not in known
        if is_new and sum(1 for d in known.values() if d.get("novo_nesta_execucao")) >= CONFIG["MAX_NEW_DOMAINS"]: continue
        timestamp = now()
        if is_new:
            new_count += 1
            known[domain] = {"dominio": domain, "ativo": True, "origem": "busca_web", "descoberto_em": timestamp, "possui_eventos": False, "possui_lotes": False, "tipo_coleta": "generico", "requires_browser": False, "status_acesso": "ok", "url_exemplo": seed, "novo_nesta_execucao": True}
            new_entries.append({"dominio": domain, "url_exemplo": seed, "descoberto_em": timestamp, "consulta_que_encontrou": query, "status": "pendente", "tipo_coleta": "generico", "ultima_verificacao": timestamp})
        queue = deque([(canonicalize_url(seed), 0, "busca_web" if query != "catalogo" else "portal_direto")])
        base = f"https://{domain}"
        robot, _, _, _ = client.get(base + "/robots.txt")
        maps = robots_sitemaps(robot) + [base + "/sitemap.xml", base + "/sitemap_index.xml"]
        for sm in list(dict.fromkeys(maps))[: (8 if deep else 3)]:
            xml, _, code, _ = client.get(sm)
            if code != 200: continue
            urls, indexes = sitemap_urls(xml, CONFIG["MAX_URLS_PER_DOMAIN"])
            for child in indexes[: (5 if deep else 2)]:
                child_xml, _, child_code, _ = client.get(child)
                if child_code == 200: urls.extend(sitemap_urls(child_xml, CONFIG["MAX_URLS_PER_DOMAIN"])[0])
            queue.extend((url, 0, "sitemap") for url in urls)
        pages = 0
        while queue and pages < CONFIG["MAX_PAGES_PER_DOMAIN"]:
            url, depth, source = queue.popleft()
            if url in visited or host(url) != domain: continue
            visited.add(url); pages += 1
            body, final, code, headers = client.get(url)
            diag = diagnostics.setdefault(domain, {"dominio": domain, "eventos_encontrados": 0, "lotes_encontrados": 0, "status_acesso": "ok", "metodo_funcional": source})
            if code != 200:
                diag["ultima_falha"] = now(); diag["http_status"] = code; diag["status_acesso"] = "rate_limited" if code == 429 else "temporariamente_bloqueado" if code == 403 else "erro_temporario"
                continue
            page_lots, links = collector.parse_html(final, body)
            discovered.append({"nome": page_lots[0].get("titulo") if page_lots else f"Leilão em {domain}", "link": final, "site_leiloeiro": final, "fonte_descoberta": source, "dominio_origem": domain, "url_descoberta": seed, "descoberto_em": now(), "confianca_dados": "alta" if any(x.get("fonte_descoberta") == "json_ld" for x in page_lots) else "media", "status_evento": "desconhecido"})
            lots.extend(dict(lot, dominio_origem=domain, url_descoberta=seed, descoberto_em=now()) for lot in page_lots[:CONFIG["MAX_LOTS_PER_DOMAIN"]])
            diag.update({"eventos_encontrados": diag["eventos_encontrados"] + 1, "lotes_encontrados": diag["lotes_encontrados"] + len(page_lots), "ultimo_sucesso": now()})
            if depth < CONFIG["MAX_DEPTH"]: queue.extend((link, depth + 1, "link_interno") for link in links[:CONFIG["MAX_URLS_PER_DOMAIN"]])
        known[domain]["ultima_verificacao"] = now(); known[domain]["possui_eventos"] = diagnostics.get(domain, {}).get("eventos_encontrados", 0) > 0; known[domain]["possui_lotes"] = diagnostics.get(domain, {}).get("lotes_encontrados", 0) > 0; known[domain]["status_acesso"] = diagnostics.get(domain, {}).get("status_acesso", "erro_temporario")
    for value in known.values(): value.pop("novo_nesta_execucao", None)
    write_json(CATALOG, sorted(known.values(), key=lambda x: x["dominio"])); write_json(NEW_CATALOG, new_entries)
    write_json(EVENTS, {"executado_em": now(), "eventos": discovered, "lotes": lots}); consolidate(map_events, discovered)
    sources = Counter(event["fonte_descoberta"] for event in discovered); domains = Counter(event["dominio_origem"] for event in discovered)
    report = {"executado_em": now(), "grupo_consultas": group, "busca_web_configurada": configured, "consultas_executadas": queries if configured else [], "resultados_de_busca": results, "dominios_encontrados": len(diagnostics), "novos_dominios": new_count, "dominios_visitados": len(diagnostics), "eventos_descobertos": len(discovered), "lotes_descobertos": len(lots), "lotes_novos": len(lots), "duplicados": 0, "bloqueados": sum(x["status_acesso"] == "temporariamente_bloqueado" for x in diagnostics.values()), "requires_browser": sum(x["status_acesso"] == "requires_browser" for x in diagnostics.values()), "erros": errors, "quantidade_por_fonte": dict(sources), "quantidade_por_dominio": dict(domains), "diagnostico_portais": list(diagnostics.values())}
    write_json(REPORT, report)
    coverage = {"executado_em": now(), "total_eventos_ativos": len(map_events) + len(discovered), "total_lotes_ativos": len(lots), "total_dominios": len(known), "dominios_novos": report["novos_dominios"], "dominios_com_suporte_especifico": 0, "dominios_coletor_generico": len(known), "dominios_bloqueados": report["bloqueados"], "dominios_requires_browser": report["requires_browser"], "lotes_vindos_do_mapa": 0, "lotes_fora_do_mapa": len(lots), "LOTES_FORA_DO_MAPA": len(lots), "fontes_totais": len(known), "fontes_novas_na_execucao": report["novos_dominios"], "eventos_fora_do_mapa": len(discovered)}
    write_json(COVERAGE, coverage); return report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--deep-discovery", action="store_true"); args = parser.parse_args()
    print(json.dumps(run(args.deep_discovery), ensure_ascii=False))


if __name__ == "__main__": main()
