#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
TIMEZONE = ZoneInfo("America/Sao_Paulo")

REQUIRED_FILES = [
    "index.html",
    ".nojekyll",
    "radar-leiloes.html",
    "site_template.html",
    "gerar_site_github.py",
    "atualizar_radar_leiloes.py",
    "indexador_lotes.py",
    "executar_atualizacao_radar.py",
    ".github/workflows/atualizar-radar.yml",
    "radar_leiloes_eventos_futuros.csv",
    "radar_leiloes_eventos_todos.csv",
    "radar_leiloes_patios.csv",
    "radar_leiloes_base_completa.csv",
    "radar_leiloes_resumo.json",
    "lotes.json",
    "lotes.csv",
    "leiloes_do_brasil_completo.kml",
]


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def count_csv(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except OSError:
        return 0


def iso_now() -> str:
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


def parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TIMEZONE)
    return parsed.astimezone(TIMEZONE)


def age_hours(value: object) -> float | None:
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    return round(
        (datetime.now(TIMEZONE) - parsed).total_seconds() / 3600,
        2,
    )


def build_status(extra: dict | None = None) -> dict:
    resumo = read_json(ROOT / "radar_leiloes_resumo.json")
    lotes = read_json(ROOT / "lotes.json")

    missing = [name for name in REQUIRED_FILES if not (ROOT / name).exists()]

    workflow_path = ROOT / ".github/workflows/atualizar-radar.yml"
    workflow = (
        workflow_path.read_text(encoding="utf-8", errors="replace")
        if workflow_path.exists()
        else ""
    )
    index_path = ROOT / "index.html"
    index = (
        index_path.read_text(encoding="utf-8", errors="replace")
        if index_path.exists()
        else ""
    )

    eventos_csv = count_csv(ROOT / "radar_leiloes_eventos_futuros.csv")
    patios_csv = count_csv(ROOT / "radar_leiloes_patios.csv")
    lotes_csv = count_csv(ROOT / "lotes.csv")

    lotes_list = lotes.get("lotes", [])
    lotes_json = len(lotes_list) if isinstance(lotes_list, list) else 0

    events_updated = resumo.get("atualizado_em", "")
    lots_updated = lotes.get("atualizado_em", "")
    events_age = age_hours(events_updated)
    lots_age = age_hours(lots_updated)

    checks = {
        "arquivos_obrigatorios": not missing,
        "workflow_existe": workflow_path.exists(),
        "workflow_execucao_manual": "workflow_dispatch:" in workflow,
        "workflow_agendado_6h": '17 */6 * * *' in workflow,
        "workflow_pode_salvar": "contents: write" in workflow,
        "workflow_executa_indexador": "executar_atualizacao_radar.py" in workflow,
        "eventos_csv_ok": eventos_csv > 0,
        "lotes_json_ok": lotes_json > 0,
        "lotes_csv_consistente": lotes_csv == lotes_json,
        "site_gerado": index_path.exists() and index_path.stat().st_size > 100_000,
        "base_embutida_no_site": 'id="radar-data"' in index,
        "base_eventos_recente": events_age is not None and events_age <= 12,
        "base_lotes_recente": lots_age is not None and lots_age <= 12,
    }

    status = {
        "status": "ok" if all(checks.values()) else "atencao",
        "verificado_em": iso_now(),
        "atualizado_em_base_eventos": events_updated,
        "atualizado_em_base_lotes": lots_updated,
        "idade_base_eventos_horas": events_age,
        "idade_base_lotes_horas": lots_age,
        "eventos_futuros": int(
            resumo.get("eventos_futuros_ou_hoje") or eventos_csv
        ),
        "patios": int(resumo.get("patios") or patios_csv),
        "lotes": int(lotes.get("total_lotes") or lotes_json),
        "lotes_capturados_agora": int(
            lotes.get("total_lotes_capturados_agora") or 0
        ),
        "lotes_preservados": int(
            lotes.get("total_lotes_preservados") or 0
        ),
        "eventos_indexados_com_lotes": int(
            lotes.get("eventos_com_lotes") or 0
        ),
        "checks": checks,
        "arquivos_faltando": missing,
    }

    if extra:
        status.update(extra)

    return status


def write_status(status: dict) -> None:
    (ROOT / "status_atualizacao.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    failed_checks = [
        name
        for name, passed in status.get("checks", {}).items()
        if not passed
    ]

    lines = [
        f"Status: {status.get('status')}",
        f"Verificado em: {status.get('verificado_em')}",
        f"Base de eventos: {status.get('atualizado_em_base_eventos')}",
        f"Base de lotes: {status.get('atualizado_em_base_lotes')}",
        f"Idade da base de eventos: {status.get('idade_base_eventos_horas')} horas",
        f"Idade da base de lotes: {status.get('idade_base_lotes_horas')} horas",
        f"Eventos futuros: {status.get('eventos_futuros')}",
        f"Lotes disponíveis: {status.get('lotes')}",
        f"Lotes capturados agora: {status.get('lotes_capturados_agora')}",
        f"Lotes preservados: {status.get('lotes_preservados')}",
        f"Pátios: {status.get('patios')}",
        (
            "Verificações com problema: "
            + (", ".join(failed_checks) if failed_checks else "nenhuma")
        ),
    ]

    if status.get("mensagem"):
        lines.append(f"Mensagem: {status.get('mensagem')}")

    (ROOT / "status_atualizacao.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera o diagnóstico da atualização do Radar."
    )
    parser.add_argument("--falhar-se-atencao", action="store_true")
    args = parser.parse_args()

    previous = read_json(ROOT / "status_atualizacao.json")
    keep = {
        key: previous[key]
        for key in (
            "ultima_execucao",
            "erro_em",
            "mensagem",
            "base_anterior_restaurada",
            "etapas",
        )
        if key in previous
    }

    status = build_status(keep)
    write_status(status)
    print(json.dumps(status, ensure_ascii=False, indent=2))

    if args.falhar_se_atencao and status["status"] != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
