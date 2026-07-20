import type { Filters, Lote, LotesPayload } from '../types/lote.ts';
import { includesNormalized, normalizeText } from './text.ts';
export const parseLotesPayload = (payload: LotesPayload): Lote[] => Array.isArray(payload) ? payload : Array.isArray(payload.lotes) ? payload.lotes : [];
export const getCity = (lote: Lote) => (lote.local?.split(' - ').find((p) => /[A-Za-zÀ-ÿ]/.test(p) && !/Brasil|\d{5}/i.test(p)) || '').trim();
export const getCategory = (lote: Lote) => {
  const text = `${lote.evento ?? ''} ${lote.titulo ?? ''}`;
  if (/caminh|ônibus|onibus|carro|ve[ií]culo|moto/i.test(text)) return 'Veículos';
  if (/trator|escav|pá carregadeira|maquin|retro/i.test(text)) return 'Máquinas';
  if (/equip/i.test(text)) return 'Equipamentos';
  if (/sucata/i.test(text)) return 'Sucatas';
  if (/im[oó]vel|terreno|apart/i.test(text)) return 'Imóveis';
  return 'Outros';
};
export const parsePrice = (value = '') => { const n = value.replace(/[^\d,.-]/g, '').replace(/\.(?=\d{3})/g, '').replace(',', '.'); return Number.isFinite(Number(n)) ? Number(n) : undefined; };
export const isValidImageUrl = (url = '') => /^https?:\/\/.+\.(jpe?g|png|webp|gif)(\?.*)?$/i.test(url);
export const getStatus = (lote: Lote, now = new Date()) => { if (!lote.data) return 'futuro'; const d = new Date(`${lote.data}T${lote.hora || '23:59'}:00`); const diff = d.getTime() - now.getTime(); if (diff < 0) return 'ao vivo'; if (diff < 1000*60*60*48) return 'em breve'; return 'futuro'; };
export const searchableText = (l: Lote) => [l.titulo,l.descricao,l.evento,l.leiloeiro,l.uf,l.local,l.lote].filter(Boolean).join(' ');
export const localSearch = (lotes: Lote[], query: string) => !query ? lotes : lotes.filter((l) => includesNormalized(searchableText(l), query));
export const applyFilters = (lotes: Lote[], f: Filters) => lotes.filter((l) => {
  const price = parsePrice(l.lance_atual); const cat = getCategory(l); const city = getCity(l); const status = getStatus(l);
  return (!f.categoria || cat === f.categoria) && (!f.estado || l.uf === f.estado) && (!f.cidade || includesNormalized(city, f.cidade)) && (!f.leiloeiro || l.leiloeiro === f.leiloeiro) && (!f.data || l.data === f.data) && (!f.status || status === f.status) && (!f.precoMin || (price ?? 0) >= Number(f.precoMin)) && (!f.precoMax || (price ?? Infinity) <= Number(f.precoMax));
});
export const paginate = <T,>(items: T[], page: number, perPage: number) => items.slice((page - 1) * perPage, page * perPage);
export const unique = (v: string[]) => [...new Set(v.filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt-BR'));
export const countBy = <T,>(items: T[], key: (item:T)=>string) => items.reduce<Record<string,number>>((acc,item)=>{ const k=key(item)||'Não informado'; acc[k]=(acc[k]||0)+1; return acc;},{});
export const formatDate = (date?: string) => date ? new Intl.DateTimeFormat('pt-BR',{timeZone:'UTC'}).format(new Date(`${date}T00:00:00Z`)) : 'Sem data';
export { normalizeText };
