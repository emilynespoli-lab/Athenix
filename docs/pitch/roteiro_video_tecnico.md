# Roteiro do vídeo técnico (15 a 20 segundos)

Objetivo: mostrar ao júri técnico que o Athenix é um sistema que funciona por API, não um site
estático. Tempos medidos em 21/11/2026 (Ryzen 5 5500, Windows 11).

## Preparação (fora da gravação)

1. Terminal na raiz do repositório, com o venv pronto (`python -m pip install -r requirements-dev.lock`).
2. Janela com pelo menos **110 colunas** e fonte grande (as linhas da saída têm até ~100 caracteres).
3. Rodar **uma vez antes** os dois comandos abaixo, para aquecer o disco e o Python (a primeira
   execução é mais lenta).
4. `cls` (Windows) ou `clear` para começar com a tela limpa.
5. No Windows, troque `python` por `.venv\Scripts\python`.

## Gravação

| Tempo | Comando | O que aparece |
| :-- | :-- | :-- |
| 0–2 s | digitar `python scripts/demo/demo_api.py` | o comando |
| 2–10 s | (rodando, ~7,5 s) | `Athenix · API HTTP · RN ANEEL 1.137/2025`, o servidor FastAPI subindo e as 8 linhas das chamadas, uma por vez: `/health` → `/api/login` → `/api/documents` (sha256) → estrutura (31 páginas, 315 unidades) → extração por regras → `completed` → **168 obrigações, 250 de 252 citações verificadas** → **250 citações reconferidas, válidas=sim** |
| 10–12 s | (pausa na tela) | o exemplo com o trecho literal do item 94 e o hash do trecho; `Tempo total: 7.5 s` |
| 12–14 s | digitar `python scripts/demo/conferir_citacoes.py` | o comando |
| 14–16 s | (rodando, < 1 s) | `SHA-256 do arquivo = declarado no plano: sim` e **153 de 153 / 83 de 83** deveres, `Resultado: todas as citações conferem` |
| 16–18 s | (pausa na tela) | fim |

Narração sugerida (opcional, uma frase): "A norma entra pela API, sai com cada obrigação citada
literalmente e com hash, e qualquer um confere contra o arquivo oficial."

## Saída esperada

```text
Athenix · API HTTP · RN ANEEL 1.137/2025
  servidor: http://127.0.0.1:8765  (FastAPI + trabalhador da fila, SQLite temporário, IA off)
  0. GET  /health                            status=ok ia=off
  1. POST /api/login                         sessão aberta (cookie + token CSRF)
  2. POST /api/documents                     sha256=4a581592e981158b…
  3. GET  /api/documents/{id}                31 página(s), 315 unidades estruturais
  4. POST /api/documents/{id}/runs           extração por regras enfileirada
  5. GET  /api/runs/{id}                     estado=completed
  6. GET  /api/obligations                   168 obrigações, 250 de 252 citações verificadas
  7. GET  /api/evidence/verify               250 citações reconferidas, válidas=sim

  Modalidade: dever 156, faculdade 12
  Exemplo:    «94. As distribuidoras devem estabelecer um plano de manejo vegetal na sua área de atuaçã…»
              âncora u0026 · hash do trecho 771e0af117ae…

Tempo total: 7.5 s (inclui subir o servidor)
```

```text
RN ANEEL 1.137/2025 · tests/norma_poc/ren20251137.pdf
  SHA-256 do arquivo = declarado no plano: sim
  obrigacoes: 153 de 153 trechos encontrados
  outros_dispositivos: 14 de 14 trechos encontrados
  sem_dever_identificado: 61 de 61 trechos encontrados
REN ANEEL 1.174/2026 · tests/fontes_impacto/dou/dou_ren20261174.html
  SHA-256 do arquivo = declarado no plano: sim
  obrigacoes: 83 de 83 trechos encontrados
  outros_dispositivos: 73 de 73 trechos encontrados
  sem_dever_identificado: 151 de 151 trechos encontrados
Resultado: todas as citações conferem
```

## Alternativa (sem API): o comando único

`python -m athenix processar tests/norma_poc/ren20251137.pdf --saida plano.json` leva ~16 s e mostra
o plano em 5 linhas (deveres, prazos, enquadramento, temas). Cabe no vídeo só se for o único comando.

## Cuidados

- Nada de `.env` na tela: os scripts não o imprimem, mas não abra o arquivo nem rode `env`/`set`.
- `ATHENIX_AI_MODE` não precisa ser definido: os scripts forçam `off` (nenhuma chamada de IA).
- Se a porta 8765 estiver ocupada, o script escolhe outra sozinho (a linha "servidor" mostra qual).
