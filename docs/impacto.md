# Módulo de impacto e prioridade

Registro de 11/11/2026. Estima a consequência financeira de cada obrigação e sugere uma ordem de
ação. **Estimativa com base nas premissas listadas, não constitui parecer jurídico.**

## Como usar

1. Envie a norma (ex.: `tests/norma_poc/ren20251137.pdf`) em **Documentos** e execute a extração
   por regras.
2. Abra **Impacto** (`/impacto`). Preencha o perfil (segmento, base de cálculo, agravantes,
   atenuante, valor base) e clique em **Recalcular**. Em cada obrigação dá para escolher o grupo
   de multa (premissa).
3. **Exportar relatório** gera o HTML com as mesmas premissas (`/impacto/relatorio?…&download=1`
   baixa um arquivo autocontido; para PDF, imprima pelo navegador).

Funciona sem IA e sem chave de API.

## De onde vem cada número

| Origem | O que fornece |
| --- | --- |
| `athenix/data/penalidades_ren846.json` | 30 parâmetros da REN 846 (limites dos grupos, base, agravantes, atenuantes), 113 infrações tipificadas (arts. 9º–13) com grupo, as duas leituras do Art. 11, XXIII (D1), as alterações da régua e os alertas da fonte. Cada item tem dispositivo, trecho literal, estado da âncora e hash do PDF de origem. |
| Usuário | Segmento, base de cálculo (ROL ou RAP), número de reincidências, TN não atendidos e antecedentes, soma das multas anteriores, atenuante esperada, valor base como % do teto e grupo de cada obrigação. |

O arquivo de parâmetros é gerado por `scripts/extrair_parametros.py` (pipeline do Athenix sobre os
PDFs de `tests/fontes_impacto/`). Percentuais são lidos do trecho citado, nunca digitados. Um
parâmetro só entra no cálculo com âncora **verificada** (segunda leitura do PDF) e redação **não
revogada** (sem risco no PDF compilado); caso contrário a faixa fica "não estimável".

Os PDFs do Leis.org não estão no repositório público (termos de uso em confirmação). Sem eles, o app e
os testes usam o arquivo de parâmetros versionado; só a regeneração e os testes sobre o PDF real são
pulados.

## Regras de cálculo

- **Consequência** (regra determinística, com o motivo na tela): dever → *penalidade/multa*
  (Art. 5º); verbo de implantação → *custo de adequação*; Parcela Variável, RAP ou Fator X →
  *perda de receita*; informar, registrar, publicar → *risco de fiscalização*; faculdade → *sem
  consequência financeira identificável*.
- **Enquadramento:** grupo escolhido pelo usuário; senão, infração da REN 846 cujos instrumentos
  nomeados ("Plano de Contingência", "Poder Público" + "Situações de Emergência"…) aparecem todos no
  texto da obrigação; senão, todos os grupos (I a V). A ANEEL decide o enquadramento.
- **Faixa** (% da base do Art. 21; em R$ só se a base for informada — nunca estimada):
  - mínimo **0** (advertência do Art. 6º ou atenuante do Art. 24; metodologia do valor base fora do
    repositório);
  - máximo = teto do grupo, sem atenuante, em **dois cenários** (D5): "com teto" (resultado após
    agravantes limitado ao teto do grupo) e "sem teto" (teto × (1 + agravantes));
  - provável só com valor base informado e grupo único: valor base + agravantes (Art. 23, somados)
    − atenuante (Art. 24), nos dois cenários.
- **Prazo:** vencido → exposição atual; aberto → dias restantes; recorrente ou sem data → dito.
- **Prioridade:** vencidas, depois as que vencem em até 90 dias, depois as demais e por fim as sem
  data; dentro de cada faixa, maior exposição (provável, se houver; senão máxima), no cenário sem
  teto. A frase de decisão diz o peso e o prazo.
- **Confiança:** *alto* só com base, grupo escolhido pelo usuário e valor base informados; *médio*
  com base informada e uma premissa faltando, ou grupo só por coincidência de termos; *baixo* nos
  demais casos (inclui o perfil vazio e obrigação sem citação verificada).
- **Aplicabilidade:** obrigação cujo sujeito é de outro segmento fica fora da prioridade, com o motivo.

## Alertas na tela e no relatório

- Norma analisada que altera a REN 846 (ex.: RN 1.137, Art. 9º), com link ao dispositivo.
- D1: Art. 11, XXIII com duas redações (RN 1.137, vigente desde 30/10/2025; REN 1.148, desde
  01/01/2027). Dúvida para especialista.
- D5: os dois cenários de teto.
- Inconsistência da fonte: Art. 45-I, § 4º ("25% (cinco por cento)").
- Fonte secundária (Leis.org) visível no topo.

## Não estimável

Metodologia do valor base; teto legal externo (Art. 7º); Parcela Variável de transmissoras (norma
ausente); Fator X da distribuidora (anexos da REN 1.148 ausentes); REN 1.162/2026 e Despacho
1.293/2026 (ausentes); custo de adequação (dado interno da empresa).

## Limites conhecidos

- Enquadramento por coincidência de termos é indício, não decisão: instrumentos citados com outra
  grafia ou plural em "-ões" não casam (`shortcut` em `impacto._singular`).
- Classificação por verbos e termos: pode marcar custo de adequação ou fiscalização onde não há.
- Prazos herdam as limitações do `temporal` (datas provisórias, calculadas da publicação).
- Antecedentes sem soma informada usam a faixa máxima (5% cada), dito na premissa.
