# Matriz de rastreabilidade

Catálogo de capacidades e verificações do produto. As etapas constam no [plano](plano.md). M = essencial ao MVP, D = desejável, P = evolução posterior. As referências apontam para módulos e testes relevantes; não representam conclusão integral de cada requisito. Resultados e limitações estão no [registro de execução](execucao.md).

| Requisito | Prioridade / etapa | Capacidade e referência técnica |
| --- | --- | --- |
| RF-01 | M / E1 | PDF/HTML por conteúdo e limites: `athenix/structure.py`, `tests/test_migrations_pdf.py`. |
| RF-02 | M / E1 | Origem documental obrigatória: `athenix/services.py`, `tests/test_workflow.py`. |
| RF-03 | M / E1 | SHA-256 e bytes preservados: `athenix/db.py`, `athenix/services.py`. |
| RF-04 | M / E1 | Reenvio idempotente por hash: `tests/test_workflow.py`. |
| RF-05 | D / E1 | Identidade textual separada da identidade do arquivo: avaliação integral pendente. |
| RF-06 | M / E1 | Papel documental explícito: `athenix/structure.py`, `tests/test_faq.py`. |
| RF-07 | M / E1 | Unidades, intervalos e páginas: `tests/test_structure_temporal.py`, `tests/test_migrations_pdf.py`. |
| RF-08 | M / E1 | Alterações citadas e ato-alvo: `athenix/structure.py`, `tests/test_structure_temporal.py`. |
| RF-09 | M / E1 | Avisos para tabelas e fórmulas com extração limitada: `athenix/structure.py`. |
| RF-10 | M / E1 | Referências explícitas ou pendentes: `athenix/structure.py`, `athenix/proposals.py`. |
| RF-11 | M / E1 | Inventário de anexos e dependências: `tests/test_supplements.py`. |
| RF-12 | M / E1 | Datas com trecho de prova: `athenix/temporal.py`, `tests/test_structure_temporal.py`. |
| RF-13 | D / posterior | Comparação textual e de layout entre versões: pendente. |
| RF-14 | M / E2,E4 | Candidatos com evidências: `athenix/proposals.py`, `tests/test_proposals_ai.py`. |
| RF-15 | M / E2,E4 | Validação individual das propostas: `tests/test_proposals_ai.py`. |
| RF-16 | M / E4 | Resposta bruta e reprocessamento: `athenix/llm.py`, `athenix/reproduction.py`. |
| RF-17 | M / E2 | Geração por regras sem provedor: `athenix/proposals.py`, `tests/test_workflow.py`. |
| RF-18 | D / E4 | Múltiplas rodadas e comparação de divergências: pendente. |
| RF-19 | M / E2 | Candidatos semelhantes sinalizados sem fusão silenciosa: `athenix/proposals.py`. |
| RF-20 | M / E2 | Aviso sobre papel de FAQ: `tests/test_faq.py`. |
| RF-21 | M / E2 | Verificação literal com normalização limitada: `athenix/evidence.py`, `tests/test_evidence.py`. |
| RF-22 | M / E2 | Motor temporal determinístico: `athenix/temporal.py`, `tests/test_structure_temporal.py`. |
| RF-23 | M / E2 | Marcos explícitos e eventos: `tests/test_structure_temporal.py`. |
| RF-24 | M / E2 | Evidência local e contexto do caput: `athenix/temporal.py`. |
| RF-25 | M / E2 | FAQ depende da norma-alvo para prazo normativo: `tests/test_faq.py`. |
| RF-26 | M / E2,E3 | Cálculo provisório e confirmação humana separados: `athenix/temporal.py`, `athenix/services.py`. |
| RF-27 | D / posterior | Calendário de dias úteis com fonte e versão: pendente; ausência de calendário impede cálculo correspondente. |
| RF-28 | M / E2 | Contestações com motivos e gravidade: `athenix/proposals.py`. |
| RF-29 | M / E2,E3 | Evidência e resolução de contestações: `tests/test_review_guards.py`. |
| RF-30 | M / E3 | Estados e níveis de revisão distintos: `athenix/services.py`. |
| RF-31 | M / E3 | Identidade da sessão e justificativa: `athenix/auth.py`, `tests/test_review_guards.py`. |
| RF-32 | M / E3 | Travas de aceite: `tests/test_review_guards.py`. |
| RF-33 | M / E3 | Correção com versões e histórico: `tests/test_review_guards.py`, `tests/test_workflow.py`. |
| RF-34 | D / E3 | Duração declarada da revisão: pendente; não há medição de ganho. |
| RF-35 | M / E5 | Matriz, filtros e realce: `athenix/app.py`, `scripts/browser_qa.py`. |
| RF-36 | M / E5 | Indicadores de risco com denominadores: `athenix/services.py`, `athenix/app.py`. |
| RF-37 | M / E5 | Timeline com estados distintos: `athenix/app.py`, `athenix/templates/page.html`. |
| RF-38 | M / E5 | Avisos e documentos ausentes: `tests/test_supplements.py`. |
| RF-39 | M parcial / E5 | CSV/JSON/HTML: `athenix/app.py`, `tests/test_workflow.py`; XLSX pendente. |
| RF-40 | P | Conectores automáticos autorizados: pendentes; aquisição pública pontual não equivale a conector. |
| RF-41 | P | Estados completos de falha de fontes remotas: pendentes. |
| RF-42 | P | Reconciliação e saúde de conectores: pendentes. |

| Requisito | Restrição e verificação |
| --- | --- |
| RNF-01 | Fluxo sem chave de IA: `tests/test_workflow.py`. |
| RNF-02 | Acesso ao trecho e à cadeia documental: `scripts/browser_qa.py`; avaliação ampla de usabilidade pendente. |
| RNF-03 | Histórico e integridade da trilha: `athenix/db.py`, `tests/test_review_guards.py`. |
| RNF-04 | Reprodução com hashes e versões: `athenix/reproduction.py`, `tests/test_reproduction.py`. |
| RNF-05 | Estimativa, teto e reserva de custo: `athenix/llm.py`, `tests/test_proposals_ai.py`. |
| RNF-06 | Registro de modelo, uso e latência: `athenix/llm.py`; validação com provedor real pendente. |
| RNF-07 | Documentos e respostas tratados como entrada não confiável: `tests/test_proposals_ai.py`, `tests/test_workflow.py`. |
| RNF-08 | Segredos em ambiente e senhas com hash: `athenix/auth.py`, `scripts/check_secrets.py`. |
| RNF-09 | Autenticação e proteção de escrita: `athenix/auth.py`, `tests/test_workflow.py`. |
| RNF-10 | Desempenho em corpus representativo: avaliação pendente. |
| RNF-11 | Teclado, contraste e estados claros: auditoria completa de acessibilidade pendente. |
| RNF-12 | Métricas com escopo e denominador: `artifacts/verification.json`, `docs/execucao.md`. |
| RNF-13 | Portabilidade: migrações e configuração disponíveis; PostgreSQL/Docker precisam de execução própria. |
| RNF-14 | Testabilidade sem chamadas pagas: `tests/conftest.py`, `tests/test_proposals_ai.py`. |

## Verificações transversais

Os testes devem distinguir falhas de rede, resposta inválida, interpretação pendente e documento ausente. Falha de aquisição não demonstra ausência de obrigação. Reprodução, autenticação, limites de custo e conservação de evidências devem permanecer verificáveis a cada alteração relevante.

O registro de execução separa testes sintéticos, exercício com fonte pública, ensaio de navegador e verificações pendentes. Aprovação jurídica e validação comercial exigem evidências próprias.
