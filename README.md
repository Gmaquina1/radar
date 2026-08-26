# Radar de Leilões G MAQUINA — Premium

Site estático compatível com GitHub Pages, preparado para funcionar em:

https://gmaquina1.github.io/radar/

## O que esta versão faz

- visual Premium responsivo para celular, tablet e computador;
- mostra somente leilões e lotes que ainda irão acontecer;
- pesquisa por máquina, veículo, imóvel, cidade, estado, leiloeiro e conteúdo do edital;
- abre o lote no site oficial do leiloeiro;
- lê editais disponíveis para ampliar a qualidade da pesquisa;
- informa claramente que o Radar é independente e não realiza nem intermedeia leilões;
- usa carrosséis com nove fotografias reais incorporadas ao HTML, com troca automática e gesto de deslizar no celular;
- captura a fotografia verdadeira de cada lote quando o leiloeiro disponibiliza e usa uma imagem real da categoria como segurança;
- salva oportunidades no próprio aparelho do visitante;
- usa exclusivamente os eventos cadastrados no Google My Maps;
- atualiza o mapa e os lotes vinculados a esses eventos a cada 6 horas;
- mantém uma cópia dos lotes de eventos ativos quando um portal bloqueia temporariamente a consulta.

## Atualização automática

O workflow `.github/workflows/atualizar-radar.yml` executa a cada 6 horas.

O processo executa, nesta ordem:

1. atualização do Google My Maps e leitura das datas;
2. leitura somente dos sites e editais vinculados aos eventos do mapa;
3. indexação dos lotes com 16 trabalhadores;
4. exclusão de eventos e lotes encerrados;
5. geração do `index.html` Premium;
6. testes, diagnóstico e commit automático.

Também é possível executar manualmente em **Actions → Atualizar Radar completo → Run workflow**.

Eventos encontrados por busca na internet, OpenAI ou bases paralelas não entram no Radar de Leilões.

## Arquivos principais

- `index.html`: página pronta publicada pelo GitHub Pages;
- `site_template.html`: visual e funcionamento usados para gerar a página;
- `gerar_site_github.py`: une o visual à base futura;
- `atualizar_radar_leiloes.py`: atualiza mapa, datas e links de editais;
- `indexador_lotes.py`: lê sites, APIs, HTML e documentos PDF;
- `lotes.json`: base dos lotes;
- as fotografias reais dos carrosséis já estão incorporadas em `index.html` e `site_template.html`;
- `.github/workflows/atualizar-radar.yml`: agendamento a cada 6 horas.

## GitHub Pages

Em **Settings → Pages**, utilize:

- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/(root)`

Depois de salvar, aguarde alguns minutos e atualize o site com `Ctrl + F5`.
