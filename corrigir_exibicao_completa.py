#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [ROOT / "site_template.html", ROOT / "leiloes.html"]


def patch(text: str) -> str:
    # Renderiza todos os registros do mapa de uma vez. 5.000 deixa folga para a base crescer
    # sem reintroduzir paginacao invisivel ao usuario.
    text = text.replace("visible:60", "visible:5000")
    text = text.replace("state.visible=60", "state.visible=5000")
    text = text.replace("<small>LOTES FUTUROS</small>", "<small>LOTES DISPONÍVEIS</small>")

    # Prioriza o que ainda vai acontecer, depois registros sem data e, por fim, historicos
    # do mais recente para o mais antigo. Todos continuam disponiveis na mesma listagem.
    marker = "  function upcoming(row){const start=parseStart(row);return !!start&&start.getTime()>Date.now()}\n"
    helper = marker + "  function sortAuctionRows(a,b){const now=Date.now(),da=parseStart(a),db=parseStart(b),ra=da?(da.getTime()>=now?0:2):1,rb=db?(db.getTime()>=now?0:2):1;if(ra!==rb)return ra-rb;if(ra===0)return da-db;if(ra===2)return db-da;return String(a.evento||a.nome||'').localeCompare(String(b.evento||b.nome||''),'pt-BR')}\n"
    if "function sortAuctionRows" not in text and marker in text:
        text = text.replace(marker, helper, 1)

    text = text.replace(
        "return [...groups.values()].sort((a,b)=>String(a.row.data||'9999').localeCompare(String(b.row.data||'9999'))||String(a.row.hora||'').localeCompare(String(b.row.hora||'')));",
        "return [...groups.values()].sort((a,b)=>sortAuctionRows(a.row,b.row));",
    )
    text = text.replace(
        "return sb-sa||String(a.row.data||'9999').localeCompare(String(b.row.data||'9999'))||String(a.row.hora||'').localeCompare(String(b.row.hora||''));",
        "return sb-sa||sortAuctionRows(a.row,b.row);",
    )
    return text


def main() -> None:
    changed = []
    for path in FILES:
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8")
        updated = patch(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed.append(path.name)
    print("EXIBICAO_COMPLETA_OK=" + ",".join(changed or ["sem_alteracoes"]))


if __name__ == "__main__":
    main()
