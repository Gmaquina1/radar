#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from diagnostico_radar import build_status, write_status


ROOT = Path(__file__).resolve().parent
TIMEZONE = ZoneInfo("America/Sao_Paulo")

GENERATED_FILES = [
    "index.html",
    "radar-leiloes.html",
    "leiloes_do_brasil_completo.kml",
    "leiloes_do_brasil_completo.kml.sha256",
    "radar_leiloes_base_completa.csv",
    "radar_leiloes_eventos_futuros.csv",
    "radar_leiloes_eventos_todos.csv",
    "radar_leiloes_patios.csv",
    "radar_leiloes_resumo.json",
    "lotes.json",
    "lotes.csv",
    "monitoramento.json",
    "status_atualizacao.json",
    "status_atualizacao.txt",
]


def iso_now() -> str:
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


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


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def normalize_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
        path = parts.path.rstrip("/") or "/"
        return urlunsplit(
            (
                parts.scheme.casefold(),
                parts.netloc.casefold(),
                path,
                "",
                "",
            )
        )
    except ValueError:
        return text.casefold().rstrip("/")


def lot_key(row: dict) -> str:
    lot_url = normalize_url(row.get("link_lote"))
    if lot_url:
        return f"url:{lot_url}"

    return "dados:" + "|".join(
        [
            normalize_text(row.get("leiloeiro")),
            normalize_text(row.get("evento")),
            normalize_text(row.get("lote")),
            normalize_text(row.get("titulo")),
        ]
    )


def lot_keys(payload: dict) -> set[str]:
    rows = payload.get("lotes", [])
    if not isinstance(rows, list):
        return set()
    return {
        lot_key(row)
        for row in rows
        if isinstance(row, dict) and lot_key(row)
    }


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


def is_recent(value: object, maximum_hours: float = 8.0) -> bool:
    parsed = parse_datetime(value)
    if parsed is None:
        return False
    age = (datetime.now(TIMEZONE) - parsed).total_seconds() / 3600
    return -1 <= age <= maximum_hours


def backup_generated_files(folder: Path) -> None:
    for relative in GENERATED_FILES:
        source = ROOT / relative
        if source.exists() and source.is_file():
            target = folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def restore_generated_files(folder: Path) -> None:
    for relative in GENERATED_FILES:
        backup = folder / relative
        target = ROOT / relative
        if backup.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)


def run_step(name: str, command: list[str], attempts: int = 1) -> dict:
    started = time.time()
    last_code = 1

    for attempt in range(1, attempts + 1):
        print(
            f"::group::{name} - tentativa {attempt}/{attempts}",
            flush=True,
        )
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            check=False,
        )
        print("::endgroup::", flush=True)
        last_code = result.returncode

        if result.returncode == 0:
            return {
                "nome": name,
                "comando": command,
                "tentativas": attempt,
                "duracao_segundos": round(time.time() - started, 2),
                "status": "ok",
                "codigo": 0,
            }

        if attempt < attempts:
            time.sleep(15 * attempt)

    return {
        "nome": name,
        "comando": command,
        "tentativas": attempts,
        "duracao_segundos": round(time.time() - started, 2),
        "status": "erro",
        "codigo": last_code,
    }


def validate_events() -> tuple[bool, str]:
    summary = read_json(ROOT / "radar_leiloes_resumo.json")
    event_total = count_csv(
        ROOT / "radar_leiloes_eventos_futuros.csv"
    )
    updated_at = summary.get("atualizado_em")

    if event_total < 10:
        return (
            False,
            f"A coleta retornou apenas {event_total} eventos futuros.",
        )

    if not is_recent(updated_at):
        return (
            False,
            "A data da base de eventos não foi renovada: "
            f"{updated_at!r}.",
        )

    return True, f"{event_total} eventos futuros coletados."


def validate_lots(previous_total: int) -> tuple[bool, str]:
    payload = read_json(ROOT / "lotes.json")
    rows = payload.get("lotes", [])
    rows_total = len(rows) if isinstance(rows, list) else 0
    informed_total = int(payload.get("total_lotes") or rows_total)
    csv_total = count_csv(ROOT / "lotes.csv")
    captured_total = int(
        payload.get("total_lotes_capturados_agora") or 0
    )
    preserved_total = int(
        payload.get("total_lotes_preservados") or 0
    )
    updated_at = payload.get("atualizado_em")

    minimum_safe = (
        max(25, int(previous_total * 0.05))
        if previous_total
        else 25
    )

    if not is_recent(updated_at):
        return (
            False,
            "A data da base de lotes não foi renovada: "
            f"{updated_at!r}.",
        )

    if rows_total != informed_total:
        return (
            False,
            f"O JSON informa {informed_total} lotes, "
            f"mas contém {rows_total}.",
        )

    if csv_total != rows_total:
        return (
            False,
            f"O CSV contém {csv_total} lotes, "
            f"mas o JSON contém {rows_total}.",
        )

    if rows_total < minimum_safe:
        return (
            False,
            f"A nova base ficou com apenas {rows_total} lotes. "
            f"O mínimo de segurança era {minimum_safe}.",
        )

    if captured_total == 0 and preserved_total == 0:
        return (
            False,
            "Nenhum lote foi capturado nem preservado.",
        )

    return (
        True,
        f"{rows_total} lotes na base final; "
        f"{captured_total} capturados nesta execução e "
        f"{preserved_total} preservados.",
    )


def fail_and_restore(
    backup: Path,
    results: list[dict],
    error_at: str,
    message: str,
    code: int,
) -> int:
    restore_generated_files(backup)
    status = build_status(
        {
            "status": "erro",
            "ultima_execucao": iso_now(),
            "erro_em": error_at,
            "mensagem": message,
            "base_anterior_restaurada": True,
            "etapas": results,
        }
    )
    write_status(status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return code or 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Atualiza eventos, lotes e site com proteção "
            "da base anterior."
        )
    )
    parser.add_argument("--workers-mapa", type=int, default=24)
    parser.add_argument("--workers-lotes", type=int, default=16)
    parser.add_argument("--delay-lotes", type=float, default=0)
    parser.add_argument("--sem-lotes", action="store_true")
    args = parser.parse_args()

    previous_payload = read_json(ROOT / "lotes.json")
    previous_rows = previous_payload.get("lotes", [])
    previous_total = (
        len(previous_rows)
        if isinstance(previous_rows, list)
        else int(previous_payload.get("total_lotes") or 0)
    )
    previous_keys = lot_keys(previous_payload)

    results: list[dict] = []

    with tempfile.TemporaryDirectory(
        prefix="backup_radar_"
    ) as temporary:
        backup = Path(temporary)
        backup_generated_files(backup)

        event_step = run_step(
            "Atualizar eventos pelo Google My Maps",
            [
                sys.executable,
                "atualizar_radar_leiloes.py",
                "--workers",
                str(args.workers_mapa),
            ],
            attempts=3,
        )
        results.append(event_step)

        if event_step["status"] != "ok":
            return fail_and_restore(
                backup,
                results,
                event_step["nome"],
                (
                    "Não foi possível atualizar os eventos. "
                    "A base anterior foi restaurada."
                ),
                event_step["codigo"],
            )

        events_ok, events_message = validate_events()
        print(events_message, flush=True)
        if not events_ok:
            return fail_and_restore(
                backup,
                results,
                "Validação da base de eventos",
                events_message + " A base anterior foi restaurada.",
                2,
            )

        if not args.sem_lotes:
            lot_step = run_step(
                "Procurar novos lotes nos sites dos leiloeiros",
                [
                    sys.executable,
                    "indexador_lotes.py",
                    "--delay",
                    str(args.delay_lotes),
                    "--workers",
                    str(args.workers_lotes),
                ],
                attempts=2,
            )
            results.append(lot_step)

            if lot_step["status"] != "ok":
                return fail_and_restore(
                    backup,
                    results,
                    lot_step["nome"],
                    (
                        "Não foi possível concluir a busca dos "
                        "lotes. A base anterior foi restaurada."
                    ),
                    lot_step["codigo"],
                )

            lots_ok, lots_message = validate_lots(previous_total)
            print(lots_message, flush=True)
            if not lots_ok:
                return fail_and_restore(
                    backup,
                    results,
                    "Validação da base de lotes",
                    lots_message + " A base anterior foi restaurada.",
                    3,
                )

        final_payload = read_json(ROOT / "lotes.json")
        final_rows = final_payload.get("lotes", [])
        final_total = (
            len(final_rows)
            if isinstance(final_rows, list)
            else int(final_payload.get("total_lotes") or 0)
        )
        final_keys = lot_keys(final_payload)
        new_count = len(final_keys - previous_keys)
        removed_count = len(previous_keys - final_keys)

        for name, command, attempts in [
            (
                "Gerar novamente o site",
                [sys.executable, "gerar_site_github.py"],
                2,
            ),
            (
                "Gerar diagnóstico final",
                [
                    sys.executable,
                    "diagnostico_radar.py",
                    "--falhar-se-atencao",
                ],
                1,
            ),
        ]:
            result = run_step(name, command, attempts)
            results.append(result)

            if result["status"] != "ok":
                return fail_and_restore(
                    backup,
                    results,
                    name,
                    (
                        "A etapa final apresentou erro. "
                        "A base anterior foi restaurada."
                    ),
                    result["codigo"],
                )

        status = build_status(
            {
                "status": "ok",
                "ultima_execucao": iso_now(),
                "mensagem": (
                    "Eventos, lotes e site atualizados com sucesso."
                ),
                "base_anterior_restaurada": False,
                "lotes_antes": previous_total,
                "lotes_depois": final_total,
                "lotes_novos_detectados": new_count,
                "lotes_removidos_ou_encerrados": removed_count,
                "etapas": results,
            }
        )
        write_status(status)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
