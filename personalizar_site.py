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


PROXIMITY_STYLES = """    .nearby-panel{position:relative;z-index:2;margin-top:12px;padding:18px 20px;display:grid;grid-template-columns:minmax(210px,.7fr) minmax(0,1.3fr);align-items:center;gap:18px;border:1px solid rgba(247,184,1,.35);border-radius:12px;background:linear-gradient(120deg,#202d38,#18242e)}.nearby-copy span{display:block;margin-bottom:5px;color:var(--yellow);font-size:8px;font-weight:900;letter-spacing:.15em}.nearby-copy strong{display:block;color:#f3f7fa;font-size:17px}.nearby-copy p{margin:5px 0 0;color:#aebbc6;font-size:10px;line-height:1.45}.nearby-controls{display:grid;grid-template-columns:minmax(180px,1fr) 120px auto auto;gap:8px}.nearby-controls input,.nearby-controls select,.nearby-controls button{min-height:46px;border:1px solid #3b4d5c;border-radius:7px;font:inherit;font-size:10px;font-weight:750}.nearby-controls input,.nearby-controls select{outline:0;color:#eef3f7;background:#111b24}.nearby-controls input{min-width:0;padding:0 13px}.nearby-controls input:focus,.nearby-controls select:focus{border-color:var(--yellow);box-shadow:0 0 0 3px rgba(247,184,1,.1)}.nearby-controls select{padding:0 9px}.nearby-controls button{padding:0 14px;display:flex;align-items:center;justify-content:center;gap:7px;cursor:pointer}.nearby-apply{border-color:var(--yellow)!important;color:#0a0d10;background:var(--yellow)}.nearby-gps{color:#dbe3e9;background:#263542}.nearby-clear{color:#aeb9c3;background:transparent}.nearby-clear[hidden]{display:none}.nearby-status{grid-column:2;margin:0;color:#8de3ba;font-size:10px}.distance-badge{padding:4px 7px;border:1px solid rgba(247,184,1,.35);border-radius:4px;color:var(--yellow);background:rgba(247,184,1,.08);font-size:7px;font-weight:900;letter-spacing:.06em}
    @media(max-width:760px){.nearby-panel{grid-template-columns:1fr;padding:17px 14px}.nearby-controls{grid-template-columns:1fr 105px}.nearby-controls input{grid-column:1/-1}.nearby-controls .nearby-apply{grid-column:1/-1}.nearby-status{grid-column:1}}
"""


PROXIMITY_HTML = """    <section class="nearby-panel" aria-labelledby="nearby-title">
      <div class="nearby-copy"><span>RADAR PERTO DE VOCÊ</span><strong id="nearby-title">Encontre lotes na sua região</strong><p>Escolha sua cidade ou use sua localização. O cálculo acontece somente no seu aparelho.</p></div>
      <div class="nearby-controls">
        <input id="location-input" type="search" list="municipality-list" autocomplete="off" placeholder="Digite sua cidade, ex.: Taiobeiras - MG" aria-label="Sua cidade">
        <datalist id="municipality-list"></datalist>
        <select id="radius-filter" aria-label="Distância máxima"><option value="100">Até 100 km</option><option value="200" selected>Até 200 km</option><option value="300">Até 300 km</option><option value="400">Até 400 km</option><option value="500">Até 500 km</option></select>
        <button type="button" class="nearby-gps" id="use-location"><svg class="icon"><use href="#i-pin"/></svg>Localização</button>
        <button type="button" class="nearby-apply" id="apply-location">BUSCAR PERTO</button>
        <button type="button" class="nearby-clear" id="clear-location" hidden>Remover localização</button>
      </div>
      <p class="nearby-status" id="nearby-status">Informe sua região para ordenar os leilões mais próximos.</p>
    </section>
"""


PROXIMITY_FUNCTIONS = """  const municipalities=(BASE.municipios||[]).map(row=>({name:row[0],uf:row[1],lat:Number(row[2]),lon:Number(row[3]),label:`${row[0]} - ${row[1]}`}));
  function loadMunicipalityOptions(value=''){const query=norm(value).replace(/\\s+/g,' ').trim();const matches=query.length<2?[]:municipalities.filter(city=>norm(city.label).includes(query)||norm(city.name).includes(query)).slice(0,20);$('municipality-list').innerHTML=matches.map(city=>`<option value="${esc(city.label)}"></option>`).join('')}
  function municipalityFromInput(value){const key=norm(value).replace(/\\s+/g,' ').trim();if(!key)return null;const exact=municipalities.find(city=>norm(city.label)===key);if(exact)return exact;const matches=municipalities.filter(city=>norm(city.name)===key);return matches.length===1?matches[0]:null}
  function distanceKm(row){if(!state.locationActive)return null;const lat=Number(row.latitude),lon=Number(row.longitude);if(!Number.isFinite(lat)||!Number.isFinite(lon))return null;const rad=value=>value*Math.PI/180;const dLat=rad(lat-state.userLat),dLon=rad(lon-state.userLon);const a=Math.min(1,Math.sin(dLat/2)**2+Math.cos(rad(state.userLat))*Math.cos(rad(lat))*Math.sin(dLon/2)**2);return 6371*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a))}
  function saveLocation(){try{localStorage.setItem(LOCATION_STORE,JSON.stringify({lat:state.userLat,lon:state.userLon,radius:state.radius,label:state.locationLabel}))}catch{}}
  function activateLocation(lat,lon,label){state.locationActive=true;state.userLat=Number(lat);state.userLon=Number(lon);state.locationLabel=label;state.radius=Number($('radius-filter').value)||200;state.uf='';state.savedOnly=false;$('state-filter').value='';$('location-input').value=label==='Sua localização'?'':label;$('clear-location').hidden=false;saveLocation();resetVisible();track('filter_distance',{radius_km:state.radius,location_source:label==='Sua localização'?'gps':'city',result_count:current.length});$('resultados').scrollIntoView({behavior:'smooth'})}
  function applyTypedLocation(){const city=municipalityFromInput($('location-input').value);if(!city){toast('Escolha uma cidade da lista, incluindo o estado.');$('location-input').focus();return}activateLocation(city.lat,city.lon,city.label)}
  function clearNearby(shouldRender=true){state.locationActive=false;state.userLat=null;state.userLon=null;state.locationLabel='';$('location-input').value='';$('clear-location').hidden=true;$('nearby-status').textContent='Informe sua região para ordenar os leilões mais próximos.';try{localStorage.removeItem(LOCATION_STORE)}catch{}if(shouldRender)resetVisible()}
  function restoreLocation(){try{const saved=JSON.parse(localStorage.getItem(LOCATION_STORE)||'null');if(saved&&Number.isFinite(Number(saved.lat))&&Number.isFinite(Number(saved.lon))){state.locationActive=true;state.userLat=Number(saved.lat);state.userLon=Number(saved.lon);state.radius=[100,200,300,400,500].includes(Number(saved.radius))?Number(saved.radius):200;state.locationLabel=String(saved.label||'Sua localização');$('radius-filter').value=String(state.radius);$('location-input').value=state.locationLabel==='Sua localização'?'':state.locationLabel;$('clear-location').hidden=false}}catch{}}
  function useCurrentLocation(){if(!navigator.geolocation){toast('Seu navegador não oferece localização. Digite sua cidade.');return}const button=$('use-location');button.disabled=true;button.textContent='LOCALIZANDO...';navigator.geolocation.getCurrentPosition(position=>{button.disabled=false;button.innerHTML=`${icon('pin')}Localização`;activateLocation(position.coords.latitude,position.coords.longitude,'Sua localização')},()=>{button.disabled=false;button.innerHTML=`${icon('pin')}Localização`;toast('Não foi possível acessar sua localização. Digite sua cidade.')},{enableHighAccuracy:false,timeout:10000,maximumAge:600000})}
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
        f"{DATE_HIGHLIGHTS_STYLES}\n{PROXIMITY_STYLES}\n  </style>",
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
        '    </div>\n  </section>\n\n  <section class="dashboard">',
        f'    </div>\n{PROXIMITY_HTML}  </section>\n\n  <section class="dashboard">',
        "filtro de proximidade",
    )
    result = _replace_once(
        result,
        "  const SEARCH_STORE='radar_premium_busca_v1';",
        "  const SEARCH_STORE='radar_premium_busca_v1';\n  const LOCATION_STORE='radar_localizacao_v1';",
        "armazenamento da localização",
    )
    result = _replace_once(
        result,
        "const state={query:'',category:'all',uf:'',days:'all',visible:12,savedOnly:false};",
        "const state={query:'',category:'all',uf:'',days:'all',exactDate:'',visible:12,savedOnly:false,locationActive:false,userLat:null,userLon:null,radius:200,locationLabel:''};",
        "estado dos filtros",
    )
    result = _replace_once(
        result,
        "  function parseStart(row){",
        PROXIMITY_FUNCTIONS + """  function dateKey(offset=0){const day=new Date();day.setHours(12,0,0,0);day.setDate(day.getDate()+offset);return `${day.getFullYear()}-${String(day.getMonth()+1).padStart(2,'0')}-${String(day.getDate()).padStart(2,'0')}`}
  function selectedDateTitle(value){if(!value)return 'Oportunidades encontradas';if(value===dateKey(0))return 'Leilões de hoje';if(value===dateKey(1))return 'Leilões de amanhã';const [year,month,day]=value.split('-');return `Leilões de ${day}/${month}/${year}`}
  function applyExactDate(value,source){if(!value)return;if(state.exactDate===value&&source!=='calendar'){state.exactDate='';$('exact-date-filter').value='';resetVisible();track('filter_exact_date',{date:'all',source,result_count:current.length});return}state.exactDate=value;state.days='all';state.savedOnly=false;$('date-filter').value='all';$('exact-date-filter').value=value;resetVisible();track('filter_exact_date',{date:value,source,result_count:current.length});$('resultados').scrollIntoView({behavior:'smooth'})}
  function parseStart(row){""",
        "funções de data",
    )
    result = _replace_once(
        result,
        "function filtered(){const now=new Date();const max=state.days==='all'?null:new Date(now.getTime()+Number(state.days)*86400000);const saved=loadSaved();return lots.filter(row=>{const text=rowText(row);if(!matchesQuery(row))return false;if(state.category!=='all'&&!categories[state.category].some(term=>text.includes(term)))return false;if(state.uf&&row.uf!==state.uf)return false;if(state.savedOnly&&!saved.includes(lotId(row)))return false;const start=parseStart(row);if(max&&start&&start>max)return false;return true}).sort((a,b)=>{const query=norm(state.query);const sa=query&&norm(displayTitle(a)).includes(query)?1:0;const sb=query&&norm(displayTitle(b)).includes(query)?1:0;return sb-sa||String(a.data||'9999').localeCompare(String(b.data||'9999'))||String(a.hora||'').localeCompare(String(b.hora||''))})}",
        "function filtered(){const now=new Date();const max=state.days==='all'?null:new Date(now.getTime()+Number(state.days)*86400000);const saved=loadSaved();return lots.filter(row=>{const text=rowText(row);if(!matchesQuery(row))return false;if(state.category!=='all'&&!categories[state.category].some(term=>text.includes(term)))return false;if(state.uf&&row.uf!==state.uf)return false;if(state.savedOnly&&!saved.includes(lotId(row)))return false;if(state.exactDate&&row.data!==state.exactDate)return false;if(state.locationActive){const distance=distanceKm(row);if(distance===null||distance>state.radius)return false}const start=parseStart(row);if(!state.exactDate&&max&&start&&start>max)return false;return true}).sort((a,b)=>{if(state.locationActive){const distanceOrder=distanceKm(a)-distanceKm(b);if(distanceOrder)return distanceOrder}const query=norm(state.query);const sa=query&&norm(displayTitle(a)).includes(query)?1:0;const sb=query&&norm(displayTitle(b)).includes(query)?1:0;return sb-sa||String(a.data||'9999').localeCompare(String(b.data||'9999'))||String(a.hora||'').localeCompare(String(b.hora||''))})}",
        "filtragem dos lotes",
    )
    result = _replace_once(
        result,
        "$('results-title').textContent=state.savedOnly?'Seus lotes salvos':'Leilões encontrados';",
        "$('results-title').textContent=state.savedOnly?'Seus lotes salvos':state.exactDate?(state.locationActive?`${selectedDateTitle(state.exactDate)} perto de ${state.locationLabel}`:selectedDateTitle(state.exactDate)):state.locationActive?`Leilões perto de ${state.locationLabel}`:'Leilões encontrados';",
        "título dos resultados",
    )
    result = _replace_once(
        result,
        "$('results-status').textContent=`${formatNumber(currentGroups.length)} leilões · ${formatNumber(current.length)} lotes correspondem aos filtros atuais.`;",
        "$('results-status').textContent=state.locationActive?`${formatNumber(currentGroups.length)} leilões · ${formatNumber(current.length)} lotes em um raio de ${state.radius} km.`:`${formatNumber(currentGroups.length)} leilões · ${formatNumber(current.length)} lotes correspondem aos filtros atuais.`;$('nearby-status').textContent=state.locationActive?`${formatNumber(current.length)} oportunidades até ${state.radius} km de ${state.locationLabel}. Mais próximas primeiro.`:'Informe sua região para ordenar os leilões mais próximos.';",
        "resumo da proximidade",
    )
    result = _replace_once(
        result,
        "  const lotDistanceBadge=row=>'';\n  const groupDistanceBadge=group=>'';",
        "  const lotDistanceBadge=row=>{const distance=distanceKm(row);return distance===null?'':`<span class=\"distance-badge\">A ${Math.round(distance)} KM</span>`};\n  const groupDistanceBadge=group=>{if(!state.locationActive)return '';const distances=group.items.map(entry=>distanceKm(entry.row)).filter(value=>value!==null);return distances.length?`<span class=\"distance-badge\">MAIS PRÓXIMO A ${Math.round(Math.min(...distances))} KM</span>`:''};",
        "distância nos leilões e lotes",
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
        "function clearFilters(){state.query='';state.category='all';state.uf='';state.days='all';state.exactDate='';state.savedOnly=false;$('search-input').value='';$('state-filter').value='';$('date-filter').value='all';$('exact-date-filter').value='';localStorage.removeItem(SEARCH_STORE);clearNearby(false);resetVisible()}",
        "limpeza dos filtros",
    )
    result = _replace_once(
        result,
        "$('updated-label').textContent='ATUALIZADO TODOS OS DIAS';",
        "restoreLocation();$('exact-date-filter').min=dateKey(0);$('today-count').textContent=formatNumber(lots.filter(row=>row.data===dateKey(0)).length);$('tomorrow-count').textContent=formatNumber(lots.filter(row=>row.data===dateKey(1)).length);$('updated-label').textContent='ATUALIZADO TODOS OS DIAS';",
        "configuração inicial",
    )
    result = _replace_once(
        result,
        "  $('date-filter').addEventListener('change',event=>{state.days=event.target.value;state.savedOnly=false;resetVisible();track('filter_date',{days:state.days,result_count:current.length})});",
        """  document.querySelectorAll('[data-date-shortcut]').forEach(btn=>btn.addEventListener('click',()=>applyExactDate(dateKey(btn.dataset.dateShortcut==='tomorrow'?1:0),btn.dataset.dateShortcut)));
  $('exact-date-filter').addEventListener('change',event=>{if(event.target.value)applyExactDate(event.target.value,'calendar');else{state.exactDate='';resetVisible()}});
  $('date-filter').addEventListener('change',event=>{state.days=event.target.value;state.exactDate='';$('exact-date-filter').value='';state.savedOnly=false;resetVisible();track('filter_date',{days:state.days,result_count:current.length})});
  $('location-input').addEventListener('input',event=>loadMunicipalityOptions(event.target.value));
  $('location-input').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();applyTypedLocation()}});
  $('apply-location').addEventListener('click',applyTypedLocation);
  $('use-location').addEventListener('click',useCurrentLocation);
  $('clear-location').addEventListener('click',()=>clearNearby(true));
  $('radius-filter').addEventListener('change',event=>{state.radius=Number(event.target.value)||200;if(state.locationActive){saveLocation();resetVisible();track('filter_distance_radius',{radius_km:state.radius,result_count:current.length})}});""",
        "eventos dos filtros de data",
    )
    return result
