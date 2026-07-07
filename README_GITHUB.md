# Radar de Leiloes - G MAQUINA

Aplicacao estatica para pesquisar eventos de leilao, salvar interesses e preparar monitoramento de lances.

## Arquivos principais

- `index.html`: pagina principal para publicar no GitHub Pages.
- `gerar_site_github.py`: recria o `index.html` com a base atual.
- `radar_leiloes_eventos_futuros.csv`: base de eventos futuros.
- `radar_leiloes_patios.csv`: base de patios.
- `lotes.json` e `lotes.csv`: lotes indexados dentro dos eventos, quando o leiloeiro permite leitura automatica.
- `monitoramento.json`: arquivo que futuramente recebera lances atualizados.
- `atualizar_radar_leiloes.py`: atualiza a base a partir do mapa.
- `indexador_lotes.py`: abre os links dos eventos e tenta capturar lotes por HTML, JSON e adaptadores por leiloeiro.
- O atualizador tambem tenta ler sites, PDFs e editais para confirmar data e horario do leilao.

## Publicar no GitHub Pages

1. Crie um repositorio no GitHub.
2. Envie os arquivos para a raiz do repositorio.
3. Entre em `Settings > Pages`.
4. Em `Build and deployment`, selecione `Deploy from a branch`.
5. Escolha a branch `main` e a pasta `/root`.
6. Salve.

Depois o site ficara disponivel no link informado pelo GitHub Pages.

## Lembretes

Os lembretes ficam salvos no navegador do aparelho usando `localStorage`.
Isso funciona no celular e no computador, mas cada aparelho guarda seus proprios lembretes.
Cada leilao salvo mostra um contador de quanto tempo falta para o inicio informado.

## Monitoramento de lances

O painel `Monitoramento` le o arquivo `monitoramento.json`.
Para atualizar lances de hora em hora com seguranca, o ideal e criar um robo por site/leiloeiro. O GitHub Pages sozinho nao executa busca em segundo plano; quem atualiza os arquivos e o GitHub Actions.

## Atualizacao da pagina

No GitHub Pages puro, a pagina nao atualiza a base sozinha.
O link dos leiloes continua abrindo normalmente, mas a lista interna de eventos so muda quando os arquivos do repositorio forem atualizados.

Fluxo manual:

```bash
python3 atualizar_radar_leiloes.py
python3 gerar_site_github.py
```

Depois suba os arquivos atualizados para o GitHub.

Fluxo automatico ja configurado em `.github/workflows/atualizar-radar.yml`:

- Roda por agendamento e tambem pelo botao `Run workflow`.
- Baixa novamente o KML do mapa.
- Tenta ler data/hora em sites, PDFs e editais.
- Recria as bases CSV.
- Indexa lotes possiveis.
- Regenera `index.html` e `radar-leiloes.html`.
- Faz commit dos arquivos atualizados.

## Busca por modelo especifico

A busca principal pode pesquisar duas bases:

- `radar_leiloes_eventos_futuros.csv`: eventos do mapa.
- `lotes.json`: lotes capturados pelo indexador.

A base do mapa normalmente traz eventos por categoria:

- maquinas
- caminhoes
- veiculos
- prefeitura
- seguradora
- pátio

Modelos especificos como `Palio`, `Hilux`, `Strada`, `D8` ou o modelo exato de uma maquina podem aparecer apenas dentro da pagina do leiloeiro, nos lotes.

Por isso, quando a busca nao encontra nada na base do mapa, a pagina mostra botoes para pesquisar o termo nos principais sites de leilao.

Para encontrar lotes automaticamente dentro da pagina, use:

```bash
python3 indexador_lotes.py
python3 gerar_site_github.py
```

O `indexador_lotes.py` tenta ler HTML, JSON embutido e links de lote em cada evento.
Ele tambem ja tem adaptador para ofertas abertas da Superbid/SOLD via API publica `offer-query`.

Sites com Cloudflare, login, bloqueio de robo ou conteudo 100% carregado por JavaScript podem exigir adaptadores especificos por leiloeiro.

## Adaptadores por leiloeiro

Quando um site bloquear leitura automatica, existem tres caminhos:

1. Usar a API publica usada pelo proprio site, quando existir.
2. Capturar JSON embutido no HTML, quando o site manda os lotes junto com a pagina.
3. Deixar o evento indexado e abrir a busca auxiliar no Google/site, quando o leiloeiro bloqueia robos ou exige login.

O log em `lotes.json` mostra o status por evento:

- `api_superbid_ok`: lotes capturados pela API da Superbid/SOLD.
- `http_200`: pagina aberta e lida por HTML/JSON comum.
- `bloqueado_http_403`: site bloqueou leitura automatica.
- `sem_link`: evento sem link no mapa.

## Data e horario

A ordem de prioridade para data e horario e:

1. Edital/PDF, quando o arquivo permite extracao de texto e a data e valida.
2. Site do leiloeiro, quando a pagina mostra data/hora.
3. Mapa, quando o site ou edital bloqueia leitura.

Todos os horarios sao gravados em formato 24 horas, por exemplo `04:00`, `09:30` e `14:00`.

## Automacao completa

O workflow `.github/workflows/atualizar-radar.yml` faz:

1. Verifica se o Google My Maps mudou a cada 30 minutos.
2. Se mudou, atualiza o Radar imediatamente.
3. A cada 6 horas, faz uma resincronizacao completa mesmo se o mapa parecer igual.
4. Baixa novamente o KML do mapa.
5. Tenta ler sites, PDFs e editais.
6. Indexa os lotes.
7. Gera o site.
8. Publica `status_atualizacao.json` e `status_atualizacao.txt`.
9. Faz commit dos arquivos atualizados.

Ele tambem pode ser disparado manualmente pela aba `Acoes` do GitHub.

No GitHub em portugues:

1. Abra o repositorio.
2. Clique em `Acoes`.
3. Clique em `Atualizar Radar de Leiloes`.
4. Clique em `Executar fluxo de trabalho`.
5. Mantenha `forcar_atualizacao` como `true` se quiser atualizar na hora.

Se esse workflow nao aparecer em `Acoes`, confirme se esta pasta foi enviada ao repositorio:

```text
.github/
  workflows/
    atualizar-radar.yml
```

Sem essa pasta o GitHub Pages publica o site, mas o Radar nao atualiza automaticamente.

Depois de uma execucao bem-sucedida, confira:

```text
https://gmaquina1.github.io/radar/status_atualizacao.json
```

O campo `status` deve aparecer como `ok`.
