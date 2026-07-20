export type Lote = {
  leiloeiro?: string; evento?: string; data?: string; data_original?: string; hora?: string; uf?: string; local?: string;
  link_evento?: string; link_edital?: string; resumo_edital?: string; fonte?: string; capturado_em?: string;
  status_captura?: string; titulo?: string; descricao?: string; lance_atual?: string; lote?: string; link_lote?: string; foto_lote?: string;
};
export type LotesPayload = Lote[] | { lotes?: Lote[]; atualizado_em?: string; ultima_atualizacao?: string; [key: string]: unknown };
export type Filters = { categoria: string; estado: string; cidade: string; leiloeiro: string; data: string; status: string; precoMin: string; precoMax: string };
