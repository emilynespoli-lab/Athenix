# Prova técnica (linhas para slide)

Cada linha tem o número e o comando ou arquivo de onde veio. Conferido em 21/11/2026, commit
`887cd2f`.

1. **502 testes automatizados em Python + 112 no site.** CI verde em Ubuntu, Windows e macOS
   (496 rodam no CI; 6 dependem de dados locais fora do Git).
   `python -m pytest -q` · `gh run view 44917313898`
2. **Trava de qualidade: 20 de 20 casos do gabarito**, citações corretas 0,9954.
   `python scripts/avaliar.py --rotulo local --comparar tests/baseline/metricas_v1.json`
3. **535 de 535 citações conferidas contra o arquivo oficial** com um extrator independente
   (RN 1.137: 228; REN 1.174: 307). `python scripts/demo/conferir_citacoes.py`
4. **Segunda leitura independente: 108 de 108 infrações da REN 846 no mesmo grupo**
   (catálogo Athenix: 109; segunda leitura: 108; em comum: 108; grupo diferente: 0).
   `scripts/demo/conferir_segunda_leitura.py` sobre `.review/gpt/` (respostas de IA, fora do Git)
5. **Da norma ao plano em 16 s (RN 1.137, 31 páginas, 153 deveres) e 12 s (REN 1.174, 83 deveres)**,
   sem IA e sem rede. `python scripts/demo/medir_normas.py --execucoes 3`
6. **Custo de IA: US$ 1,02 registrados para as duas normas (≈ US$ 0,51 por norma); reprocessar custa
   US$ 0** (as sugestões ficam em cache versionado). `python scripts/demo/custo_ia.py`
7. **API HTTP: do upload às obrigações com citação verificada em 7,5 s**, 250 citações reconferidas.
   `python scripts/demo/demo_api.py`
