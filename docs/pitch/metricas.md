# Métricas de eficiência: duas normas reais

Medido em **21/11/2026**, commit `887cd2f` (`main`), sem IA (`ATHENIX_AI_MODE=off`) e sem rede.

```bash
python scripts/demo/medir_normas.py --execucoes 3
```

**Máquina:** AMD Ryzen 5 5500 (6 núcleos, 12 threads), 15,9 GB de RAM, Windows 11 (10.0.26300),
Python 3.13.14. O tempo é de parede do comando único `python -m athenix processar`, incluindo a
partida do Python, a estruturação do arquivo, as regras, o cálculo e a gravação do JSON.

| Métrica | RN ANEEL 1.137/2025 | REN ANEEL 1.174/2026 |
| :-- | --: | --: |
| Arquivo oficial | PDF da ANEEL | HTML do DOU |
| Páginas do arquivo oficial | 31 | 1 (HTML sem paginação) |
| Unidades estruturais (artigo, parágrafo, inciso, alínea, item) | 315 | 368 |
| Dispositivos classificados (dever, faculdade, outro agente) | 168 | 156 |
| Deveres da distribuidora | 153 | 83 |
| … com data de prazo (todos já vencidos em 21/11/2026) | 7 | 0 |
| … recorrentes | 2 | 2 |
| … dependentes de um evento | 20 | 1 |
| … sem prazo no texto | 124 | 80 |
| Deveres com citação literal conferida de novo na medição | 153 | 83 |
| … dos quais pela primeira frase do dispositivo | 2 | 0 |
| **Tempo do comando único, mediana de 3 (s)** | **16,1** | **12,1** |
| Execuções (s) | 16,3 · 15,9 · 16,1 | 12,1 · 12,1 · 11,9 |

Arquivos e hashes:
- RN 1.137/2025: `tests/norma_poc/ren20251137.pdf`, SHA-256
  `4a581592e981158bb9a9ebbbed10a019d3c06399fd2890389bf88f3609cc5887`
- REN 1.174/2026: `tests/fontes_impacto/dou/dou_ren20261174.html`, SHA-256
  `fe1f0608ff63945912f5a37de9ffa612cbdc714cf77c231dc7df2fb4d6361507`

Como ler:
- "Citação conferida de novo" = a âncora da obrigação passou outra vez por
  `athenix.evidence.recheck` (trecho literal, posição na unidade, hash do trecho e do texto) e o
  trecho do plano está dentro da unidade. As 2 da RN 1.137 sem posição são as que o plano recupera
  pela primeira frase do dispositivo (`plano.ancorar_pendentes`).
- Conferência independente, com outro extrator (pypdfium2 / html.parser), de **todos** os trechos
  publicados no site: `python scripts/demo/conferir_citacoes.py` → RN 1.137: 228 de 228; REN 1.174:
  307 de 307 (deveres + outros dispositivos + "sem dever identificado").
- Num ambiente limpo (clone novo, venv novo, mesma máquina), o mesmo comando levou 15,4 s na RN 1.137.

## Referência manual

Tempo manual de referência: ___ (fonte: conversa com ___)

> Preencher com o que for ouvido nas conversas com distribuidoras (tempo para ler a norma, separar
> os deveres, achar prazos e enquadrar na REN 846). Não usar estimativa sem fonte.
