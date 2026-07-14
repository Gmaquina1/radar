# Como colocar o Radar Premium no GitHub

## Antes de começar

Não envie o arquivo ZIP fechado. Primeiro extraia o pacote no computador.

## Envio dos arquivos

1. Abra https://github.com/gmaquina1/radar
2. Clique em **Add file**.
3. Clique em **Upload files**.
4. Abra a pasta extraída do pacote.
5. Selecione tudo que está dentro dela.
6. Confirme que as pastas `.github` e `assets` também foram selecionadas.
7. Arraste os arquivos para a tela do GitHub.
8. Aguarde o envio terminar.
9. Em **Commit changes**, escreva: `Instalar Radar Premium`.
10. Clique no botão verde **Commit changes**.

Os arquivos com o mesmo nome, como `index.html`, serão substituídos.

## Executar a primeira atualização

1. Abra a aba **Actions** do repositório.
2. Abra **Atualizar Radar diariamente as 16h**.
3. Clique em **Run workflow**.
4. Confirme novamente em **Run workflow**.
5. Aguarde o processo ficar verde. A leitura completa pode demorar porque o sistema visita os leiloeiros e lê editais.

## Ver o site

Abra https://gmaquina1.github.io/radar/

Se ainda aparecer a página antiga, pressione `Ctrl + F5` ou abra em uma janela anônima.

## Horário automático

O GitHub executará a atualização diariamente às 16h de Brasília. O GitHub pode iniciar alguns minutos depois do horário em dias de maior movimento.

## Importante

O Radar mostra somente eventos com data futura ou horário de hoje ainda não iniciado. Quando um edital é encontrado e lido, o resultado correspondente apresenta o botão **Abrir edital completo**.
