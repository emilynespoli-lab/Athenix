# Avaliação da interpretação contra gabarito

Registro de 10/11/2026. Mede o pipeline determinístico (sem IA) em dispositivos anotados; não é
parecer jurídico nem medida de precisão global.

## Conjunto

`tests/gabarito/`: 20 casos em 3 atos de tipos e formatos diferentes (proveniência e hashes em
`fontes.json`):

| Ato | Tipo / formato | Afeta | Casos |
| --- | --- | --- | --- |
| RN ANEEL 1.137/2025 | resolução normativa, PDF compilado | distribuidoras, transmissoras | 9 |
| REH ANEEL 3.348/2024 | resolução homologatória, PDF (cópia secundária, ver ressalva) | transmissoras, ONS | 5 |
| Decreto 12.068/2024 | decreto federal, HTML windows-1252 | distribuidoras, ANEEL | 6 |

Cada caso tem um `trecho` literal e o esperado para obrigação (modalidade e sujeito), não obrigação,
prazo (quantidade, unidade, marco e data), autoria (norma dona do bloco), vigência, revogação e
remissão. **O gabarito foi elaborado por IA a partir do texto e ainda não foi revisado por especialista**
(`revisado_por_humano: false`). `tests/test_gabarito.py` garante que todo trecho existe uma única vez
na fonte, extraída sem o segmentador do sistema.

## Executar

```powershell
.\.venv\Scripts\python.exe scripts/avaliar.py --rotulo atual   # ~1 min; grava artifacts/avaliacao/atual.{json,md}
```

## Métricas

- **Acertos por verificação**: o item do sistema cobre o trecho (por qualquer âncora verificada) e o campo bate.
- **Citações corretas**: proporção de itens cujo texto literal existe na fonte real. Pega texto
  corrompido que o sistema "verifica" contra a própria extração.
- **Falsas verificadas**: âncoras que o sistema marcou como verificadas, mas cujo trecho não existe
  na fonte lida por outro motor. Tem de ser zero.
- **Sem fonte**: itens sem âncora verificada.
- Precisão é **local** (só os dispositivos anotados), não global.
- Referência da fonte: PDF pelo pypdfium2 (o extrator usa pdfplumber); HTML pelo HTMLParser da
  biblioteca padrão com a codificação conferida à mão. A comparação ignora espaços. Até a versão
  `fase2` a referência de PDF era o próprio pdfplumber, o que tornava as citações de PDF circulares.

## Versões do parser

| Versão | Mudança | Casos corretos | Falsas verificadas (RN / REH / Decreto) | Citações na fonte (RN / REH / Decreto) |
| --- | --- | --- | --- | --- |
| `inicial` | código recebido | 6/20 | não medido com referência independente | 254/254 · 29/29 · 4/92 (método circular para PDF) |
| `fase2` | prazo "têm N dias", datas, aspas aninhadas, vigência | 11/20 | 3/364 · 1/31 · 124/128 | 256/259 · 28/29 · 4/92 |
| `item0` | decodificação HTML (BOM → cabeçalho → meta → UTF-8 → windows-1252), detector de mojibake, citação confirmada por segunda leitura | 13/20 | **0/360 · 0/30 · 0/160** | 256/258 · 29/29 · 126/126 |
| `etapa1` | prazos por extenso, publicação própria × outro evento, assinatura × publicação, prazo herdado sem duplicar, obrigação periódica, título encerra dispositivo, dever + permissão por frase, sujeito sem rótulo | 18/20 | 0/336 · 0/32 · 0/173 | 252/254 · 31/31 · 140/140 |

Em `etapa1`, na RN 1.137: prazos duplicados 12 → 0, sujeitos com rótulo ("132.", "a)") 135 → 0, penalidades 4 → 3 (as 3 restantes são "Constitui infração" da RN 846), prazos recorrentes 0 → 2. Decreto: sujeitos com rótulo 9 → 0.

Em `item0`, ficam pendentes (e não verificadas) 2 âncoras da RN (itens 23-G e 23-H, cuja unidade
engole uma tabela) e 1 da REH (fórmula). Mojibake no texto do Decreto: 634 → 0.

## Resultado

Linha de base medida numa cópia do código com as quatro correções desfeitas, com o mesmo avaliador.

| Verificação | Antes | Depois |
| --- | --- | --- |
| obrigação | 6/11 | 7/11 |
| prazo | 3/8 | 5/8 |
| autoria | 5/10 | 7/10 |
| vigência | 1/4 | 3/4 |
| revogação | 1/2 | 1/2 |
| não obrigação | 2/2 | 2/2 |
| remissão | 0/1 | 0/1 |
| **casos totalmente corretos** | **6/20** | **11/20** |
| citações corretas: RN / REH / Decreto | 254/254, 29/29, 4/92 | 259/259, 29/29, 4/92 |
| sem fonte | 0% | 0% |

Correções: "têm N dias para" como dever (RN 1.137, Art. 17); datas `30.10.2025`, `21.6.2024` e
`1º de julho de 2024`; aspas internas não encerram bloco citado, "(NR)" encerra; vigência "na data de
sua publicação" derivada só com data de publicação única e marcada `basis: publication`.

## Limites conhecidos

- Gabarito elaborado por IA, sem revisão de especialista; 20 casos não medem cobertura global.
- No HTML, a segunda leitura compartilha a decodificação com o extrator. A garantia vem do detector
  de mojibake (limiar fixo de 3 ocorrências), não de um segundo decodificador.
- Tabelas e fórmulas raramente são confirmadas por outro motor (ordem das células diverge): ficam
  pendentes. Texto de OCR não tem segunda leitura: fica pendente.
- Âncoras gravadas antes de `item0` não são reconferidas automaticamente; é preciso reprocessar.
- REH 3.348 vem de cópia secundária (ver `fontes.json`).

Itens da revisão técnica fora do escopo atual (decisão de 11/11/2026: priorizar o módulo de impacto):

1. **Identidade do arquivo**: SHA-256, assinatura `%PDF-` e limite de tamanho existem; falta marcar "apenas layout" por hash do texto normalizado e registrar falha de download.
2. **Extração**: offsets e avisos por página e motor registrado existem; falta NFC na extração e mapa de posição da normalização.
3. **Ruído de layout**: não tratado (sumário colado na ementa, "1. ......", rodapé web, hifenização, cabeçalho repetido, duas colunas, HTML que quebra linha em cada tag e separa "Art." do número).
4. **Estrutura**: "art. N" no início de linha vira artigo falso; ordinais 5o/5º/5°, validação de inciso romano, itens fora de anexos, caminhos duplicados e separação de epígrafe/ementa não tratados.
5. **Blocos de alteração**: aspas aninhadas e "(NR)" tratados; falta fechar no próximo artigo próprio ou título, norma-alvo só pelo caput ("INDETERMINADO") e marcas explícitas de inclusão/revogação.
6. **Tabelas**: marcador "Tabela N" existe; unidade anterior ainda engole a tabela seguinte (itens 23-G/23-H) e não há reconstrução de células.
7. **FAQ**: perguntas separadas e origem "esclarecimento" marcada; "Publicado em/Atualizado em" não capturados.
8. **Remissões**: nenhuma é resolvida; ato e dispositivo não são distinguidos.
11. **IA**: schema estrito, resposta bruta, cache, prompt versionado, estimativa e teto existem; nenhuma chamada real feita, divisão de ações e tratamento de truncamento não exercitados.
12. **Verificação**: estados verificada/pendente/inválida e mínimo de 16 caracteres existem; falta cobertura % do texto, versão do parser nos resultados e alerta de inconsistência da fonte (necessário para a demo, Etapa 3).

## Falhas restantes (causa raiz)

| Casos | Causa |
| --- | --- |
| G18 (Decreto) | HTML quebra linha em cada tag e separa "Art." do número (item 3): o Art. 22 não vira dispositivo próprio, então revogação e autoria falham. |
| G09 | Remissões nunca resolvidas (item 8); a divergência "20 de julho" × "20 de junho" do Decreto citado passa sem alerta (item 12). |
| — | Sujeito com oração relativa no Decreto ("…à concessionária, que"): o sujeito correto está contido, mas não isolado. |
