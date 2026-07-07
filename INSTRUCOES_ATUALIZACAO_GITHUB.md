# Atualizacao automatica do Radar de Leiloes G MAQUINA

Este pacote ja vem com a automacao pronta.

## Arquivo mais importante

O GitHub so mostra a automacao na aba `Acoes` se este arquivo estiver no repositorio:

```text
.github/workflows/atualizar-radar.yml
```

No Windows, a pasta `.github` pode ficar oculta. Ao extrair o ZIP, ative `Itens ocultos` no Explorador de Arquivos para conferir.

## Como conferir no GitHub em portugues

1. Abra o repositorio `gmaquina1/radar`.
2. Clique em `Codigo`.
3. Confirme se existe a pasta `.github`.
4. Entre em `.github/workflows`.
5. Confirme se existe `atualizar-radar.yml`.
6. Clique em `Acoes`.
7. Deve aparecer `Atualizar Radar de Leiloes`.

Se aparecer apenas `Criacao e implantacao de paginas`, a automacao nao foi enviada.

## Como executar manualmente

1. Clique em `Acoes`.
2. Clique em `Atualizar Radar de Leiloes`.
3. Clique em `Executar fluxo de trabalho`.
4. Deixe `forcar_atualizacao` como `true`.
5. Clique no botao verde para executar.

## O que a automacao faz

- Verifica o Google My Maps a cada 30 minutos.
- Se o mapa mudou, atualiza o Radar.
- A cada 6 horas, faz uma resincronizacao completa mesmo se o mapa parecer igual.
- Baixa o KML do mapa com tentativas automaticas.
- Le sites, editais e PDFs quando possivel.
- Indexa lotes.
- Gera `index.html` e `radar-leiloes.html`.
- Publica `status_atualizacao.json` e `status_atualizacao.txt`.
- Faz commit automatico dos arquivos atualizados.

## Como conferir se atualizou

Depois que a acao rodar com sucesso, abra:

```text
https://gmaquina1.github.io/radar/status_atualizacao.json
```

Veja estes campos:

```json
{
  "status": "ok",
  "ultima_execucao": "...",
  "eventos_futuros": 420,
  "lotes": 3107
}
```

Tambem veja no site principal se o campo `Atualizado em` mudou.

## Arquivo de emergencia

Tambem existe uma copia visivel chamada:

```text
WORKFLOW_ATUALIZAR_RADAR.yml
```

Ela serve apenas para conferencia. O GitHub Actions so funciona quando o arquivo estiver exatamente em:

```text
.github/workflows/atualizar-radar.yml
```
