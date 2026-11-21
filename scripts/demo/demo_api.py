"""Demonstração da API HTTP do Athenix em um comando (para gravação de tela).

Sobe o servidor real (`python -m athenix serve`, com o trabalhador da fila) num banco SQLite
descartável, cria um usuário com senha gerada na hora e faz, por HTTP, o que um sistema cliente faria:

  1. POST /api/login                          -> sessão + token CSRF
  2. POST /api/documents                      -> envia o arquivo oficial; devolve o SHA-256
  3. GET  /api/documents/{id}                 -> estrutura pronta (unidades, páginas)
  4. POST /api/documents/{id}/runs  (rules)   -> extração por regras, sem IA
  5. GET  /api/runs/{id}                      -> acompanha a execução
  6. GET  /api/obligations?document_id=...    -> obrigações com citação literal verificada
  7. GET  /api/evidence/verify                -> reconfere todas as citações contra o texto

Uso (raiz do repositório):
    python scripts/demo/demo_api.py [--arquivo tests/norma_poc/ren20251137.pdf] [--porta 8765]

Sem IA (ATHENIX_AI_MODE=off), sem rede externa, sem tocar em .local/: tudo numa pasta temporária.
"""

import argparse
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PADRAO = "tests/norma_poc/ren20251137.pdf"
TITULOS = {
    "ren20251137": "RN ANEEL 1.137/2025",
    "dou_ren20261174": "REN ANEEL 1.174/2026",
}


def porta_livre(preferida):
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", preferida)) != 0:
            return preferida
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def preparar_banco(url):
    from athenix.auth import create_user
    from athenix.db import database, initialize

    engine, factory = database(url)
    initialize(engine)
    senha = secrets.token_urlsafe(12)
    with factory.begin() as session:
        create_user(session, "api-demo", senha)
    engine.dispose()
    return senha


def esperar(condicao, limite=120, passo=0.3):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        resultado = condicao()
        if resultado:
            return resultado
        time.sleep(passo)
    raise SystemExit("Tempo esgotado esperando o servidor.")


def passo(n, metodo, rota, detalhe):
    print(f"  {n}. {metodo:<4} {rota:<34} {detalhe}", flush=True)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arquivo", default=PADRAO)
    parser.add_argument("--porta", type=int, default=8765)
    args = parser.parse_args()
    arquivo = ROOT / args.arquivo
    titulo = TITULOS.get(arquivo.stem, arquivo.stem)
    porta = porta_livre(args.porta)
    base = f"http://127.0.0.1:{porta}"
    t0 = time.perf_counter()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        url = "sqlite:///" + (Path(tmp) / "api.db").as_posix()
        senha = preparar_banco(url)
        env = {**os.environ, "ATHENIX_DATABASE_URL": url, "ATHENIX_AI_MODE": "off"}
        env["PYTHONWARNINGS"] = "ignore"
        log = open(Path(tmp) / "servidor.log", "w", encoding="utf-8")
        servidor = subprocess.Popen(
            [sys.executable, "-m", "athenix", "serve", "--port", str(porta)],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            print(f"Athenix · API HTTP · {titulo}")
            print(f"  servidor: {base}  (FastAPI + trabalhador da fila, SQLite temporário, IA off)")
            with httpx.Client(base_url=base, timeout=30) as c:

                def no_ar():
                    if servidor.poll() is not None:
                        log.flush()
                        erro = (Path(tmp) / "servidor.log").read_text(encoding="utf-8")
                        raise SystemExit("O servidor não subiu:\n" + erro[-2000:])
                    try:
                        return c.get("/health").json()
                    except httpx.HTTPError:
                        return None

                saude = esperar(no_ar)
                passo(
                    0,
                    "GET",
                    "/health",
                    f"status={saude['status']} ia={saude['ai_mode']['efetivo']}",
                )

                r = c.post("/api/login", json={"username": "api-demo", "password": senha})
                r.raise_for_status()
                h = {"x-csrf-token": r.json()["csrf"]}
                passo(1, "POST", "/api/login", "sessão aberta (cookie + token CSRF)")

                with open(arquivo, "rb") as f:
                    r = c.post(
                        "/api/documents",
                        headers=h,
                        files={"file": (arquivo.name, f)},
                        data={
                            "title": titulo,
                            "origin": f"{args.arquivo} (arquivo oficial versionado no repositório)",
                            "role": "norm",
                        },
                    )
                r.raise_for_status()
                doc = r.json()
                passo(2, "POST", "/api/documents", f"sha256={doc['sha256'][:16]}…")

                def estruturado():
                    resp = c.get(f"/api/documents/{doc['id']}")
                    return resp.json() if resp.status_code == 200 else None

                dados = esperar(estruturado)
                ext = dados["extraction"]
                passo(
                    3,
                    "GET",
                    "/api/documents/{id}",
                    f"{len(ext['pages'])} página(s), {len(ext['units'])} unidades estruturais",
                )

                r = c.post(f"/api/documents/{doc['id']}/runs", headers=h, json={"kind": "rules"})
                r.raise_for_status()
                run = r.json()
                passo(4, "POST", "/api/documents/{id}/runs", "extração por regras enfileirada")

                def terminou():
                    estado = c.get(f"/api/runs/{run['id']}").json()
                    return (
                        estado
                        if estado["state"] in {"completed", "failed", "interrupted"}
                        else None
                    )

                fim = esperar(terminou)
                passo(5, "GET", "/api/runs/{id}", f"estado={fim['state']}")

                r = c.get("/api/obligations", params={"document_id": doc["id"]})
                itens = r.json()["items"]
                ancoras = [a for i in itens for a in i["anchors"]]
                verif = sum(a["state"] == "verified" for a in ancoras)
                passo(
                    6,
                    "GET",
                    "/api/obligations",
                    f"{len(itens)} obrigações, {verif} de {len(ancoras)} citações verificadas",
                )

                v = c.get("/api/evidence/verify").json()
                passo(
                    7,
                    "GET",
                    "/api/evidence/verify",
                    f"{v['verified_anchors_checked']} citações reconferidas, "
                    f"válidas={'sim' if v['valid'] else 'NÃO'}",
                )

            nomes = {"duty": "dever", "permission": "faculdade", "prohibition": "proibição"}
            modal = Counter(nomes.get(i["modality"], i["modality"]) for i in itens)
            print("\n  Modalidade: " + ", ".join(f"{k} {n}" for k, n in modal.most_common()))

            def com_hash(i):
                return (
                    i["anchors"]
                    and i["anchors"][0]["state"] == "verified"
                    and (i["anchors"][0].get("quote_hash"))
                )

            candidatos = [i for i in itens if com_hash(i)]
            exemplo = next(
                (
                    i
                    for i in candidatos
                    if i["modality"] == "duty" and "distribuidora" in i["subject"].casefold()
                ),
                candidatos[0] if candidatos else None,
            )
            if exemplo:
                a = exemplo["anchors"][0]
                trecho = " ".join(a["quote"].split())
                print(f"  Exemplo:    «{trecho[:88]}{'…' if len(trecho) > 88 else ''}»")
                print(
                    f"              âncora {a['unit_id']} · hash do trecho {a['quote_hash'][:12]}…"
                )
            print(f"\nTempo total: {time.perf_counter() - t0:.1f} s (inclui subir o servidor)")
        finally:
            servidor.terminate()
            try:
                servidor.wait(timeout=10)
            except subprocess.TimeoutExpired:
                servidor.kill()
            log.close()


if __name__ == "__main__":
    main()
