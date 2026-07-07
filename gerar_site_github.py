#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAP_EMBED_URL = "https://www.google.com/maps/d/u/0/embed?mid=1fYo8R4P75VxKA3TqsiuLsWIqIDEO27U&ehbc=2E312F"
APP_VERSION = "v2026.07.07.3"


def read_csv(name: str) -> list[dict[str, str]]:
    path = ROOT / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_lotes() -> list[dict[str, str]]:
    path = ROOT / "lotes.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        rows = data.get("lotes", [])
        return rows if isinstance(rows, list) else []
    return []


def main() -> None:
    generated_at = dt.datetime.now().isoformat(timespec="seconds")
    payload = {
        "eventos": read_csv("radar_leiloes_eventos_futuros.csv"),
        "patios": read_csv("radar_leiloes_patios.csv"),
        "lotes": read_lotes(),
        "gerado_em": generated_at,
        "mapa": MAP_EMBED_URL,
        "versao": APP_VERSION,
    }
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    html = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Radar de Leilões G MAQUINA</title>
<style>
:root{color-scheme:light;--bg:#f5f6f8;--surface:#fff;--ink:#111214;--muted:#69717d;--line:#e3e6eb;--black:#0f1113;--black2:#191b1f;--yellow:#f7b801;--yellow2:#ffcd25;--green:#078b50;--blue:#1d3d5c;--danger:#b42318;--warn:#b87500;--radius:8px;--shadow:0 18px 42px rgba(15,23,42,.10)}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Inter,Arial,Helvetica,sans-serif;background:var(--bg);color:var(--ink)}button,.btn,input,select{min-height:42px;border:1px solid var(--line);border-radius:var(--radius);background:#fff;color:var(--ink);font:inherit}button,.btn{cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:10px 14px;text-decoration:none;font-weight:900}input,select{width:100%;padding:0 13px;outline:none}input:focus,select:focus{border-color:var(--yellow);box-shadow:0 0 0 4px rgba(247,184,1,.18)}input::placeholder{color:#8d95a1}h1,h2,p{margin:0}h1{font-size:clamp(26px,3vw,38px);line-height:1.06;letter-spacing:-.03em}h2{font-size:18px}.layout{display:grid;grid-template-columns:238px minmax(0,1fr);min-height:100vh;max-width:1440px;margin:0 auto;background:#fff}.sidebar{position:sticky;top:0;height:100vh;padding:26px 18px;background:linear-gradient(180deg,var(--black),var(--black2));color:#fff;display:flex;flex-direction:column;gap:22px}.brand{display:flex;align-items:center;gap:10px}.logo{width:36px;height:36px;border-radius:10px;background:linear-gradient(145deg,var(--yellow2),var(--yellow));color:#111;display:grid;place-items:center;font-weight:1000;box-shadow:0 10px 22px rgba(247,184,1,.26)}.brand strong{font-size:15px;letter-spacing:.02em}.side-pill{display:flex;align-items:center;gap:10px;width:100%;border:0;background:var(--yellow);color:#111;border-radius:8px;padding:12px 13px;font-weight:900}.side-note{margin-top:auto;border:1px solid rgba(255,255,255,.10);border-radius:8px;padding:16px;background:linear-gradient(150deg,rgba(255,255,255,.06),rgba(247,184,1,.18))}.side-note b{display:block;font-size:14px}.side-note span{display:block;margin-top:8px;font-size:12px;line-height:1.35;color:#e8eaee}.side-version{display:inline-flex;margin-top:10px;border-radius:999px;padding:5px 9px;background:var(--yellow);color:#111;font-size:11px;font-weight:1000}.content{min-width:0;padding:28px 30px 34px}.topbar{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:18px}.subtitle{margin-top:8px;color:var(--muted);font-size:15px}.updated{display:flex;flex-direction:column;align-items:flex-end;gap:5px;color:var(--muted);font-size:13px;text-align:right}.version-badge{display:inline-flex;align-items:center;border-radius:999px;padding:5px 9px;background:#111;color:#fff;font-size:12px;font-weight:1000}.search-panel{background:#fff;border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow);padding:14px;margin-bottom:14px}.filters{display:grid;grid-template-columns:minmax(240px,1fr) 110px 180px 112px;gap:10px;align-items:end}.search-wrap{position:relative}.search-wrap input{min-height:56px;padding-left:48px;font-size:16px}.search-ico{position:absolute;left:17px;top:50%;transform:translateY(-50%);font-size:22px;color:#111}.primary{background:var(--yellow);border-color:var(--yellow);color:#111}.primary:hover{background:var(--yellow2)}label{display:grid;gap:6px;color:#4b5563;font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:.04em}.map-card{border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#fff;margin-bottom:14px}.map-card iframe{display:block;width:100%;height:260px;border:0;background:#f2efe8}.map-head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:13px 14px;border-bottom:1px solid var(--line)}.map-head span{font-size:13px;color:var(--muted)}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.tabs button{border-radius:999px;min-height:39px;background:#fff}.tabs button.active{background:#111;color:#fff;border-color:#111}.screen{display:none}.screen.active{display:block}.stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:14px}.stat{background:#fff;border:1px solid var(--line);border-radius:8px;padding:13px}.stat span{display:block;font-size:11px;color:var(--muted);font-weight:900;text-transform:uppercase;letter-spacing:.04em}.stat strong{display:block;margin-top:6px;font-size:25px;line-height:1}.stat small{display:block;margin-top:7px;font-size:12px;color:var(--muted);line-height:1.25}.panel{background:#fff;border:1px solid var(--line);border-radius:8px;overflow:hidden}.panel-head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px;border-bottom:1px solid var(--line);background:#fff}.status{font-size:13px;color:var(--muted);text-align:right}.list{display:grid}.item{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:14px;border-bottom:1px solid var(--line);background:#fff}.item:hover{background:#fbfbfc}.item:last-child{border-bottom:0}.name{font-weight:1000;margin-bottom:6px;font-size:15px;color:var(--ink);overflow-wrap:anywhere}.desc{font-size:13px;color:var(--muted);line-height:1.38;overflow-wrap:anywhere}.meta{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0}.pill{display:inline-flex;align-items:center;border-radius:999px;padding:4px 9px;background:#fff;color:#374151;border:1px solid var(--line);font-size:12px;font-weight:850}.pill.live{background:#e9fbf2;color:#066d41;border-color:#bfe8d1}.pill.soon{background:#eef4fa;color:#1d3d5c;border-color:#cbdcec}.pill.warn{background:#fff8dd;color:var(--warn);border-color:#f1da8a}.countdown{margin-top:9px;font-weight:1000;color:var(--warn)}.countdown.ended{color:var(--danger)}.actions{display:flex;gap:8px;flex-wrap:wrap;align-content:start;justify-content:flex-end}.actions .btn,.actions button{min-height:36px;border-radius:6px;padding:7px 11px;font-size:12px}.soft{background:#fff}.danger{background:#fff;color:var(--danger);border-color:#f1c7c1}.empty{padding:30px 12px;text-align:center;color:var(--muted)}.form-grid{display:grid;grid-template-columns:1fr 150px 150px;gap:10px;align-items:end;padding:10px 0 0}.reminder-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:14px;border-bottom:1px solid var(--line)}.reminder-row:last-child{border-bottom:0}.mobile-brand{display:none}footer{max-width:1440px;margin:0 auto;padding:0 30px 24px 268px;color:var(--muted);font-size:12px}.footer-version{font-weight:900;color:#111}@media(max-width:980px){.layout{display:block}.sidebar{display:none}.content{padding:0 14px 34px}.mobile-brand{display:flex;align-items:center;justify-content:space-between;margin:0 -14px 18px;padding:17px 14px;background:var(--black);color:#fff}.topbar{display:block}.updated{align-items:flex-start;text-align:left;margin-top:8px}.filters{grid-template-columns:1fr 1fr}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.item,.reminder-row{grid-template-columns:1fr}.actions{justify-content:flex-start}.map-card iframe{height:210px}footer{padding:0 14px 24px}}@media(max-width:560px){h1{font-size:23px}.filters,.form-grid{grid-template-columns:1fr}.search-wrap input{min-height:50px;font-size:14px}.stats{grid-template-columns:1fr 1fr}.panel-head{display:block}.status{text-align:left;margin-top:6px}.tabs{overflow:auto;flex-wrap:nowrap;padding-bottom:3px}.tabs button{white-space:nowrap}.item{padding:13px}.actions .btn,.actions button{min-width:120px}.map-card iframe{height:175px}}@media(max-width:380px){.stats{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <div class="brand"><div class="logo">G</div><strong>G MAQUINA</strong></div>
    <div class="side-pill">⌕ Radar de Leilões</div>
    <div class="side-note"><b>Radar de Leilões</b><span>Painel simples para buscar, filtrar e salvar leilões de interesse.</span><em class="side-version" id="sideVersao">Versão --</em></div>
  </aside>
  <main class="content">
    <div class="mobile-brand"><div class="brand"><div class="logo">G</div><strong>G MAQUINA</strong></div><div class="bell">⌁</div></div>
    <div class="topbar">
      <div><h1>Radar de Leilões G MAQUINA</h1><p class="subtitle">Busca por lote, leiloeiro, cidade, veículo, máquina e evento.</p></div>
      <div class="updated"><span id="topAtualizado">Atualizado em: --</span><span class="version-badge" id="topVersao">Versão --</span></div>
    </div>
    <div class="search-panel">
      <div class="filters">
        <label class="search-wrap">Pesquisar<span class="search-ico">⌕</span><input id="q" type="search" placeholder="Trator de esteira, Corolla, caminhão, Palio..."></label>
        <label>UF<select id="uf"><option value="">Todas</option></select></label>
        <label>Base<select id="fonte"><option value="eventos_lotes">Eventos + lotes</option><option value="lotes">Somente lotes</option><option value="eventos">Eventos futuros</option><option value="patios">Pátios</option><option value="todos">Tudo</option></select></label>
        <button class="primary" id="btnBuscar" type="button">Buscar</button>
      </div>
    </div>
    <div class="map-card">
      <div class="map-head"><h2>Mapa de leilões</h2><span id="mapResumo">--</span></div>
      <iframe id="mapaIframe" loading="lazy" referrerpolicy="no-referrer-when-downgrade" title="Mapa dos leilões"></iframe>
    </div>
    <nav class="tabs" aria-label="Navegação"><button class="active" data-tab="buscar">Radar de Leilões</button><button data-tab="lembretes">Leilões salvos</button></nav>
    <section id="buscar" class="screen active">
      <div class="stats">
        <div class="stat"><span>Lotes</span><strong id="stLotes">0</strong></div>
        <div class="stat"><span>Eventos</span><strong id="stEventos">0</strong></div>
        <div class="stat"><span>Pátios</span><strong id="stPatios">0</strong></div>
        <div class="stat"><span>Salvos</span><strong id="stSalvos">0</strong></div>
        <div class="stat"><span>Base</span><small id="stAtualizado">Atualizado em: --</small><small id="stVersao">Versão --</small></div>
      </div>
      <div class="panel" id="resultadosPanel"><div class="panel-head"><h2>Resultados do Radar</h2><span class="status" id="statusBusca">Pronto.</span></div><div class="list" id="resultados"></div></div>
    </section>
    <section id="lembretes" class="screen">
      <div class="panel"><div class="panel-head"><h2>Leilões salvos</h2><span class="status" id="statusLembretes">Nenhum salvo ainda.</span></div><div id="listaLembretes"></div></div>
    </section>
  </main>
</div>
<footer>Radar de Leilões - G MAQUINA. <span class="footer-version" id="footerVersao">Versão --</span></footer>
<script id="radar-data" type="application/json">__RADAR_DATA__</script>
<script>
const BASE=JSON.parse(document.getElementById('radar-data').textContent);const STORE='radar_leiloes_interesses_v2';const SEARCH_STORE='radar_leiloes_busca_v1';const $=id=>document.getElementById(id);const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('pt-BR');
const STOPWORDS=new Set(['de','da','do','das','dos','e','em','no','na','nos','nas','para','por','com','a','o','as','os']);
const SEARCH_ALIASES={
  caminhao:['caminhao','caminhoes','truck','cavalo'],
  caminhoes:['caminhao','caminhoes','truck','cavalo'],
  onibus:['onibus','microonibus','micro-onibus'],
  maquina:['maquina','maquinas','trator','tratores','escavadeira','carregadeira','retroescavadeira','motoniveladora','patrol','rolo','compactador'],
  maquinas:['maquina','maquinas','trator','tratores','escavadeira','carregadeira','retroescavadeira','motoniveladora','patrol','rolo','compactador'],
  veiculo:['veiculo','veiculos','carro','carros','automovel','automoveis','caminhonete','camionete','suv','moto','motos'],
  veiculos:['veiculo','veiculos','carro','carros','automovel','automoveis','caminhonete','camionete','suv','moto','motos'],
  carro:['carro','carros','automovel','automoveis'],
  carros:['carro','carros','automovel','automoveis'],
  pa:['pa','pá'],
  patio:['patio','pátio'],
  patios:['patio','pátio','patios','pátios'],
  sucata:['sucata','sucatas'],
  sucatas:['sucata','sucatas']
};
function alternatives(term){const base=new Set([term]);if(term.endsWith('s')&&term.length>3)base.add(term.slice(0,-1));else if(term.length>3)base.add(term+'s');(SEARCH_ALIASES[term]||[]).forEach(x=>base.add(norm(x)));return [...base].filter(Boolean)}
function esc(v){return String(v||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function firstLink(v){return String(v||'').split(' | ')[0].trim()}
function domainFromLink(v){try{return new URL(firstLink(v)).hostname.replace(/^www\./,'')}catch(e){return ''}}
function rowName(row){return row.titulo||row.nome||row.evento||''}
function rowLink(row){return firstLink(row.link_lote||row.link||row.link_evento||'')}
function rowLocal(row){return row.local||row.endereco_ou_localizacao||''}
function rowDate(row){return row.data_original||row.data||'sem data'}
function rowHour(row){return row.hora||row.hora_marcador||''}
function displayHour(value){const hour=parseHour(value);return hour==='08:00'&&!String(value||'').trim()?'':hour}
function rowDescription(row){return row.descricao||row.evento||''}
function rowType(row){return row.titulo?'lote':'evento'}
function rowLeiloeiro(row){return row.leiloeiro||domainFromLink(rowLink(row))||''}
function isBadResult(row){return ['whatsapp','facebook','twitter','instagram','linkedin','compartilhar'].includes(norm(rowName(row)).trim())}
function key(row){return btoa(unescape(encodeURIComponent(rowName(row)+'|'+rowLink(row)+'|'+(row.data||'')))).slice(0,48)}
function formatDateTime(value){if(!value)return '--';const date=new Date(value);if(Number.isNaN(date.getTime()))return value;return date.toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short',hourCycle:'h23'})}
function parseHour(value){const m=String(value||'').match(/(\d{1,2})[:h](\d{2})?/i);if(!m)return '08:00';const h=String(Math.min(23,Number(m[1]))).padStart(2,'0');const min=String(Math.min(59,Number(m[2]||0))).padStart(2,'0');return h+':'+min}
function auctionStart(row){if(!row.data)return '';return row.data+'T'+parseHour(rowHour(row))}
function countdownText(value){if(!value)return 'Início não informado';const target=new Date(value);if(Number.isNaN(target.getTime()))return 'Início não informado';let diff=target.getTime()-Date.now();if(diff<=0)return 'Leilão já começou';const days=Math.floor(diff/86400000);diff-=days*86400000;const hours=Math.floor(diff/3600000);diff-=hours*3600000;const minutes=Math.floor(diff/60000);if(days>0)return `Faltam ${days} dia(s), ${hours}h e ${minutes}min`;if(hours>0)return `Faltam ${hours}h e ${minutes}min`;return `Faltam ${minutes}min`}
function statusClass(row){const start=auctionStart(row);if(!start)return 'soon';const diff=new Date(start).getTime()-Date.now();return diff<=86400000&&diff>=-21600000?'live':'soon'}
function loadSaved(){try{return JSON.parse(localStorage.getItem(STORE)||'[]')}catch(e){return[]}}
function saveSaved(rows){localStorage.setItem(STORE,JSON.stringify(rows));updateSavedCount();renderReminders()}
function isSaved(row){const k=key(row);return loadSaved().some(x=>x.key===k)}
function addSaved(row){const saved=loadSaved();const k=key(row);if(saved.some(x=>x.key===k))return;const inicio=auctionStart(row);saved.push({key:k,nome:rowName(row),uf:row.uf,data:row.data,data_original:row.data_original,hora:rowHour(row),local:rowLocal(row),link:rowLink(row),descricao:rowDescription(row),inicio:inicio,lembrete:inicio,lanceMax:row.lance_atual||'',obs:''});saveSaved(saved)}
function removeSaved(k){saveSaved(loadSaved().filter(x=>x.key!==k));search()}
function updateReminder(k,field,value){const saved=loadSaved();const item=saved.find(x=>x.key===k);if(item){item[field]=value;if(field==='inicio'&&!item.lembrete)item.lembrete=value;saveSaved(saved)}}
function text(row){return ['titulo','nome','evento','uf','data','data_original','hora','hora_marcador','local','endereco_ou_localizacao','descricao','lance_atual','lote','link','link_lote','link_evento','leiloeiro'].map(k=>norm(row[k])).join(' ')}
function rowsBySource(){const f=$('fonte').value;if(f==='lotes')return BASE.lotes||[];if(f==='eventos_lotes')return (BASE.lotes||[]).concat(BASE.eventos);if(f==='patios')return BASE.patios;if(f==='todos')return (BASE.lotes||[]).concat(BASE.eventos,BASE.patios);return BASE.eventos}
function todayIso(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function isUpcoming(row){return !row.data||row.data>=todayIso()}
function setup(){BASE.lotes=BASE.lotes||[];BASE.eventos=BASE.eventos||[];BASE.patios=BASE.patios||[];$('mapaIframe').src=BASE.mapa||'';document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>showTab(b.dataset.tab)));const ufs=[...new Set(BASE.eventos.concat(BASE.patios,BASE.lotes).map(r=>r.uf).filter(Boolean))].sort();$('uf').innerHTML='<option value="">Todas</option>'+ufs.map(u=>`<option value="${esc(u)}">${esc(u)}</option>`).join('');$('q').value=localStorage.getItem(SEARCH_STORE)||'';$('stLotes').textContent=BASE.lotes.length.toLocaleString('pt-BR');$('stEventos').textContent=BASE.eventos.length.toLocaleString('pt-BR');$('stPatios').textContent=BASE.patios.length.toLocaleString('pt-BR');const versao='Versão '+(BASE.versao||'--');$('stAtualizado').textContent='Atualizado em: '+formatDateTime(BASE.gerado_em);$('stVersao').textContent=versao;$('topAtualizado').textContent='Atualizado em: '+formatDateTime(BASE.gerado_em);$('topVersao').textContent=versao;$('sideVersao').textContent=versao;$('footerVersao').textContent=versao;$('mapResumo').textContent=`${BASE.eventos.length.toLocaleString('pt-BR')} leilões · ${BASE.lotes.length.toLocaleString('pt-BR')} lotes`;updateSavedCount();search();renderReminders();setInterval(renderReminders,60000)}
function showTab(id){document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===id));document.querySelectorAll('.screen').forEach(s=>s.classList.toggle('active',s.id===id));if(id==='lembretes')renderReminders()}
function updateSavedCount(){$('stSalvos').textContent=loadSaved().length}
function search(){localStorage.setItem(SEARCH_STORE,$('q').value.trim());const terms=norm($('q').value).split(/\s+/).filter(t=>t&&!STOPWORDS.has(t));const uf=norm($('uf').value);const rows=rowsBySource().filter(r=>{if(isBadResult(r))return false;if(!isUpcoming(r))return false;if(uf&&norm(r.uf)!==uf)return false;const hay=text(r);return terms.every(t=>alternatives(t).some(a=>hay.includes(a)))}).sort((a,b)=>scoreRow(b,terms)-scoreRow(a,terms)||String(auctionStart(a)||'9999').localeCompare(String(auctionStart(b)||'9999'))||Number(!!b.titulo)-Number(!!a.titulo)||String(a.uf||'').localeCompare(String(b.uf||''))).slice(0,250);renderResults(rows)}
function scoreRow(row,terms){if(!terms.length)return 0;const title=norm(rowName(row));const desc=norm(rowDescription(row));let score=0;for(const t of terms){if(title.includes(t))score+=8;if(desc.includes(t))score+=3}return score}
function searchAndScroll(){search();setTimeout(()=>$('resultadosPanel').scrollIntoView({behavior:'smooth',block:'start'}),60)}
function renderResults(rows){$('statusBusca').textContent=rows.length+' resultado(s).';if(!rows.length){$('resultados').innerHTML='<div class="empty"><b>Nenhum resultado encontrado.</b></div>';return}$('resultados').innerHTML=rows.map(r=>{const link=rowLink(r);const saved=isSaved(r);const inicio=auctionStart(r);const type=rowType(r);const title=rowName(r);const local=rowLocal(r);const hour=displayHour(rowHour(r));const desc=type==='lote'?(r.evento||r.descricao||''):(r.descricao||local);const status=statusClass(r);return `<article class="item"><div><div class="name">${esc(title)}</div><div class="desc">${esc(desc||local||'')}</div><div class="meta"><span class="pill ${status}">${status==='live'?'AO VIVO':'EM BREVE'}</span><span class="pill">${type==='lote'?'Lote':'Evento'}</span><span class="pill">${esc(rowDate(r))}</span><span class="pill">${esc(r.uf||'UF')}</span>${hour?`<span class="pill">${esc(hour)}</span>`:''}${r.lance_atual?`<span class="pill warn">${esc(r.lance_atual)}</span>`:''}${rowLeiloeiro(r)?`<span class="pill">${esc(rowLeiloeiro(r))}</span>`:''}</div>${inicio?`<div class="countdown">${esc(countdownText(inicio))}</div>`:''}</div><div class="actions">${link?`<a class="btn primary" href="${esc(link)}" target="_blank" rel="noopener">Abrir</a>`:''}<button class="soft" type="button" data-save="${esc(key(r))}">${saved?'Salvo':'Salvar'}</button></div></article>`}).join('');document.querySelectorAll('[data-save]').forEach((btn,i)=>btn.addEventListener('click',()=>{addSaved(rows[i]);search()}))}
function renderReminders(){const saved=loadSaved().sort((a,b)=>String(a.inicio||a.lembrete||'9999').localeCompare(String(b.inicio||b.lembrete||'9999')));$('statusLembretes').textContent=saved.length?saved.length+' salvo(s).':'Nenhum salvo ainda.';if(!saved.length){$('listaLembretes').innerHTML='<div class="empty">Salve um leilão na busca para ele aparecer aqui.</div>';return}$('listaLembretes').innerHTML=saved.map(x=>{const inicio=x.inicio||x.lembrete||'';const cd=countdownText(inicio);const ended=cd.includes('já começou');return `<div class="reminder-row"><div><div class="name">${esc(x.nome)}</div><div class="desc">${esc(x.local||'')}</div><div class="countdown ${ended?'ended':''}">${esc(cd)}</div><div class="form-grid"><label>Início do leilão<input type="datetime-local" value="${esc(inicio)}" data-edit="inicio" data-key="${esc(x.key)}"></label><label>Lance máximo<input type="text" placeholder="R$" value="${esc(x.lanceMax||'')}" data-edit="lanceMax" data-key="${esc(x.key)}"></label><label>Observação<input type="text" value="${esc(x.obs||'')}" data-edit="obs" data-key="${esc(x.key)}"></label></div></div><div class="actions">${x.link?`<a class="btn primary" href="${esc(x.link)}" target="_blank" rel="noopener">Abrir</a>`:''}<button class="danger" type="button" data-remove="${esc(x.key)}">Remover</button></div></div>`}).join('');document.querySelectorAll('[data-edit]').forEach(el=>el.addEventListener('change',()=>updateReminder(el.dataset.key,el.dataset.edit,el.value)));document.querySelectorAll('[data-remove]').forEach(btn=>btn.addEventListener('click',()=>removeSaved(btn.dataset.remove)))}
$('btnBuscar').addEventListener('click',searchAndScroll);$('q').addEventListener('input',()=>localStorage.setItem(SEARCH_STORE,$('q').value));$('q').addEventListener('keydown',e=>{if(e.key==='Enter')searchAndScroll()});setup();
</script>
</body>
</html>
'''.replace("__RADAR_DATA__", data)

    for name in ("index.html", "radar-leiloes.html"):
        (ROOT / name).write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
