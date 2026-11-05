# PoC: extração fiel, comparação e estruturação de uma norma

Norma da PoC: RN ANEEL nº 1.137/2025, em dois PDFs de `tests/norma_poc/`:
`ren20251137.pdf` (texto da ANEEL, camada de texto) e `dou.pdf` (D.O.U., 43 páginas de imagem).
Nenhum dos dois é presumido mais completo ou juridicamente prevalente.

Escopo desta etapa: leitura documental, estrutura, proveniência, comparação e candidatos a obrigações.
Fora de escopo: dashboard, alertas, usuários, cálculo financeiro, SaaS.

## Executar

```powershell
.\.venv\Scripts\python.exe -m athenix poc                    # sem OCR: dou.pdf fica not_extracted
.\.venv\Scripts\python.exe -m athenix poc --ocr docling      # ver docs/docling.md
.\.venv\Scripts\python.exe -m athenix poc --ai               # + Azure gpt-5-mini, com teto por execução
.\.venv\Scripts\python.exe -m pytest -q tests/test_poc.py
```

Opções: `--a`, `--b` (PDFs), `--out` (padrão `artifacts/poc`).

## Módulos (`athenix/poc/`)

| Módulo | Responsabilidade |
| --- | --- |
| `reader.py` | Identidade (SHA-256), texto por página com bbox, estado de fidelidade, tabelas; reutiliza `structure.from_pieces` |
| `ocr.py` + `scripts/docling_ocr.py` | OCR/layout em subprocesso (opcional), com cache bruto por hash |
| `compare.py` | Casamento por norma-alvo + caminho de dispositivos; sem preferência de fonte |
| `semantic.py` | Candidatos determinísticos (`proposals`) + IA opcional; âncoras via `evidence.verify` |
| `run.py` | Orquestração, cobertura, relatórios, manifesto de hashes, registro operacional |

Reaproveitados sem reescrever: `structure` (segmentação LC 95), `evidence` (âncoras), `proposals` (regras e contestações), `temporal` (prazos), `llm` (adaptador, agora com Azure).

## Estados de fidelidade (por página)

| Estado | Significado |
| --- | --- |
| `faithful` | Texto da camada digital do PDF, sem imagens ou tabelas na página |
| `uncertain` | Texto de OCR (nunca "fiel") |
| `needs_review` | Tabelas/imagens/fórmulas, baixa confiança de OCR |
| `not_extracted` | Nenhum texto obtido; requer OCR ou inspeção |

## Artefatos (`artifacts/poc/`)

Determinísticos (mesmos hashes em reexecuções, listados em `manifest.json`): `documents.json`,
`extraction_<doc>.json` (texto canônico, páginas, linhas com offsets e bbox, unidades, tabelas),
`items_<doc>.json`, `comparison.json/.md`, `coverage.json/.md`. Operacional: `run_log.json`
(tempos, versões, chamadas de IA, custo, erros), `ai_raw/` (respostas brutas), `ocr_<hash>.json`, `pages/`.

Cadeia de rastreabilidade de cada item: documento (sha256) → `pages` → `dispositivo` →
`literal_text` com `locator` {start,end} no texto canônico e `anchors` (hash do trecho) →
`interpretation` (separada, com `interpretation_generator`). Offsets são pontos de código Unicode.
`reader.boxes(pages, start, end)` devolve página e bbox das linhas do trecho.

## Itens regulatórios

Tipos: `obligation`, `prohibition`, `permission`, `deadline`, `penalty`, `revocation`, `transitional`,
`reference`. Todo item nasce `pending_human_review` (ou `anchor_unverified` se o trecho não foi
localizado literalmente). `interpretation` é inferência, nunca texto normativo. Remissões saem com
`target: null` (não resolvidas). Datas só existem quando há quantidade e marco explícitos
(`temporal.rules`), sempre `provisional`; nenhum prazo é inventado.

## IA (Azure OpenAI gpt-5-mini)

Desligada por padrão. Configure por variáveis de ambiente (nunca no código):

| Variável | Uso |
| --- | --- |
| `ATHENIX_AZURE_ENDPOINT` | `https://<recurso>.openai.azure.com` |
| `ATHENIX_MODEL` | Nome do **deployment** |
| `ATHENIX_API_KEY` | Chave (cabeçalho `api-key`) |
| `ATHENIX_AZURE_API_VERSION` | Padrão `2025-04-01-preview` (não validado contra o serviço real) |
| `ATHENIX_REASONING_EFFORT` | Padrão `low` |
| `ATHENIX_INPUT_USD_M`, `ATHENIX_OUTPUT_USD_M`, `ATHENIX_PRICE_SOURCE`, `ATHENIX_PRICE_DATE` | Preço por 1M tokens com fonte HTTPS e data; sem isso não há chamada paga |
| `ATHENIX_RUN_BUDGET_USD` | Teto por execução (padrão `0.50`) |

Controles: reserva conservadora antes de cada chamada (entrada em bytes + saída máxima); a execução para
**antes** de exceder o teto; custo desconhecido conta a reserva, nunca zero; sem retentativa automática
após 429/5xx/timeout; respostas brutas preservadas; itens da IA passam pelas mesmas âncoras e
contestações determinísticas. Uma 2ª chamada ao mesmo modelo não é evidência de qualidade.

## Limites declarados

- Não há conjunto de referência validado: cobertura (páginas, unidades, âncoras) **não** mede precisão
  jurídica nem recall de obrigações.
- Segmentação é heurística; tabelas e fórmulas exigem conferência visual.
- Confiança de OCR é por página. Equivalência entre versões OCR e digital é incerta por construção.
- Chamada real ao Azure não foi exercitada (testada só com transporte falso).
