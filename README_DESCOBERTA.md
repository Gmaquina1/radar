# Descoberta web

`descobrir_leiloes_web.py` complementa o Google My Maps com um catálogo incremental,
sitemaps, `robots.txt`, JSON-LD, OpenGraph e links internos. O arquivo consolidado é
entregue ao indexador existente; falhas ficam isoladas por domínio.

A busca é opcional. Para usar a API Brave Search, configure apenas no ambiente:

```bash
export WEB_SEARCH_PROVIDER=brave
export WEB_SEARCH_API_KEY='...'
python descobrir_leiloes_web.py          # grupo rotativo e econômico
python descobrir_leiloes_web.py --deep-discovery
```

Sem essas variáveis, mapa, catálogo persistido, sitemaps e links internos continuam
funcionando. Limites como `MAX_DEPTH`, `REQUEST_TIMEOUT`, `REQUEST_RETRIES`,
`MAX_SEARCH_QUERIES` e `MAX_PAGES_PER_DOMAIN` também podem ser ajustados por ambiente.
Nenhuma chave é armazenada no repositório ou enviada ao frontend.
