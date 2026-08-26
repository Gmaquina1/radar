# Radar de Leiloes G MAQUINA

Site estatico publicado pelo GitHub Pages e atualizado automaticamente pelo GitHub Actions.

## O que atualiza sozinho

- O Google My Maps e verificado a cada 6 horas.
- Quando o KML muda, as bases de eventos e patios sao reconstruidas.
- A cada 6 horas, os sites e editais vinculados aos eventos do mapa sao relidos, mesmo quando o KML nao mudou.
- Os lotes sao capturados por API Superbid/SOLD, JSON, links HTML, texto da pagina e editais PDF.
- Se um site bloquear o robo ou ficar fora do ar, os lotes validos daquele mesmo evento e data sao preservados.
- `index.html`, CSVs, JSONs e o diagnostico sao regenerados e enviados por commit automatico.

## Fonte unica dos leiloes

Somente eventos existentes no Google My Maps entram na atualizacao e na pagina publicada. A busca externa de novos eventos e as bases paralelas de oportunidades ficam desativadas. Os sites dos leiloeiros continuam sendo acessados apenas para obter os lotes dos eventos que ja estao no mapa.

## Arquivos que precisam estar no repositorio

```text
.github/workflows/atualizar-radar.yml
requirements.txt
atualizar_radar_leiloes.py
indexador_lotes.py
gerar_site_github.py
diagnostico_radar.py
executar_atualizacao_radar.py
verificar_mapa_google.py
leiloes_do_brasil_completo.kml
lotes.json
lotes.csv
radar_leiloes_eventos_futuros.csv
radar_leiloes_eventos_todos.csv
radar_leiloes_patios.csv
radar_leiloes_base_completa.csv
radar_leiloes_resumo.json
index.html
radar-leiloes.html
```

Nao apague a pasta `.github`. Ela e oculta no Windows, mas e ela que faz a atualizacao automatica aparecer na aba **Actions/Acoes**.

## Ativar o GitHub Pages

1. Abra `Settings > Pages`.
2. Em `Build and deployment`, escolha `Deploy from a branch`.
3. Selecione a branch `main` e a pasta `/root`.
4. Salve.

## Executar uma atualizacao agora

1. Abra a aba `Actions` ou `Acoes`.
2. Selecione `Atualizar Radar completo`.
3. Clique em `Run workflow` ou `Executar fluxo de trabalho`.
4. Confirme no botao verde.

## Conferir o resultado

Abra:

```text
https://gmaquina1.github.io/radar/status_atualizacao.json
```

O campo `status` deve ser `ok`. O arquivo tambem informa quantos eventos, patios e lotes foram publicados, quantos lotes foram capturados na ultima rodada e quantos precisaram ser preservados por falha temporaria do site de origem.

## Limite real da automacao

Alguns leiloeiros usam login, CAPTCHA, Cloudflare ou conteudo fechado. Nenhum codigo executado apenas no GitHub Actions consegue garantir leitura de 100% desses portais. O Radar registra o bloqueio no log de `lotes.json` e conserva a ultima captura valida do mesmo evento/data para nao esvaziar a busca.
