#!/usr/bin/env python3
import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import date, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - GitHub Actions installs this normally.
    PdfReader = None


MAP_ID = "1fYo8R4P75VxKA3TqsiuLsWIqIDEO27U"
KML_URL = f"https://www.google.com/maps/d/kml?forcekml=1&mid={MAP_ID}"
TIMEZONE = ZoneInfo("America/Sao_Paulo")
FIELDS = [
    "nome",
    "camada",
    "data",
    "data_original",
    "hora_marcador",
    "status_data",
    "uf",
    "endereco_ou_localizacao",
    "latitude",
    "longitude",
    "link",
    "site_leiloeiro",
    "fonte_data_hora",
    "link_edital",
    "resumo_edital",
    "descricao",
]
VALID_UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
UF_RE = re.compile(r"(?:^|[\s,\-/])([A-Z]{2})(?:\s|,|$)")
PDF_RE = re.compile(r"\.pdf(?:$|[?#])", re.I)
HREF_RE = re.compile(r"""href=["']([^"']+)["']""", re.I)
DATE_RE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})")
DATE_LONG_RE = re.compile(
    r"(\d{1,2})\s+de\s+"
    r"(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)"
    r"(?:\s+de)?\s+(\d{4})",
    re.I,
)
TIME_RE = re.compile(r"(?<!\d)(\d{1,2})(?:[:hH](\d{2}))?\s*(?:horas?|hrs?)?(?!\d)", re.I)
KEYWORDS_RE = re.compile(
    r"data\s*(?:e|/)?\s*hor[aá]rio|hor[aá]rio|abertura|in[ií]cio|"
    r"encerramento|leil[aã]o|sess[aã]o|preg[aã]o|visita[cç][aã]o|"
    r"comiss[aã]o|pagamento|retirada|vendedor",
    re.I,
)


def text(el, path, ns):
    node = el.find(path, ns)
    return (node.text or "").strip() if node is not None else ""


def clean_html(value):
    if not value:
        return ""
    value = unescape(value)
    value = re.sub(r"<br\s*/?>", " | ", value, flags=re.I)
    value = TAG_RE.sub(" ", value)
    return SPACE_RE.sub(" ", unescape(value)).strip()


def clean_text(value):
    if not value:
        return ""
    value = unescape(value)
    value = TAG_RE.sub(" ", value)
    return SPACE_RE.sub(" ", value).strip()


def absolute_url(base, url):
    return urllib.parse.urljoin(base, unescape(url or ""))


def google_drive_download_url(url):
    parsed = urllib.parse.urlparse(url or "")
    if "drive.google.com" not in parsed.netloc:
        return url
    match = re.search(r"/file/d/([^/]+)", parsed.path)
    file_id = match.group(1) if match else urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
    if not file_id:
        return url
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def fetch_bytes(url, timeout=8, max_bytes=5_000_000, attempts=3):
    request = urllib.request.Request(
        google_drive_download_url(url),
        headers={
            "User-Agent": "Mozilla/5.0 RadarLeiloesGMaquina/1.0",
            "Accept": "text/html,application/pdf,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        },
    )
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get("content-type", "")
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    data = data[:max_bytes]
                final_url = response.geturl()
                return response.status, data, content_type, final_url
        except urllib.error.HTTPError as exc:
            try:
                data = exc.read(200_000)
            except Exception:
                data = b""
            return exc.code, data, exc.headers.get("content-type", ""), url
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    return 0, str(last_error or "").encode("utf-8"), "", url


def format_hour_24(value):
    match = TIME_RE.search(value or "")
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if hour > 23 or minute > 59:
        return ""
    return f"{hour:02d}:{minute:02d}"


def download_kml(target, attempts=4):
    request = urllib.request.Request(
        KML_URL,
        headers={
            "User-Agent": "Mozilla/5.0 RadarLeiloesGMaquina/1.0",
            "Accept": "application/vnd.google-earth.kml+xml,application/xml,text/xml,*/*",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        },
    )
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = response.read()
            if len(data) < 10_000:
                raise RuntimeError("KML baixado parece incompleto.")
            if b"<kml" not in data[:500].lower() and b"<kml" not in data.lower()[:5000]:
                raise RuntimeError("Resposta recebida nao parece ser um KML.")
            target.write_bytes(data)
            (target.with_suffix(target.suffix + ".sha256")).write_text(
                hashlib.sha256(data).hexdigest() + "\n",
                encoding="utf-8",
            )
            return
        except Exception as exc:
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(3 * attempt)
    raise SystemExit(f"Falha ao baixar KML depois de {attempts} tentativas: {last_error}")


def parent_map(root):
    return {child: parent for parent in root.iter() for child in list(parent)}


def folder_for(pm, parents, ns):
    current = pm
    while current in parents:
        current = parents[current]
        if current.tag.endswith("Folder"):
            return text(current, "kml:name", ns)
    return ""


def data_dict(pm, ns):
    out = {}
    for item in pm.findall(".//kml:Data", ns):
        name = (item.attrib.get("name") or "").strip()
        out[name] = text(item, "kml:value", ns)
    return out


def links_from(*values):
    links = []
    for value in values:
        for url in URL_RE.findall(value or ""):
            url = unescape(url).rstrip(").,;")
            if url not in links:
                links.append(url)
    return " | ".join(links)


def parse_date(value):
    match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", value or "")
    if not match:
        return ""
    day, month, year = match.groups()
    year = int(year)
    if year < 100:
        year += 2000
    try:
        return date(year, int(month), int(day)).isoformat()
    except ValueError:
        return ""


def parse_date_match(match):
    day, month, year = match.groups()
    year = int(year)
    if year < 100:
        year += 2000
    try:
        parsed = date(year, int(month), int(day))
    except ValueError:
        return "", ""
    return parsed.isoformat(), f"{int(day):02d}/{int(month):02d}/{year:04d}"


def parse_long_date_match(match):
    months = {
        "janeiro": 1,
        "fevereiro": 2,
        "marco": 3,
        "março": 3,
        "abril": 4,
        "maio": 5,
        "junho": 6,
        "julho": 7,
        "agosto": 8,
        "setembro": 9,
        "outubro": 10,
        "novembro": 11,
        "dezembro": 12,
    }
    day, month_name, year = match.groups()
    month = months.get(month_name.casefold().replace("ç", "c")) or months.get(month_name.casefold())
    if not month:
        return "", ""
    try:
        parsed = date(int(year), month, int(day))
    except ValueError:
        return "", ""
    return parsed.isoformat(), f"{int(day):02d}/{month:02d}/{int(year):04d}"


def candidate_snippets(text, radius=240):
    text = clean_text(text)
    if not text:
        return []
    snippets = []
    for match in KEYWORDS_RE.finditer(text):
        start = max(0, match.start() - radius)
        end = min(len(text), match.end() + radius)
        snippets.append(text[start:end])
        if len(snippets) >= 12:
            break
    if not snippets:
        snippets.append(text[:5000])
    return snippets


def parse_datetime_from_text(text):
    for snippet in candidate_snippets(text):
        dates = [(match.start(), match.end(), *parse_date_match(match)) for match in DATE_RE.finditer(snippet)]
        dates += [(match.start(), match.end(), *parse_long_date_match(match)) for match in DATE_LONG_RE.finditer(snippet)]
        dates = sorted(item for item in dates if item[2])
        if not dates:
            continue
        for start, end, data_iso, data_original in dates:
            right_context = snippet[end : end + 160]
            left_context = snippet[max(0, start - 80) : start]
            hour = format_hour_24(right_context) or format_hour_24(left_context)
            return data_iso, data_original, hour, clean_text(snippet)[:700]
    return "", "", "", ""


def extract_pdf_text(data):
    if not data or PdfReader is None:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages[:6]:
            pages.append(page.extract_text() or "")
        return clean_text(" ".join(pages))
    except Exception:
        return ""


def extract_pdf_links(html, base_url):
    links = []
    for href in HREF_RE.findall(html or ""):
        url = absolute_url(base_url, href)
        if PDF_RE.search(url) or "drive.google.com" in urllib.parse.urlparse(url).netloc:
            if url not in links:
                links.append(url)
    for url in URL_RE.findall(html or ""):
        url = absolute_url(base_url, url.rstrip(").,;"))
        if PDF_RE.search(url) or "drive.google.com" in urllib.parse.urlparse(url).netloc:
            if url not in links:
                links.append(url)
    return links[:2]


def inspect_document_url(url):
    status, data, content_type, final_url = fetch_bytes(url)
    if not data or status not in {200, 201, 202}:
        return {}
    is_pdf = PDF_RE.search(final_url) or "pdf" in content_type.lower() or data[:4] == b"%PDF"
    if is_pdf:
        doc_text = extract_pdf_text(data)
        data_iso, data_original, hour, snippet = parse_datetime_from_text(doc_text)
        return {
            "data": data_iso,
            "data_original": data_original,
            "hora": hour,
            "link_edital": final_url,
            "resumo_edital": snippet,
            "fonte": "edital_pdf",
        }

    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if match:
        charset = match.group(1)
    html = data.decode(charset, errors="replace")
    data_iso, data_original, hour, snippet = parse_datetime_from_text(html)
    best = {
        "data": data_iso,
        "data_original": data_original,
        "hora": hour,
        "link_edital": "",
        "resumo_edital": snippet,
        "fonte": "site",
    }
    for pdf_url in extract_pdf_links(html, final_url or url):
        pdf_info = inspect_document_url(pdf_url)
        if pdf_info.get("data"):
            return pdf_info
    return best


def enrich_row_datetime(row):
    links = [item.strip() for item in (row.get("link") or "").split("|") if item.strip()]
    for url in links[:2]:
        info = inspect_document_url(url)
        if not info.get("data"):
            continue
        try:
            captured_date = date.fromisoformat(info["data"])
            today = datetime.now(TIMEZONE).date()
            if captured_date < today - timedelta(days=2) or captured_date > today + timedelta(days=370):
                continue
        except ValueError:
            continue
        row["data"] = info["data"]
        row["data_original"] = info.get("data_original") or row.get("data_original", "")
        if info.get("hora"):
            row["hora_marcador"] = info["hora"]
        row["fonte_data_hora"] = info.get("fonte", "")
        row["link_edital"] = info.get("link_edital", "")
        row["resumo_edital"] = info.get("resumo_edital", "")
        return row
    if row.get("hora_marcador"):
        row["hora_marcador"] = format_hour_24(row["hora_marcador"]) or row["hora_marcador"]
    row.setdefault("fonte_data_hora", "mapa")
    row.setdefault("link_edital", "")
    row.setdefault("resumo_edital", "")
    return row


def enrich_rows(rows, workers=8):
    enriched = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(enrich_row_datetime, dict(row)): index
            for index, row in enumerate(rows)
        }
        for future in as_completed(futures):
            enriched.append((futures[future], future.result()))
    return [row for _, row in sorted(enriched, key=lambda item: item[0])]


def update_status(row, today):
    reference = today if isinstance(today, datetime) else datetime.combine(today, datetime.min.time(), tzinfo=TIMEZONE)
    row["status_data"] = "futuro_ou_hoje" if is_upcoming_event(row, reference) else "passado"
    return row


def is_upcoming_event(row, now=None):
    """Retorna verdadeiro apenas quando o horario do leilao ainda nao passou."""
    now = now or datetime.now(TIMEZONE)
    data_iso = row.get("data", "")
    if not data_iso:
        return False
    try:
        event_day = date.fromisoformat(data_iso)
    except ValueError:
        return False
    if event_day > now.date():
        return True
    if event_day < now.date():
        return False
    hour = format_hour_24(row.get("hora_marcador", ""))
    if not hour:
        return True
    event_at = datetime.fromisoformat(f"{data_iso}T{hour}").replace(tzinfo=TIMEZONE)
    return event_at > now


def infer_uf(*values):
    merged = " ".join(value or "" for value in values)
    for match in re.finditer(r"[-,\/]\s*([A-Z]{2})(?:\s|,|$)", merged):
        uf = match.group(1)
        if uf in VALID_UFS:
            return uf
    for match in UF_RE.finditer(merged):
        uf = match.group(1)
        if uf in VALID_UFS:
            return uf
    return ""


def parse_kml(kml_path, today):
    root = ET.parse(kml_path).getroot()
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    parents = parent_map(root)
    rows = []

    for pm in root.findall(".//kml:Placemark", ns):
        data = data_dict(pm, ns)
        name = text(pm, "kml:name", ns)
        camada = folder_for(pm, parents, ns)
        desc_raw = text(pm, "kml:description", ns)
        address = (
            text(pm, "kml:address", ns)
            or data.get("LOCALIZAÇÃO")
            or data.get("ENDEREÇO DO PATIO")
            or data.get("LOCALIZAÇÃO ALTERNATIVA", "")
        )
        data_original = data.get("DATA", "")
        data_iso = parse_date(data_original)
        descricao = clean_html(data.get("DESCRIÇÃO", "") or desc_raw)
        site = data.get("SITE DO LEILOEIRO", "")
        link = links_from(data.get("DESCRIÇÃO", ""), desc_raw, site)
        coords = text(pm, ".//kml:coordinates", ns)
        latitude = longitude = ""
        if coords:
            parts = coords.split()[0].split(",")
            if len(parts) >= 2:
                longitude, latitude = parts[0], parts[1]

        status = "sem_data"
        if data_iso:
            status = "futuro_ou_hoje" if date.fromisoformat(data_iso) >= today else "passado"

        rows.append(
            {
                "nome": name,
                "camada": camada,
                "data": data_iso,
                "data_original": data_original,
                "hora_marcador": data.get("MARCADOR", ""),
                "status_data": status,
                "uf": infer_uf(name, address, descricao),
                "endereco_ou_localizacao": address,
                "latitude": latitude,
                "longitude": longitude,
                "link": link,
                "site_leiloeiro": site,
                "fonte_data_hora": "mapa",
                "link_edital": "",
                "resumo_edital": "",
                "descricao": descricao,
            }
        )
    return rows


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Atualiza a base do Radar de Leiloes.")
    parser.add_argument("--saida", default=".", help="Pasta onde salvar os arquivos")
    parser.add_argument("--data-base", help="Data base YYYY-MM-DD. Padrao: hoje")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--sem-editais", action="store_true", help="Nao abrir sites/PDFs para enriquecer data e hora")
    parser.add_argument(
        "--usar-kml-local",
        action="store_true",
        help="Usa leiloes_do_brasil_completo.kml ja existente em vez de baixar do Google My Maps",
    )
    args = parser.parse_args()

    out = Path(args.saida).resolve()
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TIMEZONE)
    today = date.fromisoformat(args.data_base) if args.data_base else now.date()
    if args.data_base:
        now = datetime.combine(today, datetime.min.time(), tzinfo=TIMEZONE)

    kml_path = out / "leiloes_do_brasil_completo.kml"
    if args.usar_kml_local:
        if not kml_path.exists():
            raise SystemExit(f"KML local nao encontrado: {kml_path}")
        print(f"Usando KML local: {kml_path}")
    else:
        download_kml(kml_path)
    rows = parse_kml(kml_path, today)

    eventos = [
        row
        for row in rows
        if row["camada"] != "[PÁTIO DO LEILOEIRO]" and row["data_original"]
    ]
    if not args.sem_editais:
        eventos = enrich_rows(eventos, args.workers)
        eventos = [update_status(row, now) for row in eventos]
        enriched_by_key = {
            (row.get("nome", ""), row.get("link", "")): row
            for row in eventos
        }
        rows = [
            enriched_by_key.get((row.get("nome", ""), row.get("link", "")), row)
            for row in rows
        ]

    futuros = [row for row in eventos if is_upcoming_event(row, now)]
    patios = [row for row in rows if row["camada"] == "[PÁTIO DO LEILOEIRO]"]

    write_csv(out / "radar_leiloes_eventos_futuros.csv", futuros)
    write_csv(out / "radar_leiloes_eventos_todos.csv", eventos)
    write_csv(out / "radar_leiloes_patios.csv", patios)
    write_csv(out / "radar_leiloes_base_completa.csv", rows)

    summary = {
        "atualizado_em": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        "data_base": today.isoformat(),
        "total_registros": len(rows),
        "eventos_atualizacao": len(eventos),
        "eventos_futuros_ou_hoje": len(futuros),
        "patios": len(patios),
        "eventos_com_link": sum(1 for row in futuros if row["link"]),
        "eventos_com_data_hora_de_edital": sum(1 for row in futuros if row.get("fonte_data_hora") == "edital_pdf"),
        "eventos_com_data_hora_de_site": sum(1 for row in futuros if row.get("fonte_data_hora") == "site"),
        "eventos_por_uf": Counter(row["uf"] or "Sem UF" for row in futuros).most_common(),
        "datas": Counter(row["data"] or "sem_data" for row in futuros).most_common(),
    }
    (out / "radar_leiloes_resumo.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
