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
    "verificar_mapa_google.py",
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
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def count_csv(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except Exception:
        return 0


def iso_now() -> str:
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


def build_status(extra: dict | None = None) -> dict:
    resumo = read_json(ROOT / "radar_leiloes_resumo.json")
    lotes = read_json(ROOT / "lotes.json")
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).exists()]

    index = (ROOT / "index.html").read_text(encoding="utf-8", errors="replace") if (ROOT / "index.html").exists() else ""
    workflow = (
        (ROOT / ".github/workflows/atualizar-radar.yml").read_text(encoding="utf-8", errors="replace")
        if (ROOT / ".github/workflows/atualizar-radar.yml").exists()
        else ""
    )

    eventos_csv = count_csv(ROOT / "radar_leiloes_eventos_futuros.csv")
    patios_csv = count_csv(ROOT / "radar_leiloes_patios.csv")
    lotes_lista = lotes.get("lotes", [])
    total_lotes = len(lotes_lista) if isinstance(lotes_lista, list) else int(lotes.get("total_lotes") or 0)
    lotes_csv = count_csv(ROOT / "lotes.csv")

    checks = {
        "arquivos_obrigatorios": not missing,
        "workflow_existe": ".github/workflows/atualizar-radar.yml" not in missing,
        "workflow_diario_16h": '0 19 * * *' in workflow,
        "workflow_gera_diagnostico": "diagnostico_radar.py" in workflow or "executar_atualizacao_radar.py" in workflow,
        "workflow_indexa_lotes": "indexador_lotes.py" in workflow or "executar_atualizacao_radar.py" in workflow,
        "mapa_no_site": "1fYo8R4P75VxKA3TqsiuLsWIqIDEO27U" in index,
        "base_embutida_no_site": 'id="radar-data"' in index,
        "carrosseis_fotos_reais_embutidos": index.count("data:image/jpeg;base64,") >= 9
        and index.count('data-carousel="') >= 3
        and "FOTOS REAIS • REFERÊNCIA VISUAL" in index,
        "resultados_sem_fotos_de_lote": "data-lot-photo" not in index
        and '<div class="result-photo">' not in index
        and "IMAGEM REAL DE REFERÊNCIA" not in index,
        "site_informa_atualizacao_diaria": "ATUALIZADO TODOS OS DIAS" in index,
        "site_tem_aviso_independente": "site independente de busca" in index and "LI E ENTENDI" in index,
        "eventos_csv_ok": eventos_csv > 0,
        "lotes_json_ok": total_lotes > 0,
        "lotes_csv_consistente": lotes_csv == total_lotes,
    }

    status = {
        "status": "ok" if all(checks.values()) else "atencao",
        "verificado_em": iso_now(),
        "atualizado_em_base_eventos": resumo.get("atualizado_em", ""),
        "atualizado_em_base_lotes": lotes.get("atualizado_em", ""),
        "eventos_futuros": int(resumo.get("eventos_futuros_ou_hoje") or eventos_csv),
        "patios": int(resumo.get("patios") or patios_csv),
        "lotes": int(lotes.get("total_lotes") or total_lotes),
        "lotes_capturados_agora": int(lotes.get("total_lotes_capturados_agora") or 0),
        "lotes_preservados": int(lotes.get("total_lotes_preservados") or 0),
        "eventos_indexados_com_lotes": int(lotes.get("eventos_com_lotes") or 0),
        "mapa_id": "1fYo8R4P75VxKA3TqsiuLsWIqIDEO27U",
        "checks": checks,
        "arquivos_faltando": missing,
    }
    if extra:
        status.update(extra)
    return status


def write_status(status: dict) -> None:
    (ROOT / "status_atualizacao.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        f"Status: {status.get('status')}",
        f"Verificado em: {status.get('verificado_em')}",
        f"Base eventos: {status.get('atualizado_em_base_eventos')}",
        f"Base lotes: {status.get('atualizado_em_base_lotes')}",
        f"Eventos futuros: {status.get('eventos_futuros')}",
        f"Lotes: {status.get('lotes')}",
        f"Patios: {status.get('patios')}",
    ]
    (ROOT / "status_atualizacao.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera diagnostico do Radar de Leiloes.")
    parser.add_argument("--falhar-se-atencao", action="store_true")
    args = parser.parse_args()

    previous = read_json(ROOT / "status_atualizacao.json")
    keep = {
        key: previous[key]
        for key in ("ultima_execucao", "erro_em", "etapas")
        if key in previous
    }
    status = build_status(keep)
    write_status(status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 1 if args.falhar_se_atencao and status["status"] != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
