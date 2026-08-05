(() => {
  'use strict';

  const PNCP_ENDPOINT = 'https://pncp.gov.br/api/consulta/v1/contratacoes/proposta';
  const CACHE_DB = 'radar-licitacoes-cache-v2';
  const CACHE_STORE = 'bases';
  const CACHE_KEY = 'pncp-abertas';
  const CACHE_MAX_AGE_MS = 30 * 60 * 1000;
  const MAX_PAGES = 1000;
  const PAGE_SIZES = [500, 200, 100, 50];
  const PAGE_DELAY_MS = 900;
  const MAX_ATTEMPTS = 7;

  const $ = (id) => document.getElementById(id);
  const state = {
    rows: [], filtered: [], query: '', uf: '', modality: '', period: 365,
    sort: 'deadline', limit: 36, sourceText: 'Base local', updatedAt: '',
  };
  const saved = new Set(JSON.parse(localStorage.getItem('radar_licitacoes_salvas_v2') || '[]'));
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const todayIso = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
  const addDaysIso = (days) => {
    const d = new Date(`${todayIso()}T12:00:00-03:00`);
    d.setDate(d.getDate() + days);
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(d);
  };
  const pncpDate = (days) => addDaysIso(days).replaceAll('-', '');
  const dateOnly = (value) => String(value || '').slice(0, 10);
  const normalize = (value) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const escapeHtml = (value) => String(value || '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
  const number = (value) => new Intl.NumberFormat('pt-BR').format(Number(value) || 0);
  const money = (value) => Number(value) > 0
    ? new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(Number(value))
    : 'Não informado';
  const formatDate = (value) => {
    if (!value) return 'Não informada';
    const text = String(value);
    const d = new Date(text);
    if (Number.isNaN(d.getTime())) return dateOnly(text).split('-').reverse().join('/');
    return new Intl.DateTimeFormat('pt-BR', {
      dateStyle: 'short', timeStyle: text.includes('T') ? 'short' : undefined,
      timeZone: 'America/Sao_Paulo',
    }).format(d);
  };

  function pncpLink(numeroControle) {
    const match = String(numeroControle || '').match(/^(\d{14})-\d+-(\d+)\/(\d{4})$/);
    if (!match) return 'https://pncp.gov.br/app/editais';
    return `https://pncp.gov.br/app/editais/${match[1]}/${match[3]}/${Number(match[2])}`;
  }

  function isAuction(row) {
    return normalize(`${row.modalidade || ''} ${row.modalidadeNome || ''}`).includes('leilao');
  }

  function mapPncp(raw) {
    const numero = String(raw.numeroControlePNCP || '').trim();
    const orgao = raw.orgaoEntidade && typeof raw.orgaoEntidade === 'object'
      ? raw.orgaoEntidade.razaoSocial : raw.orgaoEntidadeRazaoSocial;
    const unidade = raw.unidadeOrgao && typeof raw.unidadeOrgao === 'object'
      ? raw.unidadeOrgao.nomeUnidade : raw.unidadeOrgaoNomeUnidade;
    const uf = raw.unidadeOrgao && typeof raw.unidadeOrgao === 'object'
      ? raw.unidadeOrgao.ufSigla : raw.unidadeOrgaoUfSigla;
    const cidade = raw.unidadeOrgao && typeof raw.unidadeOrgao === 'object'
      ? raw.unidadeOrgao.municipioNome : raw.unidadeOrgaoMunicipioNome;
    return {
      id: numero || `${orgao || ''}|${raw.numeroCompra || ''}|${raw.dataEncerramentoProposta || ''}`,
      numero,
      numero_compra: String(raw.numeroCompra || '').trim(),
      processo: String(raw.processo || '').trim(),
      orgao: String(orgao || '').trim(),
      unidade: String(unidade || '').trim(),
      objeto: String(raw.objetoCompra || '').trim(),
      informacao_complementar: String(raw.informacaoComplementar || '').trim(),
      modalidade: String(raw.modalidadeNome || raw.modalidadeNomePncp || '').trim(),
      situacao: String(raw.situacaoCompraNome || raw.situacaoCompraNomePncp || '').trim(),
      data_publicacao: String(raw.dataPublicacaoPncp || '').replace(' ', 'T'),
      data_abertura: String(raw.dataAberturaProposta || raw.dataAberturaPropostaPncp || '').replace(' ', 'T'),
      data_encerramento: String(raw.dataEncerramentoProposta || raw.dataEncerramentoPropostaPncp || '').replace(' ', 'T'),
      valor_estimado: raw.valorTotalEstimado,
      uf: String(uf || '').trim().toUpperCase(),
      cidade: String(cidade || '').trim(),
      link: pncpLink(numero),
      fonte: 'PNCP ao vivo',
    };
  }

  function rowKey(row) {
    if (row.id) return `id:${normalize(row.id)}`;
    if (row.link) return `url:${String(row.link).replace(/[#?].*$/, '')}`;
    return `dados:${normalize(`${row.orgao}|${row.objeto}|${row.data_encerramento}`)}`;
  }

  function mergeRows(incoming) {
    const map = new Map(state.rows.map((row) => [rowKey(row), row]));
    for (const row of incoming || []) {
      if (!row || typeof row !== 'object' || isAuction(row)) continue;
      const closing = dateOnly(row.data_encerramento);
      if (closing && closing < todayIso()) continue;
      const key = rowKey(row);
      const current = map.get(key) || {};
      const merged = { ...current, ...row };
      for (const [field, value] of Object.entries(current)) {
        if (merged[field] === null || merged[field] === undefined || merged[field] === '') merged[field] = value;
      }
      map.set(key, merged);
    }
    state.rows = [...map.values()].sort((a, b) => String(a.data_encerramento || '9999').localeCompare(String(b.data_encerramento || '9999')));
  }

  function rebuildOptions() {
    const ufSelect = $('uf-filter');
    const modalitySelect = $('modality-filter');
    if (!ufSelect || !modalitySelect) return;
    const selectedUf = state.uf;
    const selectedModality = state.modality;
    const ufs = [...new Set(state.rows.map((row) => row.uf).filter(Boolean))].sort();
    const modalities = [...new Set(state.rows.map((row) => row.modalidade).filter(Boolean))].sort();
    ufSelect.innerHTML = '<option value="">Todos os estados</option>' + ufs.map((uf) => `<option value="${escapeHtml(uf)}">${escapeHtml(uf)}</option>`).join('');
    modalitySelect.innerHTML = '<option value="">Todas as modalidades</option>' + modalities.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
    ufSelect.value = ufs.includes(selectedUf) ? selectedUf : '';
    modalitySelect.value = modalities.includes(selectedModality) ? selectedModality : '';
  }

  function updateMetrics() {
    $('metric-total').textContent = number(state.rows.length);
    $('metric-states').textContent = number(new Set(state.rows.map((row) => row.uf).filter(Boolean)).size);
    $('metric-organs').textContent = number(new Set(state.rows.map((row) => row.orgao).filter(Boolean)).size);
  }

  function filteredRows() {
    const lastDate = addDaysIso(state.period);
    const query = normalize(state.query);
    const rows = state.rows.filter((row) => {
      const end = dateOnly(row.data_encerramento);
      if (end && end < todayIso()) return false;
      if (end && end > lastDate) return false;
      if (state.uf && row.uf !== state.uf) return false;
      if (state.modality && row.modalidade !== state.modality) return false;
      if (query) {
        const haystack = normalize([
          row.objeto, row.informacao_complementar, row.orgao, row.unidade,
          row.cidade, row.uf, row.modalidade, row.numero, row.numero_compra, row.processo,
        ].join(' '));
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
    rows.sort((a, b) => {
      if (state.sort === 'recent') return String(b.data_publicacao || '').localeCompare(String(a.data_publicacao || ''));
      if (state.sort === 'value') return (Number(b.valor_estimado) || 0) - (Number(a.valor_estimado) || 0);
      return String(a.data_encerramento || '9999').localeCompare(String(b.data_encerramento || '9999'));
    });
    return rows;
  }

  function card(row) {
    const id = escapeHtml(row.id || rowKey(row));
    const place = [row.cidade, row.uf].filter(Boolean).join(' - ') || 'Local não informado';
    const officialLink = row.link || pncpLink(row.numero || '');
    return `<article class="card">
      <div class="card-top"><span class="tag">${escapeHtml(row.modalidade || 'Licitação')}</span><button class="save ${saved.has(row.id) ? 'active' : ''}" type="button" data-save="${id}" aria-label="Salvar oportunidade">★</button></div>
      <h3>${escapeHtml(row.objeto || 'Objeto não informado')}</h3>
      <p class="org">${escapeHtml(row.orgao || 'Órgão não informado')}${row.unidade ? ` • ${escapeHtml(row.unidade)}` : ''}</p>
      <div class="details"><span>📍 <b>${escapeHtml(place)}</b></span><span>⏱ Encerra: <b>${escapeHtml(formatDate(row.data_encerramento))}</b></span><span>▤ Processo: <b>${escapeHtml(row.processo || row.numero_compra || row.numero || 'Não informado')}</b></span></div>
      <div class="value"><span><small>VALOR ESTIMADO</small><strong>${escapeHtml(money(row.valor_estimado))}</strong></span><a class="official" href="${escapeHtml(officialLink)}" target="_blank" rel="noopener">VER OFICIAL ↗</a></div>
    </article>`;
  }

  function render(reset = true) {
    if (reset) state.limit = 36;
    state.filtered = filteredRows();
    $('results-status').textContent = `${number(state.filtered.length)} resultado${state.filtered.length === 1 ? '' : 's'} • ${state.sourceText}${state.updatedAt ? ` • ${formatDate(state.updatedAt)}` : ''}`;
    $('cards').innerHTML = state.filtered.length
      ? state.filtered.slice(0, state.limit).map(card).join('')
      : '<div class="empty"><strong>Nenhuma oportunidade encontrada.</strong><br>Altere os filtros ou confira novamente a fonte oficial.</div>';
    $('load-more').style.display = state.filtered.length > state.limit ? 'block' : 'none';
    updateMetrics();
  }

  function setLiveStatus(text, kind = 'info') {
    const box = $('live-status');
    if (!box) return;
    box.className = `live-status ${kind}`;
    box.textContent = text;
  }

  async function fetchJson(url, attempt = 0) {
    try {
      const response = await fetch(url, { cache: 'no-store', headers: { Accept: 'application/json' } });
      if (response.ok) return await response.json();
      if ((response.status === 429 || response.status >= 500) && attempt < MAX_ATTEMPTS - 1) {
        const retryAfter = Number(response.headers.get('Retry-After'));
        const wait = Number.isFinite(retryAfter) && retryAfter > 0
          ? Math.min(retryAfter * 1000, 300000)
          : Math.min(300000, 5000 * (2 ** attempt));
        setLiveStatus(`O PNCP limitou temporariamente os acessos. Retomando em ${Math.ceil(wait / 1000)} segundos…`, 'warning');
        await sleep(wait);
        return fetchJson(url, attempt + 1);
      }
      throw new Error(`HTTP ${response.status}`);
    } catch (error) {
      if (attempt < MAX_ATTEMPTS - 1) {
        const wait = Math.min(120000, 3000 * (2 ** attempt));
        await sleep(wait);
        return fetchJson(url, attempt + 1);
      }
      throw error;
    }
  }

  function pncpUrl(finalDate, page, size) {
    const params = new URLSearchParams({ dataFinal: finalDate, pagina: String(page), tamanhoPagina: String(size) });
    return `${PNCP_ENDPOINT}?${params}`;
  }

  async function choosePageSize(finalDate) {
    let lastError;
    for (const size of PAGE_SIZES) {
      try {
        const first = await fetchJson(pncpUrl(finalDate, 1, size));
        return { size, first };
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error('O PNCP não aceitou a consulta.');
  }

  function openDatabase() {
    return new Promise((resolve, reject) => {
      if (!('indexedDB' in window)) return resolve(null);
      const request = indexedDB.open(CACHE_DB, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(CACHE_STORE);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function readCache() {
    try {
      const db = await openDatabase();
      if (!db) return null;
      return await new Promise((resolve) => {
        const tx = db.transaction(CACHE_STORE, 'readonly');
        const request = tx.objectStore(CACHE_STORE).get(CACHE_KEY);
        request.onsuccess = () => resolve(request.result || null);
        request.onerror = () => resolve(null);
      });
    } catch { return null; }
  }

  async function writeCache(value) {
    try {
      const db = await openDatabase();
      if (!db) return;
      await new Promise((resolve, reject) => {
        const tx = db.transaction(CACHE_STORE, 'readwrite');
        tx.objectStore(CACHE_STORE).put(value, CACHE_KEY);
        tx.oncomplete = resolve;
        tx.onerror = () => reject(tx.error);
      });
    } catch { /* cache opcional */ }
  }

  async function loadStaticBase() {
    const embedded = window.__LICITACOES_EMBEDDED__ || {};
    if (Array.isArray(embedded.licitacoes)) {
      mergeRows(embedded.licitacoes);
      state.updatedAt = embedded.atualizado_em || '';
      state.sourceText = embedded.parcial ? 'Base local parcial' : 'Base local';
    }
    try {
      const response = await fetch(`./licitacoes.json?v=${Date.now()}`, { cache: 'no-store' });
      const payload = response.ok ? await response.json() : null;
      if (payload && Array.isArray(payload.licitacoes)) {
        mergeRows(payload.licitacoes);
        state.updatedAt = payload.atualizado_em || state.updatedAt;
        state.sourceText = payload.parcial ? 'Base local parcial' : 'Base local';
      }
    } catch { /* base embutida permanece */ }
    rebuildOptions();
    render();
  }

  async function loadLivePncp(force = false) {
    $('refresh-live').disabled = true;
    const cached = await readCache();
    if (cached && Array.isArray(cached.rows)) {
      mergeRows(cached.rows);
      state.updatedAt = cached.updatedAt || state.updatedAt;
      state.sourceText = 'PNCP ao vivo em cache';
      rebuildOptions();
      render();
      if (!force && Date.now() - Number(cached.savedAt || 0) < CACHE_MAX_AGE_MS) {
        setLiveStatus(`Base oficial completa carregada do cache: ${number(cached.rows.length)} oportunidades.`, 'success');
        $('refresh-live').disabled = false;
        return;
      }
    }

    try {
      const finalDate = pncpDate(365);
      setLiveStatus('Consultando o PNCP ao vivo…', 'loading');
      const { size, first } = await choosePageSize(finalDate);
      const totalPages = Math.min(Number(first.totalPaginas) || 1, MAX_PAGES);
      const collected = [];
      const absorb = (payload) => {
        const source = Array.isArray(payload.data) ? payload.data : [];
        for (const raw of source) {
          const row = mapPncp(raw);
          if (!isAuction(row) && (!dateOnly(row.data_encerramento) || dateOnly(row.data_encerramento) >= todayIso())) collected.push(row);
        }
      };
      absorb(first);
      mergeRows(collected);
      state.sourceText = `PNCP ao vivo: página 1 de ${totalPages}`;
      rebuildOptions();
      render();

      for (let page = 2; page <= totalPages; page += 1) {
        await sleep(PAGE_DELAY_MS);
        const payload = await fetchJson(pncpUrl(finalDate, page, size));
        absorb(payload);
        if (page % 5 === 0 || page === totalPages) {
          mergeRows(collected);
          state.sourceText = `PNCP ao vivo: página ${page} de ${totalPages}`;
          setLiveStatus(`Atualizando a base oficial: página ${page} de ${totalPages} • ${number(state.rows.length)} oportunidades…`, 'loading');
          rebuildOptions();
          render(false);
        }
      }

      mergeRows(collected);
      state.updatedAt = new Date().toISOString();
      state.sourceText = 'Base oficial completa do PNCP';
      rebuildOptions();
      render();
      await writeCache({ rows: state.rows, updatedAt: state.updatedAt, savedAt: Date.now(), pageSize: size, totalPages });
      setLiveStatus(`Atualização oficial concluída: ${number(state.rows.length)} oportunidades abertas em ${totalPages} páginas.`, 'success');
    } catch (error) {
      console.error('Falha na atualização ao vivo do PNCP:', error);
      setLiveStatus(`O PNCP não concluiu a consulta ao vivo. A base local com ${number(state.rows.length)} oportunidades continua disponível.`, 'warning');
    } finally {
      $('refresh-live').disabled = false;
    }
  }

  function bindEvents() {
    $('search-form').addEventListener('submit', (event) => {
      event.preventDefault();
      state.query = $('search-input').value.trim();
      state.uf = $('uf-filter').value;
      state.modality = $('modality-filter').value;
      state.period = Number($('period-filter').value) || 365;
      render();
    });
    ['uf-filter', 'modality-filter', 'period-filter'].forEach((id) => $(id).addEventListener('change', () => $('search-form').requestSubmit()));
    $('sort-filter').addEventListener('change', (event) => { state.sort = event.target.value; render(); });
    $('load-more').addEventListener('click', () => { state.limit += 36; render(false); });
    $('refresh-live').addEventListener('click', () => loadLivePncp(true));
    $('cards').addEventListener('click', (event) => {
      const button = event.target.closest('[data-save]');
      if (!button) return;
      const id = button.dataset.save;
      saved.has(id) ? saved.delete(id) : saved.add(id);
      localStorage.setItem('radar_licitacoes_salvas_v2', JSON.stringify([...saved]));
      button.classList.toggle('active', saved.has(id));
    });
    const parts = ['55', '38', '99846', '5955'];
    document.querySelectorAll('[data-whatsapp]').forEach((link) => {
      link.href = `https://wa.me/${parts.join('')}?text=${encodeURIComponent('Olá! Entrei em contato pelo Radar de Licitações.')}`;
      link.target = '_blank';
    });
  }

  async function start() {
    bindEvents();
    await loadStaticBase();
    await loadLivePncp(false);
  }

  start();
})();
