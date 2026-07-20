import test from 'node:test';
import assert from 'node:assert/strict';
import { applyFilters, localSearch, normalizeText, paginate, parseLotesPayload } from './lotes.ts';
import type { Lote } from '../types/lote.ts';
const lotes: Lote[] = [
  { titulo:'Caminhão Basculante', evento:'Leilão de veículos', uf:'SP', local:'Pátio - Campinas - SP - Brasil', leiloeiro:'A', data:'2026-08-01', link_evento:'e1' },
  { titulo:'Máquina Pá Carregadeira', evento:'Máquinas pesadas', uf:'RJ', local:'Centro - Niterói - RJ - Brasil', leiloeiro:'B', data:'2026-08-02', link_evento:'e2' },
];
test('lê payload compatível com lotes.json', () => { assert.equal(parseLotesPayload({ lotes }).length, 2); assert.equal(parseLotesPayload(lotes).length, 2); });
test('faz pesquisa local sem diferenciar acentos e caixa', () => { assert.equal(localSearch(lotes, 'caminhao').length, 1); assert.equal(localSearch(lotes, 'pa carregadeira').length, 1); });
test('filtra por estado', () => { assert.equal(applyFilters(lotes, {categoria:'',estado:'SP',cidade:'',leiloeiro:'',data:'',status:'',precoMin:'',precoMax:''}).length, 1); });
test('filtra por categoria', () => { assert.equal(applyFilters(lotes, {categoria:'Máquinas',estado:'',cidade:'',leiloeiro:'',data:'',status:'',precoMin:'',precoMax:''}).length, 1); });
test('remove acentos', () => { assert.equal(normalizeText('Leilões São Luís'), 'leiloes sao luis'); });
test('pagina resultados', () => { assert.deepEqual(paginate([1,2,3,4,5],2,2), [3,4]); });
