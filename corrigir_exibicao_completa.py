#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [ROOT / "site_template.html", ROOT / "leiloes.html"]
VISIBLE_ALL = "999999999"


def patch(text: str) -> str:
    # Não pagina nem limita os registros do mapa.
    text = re.sub(r"visible:(?:60|5000|999999999)", f"visible:{VISIBLE_ALL}", text)
    text = re.sub(r"state\.visible=(?:60|5000|999999999)", f"state.visible={VISIBLE_ALL}", text)
    text = text.replace("<small>LOTES FUTUROS</small>", "<small>LOTES DISPONÍVEIS</small>")

    # Prioriza o que ainda vai acontecer, depois registros sem data e, por fim, históricos.
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

    # Exibe a descrição capturada do lote na própria página, em vez de mostrar somente o título.
    old_title = '<h4>${esc(displayTitle(row))}</h4><div class="auction-lot-meta">'
    new_title = '<h4>${esc(displayTitle(row))}</h4>${row.descricao?`<p class="auction-lot-description">${esc(row.descricao)}</p>`:\'\'}<div class="auction-lot-meta">'
    text = text.replace(old_title, new_title)

    # Todos os lotes de cada leilão ficam abertos de uma vez. Não há corte de 12 em 12.
    text = re.sub(
        r"const row=group\.row,hasLots=group\.items\.length>0,expanded=hasLots&&expandedAuctions\.has\(group\.key\),visibleLots=visibleLotsByAuction\.get\(group\.key\)\|\|12,shown=expanded\?group\.items\.slice\(0,visibleLots\):\[\],official=safeUrl\(row\.link_evento\);",
        "const row=group.row,hasLots=group.items.length>0,expanded=hasLots,visibleLots=group.items.length,shown=hasLots?group.items:[],official=safeUrl(row.link_evento);",
        text,
    )

    # Em vez de botão que recolhe/resume os lotes, mantém apenas o acesso ao leilão oficial.
    action_pattern = re.compile(
        r"const action=hasLots\?`<button type=\"button\" class=\"auction-toggle\" data-toggle-auction=\"\$\{esc\(group\.key\)\}\" aria-expanded=\"\$\{expanded\}\">\$\{expanded\?'FECHAR LOTES':`VER \$\{formatNumber\(group\.items\.length\)\} \$\{group\.items\.length===1\?'LOTE':'LOTES'\}`\} \$\{icon\('arrow'\)\}</button>`:official\?`<a class=\"auction-toggle\" href=\"\$\{esc\(official\)\}\" target=\"_blank\" rel=\"noopener\" data-open-auction=\"\$\{esc\(group\.key\)\}\">ABRIR LEILÃO \$\{icon\('external'\)\}</a>`:`<span class=\"auction-toggle unavailable\">LINK A CONFIRMAR</span>`;"
    )
    replacement = "const action=official?`<a class=\"auction-toggle\" href=\"${esc(official)}\" target=\"_blank\" rel=\"noopener\" data-open-auction=\"${esc(group.key)}\">ABRIR LEILÃO OFICIAL ${icon('external')}</a>`:`<span class=\"auction-toggle unavailable\">LINK A CONFIRMAR</span>`;"
    text = action_pattern.sub(replacement, text)

    # A condição abaixo passa a ser sempre falsa porque visibleLots == quantidade total.
    # Mantemos a estrutura por compatibilidade com versões antigas do template.

    if ".auction-lot-description{" not in text:
        css = "\n  .auction-lot-description{margin:8px 0 10px;white-space:pre-line;line-height:1.48;color:var(--muted);font-size:.92rem;max-width:1050px}\n"
        text = text.replace("</style>", css + "</style>", 1)

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
