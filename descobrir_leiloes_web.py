#!/usr/bin/env python3
"""Descoberta incremental de leilões públicos independente do Google My Maps."""
from __future__ import annotations

import argparse
import csv
import email.utils
import gzip
import json
import os
import random
import re
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
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


CONFIG = {
    "MAX_SEARCH_QUERIES": env_int("OPENAI_MAX_SEARCH_QUERIES", 8),
    "MAX_RESULTS_PER_QUERY": env_int("MAX_RESULTS_PER_QUERY", 10),
    "MAX_NEW_DOMAINS": env_int("MAX_NEW_DOMAINS", 10),
    "MAX_PAGES_PER_DOMAIN": env_int("MAX_PAGES_PER_DOMAIN", 12),
    "MAX_URLS_PER_DOMAIN": env_int("MAX_URLS_PER_DOMAIN", 50),
    "MAX_DEPTH": env_int("MAX_DEPTH", 2),
    "MAX_LOTS_PER_DOMAIN": env_int("MAX_LOTS_PER_DOMAIN", 250),
    "REQUEST_TIMEOUT": env_int("REQUEST_TIMEOUT", 15),
    "REQUEST_RETRIES": env_int("REQUEST_RETRIES", 2),
    "GLOBAL_WORKERS": env_int("GLOBAL_WORKERS", 6),
    "FAST_MAX_PORTALS": env_int("FAST_MAX_PORTALS", 30),
    "DOMAIN_TIME_BUDGET": env_int("DOMAIN_TIME_BUDGET", 45),
    "DISCOVERY_TIME_BUDGET": env_int("DISCOVERY_TIME_BUDGET", 7200),
    "FAILURE_BACKOFF_BASE": env_int("FAILURE_BACKOFF_BASE", 3600),
    "FAILURE_BACKOFF_MAX": env_int("FAILURE_BACKOFF_MAX", 86400),
    "CACHE_TTL": env_int("CACHE_TTL", 21600),
}


def now() -> str: return datetime.now(timezone.utc).isoformat(timespec="seconds")
def read_json(path: Path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return default
def write_json(path: Path, value) -> None: path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def host(url) -> str:
    canonical = canonicalize_url(url)
    if not canonical: return ""
    try: return (urllib.parse.urlsplit(canonical).hostname or "").removeprefix("www.").casefold()
    except (TypeError, ValueError): return ""


class DomainBudgetExceeded(TimeoutError):
    """Indica que um portal consumiu todo o orçamento desta execução."""


def normalize_portal(entry: dict) -> dict:
    """Migra entradas antigas preservando campos e adicionando estado incremental."""
    value = dict(entry)
    defaults = {"ativo": True, "origem": "catalogo", "url_exemplo": "", "pagina_eventos": "", "sitemap": "", "tipo_coleta": "generico", "possui_eventos": False, "possui_lotes": False, "ultima_verificacao": "", "ultimo_sucesso": "", "status_acesso": "pendente", "falhas_consecutivas": 0, "tempo_resposta": 0, "proxima_verificacao": "", "caminhos_conhecidos": [], "etag": "", "last_modified": "", "hash_conteudo": ""}
    for key, default in defaults.items(): value.setdefault(key, default)
    if not isinstance(value["caminhos_conhecidos"], list): value["caminhos_conhecidos"] = []
    example = canonicalize_url(value.get("url_exemplo"))
    if example and example not in value["caminhos_conhecidos"]: value["caminhos_conhecidos"].append(example)
    return value


def _urls(value):
    if isinstance(value, dict):
        for item in value.values(): yield from _urls(item)
    elif isinstance(value, list):
        for item in value: yield from _urls(item)
    elif isinstance(value, str):
        yield from re.findall(r"https?://[^\s<>'\"\]\)]+", value, re.I)


def bootstrap_portais(catalog_path: Path | None = None, sources: list[Path] | None = None, minimum: int = 3) -> list[dict]:
    """Seed a small/empty catalog strictly from Radar's persisted datasets."""
    catalog_path = catalog_path or CATALOG
    current = read_json(catalog_path, []); current = current if isinstance(current, list) else []
    known = {x.get("dominio"): x for x in current if isinstance(x, dict) and x.get("dominio")}
    if len(known) >= minimum: return sorted(known.values(), key=lambda x: x["dominio"])
    sources = sources or [ROOT / name for name in ("radar_leiloes_eventos_futuros.csv", "radar_leiloes_eventos_todos.csv", "lotes.json", "relatorio_atualizacao_lotes.json")]
    for path in sources:
        try:
            if path.suffix == ".csv":
                with path.open(encoding="utf-8-sig", newline="") as handle:
                    values = (value for row in csv.DictReader(handle) for value in row.values())
                    urls = (url for value in values for url in _urls(value))
                    for url in urls:
                        domain = host(url)
                        if domain: known.setdefault(domain, {"dominio": domain, "ativo": True, "origem": "bootstrap_base", "url_exemplo": canonicalize_url(url), "tipo_coleta": "generico"})
            else:
                for url in _urls(read_json(path, {})):
                    domain = host(url)
                    if domain: known.setdefault(domain, {"dominio": domain, "ativo": True, "origem": "bootstrap_base", "url_exemplo": canonicalize_url(url), "tipo_coleta": "generico"})
        except (OSError, csv.Error, UnicodeError, ValueError):
            continue
    result = sorted(known.values(), key=lambda x: x["dominio"]); write_json(catalog_path, result); return result


def error_record(domain, url, stage, exc=None, http_status=None):
    return {"dominio": domain or "", "url": str(url or ""), "etapa": stage, "tipo_erro": type(exc).__name__ if exc else "HTTPError", "mensagem": str(exc) if exc else f"HTTP {http_status}", "http_status": http_status}


def query_group(state_path: Path | None = None, deep: bool = False) -> tuple[str, list[str]]:
    state_path = state_path or STATE
    state = read_json(state_path, {})
    index = int(state.get("next_group", 0)) % 4
    groups = [UFS[i::4] for i in range(4)]
    queries = [f"leilão {TERMS[(index + n) % len(TERMS)]} {uf}" for n, uf in enumerate(groups[index])]
    queries += [
        "leilões online abertos hoje",
        "edital de leilão público",
        "site de leilões online Brasil",
        "leiloeiro oficial leilões online",
        "próximos leilões máquinas",
        "próximos leilões veículos",
        "garra florestal leilão",
    ]
    limit = max(CONFIG["MAX_SEARCH_QUERIES"], 30) if deep else CONFIG["MAX_SEARCH_QUERIES"]
    write_json(state_path, {"last_group": chr(65 + index), "next_group": (index + 1) % 4, "executado_em": now()})
    return chr(65 + index), queries[:limit]


class HttpClient:
    def __init__(self, sleep=time.sleep): self.sleep, self.attempts = sleep, []
    def get(self, url: str, deadline: float | None = None) -> tuple[str, str, int, dict]:
        for attempt in range(CONFIG["REQUEST_RETRIES"] + 1):
            remaining = (
                deadline - time.monotonic()
                if deadline is not None
                else float(CONFIG["REQUEST_TIMEOUT"])
            )
            if remaining <= 0:
                raise DomainBudgetExceeded(url)
            request_timeout = max(
                0.25,
                min(float(CONFIG["REQUEST_TIMEOUT"]), remaining),
            )
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "RadarLeiloes/1.0 (+https://radar.empaez.com)"})
                with urllib.request.urlopen(req, timeout=request_timeout) as response:
                    body = response.read(3_000_000).decode(response.headers.get_content_charset() or "utf-8", "replace")
                    return body, response.geturl(), response.status, dict(response.headers)
            except urllib.error.HTTPError as exc:
                retry = exc.headers.get("Retry-After", "")
                self.attempts.append({"url": url, "http_status": exc.code, "retry_after": retry})
                if exc.code == 403: return "", url, 403, dict(exc.headers)
                if exc.code != 429 and exc.code < 500: return "", url, exc.code, dict(exc.headers)
                if attempt == CONFIG["REQUEST_RETRIES"]: return "", url, exc.code, dict(exc.headers)
                delay = retry_seconds(retry) or (2 ** attempt + random.random())
                if deadline is not None and time.monotonic() + delay >= deadline:
                    raise DomainBudgetExceeded(url)
                self.sleep(min(delay, 30))
            except (OSError, TimeoutError):
                if attempt == CONFIG["REQUEST_RETRIES"]: return "", url, 0, {}
                delay = 2 ** attempt + random.random()
                if deadline is not None and time.monotonic() + delay >= deadline:
                    raise DomainBudgetExceeded(url)
                self.sleep(delay)
        return "", url, 0, {}


def retry_seconds(value: str) -> float:
    if str(value).isdigit(): return float(value)
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return max(0, (parsed - datetime.now(parsed.tzinfo)).total_seconds())
    except (TypeError, ValueError): return 0


def sitemap_urls(xml: str | bytes, limit: int = 100) -> tuple[list[str], list[str]]:
    try:
        if isinstance(xml, bytes) and xml[:2] == b"\x1f\x8b": xml = gzip.decompress(xml)
        root = ET.fromstring(xml)
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


def consolidate(map_events: list[dict], web_events: list[dict], output: Path | None = None) -> None:
    output = output or CONSOLIDATED
    rows, seen = [], set()
    for row in map_events + web_events:
        url = row.get("site_leiloeiro") or row.get("link") or row.get("link_evento") or row.get("url_descoberta", "")
        canonical = canonicalize_url(url)
        key = canonical or "|".join((host(url), str(row.get("nome") or row.get("titulo") or "").casefold().strip(), str(row.get("data") or "").strip()))
        if not key or key in seen: continue
        seen.add(key); item = dict(row)
        item.setdefault("nome", item.get("titulo") or f"Leilão descoberto em {host(url)}")
        item.setdefault("link", url); item.setdefault("site_leiloeiro", url)
        rows.append(item)
    fields = list(dict.fromkeys([key for row in rows for key in row] or ["nome", "link", "fonte_descoberta"]))
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _client_get(client, url: str, deadline: float):
    if isinstance(client, HttpClient):
        return client.get(url, deadline=deadline)
    if time.monotonic() >= deadline:
        raise DomainBudgetExceeded(url)
    return client.get(url)


def _parsed_timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _portal_due(entry: dict, current: datetime | None = None) -> bool:
    next_check = _parsed_timestamp(entry.get("proxima_verificacao"))
    return next_check is None or next_check <= (current or datetime.now(timezone.utc))


def select_portals(catalog: list[dict], deep: bool) -> list[dict]:
    active = [entry for entry in catalog if entry.get("ativo", True) and _portal_due(entry)]
    active.sort(
        key=lambda entry: (
            _parsed_timestamp(entry.get("ultima_verificacao"))
            or datetime.min.replace(tzinfo=timezone.utc),
            entry["dominio"],
        )
    )
    if deep or not CONFIG["FAST_MAX_PORTALS"]:
        return active
    return active[:CONFIG["FAST_MAX_PORTALS"]]


def _merge_records(previous: list[dict], current: list[dict], fields: tuple[str, ...]) -> tuple[list[dict], int]:
    merged: list[dict] = []
    seen: set[str] = set()
    current_keys: set[str] = set()
    for is_current, row in (
        [(True, row) for row in current]
        + [(False, row) for row in previous]
    ):
        if not isinstance(row, dict):
            continue
        key = next(
            (
                canonicalize_url(row.get(field))
                for field in fields
                if canonicalize_url(row.get(field))
            ),
            "",
        )
        if not key:
            key = "|".join(
                (
                    host(row.get("dominio_origem") or row.get("url_descoberta")),
                    str(row.get("nome") or row.get("titulo") or "").casefold().strip(),
                    str(row.get("lote") or "").casefold().strip(),
                )
            )
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(row)
        if is_current:
            current_keys.add(key)
    return merged, max(0, len(merged) - len(current_keys))


def _crawl_domain(
    index: int,
    total: int,
    domain: str,
    seeds: list[tuple[str, str]],
    entry: dict,
    deep: bool,
    client,
    global_deadline: float,
) -> dict:
    started = time.monotonic()
    domain_deadline = min(
        global_deadline,
        started + max(1, CONFIG["DOMAIN_TIME_BUDGET"]),
    )
    print(f"[PORTAL {index}/{total}] {domain}", flush=True)
    collector = GenericCollector()
    errors: list[dict] = []
    discovered: list[dict] = []
    lots: list[dict] = []
    paths: list[str] = []
    visited: set[str] = set()
    queue: deque[tuple[str, int, str]] = deque()
    max_seed_urls = 5 if deep else 2
    for seed, source in seeds[:max_seed_urls]:
        canonical = canonicalize_url(seed)
        if canonical and canonical not in visited:
            queue.append((canonical, 0, source))
    base = f"https://{domain}"
    if not queue:
        queue.append((base + "/", 0, "home"))

    diag = {
        "dominio": domain,
        "eventos_encontrados": 0,
        "lotes_encontrados": 0,
        "paginas_visitadas": 0,
        "status_acesso": "pendente",
        "metodo_funcional": seeds[0][1] if seeds else "home",
        "tempo_resposta": 0,
    }
    timed_out = False

    def crawl_queue() -> None:
        nonlocal timed_out
        while queue and diag["paginas_visitadas"] < CONFIG["MAX_PAGES_PER_DOMAIN"]:
            if time.monotonic() >= domain_deadline:
                timed_out = True
                return
            url, depth, source = queue.popleft()
            if url in visited or host(url) != domain:
                continue
            visited.add(url)
            diag["paginas_visitadas"] += 1
            try:
                body, final, code, _ = _client_get(client, url, domain_deadline)
            except DomainBudgetExceeded as exc:
                errors.append(error_record(domain, url, "domain_budget", exc))
                timed_out = True
                return
            except Exception as exc:
                errors.append(error_record(domain, url, "pagina", exc))
                continue
            if code != 200:
                errors.append(error_record(domain, url, "http", http_status=code))
                diag["ultima_falha"] = now()
                diag["http_status"] = code
                diag["status_acesso"] = (
                    "rate_limited"
                    if code == 429
                    else "temporariamente_bloqueado"
                    if code == 403
                    else "timeout"
                    if code == 0
                    else "erro_temporario"
                )
                continue
            try:
                page_lots, links = collector.parse_html(final, body)
            except Exception as exc:
                errors.append(error_record(domain, final, "parse_html", exc, code))
                continue
            learned = canonicalize_url(final)
            if learned and learned not in paths:
                paths.append(learned)
            discovered.append(
                {
                    "nome": (
                        page_lots[0].get("titulo")
                        if page_lots
                        else f"Leilão em {domain}"
                    ),
                    "link": final,
                    "site_leiloeiro": final,
                    "fonte_descoberta": source,
                    "dominio_origem": domain,
                    "url_descoberta": seeds[0][0] if seeds else final,
                    "descoberto_em": now(),
                    "confianca_dados": (
                        "alta"
                        if any(
                            item.get("fonte_descoberta") == "json_ld"
                            for item in page_lots
                        )
                        else "media"
                    ),
                    "status_evento": "desconhecido",
                }
            )
            lots.extend(
                dict(
                    lot,
                    dominio_origem=domain,
                    url_descoberta=seeds[0][0] if seeds else final,
                    descoberto_em=now(),
                )
                for lot in page_lots[:CONFIG["MAX_LOTS_PER_DOMAIN"]]
            )
            diag["eventos_encontrados"] += 1
            diag["lotes_encontrados"] += len(page_lots)
            diag["ultimo_sucesso"] = now()
            diag["status_acesso"] = "ok"
            diag["metodo_funcional"] = source
            if depth < CONFIG["MAX_DEPTH"]:
                for link in links[:CONFIG["MAX_URLS_PER_DOMAIN"]]:
                    queue.append((link, depth + 1, "link_interno"))

    crawl_queue()

    # No modo rápido, sitemap/home são fallback. No profundo, fazem parte da
    # descoberta, mas apenas uma vez por domínio.
    should_try_sitemap = deep or diag["eventos_encontrados"] == 0
    learned_sitemap = ""
    if (
        should_try_sitemap
        and not timed_out
        and diag["paginas_visitadas"] < CONFIG["MAX_PAGES_PER_DOMAIN"]
    ):
        sitemap_candidates: list[str] = []
        configured_sitemap = canonicalize_url(entry.get("sitemap"))
        if configured_sitemap:
            sitemap_candidates.append(configured_sitemap)
        if deep:
            try:
                robot, _, robot_code, _ = _client_get(
                    client,
                    base + "/robots.txt",
                    domain_deadline,
                )
                if robot_code == 200:
                    sitemap_candidates.extend(robots_sitemaps(robot))
            except DomainBudgetExceeded as exc:
                errors.append(error_record(domain, base + "/robots.txt", "domain_budget", exc))
                timed_out = True
            except Exception as exc:
                errors.append(error_record(domain, base + "/robots.txt", "robots", exc))
        sitemap_candidates.extend([base + "/sitemap.xml", base + "/sitemap_index.xml"])
        sitemap_limit = 8 if deep else 1
        for sitemap in list(dict.fromkeys(sitemap_candidates))[:sitemap_limit]:
            if timed_out or time.monotonic() >= domain_deadline:
                timed_out = True
                break
            try:
                xml, _, code, _ = _client_get(client, sitemap, domain_deadline)
            except DomainBudgetExceeded as exc:
                errors.append(error_record(domain, sitemap, "domain_budget", exc))
                timed_out = True
                break
            except Exception as exc:
                errors.append(error_record(domain, sitemap, "sitemap", exc))
                continue
            if code != 200:
                continue
            learned_sitemap = sitemap
            urls, indexes = sitemap_urls(xml, CONFIG["MAX_URLS_PER_DOMAIN"])
            print(f"[SITEMAP] {domain} URLs={len(urls)}", flush=True)
            if deep:
                for child in indexes[:5]:
                    try:
                        child_xml, _, child_code, _ = _client_get(
                            client,
                            child,
                            domain_deadline,
                        )
                    except DomainBudgetExceeded as exc:
                        errors.append(error_record(domain, child, "domain_budget", exc))
                        timed_out = True
                        break
                    except Exception as exc:
                        errors.append(error_record(domain, child, "sitemap_filho", exc))
                        continue
                    if child_code == 200:
                        urls.extend(
                            sitemap_urls(
                                child_xml,
                                CONFIG["MAX_URLS_PER_DOMAIN"],
                            )[0]
                        )
            for url in urls[:CONFIG["MAX_URLS_PER_DOMAIN"]]:
                queue.append((url, 0, "sitemap"))
            if urls:
                break
        crawl_queue()

    if timed_out:
        diag["status_acesso"] = "timeout"
        diag["ultima_falha"] = now()
        print(f"[TIMEOUT] {domain}", flush=True)
    elif diag["status_acesso"] == "pendente":
        diag["status_acesso"] = "erro_temporario"
        diag["ultima_falha"] = now()
    diag["tempo_resposta"] = round(time.monotonic() - started, 2)
    print(
        f"[EVENTO] {domain} {diag['eventos_encontrados']} "
        f"[LOTES] {diag['lotes_encontrados']} "
        f"DURAÇÃO={diag['tempo_resposta']}s",
        flush=True,
    )
    return {
        "dominio": domain,
        "diagnostico": diag,
        "erros": errors,
        "eventos": discovered,
        "lotes": lots,
        "caminhos_conhecidos": paths,
        "sitemap": learned_sitemap,
    }


def run(deep: bool = False, client: HttpClient | None = None, search=search_web, map_path: Path | None = None) -> dict:
    started = time.monotonic()
    global_deadline = started + max(1, CONFIG["DISCOVERY_TIME_BUDGET"])
    client = client or HttpClient()
    catalog = [
        normalize_portal(entry)
        for entry in bootstrap_portais(sources=[map_path] if map_path else None)
        if isinstance(entry, dict) and entry.get("dominio")
    ]
    known = {entry["dominio"]: entry for entry in catalog}
    selected = select_portals(catalog, deep)
    selected_domains = {entry["dominio"] for entry in selected}
    new_entries = read_json(NEW_CATALOG, [])
    if not isinstance(new_entries, list):
        new_entries = []
    map_events = load_map_events(
        map_path or ROOT / "radar_leiloes_eventos_futuros.csv"
    )
    print(
        f"[MAPA] eventos={len(map_events)} modo={'PROFUNDO' if deep else 'RAPIDO'}",
        flush=True,
    )

    errors: list[dict] = []
    search_results = 0
    queries_executed: list[str] = []
    candidates: list[tuple[str, str]] = []
    provider_name = os.getenv("WEB_SEARCH_PROVIDER", "openai").strip().casefold() or "openai"
    configured = provider_name == "openai" and bool(os.getenv("OPENAI_API_KEY", "").strip())
    search_enabled = configured and (deep or os.getenv("OPENAI_SEARCH_IN_QUICK", "0") == "1")
    group, queries = ("NA", [])
    if search_enabled:
        group, queries = query_group(deep=deep)
        for position, query in enumerate(queries, 1):
            if time.monotonic() >= global_deadline:
                errors.append(
                    {
                        "consulta": query,
                        "erro": "GlobalBudgetExceeded",
                        "mensagem": "Orçamento global esgotado antes da consulta.",
                    }
                )
                break
            print(f"[OPENAI {position}/{len(queries)}] {query}", flush=True)
            try:
                found = search(query, 1, CONFIG["MAX_RESULTS_PER_QUERY"])
                queries_executed.append(query)
                search_results += len(found)
                candidates.extend((item.url, "busca_web") for item in found)
                print(f"[OPENAI] resultados={len(found)}", flush=True)
            except Exception as exc:
                queries_executed.append(query)
                errors.append(
                    {
                        "consulta": query,
                        "erro": type(exc).__name__,
                        "mensagem": str(exc),
                    }
                )
                print(f"[ERRO] OPENAI {type(exc).__name__}: {exc}", flush=True)

    for entry in selected:
        learned = (
            entry.get("caminhos_conhecidos")
            or [entry.get("pagina_eventos"), entry.get("url_exemplo")]
        )
        candidates.extend(
            (url, "portal_direto")
            for url in learned
            if url
        )
    # O mapa só alimenta a descoberta profunda. No modo rápido, os mesmos
    # eventos serão atualizados pelo indexador de lotes, evitando rede duplicada.
    if deep or search_enabled:
        candidates.extend(
            (
                entry.get("site_leiloeiro") or entry.get("link"),
                "mapa",
            )
            for entry in map_events
            if entry.get("site_leiloeiro") or entry.get("link")
        )

    grouped: dict[str, list[tuple[str, str]]] = {}
    new_count = 0
    invalid_seen: set[str] = set()
    for seed, source in candidates:
        canonical = canonicalize_url(seed)
        domain = host(canonical)
        if not domain:
            raw = str(seed or "")
            if raw not in invalid_seen:
                errors.append(error_record("", raw, "validar_url", ValueError("URL inválida")))
                invalid_seen.add(raw)
            continue
        is_new = domain not in known
        if is_new and new_count >= CONFIG["MAX_NEW_DOMAINS"]:
            continue
        if is_new:
            timestamp = now()
            new_count += 1
            selected_domains.add(domain)
            known[domain] = normalize_portal(
                {
                    "dominio": domain,
                    "ativo": True,
                    "origem": "openai_web_search" if source == "busca_web" else source,
                    "descoberto_em": timestamp,
                    "url_exemplo": canonical,
                    "novo_nesta_execucao": True,
                }
            )
            new_entries.append(
                {
                    "dominio": domain,
                    "url_exemplo": canonical,
                    "descoberto_em": timestamp,
                    "consulta_que_encontrou": source,
                    "status": "pendente",
                    "tipo_coleta": "generico",
                    "ultima_verificacao": timestamp,
                }
            )
        if domain not in selected_domains and not deep:
            continue
        bucket = grouped.setdefault(domain, [])
        item = (canonical, source)
        if canonical and item not in bucket:
            bucket.append(item)

    work = sorted(grouped.items())
    discovered: list[dict] = []
    lots: list[dict] = []
    diagnostics: dict[str, dict] = {}
    workers = max(1, min(CONFIG["GLOBAL_WORKERS"], len(work) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _crawl_domain,
                index,
                len(work),
                domain,
                seeds,
                known[domain],
                deep,
                client,
                global_deadline,
            ): domain
            for index, (domain, seeds) in enumerate(work, 1)
        }
        for future in as_completed(futures):
            domain = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                errors.append(error_record(domain, "", "portal", exc))
                print(f"[ERRO] {domain} {type(exc).__name__}: {exc}", flush=True)
                result = {
                    "dominio": domain,
                    "diagnostico": {
                        "dominio": domain,
                        "eventos_encontrados": 0,
                        "lotes_encontrados": 0,
                        "paginas_visitadas": 0,
                        "status_acesso": "erro_temporario",
                        "ultima_falha": now(),
                        "tempo_resposta": 0,
                    },
                    "erros": [],
                    "eventos": [],
                    "lotes": [],
                    "caminhos_conhecidos": [],
                    "sitemap": "",
                }
            diag = result["diagnostico"]
            diagnostics[domain] = diag
            errors.extend(result["erros"])
            discovered.extend(result["eventos"])
            lots.extend(result["lotes"])

            portal = known[domain]
            portal["ultima_verificacao"] = now()
            portal["possui_eventos"] = diag["eventos_encontrados"] > 0
            portal["possui_lotes"] = diag["lotes_encontrados"] > 0
            portal["status_acesso"] = diag["status_acesso"]
            portal["tempo_resposta"] = diag["tempo_resposta"]
            paths = portal.setdefault("caminhos_conhecidos", [])
            for path in result["caminhos_conhecidos"]:
                if path not in paths:
                    paths.append(path)
            portal["caminhos_conhecidos"] = paths[:CONFIG["MAX_URLS_PER_DOMAIN"]]
            if result["sitemap"]:
                portal["sitemap"] = result["sitemap"]
            success = diag["status_acesso"] == "ok"
            failures = (
                0
                if success
                else int(portal.get("falhas_consecutivas", 0) or 0) + 1
            )
            portal["falhas_consecutivas"] = failures
            if success:
                portal["ultimo_sucesso"] = diag.get("ultimo_sucesso", now())
                portal["proxima_verificacao"] = ""
                if paths:
                    portal["pagina_eventos"] = paths[0]
            else:
                delay = min(
                    CONFIG["FAILURE_BACKOFF_MAX"],
                    CONFIG["FAILURE_BACKOFF_BASE"]
                    * (2 ** max(0, failures - 1)),
                )
                portal["proxima_verificacao"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=delay)
                ).isoformat(timespec="seconds")

    for value in known.values():
        value.pop("novo_nesta_execucao", None)
    write_json(CATALOG, sorted(known.values(), key=lambda item: item["dominio"]))
    write_json(NEW_CATALOG, new_entries)

    previous_payload = read_json(EVENTS, {})
    previous_events = previous_payload.get("eventos", [])
    previous_lots = previous_payload.get("lotes", [])
    previous_events = previous_events if isinstance(previous_events, list) else []
    previous_lots = previous_lots if isinstance(previous_lots, list) else []
    merged_events, preserved_events = _merge_records(
        previous_events,
        discovered,
        ("site_leiloeiro", "link", "url_descoberta"),
    )
    merged_lots, preserved_lots = _merge_records(
        previous_lots,
        lots,
        ("link_lote",),
    )
    write_json(
        EVENTS,
        {
            "executado_em": now(),
            "modo": "profundo" if deep else "rapido",
            "eventos": merged_events,
            "lotes": merged_lots,
            "eventos_atualizados": len(discovered),
            "eventos_preservados": preserved_events,
            "lotes_atualizados": len(lots),
            "lotes_preservados": preserved_lots,
        },
    )
    consolidate(map_events, merged_events)
    sources = Counter(event["fonte_descoberta"] for event in discovered)
    domains = Counter(event["dominio_origem"] for event in discovered)
    openai_errors = [error for error in errors if "consulta" in error]
    report = {
        "status": "ok" if not errors else "parcial" if diagnostics else "erro",
        "modo": "profundo" if deep else "rapido",
        "executado_em": now(),
        "grupo_consultas": group,
        "provider": "openai",
        "web_search_provider": provider_name,
        "openai_configurada": configured,
        "openai_connection": (
            "OK"
            if search_enabled and not openai_errors
            else "ERRO"
            if search_enabled
            else "NAO_TESTADA"
        ),
        "openai_web_search": (
            "OK"
            if search_enabled and not openai_errors
            else "ERRO"
            if search_enabled
            else "NAO_TESTADA"
        ),
        "busca_web_configurada": configured,
        "modelo": os.getenv("OPENAI_SEARCH_MODEL", "").strip() or "gpt-5-mini",
        "consultas_executadas": len(queries_executed),
        "consultas": queries_executed,
        "resultados_web": search_results,
        "resultados_de_busca": search_results,
        "urls_descobertas": sum(len(items) for items in grouped.values()),
        "dominios_encontrados": len(diagnostics),
        "novos_dominios": new_count,
        "portais_total": len(known),
        "portais_planejados": len(work),
        "dominios_visitados": len(diagnostics),
        "portais_ok": sum(
            item["status_acesso"] == "ok" for item in diagnostics.values()
        ),
        "eventos_fora_do_mapa": len(merged_events),
        "lotes_fora_do_mapa": len(merged_lots),
        "eventos_descobertos": len(discovered),
        "eventos_preservados": preserved_events,
        "lotes_descobertos": len(lots),
        "lotes_preservados": preserved_lots,
        "lotes_novos": len(lots),
        "duplicados": 0,
        "bloqueados": sum(
            item["status_acesso"] == "temporariamente_bloqueado"
            for item in diagnostics.values()
        ),
        "timeouts": sum(
            item["status_acesso"] == "timeout"
            for item in diagnostics.values()
        ),
        "duracao": round(time.monotonic() - started, 2),
        "requires_browser": sum(
            item["status_acesso"] == "requires_browser"
            for item in diagnostics.values()
        ),
        "erros_openai": openai_errors,
        "erros": errors,
        "quantidade_por_fonte": dict(sources),
        "quantidade_por_dominio": dict(domains),
        "diagnostico_portais": [
            diagnostics[domain] for domain in sorted(diagnostics)
        ],
    }
    write_json(REPORT, report)
    coverage = {
        "executado_em": now(),
        "modo": report["modo"],
        "total_eventos_ativos": len(map_events) + len(merged_events),
        "total_lotes_ativos": len(merged_lots),
        "total_dominios": len(known),
        "dominios_novos": report["novos_dominios"],
        "dominios_com_suporte_especifico": 0,
        "dominios_coletor_generico": len(known),
        "dominios_bloqueados": report["bloqueados"],
        "dominios_timeout": report["timeouts"],
        "dominios_requires_browser": report["requires_browser"],
        "lotes_vindos_do_mapa": 0,
        "lotes_fora_do_mapa": len(merged_lots),
        "LOTES_FORA_DO_MAPA": len(merged_lots),
        "fontes_totais": len(known),
        "fontes_novas_na_execucao": report["novos_dominios"],
        "eventos_fora_do_mapa": len(merged_events),
    }
    write_json(COVERAGE, coverage)
    print(
        f"[FIM] MODO={report['modo'].upper()} "
        f"PORTAIS={report['dominios_visitados']} "
        f"EVENTOS={report['eventos_descobertos']} "
        f"LOTES={report['lotes_descobertos']} "
        f"DURAÇÃO={report['duracao']}s",
        flush=True,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--deep-discovery", action="store_true")
    mode.add_argument("--quick-refresh", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.deep_discovery), ensure_ascii=False)); return 0
    except Exception as exc:
        details = {"status": "erro", "causa": str(exc), "tipo_erro": type(exc).__name__, "traceback_resumido": traceback.format_exc(), "etapa": "fatal", "dominio": "", "url": "", "executado_em": now()}
        write_json(REPORT, details)
        traceback.print_exc()
        return 1


if __name__ == "__main__": raise SystemExit(main())
