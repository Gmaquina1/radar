#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from diagnostico_radar import build_status, write_status


ROOT = Path(__file__).resolve().parent
TIMEZONE = ZoneInfo("America/Sao_Paulo")


def iso_now() -> str:
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


def run_step(name: str, command: list[str], attempts: int = 1) -> dict:
    started = time.time()
    last = None
    for attempt in range(1, attempts + 1):
        print(f"::group::{name} - tentativa {attempt}/{attempts}", flush=True)
        result = subprocess.run(command, cwd=ROOT, text=True)
        print("::endgroup::", flush=True)
        last = result
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
            time.sleep(10 * attempt)
    return {
        "nome": name,
        "comando": command,
        "tentativas": attempts,
        "duracao_segundos": round(time.time() - started, 2),
        "status": "erro",
        "codigo": last.returncode if last else 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa a atualizacao completa do Radar.")
    parser.add_argument("--workers-mapa", type=int, default=24)
    parser.add_argument("--workers-lotes", type=int, default=16)
    parser.add_argument("--delay-lotes", type=float, default=0)
    parser.add_argument("--sem-lotes", action="store_true")
    args = parser.parse_args()

    steps = [
        (
            "Atualizar base pelo Google My Maps",
            [sys.executable, "atualizar_radar_leiloes.py", "--workers", str(args.workers_mapa)],
            3,
        ),
    ]
    if not args.sem_lotes:
        steps.append(
            (
                "Indexar lotes nos sites dos leiloeiros",
                [
                    sys.executable,
                    "indexador_lotes.py",
                    "--delay",
                    str(args.delay_lotes),
                    "--workers",
                    str(args.workers_lotes),
                ],
                2,
            )
        )
    steps.extend(
        [
            ("Gerar site estatico", [sys.executable, "gerar_site_github.py"], 2),
            ("Gerar diagnostico", [sys.executable, "diagnostico_radar.py"], 1),
        ]
    )

    results = []
    for name, command, attempts in steps:
        result = run_step(name, command, attempts)
        results.append(result)
        if result["status"] != "ok":
            status = build_status(
                {
                    "status": "erro",
                    "ultima_execucao": iso_now(),
                    "erro_em": name,
                    "etapas": results,
                }
            )
            write_status(status)
            print(json.dumps(status, ensure_ascii=False, indent=2))
            return result["codigo"] or 1

    status = build_status(
        {
            "status": "ok",
            "ultima_execucao": iso_now(),
            "etapas": results,
        }
    )
    write_status(status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
