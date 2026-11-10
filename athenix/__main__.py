import argparse
import getpass
import json
import time

from .auth import create_user
from .config import Settings
from .db import database, initialize, verify_chain


def main():
    parser = argparse.ArgumentParser(
        description="Athenix — inteligência regulatória com evidências"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Servidor local com trabalhador integrado")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--no-worker", action="store_true")
    sub.add_parser("worker", help="Trabalhador separado da fila persistente")
    sub.add_parser("verify", help="Conferir trilha")
    user = sub.add_parser(
        "create-user", help="Provisionar conta; papel jurídico exige verificação externa"
    )
    user.add_argument("username")
    user.add_argument("--role", choices=["operator", "technical", "legal"], default="technical")
    poc = sub.add_parser("poc", help="Extração, comparação e estruturação da norma de PoC")
    poc.add_argument("--a", default="tests/norma_poc/ren20251137.pdf")
    poc.add_argument("--b", default="tests/norma_poc/dou.pdf")
    poc.add_argument("--out", default="artifacts/poc")
    poc.add_argument("--ocr", choices=["none", "docling"], default="none")
    poc.add_argument("--ai", action="store_true", help="Usa o modelo configurado (Azure), com teto")
    args = parser.parse_args()
    settings = Settings()
    settings.prepare()
    if args.command == "poc":
        from .poc.run import run

        ocr = None
        if args.ocr == "docling":
            from pathlib import Path

            from .poc.ocr import docling_ocr

            def ocr(path, pages):
                images = Path(args.out) / "pages" / Path(path).stem
                return docling_ocr(path, pages, cache_dir=args.out, images_dir=images)

        result = run(args.a, args.b, args.out, settings, ocr=ocr, ai=args.ai)
        print(json.dumps({"comparison": result["comparison"], "log": result["log"]["ai"]}))
        return
    if args.command == "serve":
        import uvicorn
        from .app import create_app

        uvicorn.run(
            create_app(settings, embedded_worker=not args.no_worker),
            host=args.host,
            port=args.port,
            access_log=False,
        )
        return
    engine, factory = database(settings.database_url)
    initialize(engine)
    if args.command == "create-user":
        password = getpass.getpass("Senha (mínimo 12 caracteres): ")
        if password != getpass.getpass("Confirme a senha: "):
            raise SystemExit("Senhas diferentes.")
        with factory.begin() as session:
            create_user(session, args.username, password, args.role)
        print("Conta provisionada. A atribuição de papel não comprova qualificação profissional.")
    elif args.command == "verify":
        with factory() as session:
            print(verify_chain(session))
    else:
        from .services import recover_stale, run_one

        recover_stale(factory)
        try:
            while True:
                if not run_one(factory, settings):
                    time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    engine.dispose()


if __name__ == "__main__":
    main()
