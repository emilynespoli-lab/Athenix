# Inventário técnico: o que existe e o que funciona

Conferido em **21/11/2026** no commit `887cd2f` (`main`), Windows 11, Python 3.13.14, sem IA
(`ATHENIX_AI_MODE=off`). Cada linha diz se a peça existe, se funcionou agora, como rodar e a
evidência (saída do comando). O que não foi testado está marcado como **não testado**.

## Resumo

| Peça | Existe | Funciona agora | Como rodar |
| :-- | :-- | :-- | :-- |
| API HTTP (FastAPI) | sim | **sim** | `python -m athenix serve` · `python scripts/demo/demo_api.py` |
| Rota que devolve o plano completo | **não** | — | o plano sai do comando único (abaixo) |
| Comando único (norma → plano JSON) | sim | **sim** | `python -m athenix processar <arquivo> --saida plano.json` |
| Banco SQLite + migrações Alembic | sim | **sim** | padrão; `ATHENIX_DATABASE_URL` muda |
| PostgreSQL via Docker Compose | sim | **não testado** (máquina sem Docker) | `docker compose up -d --build` |
| IA híbrida (off / cached / live) | sim | **off e cached: sim** (testes); live não rodado | `ATHENIX_AI_MODE` |
| Testes Python | sim | **sim: 502 aprovados** | `python -m pytest -q` |
| Testes do site | sim | **sim no CI: 112** (sem Node nesta máquina) | `cd landing && npm test` |
| Trava do gabarito | sim | **sim: 20/20** | `python scripts/avaliar.py --rotulo local --comparar tests/baseline/metricas_v1.json` |
| CI em 3 sistemas | sim | **sim: verde** | `.github/workflows/ci.yml` |
| Instalação limpa | — | **sim** (clone novo, venv novo) | 3 comandos do README |
| Demo web local com login | sim | **não executada agora** (grava em `.local/`); coberta por `tests/test_demo.py` | `python -m athenix demo` |
| Relatório-piloto (PDF) | sim | **não executado agora**; fora do CI (achado A2 da auditoria) | `scripts/piloto/gerar_relatorio.py` |

## API HTTP

- **Existe:** `athenix/app.py`, FastAPI 0.162.0 (`requirements.lock`). 13 rotas `/api/*`,
  mais `/export/{json,csv,html}` e `/health`, listadas em [API.md](API.md); as telas HTML do
  aplicativo usam as mesmas funções. Sessão por cookie, CSRF em toda mutação, recusa de
  `Origin` estrangeiro.
- **Recebe uma norma?** Sim: `POST /api/documents` (multipart) devolve id e SHA-256;
  `POST /api/documents/{id}/runs` com `{"kind":"rules"}` extrai; `GET /api/obligations` devolve as
  obrigações com citação verificada.
- **Devolve o plano?** **Não diretamente.** A API devolve as obrigações candidatas por regras (168 na
  RN 1.137, entre deveres e faculdades). A classificação dever × faculdade × competência, o
  enquadramento, o valor e a área são montados pelo comando único, que usa a API por dentro.
- **Evidência** (`python scripts/demo/demo_api.py`, servidor real em SQLite temporário):

```text
  2. POST /api/documents                     sha256=4a581592e981158b…
  3. GET  /api/documents/{id}                31 página(s), 315 unidades estruturais
  5. GET  /api/runs/{id}                     estado=completed
  6. GET  /api/obligations                   168 obrigações, 250 de 252 citações verificadas
  7. GET  /api/evidence/verify               250 citações reconferidas, válidas=sim
Tempo total: 7.5 s (inclui subir o servidor)
```

  REN 1.174 (`--arquivo tests/fontes_impacto/dou/dou_ren20261174.html`): 368 unidades, 156
  obrigações, 223 de 225 citações verificadas, 4,1 s. Também testado à mão com `curl` e com
  PowerShell (`Invoke-RestMethod` e `curl.exe`); `GET /export/csv` devolveu 200 e 533 linhas;
  `GET /api/audit/verify` → `{"valid":true,"events":5,…}`.

## Banco

- **Existe:** `athenix/db.py` (SQLAlchemy 2.1.8), migrações `migrations/versions/0001_initial.py` e
  `0002_supplements.py`, aplicadas ao subir (`db.initialize` → Alembic `upgrade head`).
- **Guarda:** usuários e sessões; arquivos (bytes imutáveis, chave = SHA-256); documentos; extrações
  (texto canônico, páginas, unidades); execuções da fila; interpretações (obrigações); decisões
  humanas; contestações; ligações entre normas; respostas de IA e travas de chamada paga; trilha de
  auditoria encadeada por hash (`users`, `sessions`, `artifacts`, `documents`, `extractions`, `runs`,
  `interpretations`, `decisions`, `findings`, `dependency_links`, `model_responses`, `call_claims`,
  `audit_events`).
- **SQLite:** funciona (todas as execuções acima e a suíte de testes).
- **PostgreSQL:** `compose.yaml` sobe `postgres:18` + `web` + `worker`; senha só pelo ambiente
  (`ATHENIX_DB_PASSWORD`). **Não testado nesta conferência:** a máquina não tem Docker
  (`docker: command not found`). O teste `tests/test_infra.py` confere a configuração do compose,
  não sobe o banco.

## Comando único

- **Existe:** `python -m athenix processar <arquivo> --agente distribuidora --saida <json>`
  (`athenix/__main__.py` → `scripts/exportar_plano_demo.py:processar_norma`). Sem IA, sem rede;
  sugestões de IA só do cache versionado, marcadas.
- **Evidência** (ambiente limpo, RN 1.137):

```text
Athenix · processar ren20251137.pdf para distribuidora
  1. Obrigações extraídas: 168 dispositivos lidos
  2. Deveres da distribuidora: 153 · outros dispositivos (faculdades, direitos, outros agentes): 14 · fora do perfil: 1
  3. Prazos: 7 vencidas · 0 nos próximos 90 dias · 2 recorrentes · 144 sem data
  4. Enquadramento na REN 846: 43 identificados no texto · 110 a confirmar (102 com sugestão da IA em cache, marcadas) · 0 sem multa
  5. Temas: 8 · plano gravado em plano.json
Tempo total: 15.4 s
```

  REN 1.174: 156 lidos · 83 deveres · 73 outros · 0 vencidas · 2 recorrentes · 0 identificados no
  texto · 83 a confirmar (79 com sugestão da IA) · 4 temas. Tempos de 3 execuções em
  [pitch/metricas.md](pitch/metricas.md).

## IA híbrida

- **Modos** (`athenix/llm.py:modo`): `off` (padrão, nenhuma chamada de rede), `cached` (só respostas
  gravadas), `live` (só com modelo, chave, preço com fonte e data e teto de custo; senão cai para
  `off` e diz o motivo). `GET /health` mostra o modo efetivo.
- **Orçamento:** teto por execução (`ATHENIX_RUN_BUDGET_USD`), reserva conservadora antes da chamada,
  estimativa em `GET /api/documents/{id}/estimate`; 429 repetido até 3 vezes.
- **Validação de citação:** sugestão de enquadramento só vale com as duas citações literais
  encontradas na fonte (`enquadramento.validar_ia`); títulos e recomendações também citam um trecho.
- **Cache:** `athenix/data/ia_cache_*.json`, `recomendacoes_*.json`, `titulos_curtos_*.json`,
  `evite_*.json`, `tipos_ia_cache.json` (só a sugestão processada, nunca a resposta bruta).
- **Evidência:** `tests/test_modos_ia.py` (8 testes, aprovados: off sem rede mesmo com credencial,
  cached nunca chama, live respeita o teto e só repete 429). Custo registrado:
  `python scripts/demo/custo_ia.py` → **US$ 1,0209 em 6 execuções** para as duas normas (preço
  informado, a confirmar no portal; tipos ao preço-teto). O ensaio de 17/11 da RN 1.137
  (`ia_cache_rn1137.json`) não tem custo gravado no arquivo.
- **Não funciona como prometido:** o script antigo `scripts/classificar_tipos_ia.py --executar` não
  consulta o modo de IA (achado M2 da auditoria; exige `--executar`, não roda na demo).

## Testes, trava e CI

- **pytest:** `python -m pytest -q` → `502 passed in 174.32s` (máquina de desenvolvimento). Num clone
  limpo → `496 passed, 6 skipped` (os 6 dependem de dados locais fora do Git: CSV de autos, votos da
  ANEEL, cópia de conferência, REN 846 original). 44 arquivos de teste; os maiores: `test_tipos.py`
  (50), `test_impacto.py` (34), `test_prazos_obrigacoes.py` (32).
- **Site:** 112 testes (`node --test`), aprovados no CI. Não rodados nesta máquina (sem Node).
- **Trava:** `scripts/avaliar.py` → `casos corretos: 20 / 20`, citações corretas 0,9954, sem fonte
  0,0069, "Sem regressão em relação a tests/baseline/metricas_v1.json". O gabarito
  (`tests/gabarito/`) não tem revisão humana.
- **CI:** `.github/workflows/ci.yml` em `ubuntu-latest`, `windows-latest` e `macos-15-intel`: testes
  e build do site, ruff, segredos, trava, reprodução dos dois JSONs do plano e pytest. Execução
  `44917313898` (commit `887cd2f`): verde nos três.
- **Lint e segredos:** `ruff check` → "All checks passed!"; `ruff format --check` → 118 arquivos
  formatados; `scripts/check_secrets.py` → nenhum padrão conhecido.

## Instalação limpa

Clone novo do repositório (sem `.env`, sem `.local/`) e venv novo, Python 3.13.14:

| Passo | Comando | Resultado | Tempo |
| :-- | :-- | :-- | --: |
| Instalar | `python -m pip install -r requirements-dev.lock` | ok | 33 s |
| Testar | `python -m pytest -q` | 496 passed, 6 skipped | 2 min 17 s |
| Processar | `python -m athenix processar tests/norma_poc/ren20251137.pdf --saida plano.json` | 153 deveres, 8 temas | 17 s |

Não testado: Python 3.11 local (o CI usa 3.11), Linux e macOS locais (cobertos pelo CI).
