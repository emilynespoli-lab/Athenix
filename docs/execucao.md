# Evidências e estado da entrega

Registro de verificações da aplicação, atualizado em 05/11/2026.

## Implementado e exercitado

| Capacidade | Código / evidência |
| --- | --- |
| Recebimento PDF/HTML, origem, papel, hash e reenvio idempotente | `athenix/services.py`, `structure.py`; testes de upload, concorrência, PDF sintético, arquivo corrompido e igualdade de recortes |
| Originais imutáveis na mesma transação dos metadados | `athenix/db.py`; triggers para UPDATE/DELETE e testes de integridade |
| Estrutura, blocos citados, páginas, links, datas e avisos | `athenix/structure.py`; casos sintéticos novos, sem prova sobre a norma de referência |
| Regras, âncoras e normalização com mapeamento ao original | `proposals.py`, `evidence.py`; propriedade Unicode, alteração de palavras, outra unidade, ambiguidade e verificador independente |
| Prazos determinísticos, herança, esclarecimento e eventos | `temporal.py`; datas sintéticas, fim de mês, calendário ausente e marcos independentes |
| Contestações e faixas de incerteza | `proposals.py`; modalidades, definições, sujeitos, condições, exceções, dependências, agrupamento, quantidade e marco |
| Contestações humanas ancoradas e associação de dependências | `services.py`; trecho obrigatório; confirmação não controlada pelo cliente; obtido distinto de interpretado |
| Revisão técnica, travas, correção, resolução e confirmação de prazos | `auth.py`, `services.py`; identidade da sessão, justificativa, versões anteriores preservadas e concorrência otimista |
| API autenticada, CSRF, escape de HTML e CSV | `app.py`; testes HTTP e ensaio Chromium |
| Matriz, timeline, riscos, evidência realçada, histórico e exportação | templates e assets originais; capturas desktop/mobile e fluxo automatizado |
| Adaptador de IA, preço/teto, resposta bruta, cache, trava e reprodução | `llm.py`, `services.py`; apenas contratos com provedores falsos; nenhuma chamada real |
| Migrações aditivas e recuperação conservadora de jobs | Alembic 0001/0002; teste de igualdade de schema, downgrade recusado, pagamento interrompido não repetido |
| Trilha e artefato determinístico de execução | `db.py`, `reproduction.py`; encadeamento, adulteração plantada e conteúdo separado de metadados operacionais |

## Verificações registradas

O resultado final da suíte está em `artifacts/tests.xml`: 80 testes aprovados, sem falhas, erros ou testes ignorados. O resultado do navegador está em `artifacts/browser-qa.json`, com conjunto rotulado `synthetic_new`. O relatório final registra seis candidatos, nove âncoras verificadas conferidas (incluindo a nova versão após correção), zero falhas no recálculo, duas versões preservadas e nenhum erro JavaScript no roteiro. O encerramento do servidor e a remoção do banco temporário também passaram. Isso não mede precisão jurídica, recall nem desempenho da IA.

`artifacts/verification.json` consolida contagens do JUnit, ambiente e hashes dos arquivos de código com LF normalizado. A suíte emite um aviso de depreciação do cliente de testes Starlette/httpx; ele está registrado e não é falha da aplicação.

Capturas em `artifacts/dashboard-desktop.png`, `dashboard-mobile.png`, `matrix-desktop.png` e `evidence-desktop.png`. O QA do navegador usa banco descartável e não semeia o ambiente principal. O inventário de terceiros está em `terceiros.json`. Lint, formatação e verificação limitada de padrões de segredos são executados localmente; a ausência de padrões não é garantia de ausência de qualquer segredo.

O FAQ oficial foi obtido por HTTPS, após robots.txt HTTP 200 e permissão explícita de coleta para a URL. A origem, instante da aquisição e hashes do arquivo/robots estão em `public_source.json`; bytes preservados em `.local/public/`. `artifacts/public-faq-check.json` registra a verificação: 32 perguntas, 28 candidatos por regras, 30 âncoras verificadas e zero falhas no recálculo, recortes íntegros em todas as unidades e zero datas finais sem norma-alvo vinculada. Isso valida comportamento sobre um esclarecimento real, sem medir correção jurídica. O comando `python scripts/check_public_faq.py` repete a verificação sem rede.

## Pendências que impedem declarar o MVP integralmente aceito

- PDF oficial da norma e seus anexos ainda não obtidos; estrutura e prazos que dependem da REN não foram verificados. A aquisição e verificação do FAQ acima não os substituem.
- PostgreSQL real, execução da composição e CI remoto: não exercitados.
- Cota, modelo, preço corrente e execução real de IA: não verificados; contratos simulados não comprovam o funcionamento do serviço real.
- Retentativas programadas com Retry-After, limites de tempo/memória em isolamento de processo e processamento seguro de PDFs patológicos: endurecimento pendente.
- Algoritmo de segmentação não foi certificado na norma real; não há promessa de número de artigos ou cobertura estrutural fora do corpus sintético.
- Versões textuais iguais preservam proveniências e extrações separadas; a deduplicação física do texto canônico entre arquivos ainda é parcial.
- Fundamentação cruzada entre várias normas, diff de versões, calendário versionado, múltiplas amostras com divergência e avaliação independente: pendentes.
- Revisão dos mecanismos críticos por outra pessoa, revisão jurídica, identidade profissional verificada e dois ensaios oficiais cronometrados: não realizados.
- A cobertura integral dos critérios de aceitação ainda não foi medida. Contagem de testes executáveis não equivale à cobertura de requisitos.
- Licença própria: decisão do titular pendente; nenhuma licença pública foi concedida.

Os requisitos completos continuam na matriz. Uma linha implementada parcialmente não é considerada encerrada por existir uma tela ou por passar apenas no corpus sintético.
