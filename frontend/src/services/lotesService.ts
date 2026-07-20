import type { Lote, LotesPayload } from '../types/lote.ts';
import { localSearch, parseLotesPayload } from '../utils/lotes.ts';
export async function fetchLotes(): Promise<Lote[]> { const res = await fetch('/lotes.json'); if (!res.ok) throw new Error('Não foi possível carregar lotes.json'); return parseLotesPayload(await res.json() as LotesPayload); }
export async function searchLotes(lotes: Lote[], query: string): Promise<Lote[]> {
  const appId = import.meta.env?.VITE_ALGOLIA_APP_ID; const key = import.meta.env?.VITE_ALGOLIA_SEARCH_API_KEY; const indexName = import.meta.env?.VITE_ALGOLIA_INDEX_NAME;
  if (!query || !appId || !key || !indexName) return localSearch(lotes, query);
  try { const res = await fetch(`https://${appId}-dsn.algolia.net/1/indexes/${encodeURIComponent(indexName)}/query`, { method:'POST', headers:{'content-type':'application/json','x-algolia-api-key':key,'x-algolia-application-id':appId}, body: JSON.stringify({query,hitsPerPage:200}) }); if(!res.ok) throw new Error('Algolia indisponível'); const json = await res.json() as { hits?: Lote[] }; return json.hits?.length ? json.hits : localSearch(lotes, query); }
  catch { return localSearch(lotes, query); }
}
