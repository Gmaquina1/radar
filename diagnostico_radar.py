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
    "CNAME",
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
        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
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
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
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
        (
            datetime.now(TIMEZONE) - parsed
        ).total_seconds() / 3600,
        2,
    )


def build_status(extra: dict | None = None) -> dict:
    summary = read_json(
        ROOT / "radar_leiloes_resumo.json"
    )
    lots = read_json(ROOT / "lotes.json")

    missing = [
        name
        for name in REQUIRED_FILES
        if not (ROOT / name).exists()
    ]

    workflow_path = (
        ROOT / ".github/workflows/atualizar-radar.yml"
    )
    workflow = (
        workflow_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        if workflow_path.exists()
        else ""
    )

    index_path = ROOT / "index.html"
    index = (
        index_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        if index_path.exists()
        else ""
    )

    event_csv_total = count_csv(
        ROOT / "radar_leiloes_eventos_futuros.csv"
    )
    yard_csv_total = count_csv(
        ROOT / "radar_leiloes_patios.csv"
    )
    lot_csv_total = count_csv(ROOT / "lotes.csv")

    lot_list = lots.get("lotes", [])
    lot_json_total = (
        len(lot_list)
        if isinstance(lot_list, list)
        else 0
    )

    events_updated = summary.get("atualizado_em", "")
    lots_updated = lots.get("atualizado_em", "")
    events_age = age_hours(events_updated)
    lots_age = age_hours(lots_updated)

    checks = {
        "arquivos_obrigatorios": not missing,
        "workflow_existe": workflow_path.exists(),
        "workflow_execucao_manual": (
            "workflow_dispatch:" in workflow
        ),
        "workflow_agendado_6h": (
            '17 */6 * * *' in workflow
        ),
        "workflow_pode_salvar": (
            "contents: write" in workflow
        ),
        "workflow_executa_indexador": (
            "executar_atualizacao_radar.py" in workflow
        ),
        "eventos_csv_ok": event_csv_total > 0,
        "lotes_json_ok": lot_json_total > 0,
        "lotes_csv_consistente": (
            lot_csv_total == lot_json_total
        ),
        "site_gerado": (
            index_path.exists()
            and index_path.stat().st_size > 100_000
        ),
        "base_embutida_no_site": (
            'id="radar-data"' in index
        ),
        "dominio_configurado": (
            (ROOT / "CNAME").read_text(
                encoding="utf-8",
                errors="replace",
            ).strip()
            == "radar.empaez.com"
        ),
        "base_eventos_recente": (
            events_age is not None and events_age <= 12
        ),
        "base_lotes_recente": (
            lots_age is not None and lots_age <= 12
        ),
    }

    status = {
        "status": (
            "ok" if all(checks.values()) else "atencao"
        ),
        "verificado_em": iso_now(),
        "atualizado_em_base_eventos": events_updated,
        "atualizado_em_base_lotes": lots_updated,
        "idade_base_eventos_horas": events_age,
        "idade_base_lotes_horas": lots_age,
        "eventos_futuros": int(
            summary.get("eventos_futuros_ou_hoje")
            or event_csv_total
        ),
        "patios": int(
            summary.get("patios") or yard_csv_total
        ),
        "lotes": int(
            lots.get("total_lotes") or lot_json_total
        ),
        "lotes_capturados_agora": int(
            lots.get("total_lotes_capturados_agora")
            or 0
        ),
        "lotes_preservados": int(
            lots.get("total_lotes_preservados")
            or 0
        ),
        "eventos_indexados_com_lotes": int(
            lots.get("eventos_com_lotes") or 0
        ),
        "checks": checks,
        "arquivos_faltando": missing,
    }

    if extra:
        status.update(extra)

    return status


def write_status(status: dict) -> None:
    (ROOT / "status_atualizacao.json").write_text(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    failed_checks = [
        name
        for name, passed in status.get(
            "checks",
            {},
        ).items()
        if not passed
    ]

    lines = [
        f"Status: {status.get('status')}",
        f"Verificado em: {status.get('verificado_em')}",
        (
            "Base de eventos: "
            f"{status.get('atualizado_em_base_eventos')}"
        ),
        (
            "Base de lotes: "
            f"{status.get('atualizado_em_base_lotes')}"
        ),
        (
            "Idade da base de eventos: "
            f"{status.get('idade_base_eventos_horas')} horas"
        ),
        (
            "Idade da base de lotes: "
            f"{status.get('idade_base_lotes_horas')} horas"
        ),
        (
            "Eventos futuros: "
            f"{status.get('eventos_futuros')}"
        ),
        (
            "Lotes disponíveis: "
            f"{status.get('lotes')}"
        ),
        (
            "Lotes capturados nesta execução: "
            f"{status.get('lotes_capturados_agora')}"
        ),
        (
            "Lotes preservados: "
            f"{status.get('lotes_preservados')}"
        ),
        f"Lotes antes: {status.get('lotes_antes', '-')}",
        f"Lotes depois: {status.get('lotes_depois', '-')}",
        (
            "Lotes novos detectados: "
            f"{status.get('lotes_novos_detectados', '-')}"
        ),
        (
            "Lotes removidos ou encerrados: "
            f"{status.get('lotes_removidos_ou_encerrados', '-')}"
        ),
        f"Pátios: {status.get('patios')}",
        (
            "Verificações com problema: "
            + (
                ", ".join(failed_checks)
                if failed_checks
                else "nenhuma"
            )
        ),
    ]

    if status.get("mensagem"):
        lines.append(
            f"Mensagem: {status.get('mensagem')}"
        )

    (ROOT / "status_atualizacao.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Gera o diagnóstico da atualização do Radar."
        )
    )
    parser.add_argument(
        "--falhar-se-atencao",
        action="store_true",
    )
    args = parser.parse_args()

    previous = read_json(
        ROOT / "status_atualizacao.json"
    )

    keep_keys = (
        "ultima_execucao",
        "erro_em",
        "mensagem",
        "base_anterior_restaurada",
        "lotes_antes",
        "lotes_depois",
        "lotes_novos_detectados",
        "lotes_removidos_ou_encerrados",
        "etapas",
    )
    keep = {
        key: previous[key]
        for key in keep_keys
        if key in previous
    }

    status = build_status(keep)
    write_status(status)
    print(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2,
        )
    )

    if (
        args.falhar_se_atencao
        and status["status"] != "ok"
    ):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
