# Parâmetros de penalidade para o módulo de impacto

Registro de 11/11/2026. Os parâmetros foram extraídos pelo pipeline do Athenix com
`scripts/extrair_parametros.py`, sem nenhum valor de memória. Cada linha traz o dispositivo, o
trecho literal e o estado da âncora. **verificada** quer dizer que o trecho existe na segunda
leitura independente do PDF (pypdfium2).

**Isto não é parecer jurídico.** O documento não foi revisado por especialista.

## Decisões do fundador (11/11/2026)

- **D4, resolvida:** redação riscada no PDF fica fora da interpretação e do cálculo. A extração marca
  os dispositivos revogados (risco em ≥ 90% do texto) ou com risco parcial; os dois ficam com âncora
  pendente e não geram obrigação. Na REN 846: 12 revogados, 0 parciais (`tests/test_redacao_revogada.py`).
- **D5:** não decidida. O módulo calcula e mostra os dois cenários ("com teto" e "sem teto"),
  marcados como "depende de interpretação".
- **D1:** dúvida para especialista. A tela mostra as duas leituras do inciso XXIII, com a vigência de
  cada uma.
- **D2 e D3:** alertas de inconsistência da fonte (D2 já aparece na tela de impacto; D3 entra na demo).
- **Fonte:** PDFs do Leis.org (fonte secundária), aviso visível na tela e no relatório; fora do
  repositório público até confirmar os termos de uso.
- **REN 1.162, Despacho 1.293 e norma de Parcela Variável:** seguem como "não estimável".

Os parâmetros usados pelo módulo estão em `athenix/data/penalidades_ren846.json` (ver `docs/impacto.md`).

## Fontes

Os hashes e a proveniência estão em `tests/fontes_impacto/fontes.json`, conferidos por
`tests/test_ren846.py`.

| Ato | Arquivo | SHA-256 (12) | Vigência declarada |
| --- | --- | --- | --- |
| REN 846/2019, texto compilado | `tests/fontes_impacto/ren2019846_compilada.pdf` | d8b6fae9322f | Art. 49 |
| RN 1.137/2025 | `tests/norma_poc/ren20251137.pdf` | 4a581592e981 | publicação (Art. 21; DOU 30.10.2025) |
| REN 1.148/2026 | `tests/fontes_impacto/ren20261148.pdf` | 00f8c4a41605 | **1º/1/2027** (Art. 10) |
| REN 1.174/2026, texto compilado | `tests/fontes_impacto/ren20261174.pdf` | a2f89f9e431e | publicação, salvo exceções (Art. 18; DOU 04.11.2026) |

**Ressalva de origem.** O rodapé de todas as páginas diz "Leis.org/aneel – … Gerado em". São
compilações de terceiro, não o PDF publicado pela ANEEL. Até conferir com a ANEEL ou o DOU, valem
como fonte secundária.

**Não fornecidos:**

- REN 1.162/2026, que altera os arts. 9º, 10 e o § 11 do art. 21, segundo o compilado.
- Despacho 1.293/2026.
- A norma de Parcela Variável (PVI/PVRO).

## Parâmetros da REN 846 compilada

| # | Parâmetro | Dispositivo | Trecho literal | Âncora |
| --- | --- | --- | --- | --- |
| P1 | Limite do Grupo I | Art. 8º, I | "I - Grupo I: até 0,125% (cento e vinte e cinco milésimos por cento);" | verificada |
| P2 | Limite do Grupo II | Art. 8º, II | "II - Grupo II: até 0,25% (vinte e cinco centésimos por cento);" | verificada |
| P3 | Limite do Grupo III | Art. 8º, III | "III - Grupo III: até 0,5% (cinco décimos por cento);" | verificada |
| P4 | Limite do Grupo IV | Art. 8º, IV | "IV - Grupo IV: até 1% (um por cento); e" | verificada |
| P5 | Limite do Grupo V | Art. 8º, V | "V - Grupo V: até 2% (dois por cento)." | verificada |
| P6 | Os percentuais incidem sobre a base do art. 21 | Art. 8º, caput | "…a que correspondem os seguintes limites percentuais incidentes sobre a base de cálculo estabelecida no art. 21:" | verificada¹ |
| P7 | Teto legal por infração (externo à REN 846) | Art. 7º | "observado o limite, por infração, estabelecido na legislação." | verificada¹ · **valor não estimável** (a lei não está no repositório) |
| P8 | Multa não repassável à tarifa | Art. 7º, parágrafo único | "É vedado o repasse tarifário ou orçamentário do valor relativo à penalidade de multa." | verificada |
| P9 | Base de cálculo | Art. 21, caput | "…será o valor da Receita Operacional Líquida - ROL ou o valor estimado da energia produzida nos casos de autoprodução e produção independente, ambos correspondentes aos doze meses anteriores à lavratura do Auto de Infração - AI." | verificada¹ ² |
| P10 | Base de transmissora fora de operação | Art. 21, § 3º | "No caso de agente de transmissão que não esteja em operação, a base de cálculo será a Receita Anual Permitida - RAP vigente na data da lavratura do AI." | verificada |
| P11 | Base restrita ao segmento da infração | Art. 21, § 6º | "…a base de cálculo será a referente ao segmento no qual foi identificada a infração, desde que essa possa ser associada a apenas um dos segmentos." | verificada |
| P12 | Advertência no lugar da multa (piso zero) | Art. 6º | "…penalidade de advertência, nas infrações passíveis de multa e enquadradas nos arts. 9º a 13, quando não houver reincidência específica, conforme definido no art. 23, e a infração for de baixa ofensividade." | verificada¹ |
| P13 | Ordem do cálculo | Art. 22, § 1º | "A multa será calculada a partir do seu valor base, ao qual serão acrescidos os percentuais de agravantes, sendo posteriormente reduzidos os percentuais de atenuantes." | verificada |
| P14 | Valor base por metodologia própria (pisos e tetos) | Art. 22, §§ 2º e 6º | "…podendo ser adotados pisos e tetos." · "A ANEEL poderá afastar, excepcionalmente e de modo fundamentado, a aplicação de metodologia para o cálculo do valor base da multa, quando existente…" | verificada · **metodologia não estimável** (não está no repositório) |
| P15 | Agravante por reincidência | Art. 23, I | "40% (quarenta por cento) para cada caso de reincidência específica, até o limite de 120% (cento e vinte por cento);" | verificada |
| P16 | Agravante por Termo de Notificação não atendido | Art. 23, II | "de até 15% (quinze por cento), para cada caso em que a Autuada tenha deixado de atender, no prazo, as determinações constantes no Termo de Notificação; e" | verificada |
| P17 | Agravante por antecedentes | Art. 23, III, a)–e) | "de 1% a 5% (um a cinco por cento) para cada caso de antecedente de penalidade irrecorrível, até o limite de 50% (cinquenta por cento)". Escala: 5% se o somatório for ≥ 2%; 4% se ≥ 1% e < 2%; 3% se ≥ 0,25% e < 1%; 2% se ≥ 0,01% e < 0,25%; 1% se < 0,01%, tudo da base de cálculo | verificada |
| P18 | Definições de antecedente e reincidência | Art. 23, § 1º, I e II | "nos últimos quatro anos anteriores à lavratura do AI" · "repetição, em até dois anos, de falta enquadrada no mesmo tipo infracional" | verificada |
| P19 | Agravantes somam | Art. 23, § 2º | "…deverão ser somados os percentuais relativos a cada fator." | verificada |
| P20 | Atenuante: cessação espontânea | Art. 24, I | "95% (noventa e cinco por cento), no caso de cessação espontânea da infração e reparação total do dano…, previamente à comunicação formal…" | verificada |
| P21 | Atenuante: cessação até o prazo do TN | Art. 24, II | "50% (cinquenta por cento), no caso de cessação da infração e reparação total do dano… até o fim do prazo estabelecido para manifestação ao TN." | verificada |
| P22 | Atenuantes não se acumulam | Art. 24, caput | "…serão deduzidos os percentuais abaixo, de forma não cumulativa…" | verificada¹ |
| P23 | Multa diária por obrigação de fazer ou não fazer | Art. 15, § 2º | "…multa diária, conforme o porte do agente setorial ou a natureza da entidade, a ser definida no ato que estabelece a obrigação e aplicada no máximo por trinta dias e limitada a 2% (dois por cento) da base de cálculo a que se refere o art. 21." | verificada |
| P24 | Multa diária por embargo ou interdição | Art. 16, § 1º | "…implicará multa diária, nas condições estabelecidas no art. 15." | verificada³ |
| P25 | Prazo de pagamento | Art. 38, caput | "O pagamento da multa deve ser efetuado no prazo de vinte dias…" | verificada¹ |
| P26 | Redução por renúncia ao recurso | Art. 38, § 2º (redação da REN 949/2021) | "O infrator que renunciar expressamente ao direito de interpor recurso, no prazo de dez dias, nos termos do caput do art. 36, fará jus ao fator de redução de 25% (vinte e cinco por cento)…" | verificada⁴ |
| P27 | Encargos de atraso (fora da REN 846) | Art. 40, II | "o acréscimo de correção, juros e multa de mora, calculados nos termos e na forma da legislação aplicável aos tributos federais" | verificada · **valor não estimável** |
| P28 | Parcelamento | Art. 41, caput e § 3º | "…em até trinta e seis parcelas mensais… não podendo cada parcela ser inferior a R$ 10.000,00 (dez mil reais)." · "superior a doze, a primeira parcela deverá representar 20% (vinte por cento) do débito." | verificada |
| P29 | Barragens: grupos | Art. 45-G, I e II | "Grupo I: até 1% (um por cento);" · "Grupo II: até 2% (dois por cento);" | verificada |
| P30 | Barragens: multa diária | Art. 45-J, § 4º | "…multa diária correspondente a 2% do valor teto estabelecido…" | verificada |

**Notas da tabela:**

1. O texto foi confirmado pela segunda leitura, mas o selo "Art. N" não. Nesse layout, o pypdfium2 lê o
   selo fora do lugar. O rótulo do artigo vem só do extrator.
2. O rodapé da página interrompe o caput ("concessionários, […] permissionários"). A citação foi feita
   em dois pedaços contíguos, cada um verificado.
3. Antes da correção desta etapa, o pipeline citava este parágrafo como "Art. 8º, § 1º", porque a
   remissão "art. 8º da Lei nº 9.074" no início da linha virava artigo. Foi corrigido, e há teste de
   regressão.
4. O compilado traz as duas redações do § 2º. A antiga aparece riscada na página. A extração de texto
   lê as duas como vigentes; ver D4.

## Enquadramento explícito das infrações ligadas à demo

| Infração (texto da norma) | Dispositivo da REN 846 | Grupo e teto | Origem |
| --- | --- | --- | --- |
| Deixar de prestar informações sobre interrupções aos consumidores | Art. 11, XXIII | III, 0,5% | RN 1.137/2025, Art. 9º |
| Ausência, inadequação ou descumprimento do Plano de Contingência | Art. 12, XXVI | IV, 1% | RN 1.137/2025, Art. 9º |
| Ausência, inadequação ou descumprimento do Plano de Manejo Vegetal | Art. 12, XXVII | IV, 1% | RN 1.137/2025, Art. 9º |
| Comunicar-se de forma ineficiente com o Poder Público em Situações de Emergência | Art. 12, XXVIII | IV, 1% | RN 1.137/2025, Art. 9º |
| Atuar de forma inadequada no restabelecimento (distribuição) | Art. 13, XIX | V, 2% | RN 1.137/2025, Art. 9º |
| Atuar de forma inadequada no retorno à disponibilidade (transmissão) | Art. 13, XX | V, 2% | RN 1.137/2025, Art. 9º |
| Deixar a Função Transmissão indisponível além dos limites de PVI/PVRO | Art. 13, XIII | V, 2% | original; os limites estão na norma de PV, que não foi fornecida |
| Atrasar ou dificultar a opção de migração do consumidor | Art. 11, XXIV | III, 0,5% | REN 1.174/2026, Art. 10 |

O texto dessas infrações vem do compilado e é verificado. Para as demais obrigações, a norma diz
apenas "sujeita às penalidades da REN 846", sem indicar o grupo. É o caso da REN 1.174, art. 172-B
(REN 1.000) e art. 9º-A, § 2º (REN 1.011). Nesses casos, o grupo será uma premissa editável, com
confiança baixa.

## O que cada alteração mudou

| Ato | O que muda na REN 846 | Muda limites, base ou dosimetria? | O compilado reflete? |
| --- | --- | --- | --- |
| RN 1.137/2025, Art. 9º | Acrescenta Art. 11, XXIII; Art. 12, XXVI–XXVIII; Art. 13, XIX–XX | Não | **Sim**: os 6 incisos são literalmente iguais (comparação automática, sem espaços e marcas de redação) |
| REN 1.174/2026, Art. 10 | Acrescenta Art. 11, XXIV | Não | **Sim**: literalmente igual |
| REN 1.174/2026, art. 172-B (REN 1.000) e art. 9º-A (REN 1.011) | Novas condutas "sujeitas às penalidades" da REN 846, sem grupo | Não | Não se aplica: estão em outras normas. O art. 9º-A produz efeitos em 180 dias (Art. 18, I, a) |
| REN 1.148/2026, Art. 8º | Dá nova redação ao **Art. 11, XXIII** (respostas no SGO/ANEEL) | Não | **Não**: ver D1 |
| REN 1.148/2026, Arts. 5º e 6º | Indicadores IASC, ICA e IS e o ISFP entram no Fator X (PRORET 2.5 e 2.5-A, v5.0 e v4.0) | Não muda a multa; é consequência de **receita** da distribuidora | Os anexos com as fórmulas do Fator X não estão no arquivo: **não estimável** |
| REN 1.162/2026 | Segundo o compilado: Art. 9º, IV e VII; Art. 10, VII, XII e XIX; Art. 21, § 11 (armazenamento) | Só a base de armazenamento (§ 11) | Não confirmável: arquivo não fornecido |

## Divergências encontradas (não resolvidas)

- **D1 – Inciso XXIII do Art. 11 com dois conteúdos.**
  - A RN 1.137/2025 criou o XXIII: "deixar de prestar informações decorrentes de interrupções…",
    vigente desde a publicação.
  - A REN 1.148/2026 dá ao mesmo XXIII outro texto: "deixar de responder ou responder de forma não
    conclusiva as demandas relacionadas ao Sistema de Gestão de Ouvidoria…", vigente a partir de
    1º/1/2027.
  - O compilado mostra só a redação da 1.137, embora liste a 1.148 entre os atos que alteram a REN 846.
  - Não está claro se, a partir de 2027, a 1.148 substitui o inciso da 1.137 ou se houve colisão de
    numeração. Não escolhi uma versão. As duas condutas ficam no Grupo III (0,5%).
- **D2 – Algarismo diferente do extenso.** No Art. 45-I, § 4º: "Será acrescido o valor de 25% (cinco
  por cento) para cada antecedente…". O conferidor automático marcou a divergência. Não uso nenhum dos
  dois valores sem decisão humana. Esse parágrafo vale só para barragens.
- **D3 – Data citada de forma diferente dentro da própria RN 1.137.** A ementa cita a "REN nº 948, de
  16 de novembro de 2021"; o Art. 1º cita a "nº 948, de 21 de novembro de 2021". Não afeta a multa.
  Entra no alerta de inconsistência da fonte (item 12).
- **D4 – Redações revogadas aparecem como texto válido** (resolvida; ver acima).
  - No compilado, as redações antigas estão riscadas: Art. 21, §§ 8º e 9º; Art. 38, § 2º; Art. 11, X;
    Art. 9º, IV e VII; Art. 10, VII, XII e XIX.
  - O texto extraído não guarda o risco. O pipeline cita as duas redações e as duas são "verificadas",
    porque ambas existem no PDF.
  - O script já detecta as linhas de risco pelo pdfplumber: 1.625 caracteres. Mas só em nível de
    dispositivo, com falsos positivos quando a redação nova começa igual à antiga.
  - A correção de verdade é marcar o caractere riscado na extração. Proponho incluí-la antes do módulo.
- **D5 – A dosimetria pode passar do teto do grupo?** O Art. 8º fixa "limites percentuais", e o
  Art. 23 acresce agravantes ao "valor base". Nada do que foi extraído diz se o resultado final
  continua limitado ao teto do grupo. Fica como premissa a decidir por especialista.

## Consequências para o módulo de impacto

- **Faixa da multa:**
  - Mínimo de 0, por advertência (P12) ou atenuante de 95% (P20).
  - Máximo igual ao teto do grupo × a base do Art. 21.
  - O "provável" depende da metodologia de valor base (P14), que não está no repositório. Proponho
    deixá-lo como premissa editável, sem número próprio.
- **Sem a ROL ou a RAP da empresa,** o resultado sai só em percentual da base, e o sistema pede o
  valor.
- **Transmissoras:** a perda de receita por Parcela Variável é consequência separada da multa e fica
  **não estimável** até a norma de PV entrar no repositório.
- **Redução de receita da distribuidora pelo Fator X** (REN 1.148, a partir de 2027): **não
  estimável**, porque faltam os anexos do PRORET.
