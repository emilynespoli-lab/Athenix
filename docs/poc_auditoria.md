# PoC RN ANEEL 1.137/2025: guia para auditoria independente

Registro de 05/11/2026. Leia `docs/poc.md` (arquitetura e uso) e verifique os artefatos sem depender
das explicações do autor. Nada aqui é parecer jurídico.

## Originais (SHA-256)

| Arquivo | SHA-256 | Observação |
| --- | --- | --- |
| `tests/norma_poc/ren20251137.pdf` | `4a581592e981158bb9a9ebbbed10a019d3c06399fd2890389bf88f3609cc5887` | 31 p., camada de texto (Word) |
| `tests/norma_poc/dou.pdf` | `ca2dbbb8ffda728d78ad1c6cc0a3f581ed7a39aa996bdacf9c6bc97dfd05fec2` | 43 p., 100% imagem (Print to PDF); inclui Módulos 4 e 6 das Regras de Transmissão (p. 21-43) ausentes no outro PDF |

## Reproduzir

```powershell
.\.venv\Scripts\python.exe -m athenix poc --ocr docling --out artifacts/poc   # ~21 min (OCR em CPU); ver docs/docling.md
.\.venv\Scripts\python.exe scripts/verify_poc.py artifacts/poc tests/norma_poc   # verificador independente (só stdlib)
.\.venv\Scripts\python.exe -m pytest -q --junitxml=artifacts/tests.xml
```

Sem Docling: `python -m athenix poc` (o `dou.pdf` fica `not_extracted`, 43 páginas, registrado em `run_log.json`).

## Resultados medidos (execução com Docling 2.147.0 + RapidOCR 3.10.0, CPU)

| Medida | ren20251137.pdf | dou.pdf |
| --- | --- | --- |
| Páginas por estado | 19 `faithful`, 12 `needs_review` | 3 `uncertain`, 40 `needs_review` |
| Unidades normativas | 284 | 414 |
| Tabelas detectadas | 24 (geometria) | 36 (TableFormer) |
| Itens (candidatos) | 254 | 352 |
| Âncoras verificadas literalmente | 356/356 | 456/459 |

Comparação (unidades por chave estrutural): 78 iguais, 64 divergentes, 58 de equivalência incerta,
83 só no ren, 213 só no dou. **As 64 divergências estão marcadas `possible_ocr_error`** porque um dos
lados é OCR: não se sabe quais são diferenças reais. As unidades só no dou concentram-se nas p. 25-29, 31, 40 e 43
(anexos das Regras de Transmissão, que o ren não traz). 58 pares "incertos" têm texto igual, mas norma-alvo atribuída
diferente pelo segmentador entre as versões: revisar.

Verificador independente: 606 itens, 815 âncoras, 698 unidades, **0 erros** (manifesto, hashes,
offsets, hash do trecho, unicidade de ids, coerência de páginas).
Testes: 94 aprovados, 0 falhas (80 anteriores + 14 da PoC). Lint, formatação e `check_secrets` passam.
Custo de IA: US$ 0,00 (nenhuma chamada paga foi feita).

## Testes da PoC (`tests/test_poc.py`)

Identidade/hash e entradas inválidas; hierarquia (artigo > inciso > alínea) e âncoras literais com
bbox; página sem texto nunca silenciosa, OCR nunca `faithful`, camada digital prevalece; comparação sem
preferência de fonte; divergência com OCR sinalizada; alvo/URL/cabeçalhos do Azure; teto de custo
(parada antes de exceder, custo desconhecido = reserva, sem retentativa, citação inventada nunca vira
`literal_text`); repetibilidade (mesmos hashes de artefatos); cache e falha do OCR; adulteração
plantada detectada pelo verificador.

## O que um auditor deve procurar (não verificado pelo autor)

1. **Obrigações omitidas:** o detector determinístico exige verbo deôntico (`deve`, `poderá`...) ou herda do *caput*. Os incisos do art. 13 ("Até 90 dias para revisar...") geram, cada um, itens `obligation` (por herança do *caput*), `deadline`, `transitional` e `reference`: o mesmo dispositivo aparece em vários tipos; conferir duplicidade e se o sujeito herdado é correto.
2. **Dispositivos mal atribuídos:** a norma-alvo (RN 956, 1.000, 846, 948) é inferida por heurística de "passa a vigorar"; conferir os 58 pares incertos e `owner_norm` de blocos citados.
3. **Remissões:** todas com `target: null`; nenhuma foi resolvida contra o acervo.
4. **Tabelas e fórmulas:** células reconstruídas, não certificadas; fórmulas (DISE, Comp_DISE, anexos de transmissão) não são lidas pelo OCR. Conferir com `artifacts/poc/pages/dou/*.png`.
5. **Texto do OCR:** a pontuação por página (~0,92-0,97) não mede correção. Exemplos observados: "Consuridora" por "Consumidora", fórmula DISE ilegível.
6. **Ordem de leitura:** assume coluna única (topo→base, esquerda→direita).
7. **Baixa confiança de OCR:** 40 das 43 páginas do dou.pdf têm ao menos uma linha com confiança < 0,85; as p. 2-9 e 25-29 têm mais (5 a 12 linhas por página).

## Divergências entre documentos (para decisão do titular)

- `docs/execucao.md` diz que o PDF oficial da norma não foi obtido; agora há dois PDFs em `tests/norma_poc/`.
- `docs/arquitetura.md` afirma "sem OCR"; a PoC adiciona OCR opcional (Docling, fora do CI).
- Limite de upload de 10 MiB (`Settings.max_bytes`) rejeitaria `dou.pdf` (12,9 MB) pela aplicação web; a PoC lê do disco e não passa por esse limite.
- O repositório remoto traz `LICENSE`; `docs/execucao.md` registra a licença própria como decisão pendente.

## Não validado

Chamada real ao Azure gpt-5-mini (somente transporte falso; versão de API `2025-04-01-preview` e parâmetros `reasoning_effort`/`max_completion_tokens` não confirmados no serviço); preço do modelo; precisão e recall jurídicos (sem conjunto de referência); PostgreSQL; revisão jurídica; qualquer ganho para o usuário.
