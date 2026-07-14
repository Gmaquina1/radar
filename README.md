# Radar de Leilões G MAQUINA — Premium

Site estático compatível com GitHub Pages, preparado para funcionar em:

https://gmaquina1.github.io/radar/

## O que esta versão faz

- visual Premium responsivo para celular, tablet e computador;
- mostra somente leilões e lotes que ainda irão acontecer;
- pesquisa por máquina, veículo, imóvel, cidade, estado, leiloeiro e conteúdo do edital;
- abre o lote no site oficial do leiloeiro;
- mostra **Abrir edital completo** quando o PDF ou documento foi localizado;
- salva oportunidades no próprio aparelho do visitante;
- atualiza mapa, eventos, lotes e editais todos os dias às 16h de Brasília;
- mantém uma cópia dos lotes de eventos ativos quando um portal bloqueia temporariamente a consulta.

## Atualização automática

O workflow `.github/workflows/atualizar-radar.yml` executa diariamente às 19:00 UTC, equivalente a 16:00 no horário de Brasília.

O processo executa, nesta ordem:

1. atualização do Google My Maps e leitura das datas;
2. leitura dos sites dos leiloeiros e dos editais PDF;
3. indexação dos lotes com 16 trabalhadores;
4. exclusão de eventos e lotes encerrados;
5. geração do `index.html` Premium;
6. testes, diagnóstico e commit automático.

Também é possível executar manualmente em **Actions → Atualizar Radar diariamente as 16h → Run workflow**.

## Arquivos principais

- `index.html`: página pronta publicada pelo GitHub Pages;
- `site_template.html`: visual e funcionamento usados para gerar a página;
- `gerar_site_github.py`: une o visual à base futura;
- `atualizar_radar_leiloes.py`: atualiza mapa, datas e links de editais;
- `indexador_lotes.py`: lê sites, APIs, HTML e documentos PDF;
- `lotes.json`: base dos lotes;
- `assets/`: imagens do visual Premium;
- `.github/workflows/atualizar-radar.yml`: agendamento diário.

## GitHub Pages

Em **Settings → Pages**, utilize:

- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/(root)`

Depois de salvar, aguarde alguns minutos e atualize o site com `Ctrl + F5`.
