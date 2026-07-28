from __future__ import annotations


DATE_HIGHLIGHTS_STYLES = """    .date-highlights{margin:0 12px 12px;padding:13px 14px;display:flex;align-items:center;justify-content:space-between;gap:16px;border:1px solid #263544;border-radius:9px;background:linear-gradient(120deg,rgba(18,31,43,.98),rgba(11,20,28,.98))}
    .date-highlights-copy span{display:block;color:var(--yellow);font-size:8px;font-weight:850;letter-spacing:.15em;margin-bottom:4px}.date-highlights-copy strong{display:block;font-size:13px;color:#f3f6f9}.date-actions{display:flex;align-items:stretch;gap:8px}.date-shortcut,.date-picker{min-height:48px;border:1px solid #314252;border-radius:7px;background:#0b141d;color:#dfe6ed}.date-shortcut{min-width:112px;padding:7px 11px;display:flex;align-items:center;justify-content:space-between;gap:12px;font:inherit;font-size:10px;font-weight:850;cursor:pointer;transition:border-color .2s ease,background .2s ease,color .2s ease}.date-shortcut strong{min-width:25px;padding:4px 6px;border-radius:99px;background:#1a2835;color:#aeb9c5;font-size:9px;text-align:center}.date-shortcut:hover,.date-shortcut.active{border-color:var(--yellow);background:var(--yellow);color:#090c10}.date-shortcut.active strong,.date-shortcut:hover strong{background:rgba(0,0,0,.16);color:#090c10}.date-picker{min-width:190px;padding:6px 10px;display:grid;grid-template-columns:auto 1fr;column-gap:8px;align-items:center;cursor:pointer}.date-picker .icon{grid-row:1/3;color:var(--yellow)}.date-picker span{align-self:end;color:#8794a1;font-size:7px;font-weight:800;letter-spacing:.1em}.date-picker input{align-self:start;width:100%;border:0;outline:0;background:transparent;color:#f1f4f7;font:inherit;font-size:10px;font-weight:750;color-scheme:dark;cursor:pointer}
    @media(max-width:760px){.date-highlights{align-items:flex-start;flex-direction:column}.date-actions{width:100%;display:grid;grid-template-columns:1fr 1fr}.date-shortcut{min-width:0}.date-picker{grid-column:1/-1;min-width:0}.date-highlights-copy strong{font-size:12px}}
"""


DATE_HIGHLIGHTS_HTML = """      <div class="date-highlights" aria-label="Filtrar destaques pela data">
        <div class="date-highlights-copy"><span>QUANDO VOCÊ QUER VER?</span><strong>Escolha o dia do leilão</strong></div>
        <div class="date-actions">
          <button type="button" class="date-shortcut" data-date-shortcut="today" aria-pressed="false"><span>Hoje</span><strong id="today-count">0</strong></button>
          <button type="button" class="date-shortcut" data-date-shortcut="tomorrow" aria-pressed="false"><span>Amanhã</span><strong id="tomorrow-count">0</strong></button>
          <label class="date-picker" for="exact-date-filter"><svg class="icon"><use href="#i-calendar"/></svg><span>ESCOLHER DATA</span><input id="exact-date-filter" type="date" aria-label="Escolher uma data específica"></label>
        </div>
      </div>
"""


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    occurrences = source.count(old)
    if occurrences != 1:
        raise ValueError(
            f"Não foi possível aplicar a personalização de data em {label}: "
            f"esperada 1 ocorrência, encontradas {occurrences}."
        )
    return source.replace(old, new, 1)


def apply_date_highlights(template: str) -> str:
    """Adiciona ao template os filtros Hoje, Amanhã e data específica."""
    result = _replace_once(
        template,
        "</style>",
        f"{DATE_HIGHLIGHTS_STYLES}\n  </style>",
        "estilos",
    )
    result = _replace_once(
        result,
        '      <div class="feature-grid">',
        f"{DATE_HIGHLIGHTS_HTML}\n      <div class=\"feature-grid\">",
        "área de destaques",
    )
    result = _replace_once(
        result,
        "const state={query:'',category:'all',uf:'',days:'all',visible:12,savedOnly:false};",
        "const state={query:'',category:'all',uf:'',days:'all',exactDate:'',visible:12,savedOnly:false};",
        "estado dos filtros",
    )
    result = _replace_once(
        result,
        "  function parseStart(row){",
        """  function dateKey(offset=0){const day=new Date();day.setHours(12,0,0,0);day.setDate(day.getDate()+offset);return `${day.getFullYear()}-${String(day.getMonth()+1).padStart(2,'0')}-${String(day.getDate()).padStart(2,'0')}`}
  function selectedDateTitle(value){if(!value)return 'Oportunidades encontradas';if(value===dateKey(0))return 'Leilões de hoje';if(value===dateKey(1))return 'Leilões de amanhã';const [year,month,day]=value.split('-');return `Leilões de ${day}/${month}/${year}`}
  function applyExactDate(value,source){if(!value)return;if(state.exactDate===value&&source!=='calendar'){state.exactDate='';$('exact-date-filter').value='';resetVisible();track('filter_exact_date',{date:'all',source,result_count:current.length});return}state.exactDate=value;state.days='all';state.savedOnly=false;$('date-filter').value='all';$('exact-date-filter').value=value;resetVisible();track('filter_exact_date',{date:value,source,result_count:current.length});$('resultados').scrollIntoView({behavior:'smooth'})}
  function parseStart(row){""",
        "funções de data",
    )
    result = _replace_once(
        result,
        "function filtered(){const now=new Date();const max=state.days==='all'?null:new Date(now.getTime()+Number(state.days)*86400000);const saved=loadSaved();return lots.filter(row=>{const text=rowText(row);if(!matchesQuery(row))return false;if(state.category!=='all'&&!categories[state.category].some(term=>text.includes(term)))return false;if(state.uf&&row.uf!==state.uf)return false;if(state.savedOnly&&!saved.includes(lotId(row)))return false;const start=parseStart(row);if(max&&start&&start>max)return false;return true}).sort((a,b)=>{const query=norm(state.query);const sa=query&&norm(displayTitle(a)).includes(query)?1:0;const sb=query&&norm(displayTitle(b)).includes(query)?1:0;return sb-sa||String(a.data||'9999').localeCompare(String(b.data||'9999'))||String(a.hora||'').localeCompare(String(b.hora||''))})}",
        "function filtered(){const now=new Date();const max=state.days==='all'?null:new Date(now.getTime()+Number(state.days)*86400000);const saved=loadSaved();return lots.filter(row=>{const text=rowText(row);if(!matchesQuery(row))return false;if(state.category!=='all'&&!categories[state.category].some(term=>text.includes(term)))return false;if(state.uf&&row.uf!==state.uf)return false;if(state.savedOnly&&!saved.includes(lotId(row)))return false;if(state.exactDate&&row.data!==state.exactDate)return false;const start=parseStart(row);if(!state.exactDate&&max&&start&&start>max)return false;return true}).sort((a,b)=>{const query=norm(state.query);const sa=query&&norm(displayTitle(a)).includes(query)?1:0;const sb=query&&norm(displayTitle(b)).includes(query)?1:0;return sb-sa||String(a.data||'9999').localeCompare(String(b.data||'9999'))||String(a.hora||'').localeCompare(String(b.hora||''))})}",
        "filtragem dos lotes",
    )
    result = _replace_once(
        result,
        "$('results-title').textContent=state.savedOnly?'Seus lotes salvos':'Oportunidades encontradas';",
        "$('results-title').textContent=state.savedOnly?'Seus lotes salvos':selectedDateTitle(state.exactDate);",
        "título dos resultados",
    )
    result = _replace_once(
        result,
        "document.querySelectorAll('[data-category]').forEach(btn=>btn.classList.toggle('active',btn.dataset.category===state.category));",
        """document.querySelectorAll('[data-category]').forEach(btn=>btn.classList.toggle('active',btn.dataset.category===state.category));
    document.querySelectorAll('[data-date-shortcut]').forEach(btn=>{const offset=btn.dataset.dateShortcut==='tomorrow'?1:0;const active=state.exactDate===dateKey(offset);btn.classList.toggle('active',active);btn.setAttribute('aria-pressed',String(active))});""",
        "estado visual dos botões",
    )
    result = _replace_once(
        result,
        "function clearFilters(){state.query='';state.category='all';state.uf='';state.days='all';state.savedOnly=false;$('search-input').value='';$('state-filter').value='';$('date-filter').value='all';localStorage.removeItem(SEARCH_STORE);resetVisible()}",
        "function clearFilters(){state.query='';state.category='all';state.uf='';state.days='all';state.exactDate='';state.savedOnly=false;$('search-input').value='';$('state-filter').value='';$('date-filter').value='all';$('exact-date-filter').value='';localStorage.removeItem(SEARCH_STORE);resetVisible()}",
        "limpeza dos filtros",
    )
    result = _replace_once(
        result,
        "$('updated-label').textContent='ATUALIZADO TODOS OS DIAS';",
        "$('exact-date-filter').min=dateKey(0);$('today-count').textContent=formatNumber(lots.filter(row=>row.data===dateKey(0)).length);$('tomorrow-count').textContent=formatNumber(lots.filter(row=>row.data===dateKey(1)).length);$('updated-label').textContent='ATUALIZADO TODOS OS DIAS';",
        "configuração inicial",
    )
    result = _replace_once(
        result,
        "  $('date-filter').addEventListener('change',event=>{state.days=event.target.value;state.savedOnly=false;resetVisible();track('filter_date',{days:state.days,result_count:current.length})});",
        """  document.querySelectorAll('[data-date-shortcut]').forEach(btn=>btn.addEventListener('click',()=>applyExactDate(dateKey(btn.dataset.dateShortcut==='tomorrow'?1:0),btn.dataset.dateShortcut)));
  $('exact-date-filter').addEventListener('change',event=>{if(event.target.value)applyExactDate(event.target.value,'calendar');else{state.exactDate='';resetVisible()}});
  $('date-filter').addEventListener('change',event=>{state.days=event.target.value;state.exactDate='';$('exact-date-filter').value='';state.savedOnly=false;resetVisible();track('filter_date',{days:state.days,result_count:current.length})});""",
        "eventos dos filtros de data",
    )
    return result
