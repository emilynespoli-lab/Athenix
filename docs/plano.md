# Plano de desenvolvimento e verificação

As etapas organizam a evolução do produto. Os resultados executados estão no [registro de execução](execucao.md); esta tabela define critérios de verificação, sem declarar conclusão automática.

| Etapa | Entrega operacional | Critério de verificação |
| --- | --- | --- |
| E0 | Autenticação, persistência versionada e trilha | Escrita anônima recusada; migrações em banco descartável; integridade da trilha testada. |
| E1 | Upload PDF/HTML, arquivo preservado e estrutura | Identificação por conteúdo; SHA-256; reenvio idempotente; recortes conferem com o texto; avisos de extração visíveis. |
| E2 | Candidatos, evidências, prazos e contestações | Fluxo local sem IA; citação alterada recusada; referência ambígua pendente; evento sem marco não produz data final. |
| E3 | Revisão técnica e correções | Identidade e justificativa registradas; evidência inválida impede aceite; correção preserva versões; comandos obsoletos recusados. |
| E4 | IA, custos, fila, cache e reprodução | Contratos simulados para respostas parciais e falhas; idempotência concorrente; resposta bruta registrada; testes sem chamadas pagas. |
| E5 | Matriz, riscos, timeline e exportações | Indicadores derivados dos dados; ausências e avisos visíveis; CSV protegido contra fórmulas; acesso ao trecho de evidência. |
| E6 | Corpus oficial e avaliação | Origem e hash registrados; revisão das estruturas e prazos; avaliação humana adicional; cenários reais documentados. |

## Fluxo principal

Entrar com conta técnica, enviar documento com origem e papel documental, preservar o arquivo, estruturar o texto, gerar candidatos, verificar os trechos, aceitar ou rejeitar e consultar a trilha. A IA acrescenta propostas a esse fluxo; a verificação determinística e a decisão humana continuam separadas.

## Testes e evidências

A suíte exercita recortes Unicode, normalização limitada, alterações citadas, marcos temporais, autorização, concorrência, correção com histórico e detecção de adulteração. Os testes usam bancos descartáveis e transportes simulados para IA. Resultados JUnit, hashes do código e verificações de navegador ficam em `artifacts/`.

Casos sintéticos, execução com documento público e ensaios de navegador têm escopos distintos. A contagem de testes não mede, por si só, a cobertura dos requisitos. Casos pendentes permanecem explícitos no registro de execução.

SQLite local não substitui a validação em PostgreSQL. Docker, chamadas reais ao provedor e avaliação jurídica precisam de verificações próprias. A revisão por outra pessoa deve ser registrada quando ocorrer; o implementador não a substitui.
