#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
import urllib.request
from pathlib import Path


MAP_ID = "1fYo8R4P75VxKA3TqsiuLsWIqIDEO27U"
KML_URL = f"https://www.google.com/maps/d/kml?forcekml=1&mid={MAP_ID}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def baixar_kml(attempts: int = 4) -> bytes:
    last_error = ""
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            KML_URL,
            headers={
                "User-Agent": "Mozilla/5.0 RadarLeiloesGMaquina/1.0",
                "Accept": "application/vnd.google-earth.kml+xml,application/xml,text/xml,*/*",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = response.read()
            if len(data) < 10_000 or b"<kml" not in data[:5000].lower():
                raise RuntimeError("KML baixado parece incompleto ou invalido.")
            return data
        except Exception as exc:
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(3 * attempt)
    raise SystemExit(f"Falha ao verificar o mapa depois de {attempts} tentativas: {last_error}")


def escrever_output_github(nome: str, valor: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{nome}={valor}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica se o Google My Maps mudou.")
    parser.add_argument("--kml", default="leiloes_do_brasil_completo.kml")
    args = parser.parse_args()

    atual = baixar_kml()
    atual_hash = sha256_bytes(atual)
    kml_path = Path(args.kml)

    anterior_hash = ""
    if kml_path.exists():
        anterior_hash = sha256_bytes(kml_path.read_bytes())

    alterado = not anterior_hash or anterior_hash != atual_hash
    escrever_output_github("alterado", "true" if alterado else "false")
    escrever_output_github("hash_atual", atual_hash)
    escrever_output_github("hash_anterior", anterior_hash)

    if alterado:
        print("Mapa alterado. A atualizacao completa sera executada.")
    else:
        print("Mapa sem alteracao. A atualizacao completa sera ignorada.")
    print(f"hash_atual={atual_hash}")
    if anterior_hash:
        print(f"hash_anterior={anterior_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
