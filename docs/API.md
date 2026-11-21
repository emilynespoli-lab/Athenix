# API HTTP do Athenix

App FastAPI em `athenix/app.py`. Um sistema cliente envia o arquivo oficial da norma e recebe as
obrigações com a citação literal verificada, o hash do arquivo e a trilha de auditoria. Tudo abaixo
foi executado em 21/11/2026 no commit `887cd2f`, com `ATHENIX_AI_MODE=off`.

**O que a API entrega e o que não entrega.** A API devolve a primeira camada: as obrigações
candidatas por regras (sujeito, ação, modalidade dever/faculdade/proibição, prazos lidos e âncora
verificada). O **plano completo** (dever × faculdade × competência da ANEEL, enquadramento na REN
846, valor por infração, área, recomendações) é montado pelo comando único
`python -m athenix processar`, que chama esta mesma API por dentro (`TestClient`). Ainda não há uma
rota que devolva o plano pronto: está no roteiro.

## Subir

```bash
python -m athenix demo                 # banco próprio, usuário "demo" com senha gerada, RN 1.137 já carregada
# ou, com banco e usuário seus:
python -m athenix create-user analista # pede a senha (mínimo 12 caracteres)
python -m athenix serve --port 8000    # API + trabalhador da fila
```

Banco: SQLite em `.local/athenix.db` por padrão; `ATHENIX_DATABASE_URL` aponta para outro.
Migrações em `migrations/` (Alembic), aplicadas ao subir.

Com Docker e PostgreSQL 18 (não testado nesta conferência, a máquina não tinha Docker):

1. Defina `ATHENIX_DB_PASSWORD=<senha forte>` no ambiente ou num `.env` na raiz (fora do Git).
2. `docker compose up -d --build` (serviços `db`, `web`, `worker`; porta só em `127.0.0.1:8000`).
3. Crie a conta pelo terminal: `docker compose exec web python -m athenix create-user <usuario>`.
   A tela `/setup` só aceita acesso local ao processo e responde 403 dentro do container, de propósito.

## Rotas da API

Autenticação por sessão (cookie `athenix_session`, HttpOnly, SameSite=Strict). Toda chamada que não é
GET exige o cabeçalho `X-CSRF-Token` devolvido no login. Requisição com `Origin` de outro site é
recusada (403).

| Método | Rota | O que faz |
| :-- | :-- | :-- |
| GET | `/health` | Estado e modo de IA efetivo (sem autenticação) |
| POST | `/api/login` | `{"username", "password"}` → cookie de sessão + `{"csrf", "username", "role"}` |
| POST | `/api/documents` | Envio multipart (`file`, `title`, `origin`, `role=norm`) → `{"id", "sha256", "reused"}`; enfileira a estruturação |
| GET | `/api/documents/{id}` | Documento + extração (páginas, unidades, datas, remissões); 400 "ainda não estruturado" enquanto a fila trabalha |
| POST | `/api/documents/{id}/runs` | `{"kind": "rules"}` enfileira a extração por regras; `"ai"` exige `confirm_paid` e orçamento |
| GET | `/api/documents/{id}/estimate` | Estimativa de custo de IA **antes** de qualquer chamada (lotes, tokens, teto em US$) |
| POST | `/api/documents/{id}/dependencies` | Liga uma remissão a outro documento do acervo |
| GET | `/api/runs/{id}` | Estado da execução (`queued`, `running`, `completed`, `failed`) e resultado |
| GET | `/api/runs/{id}/reproduction` | Pacote para reproduzir a execução (hash do arquivo, hash do texto, itens) |
| GET | `/api/obligations` | Obrigações; filtros `document_id`, `status`, `band`, `subject`, `origin`, `deadline` |
| POST | `/api/obligations/{id}/review` | Decisão humana (`accept`, `reject`, `correct`, `confirm_deadline`, `frame`…), técnica ou jurídica, com justificativa; papel jurídico exigido para revisão jurídica |
| POST | `/api/obligations/{id}/findings` | Registra contestação de um item |
| GET | `/api/evidence/verify` | Reconfere todas as citações verificadas contra o texto (posição, trecho, hashes) |
| GET | `/api/audit/verify` | Confere a cadeia de hashes da trilha de auditoria |
| GET | `/export/{json,csv,html}` | Exporta as obrigações (CSV com proteção contra fórmula) |

## Exemplo com `curl` (Linux, macOS, Git Bash)

```bash
B=http://127.0.0.1:8000; J=cookies.txt
CSRF=$(curl -s -c $J -H "Content-Type: application/json" \
  -d '{"username":"analista","password":"<sua senha>"}' $B/api/login | python -c "import sys,json;print(json.load(sys.stdin)['csrf'])")

curl -s -b $J -H "X-CSRF-Token: $CSRF" \
  -F "file=@tests/norma_poc/ren20251137.pdf" -F "title=RN ANEEL 1.137/2025" \
  -F "origin=PDF oficial da ANEEL" -F "role=norm" $B/api/documents
# {"id":"75a3413a…","sha256":"4a581592e981158bb9a9ebbbed10a019d3c06399fd2890389bf88f3609cc5887","reused":false}

# espere a estruturação (GET /api/documents/{id} passa de 400 para 200), depois:
curl -s -b $J -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" \
  -d '{"kind":"rules"}' $B/api/documents/$ID/runs
# {"id":"c8aa407c…","state":"queued","reused":false}
curl -s -b $J $B/api/runs/$RUN
# {"id":"c8aa407c…","state":"completed","progress":100,"result":{"accepted":168,"total":168,"discards":[]}}

curl -s -b $J "$B/api/obligations?document_id=$ID"     # 168 itens
curl -s -b $J $B/api/evidence/verify
# {"verified_anchors_checked":250,"invalid":[],"valid":true}
curl -s -b $J -o athenix.csv $B/export/csv
```

Trecho de um item de `/api/obligations` (RN 1.137, item 94):

```json
{
  "subject": "As distribuidoras",
  "modality": "duty",
  "status": "detected",
  "file_sha256": "4a581592e981158bb9a9ebbbed10a019d3c06399fd2890389bf88f3609cc5887",
  "anchors": [{
    "unit_id": "u0026",
    "state": "verified",
    "quote": "94. As distribuidoras devem estabelecer um plano de manejo vegetal na sua área de atuação, …",
    "quote_hash": "771e0af117ae…"
  }]
}
```

## Equivalente em PowerShell (Windows PowerShell 5.1)

```powershell
$B = "http://127.0.0.1:8000"
$login = Invoke-RestMethod -Method Post -Uri "$B/api/login" -ContentType "application/json" `
  -Body '{"username":"analista","password":"<sua senha>"}' -SessionVariable s
$o = Invoke-RestMethod -Uri "$B/api/obligations" -WebSession $s
$o.count                                   # 168
(Invoke-RestMethod -Uri "$B/api/evidence/verify" -WebSession $s).valid   # True
```

O PowerShell 5.1 não monta multipart com `Invoke-RestMethod`; para enviar o arquivo, use o
`curl.exe` que vem no Windows (aspas do JSON escapadas com `\"`):

```powershell
$J = "$env:TEMP\athenix-cookies.txt"
$login = curl.exe -s -c $J -H "Content-Type: application/json" `
  -d '{\"username\":\"analista\",\"password\":\"<sua senha>\"}' "$B/api/login" | ConvertFrom-Json
curl.exe -s -b $J -H "X-CSRF-Token: $($login.csrf)" -F "file=@tests/fontes_impacto/dou/dou_ren20261174.html" `
  -F "title=REN ANEEL 1.174/2026" -F "origin=HTML oficial do DOU" -F "role=norm" "$B/api/documents"
# {"id":"40a1748b…","sha256":"fe1f0608ff63945912f5a37de9ffa612cbdc714cf77c231dc7df2fb4d6361507","reused":false}
```

## Demonstração em um comando

```bash
python scripts/demo/demo_api.py                                                   # RN 1.137
python scripts/demo/demo_api.py --arquivo tests/fontes_impacto/dou/dou_ren20261174.html
```

Sobe o servidor real num SQLite temporário, cria um usuário com senha gerada na hora, faz as 7
chamadas e imprime um resumo. Saída de 21/11/2026 (RN 1.137):

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

As 2 citações que a API deixa pendentes (252 − 250) têm tabela ou quebra de linha no meio do
trecho; o plano as recupera pela primeira frase do dispositivo, conferida na fonte
(`plano.ancorar_pendentes`). Na REN 1.174: 156 obrigações, 223 de 225 citações verificadas.
