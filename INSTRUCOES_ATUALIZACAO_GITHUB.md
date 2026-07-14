# Instalacao no GitHub

## Forma recomendada

1. Extraia o ZIP completo.
2. No repositorio `gmaquina1/radar`, envie todos os arquivos e pastas, inclusive `.github`.
3. Confirme que existe `.github/workflows/atualizar-radar.yml`.
4. Abra `Actions > Atualizar Radar de Leiloes > Run workflow`.
5. Execute com `forcar_atualizacao = true`.
6. Aguarde o simbolo verde e abra `https://gmaquina1.github.io/radar/`.

## Se a aba Actions nao mostrar a automacao

O arquivo abaixo nao foi enviado ou foi salvo no lugar errado:

```text
.github/workflows/atualizar-radar.yml
```

O nome e o caminho devem ser exatamente esses. A pasta `.github` comeca com ponto.

## Se a atualizacao falhar

Abra a execucao vermelha na aba `Actions`, entre na etapa que falhou e copie a mensagem. O diagnostico publicado em `status_atualizacao.json` tambem mostra a ultima etapa executada.
