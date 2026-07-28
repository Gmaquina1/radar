# Descoberta web

`descobrir_leiloes_web.py` complementa o Google My Maps com um catálogo incremental,
sitemaps, `robots.txt`, JSON-LD, OpenGraph e links internos. O arquivo consolidado é
entregue ao indexador existente; falhas ficam isoladas por domínio.

`fontes_planilha.json` mantém o catálogo nacional fornecido ao Radar. A cada execução,
as fontes marcadas com `coletar_lotes` são mescladas ao catálogo incremental sem
apagar caminhos ou estados aprendidos anteriormente. A descoberta profunda também
executa `auditar_fontes_planilha.py`, que testa todos os portais, fontes oficiais e
Juntas Comerciais e registra bloqueios, timeouts e endereços acessíveis.

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

No GitHub Actions, `WEB_SEARCH_PROVIDER` deve ser uma **Variable** do repositório com
valor `brave`, enquanto `WEB_SEARCH_API_KEY` deve existir exclusivamente como
**Secret**. A etapa `Verificar busca web` informa apenas se o secret está configurado,
sem imprimir seu conteúdo. O relatório registra o provider, o total de consultas e o
total de resultados, mas nunca a chave.
