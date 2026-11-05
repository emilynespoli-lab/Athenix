"""Ensaio sintético em navegador real e banco descartável; não mede qualidade jurídica."""

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main():
    artifact = ROOT / "artifacts"
    artifact.mkdir(exist_ok=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="athenix-qa-") as temporary:
        environment = os.environ | {
            "ATHENIX_DATABASE_URL": "sqlite:///" + (Path(temporary) / "test.db").as_posix(),
            "ATHENIX_API_KEY": "",
            "ATHENIX_MODEL": "",
        }
        process = subprocess.Popen(
            [sys.executable, "-m", "athenix", "serve", "--port", str(port)],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 25
            while True:
                try:
                    if httpx.get(url + "/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("Servidor QA não ficou pronto.")
                time.sleep(0.2)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000}, accept_downloads=True
                )
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/*",
                    lambda route: (
                        route.continue_() if route.request.url.startswith(url) else route.abort()
                    ),
                )
                page.goto(url + "/login")
                password = secrets.token_urlsafe(24)
                page.get_by_label("Usuário", exact=True).fill("qa-sintetico")
                page.get_by_label("Senha", exact=False).fill(password)
                page.get_by_role("button", name="Criar conta técnica").click()
                page.get_by_label("Usuário", exact=True).fill("qa-sintetico")
                page.get_by_label("Senha", exact=True).fill(password)
                page.get_by_role("button", name="Entrar", exact=True).click()
                page.get_by_role("button", name="Carregar exemplo sintético").click()
                page.get_by_role("heading", name="Texto canônico e unidades").wait_for(
                    timeout=30_000
                )
                page.get_by_role("button", name="Executar regras · sem IA").click()
                deadline = time.monotonic() + 20
                while True:
                    rows = context.request.get(url + "/api/obligations").json()
                    if rows["count"]:
                        break
                    if time.monotonic() > deadline:
                        raise RuntimeError("Fila não produziu candidatos.")
                    page.wait_for_timeout(200)
                assert rows["count"] == 6, rows
                page.goto(url + "/matrix")
                page.screenshot(path=str(artifact / "matrix-desktop.png"), full_page=True)
                page.locator(".row-link").first.click()
                assert page.locator("mark").count() > 0
                page.locator(".review").get_by_label("Justificativa").fill(
                    "Conferência técnica do ensaio sintético; sem validade jurídica."
                )
                page.get_by_role("button", name="Registrar decisão e trilha").click()
                assert page.get_by_text("Aceita", exact=True).count() > 0
                page.screenshot(path=str(artifact / "evidence-desktop.png"), full_page=True)
                page.get_by_text("Corrigir interpretação · cria nova versão", exact=True).click()
                page.get_by_label("Objeto", exact=True).fill(
                    "registro auditável das solicitações recebidas"
                )
                page.get_by_label("Justificativa da correção", exact=True).fill(
                    "Objeto explicitado no ensaio sintético."
                )
                page.get_by_role("button", name="Salvar nova interpretação", exact=True).click()
                assert page.get_by_role("link", name="Versão 1", exact=True).count() == 1
                assert page.get_by_role("link", name="Versão 2", exact=True).count() == 1
                for path in ("/timeline", "/risks", "/audit", "/documents"):
                    response = page.goto(url + path)
                    assert response.status == 200
                    assert page.get_by_text("Estudo experimental", exact=False).count()
                integrity = context.request.get(url + "/api/audit/verify").json()
                evidence = context.request.get(url + "/api/evidence/verify").json()
                assert integrity["valid"] and evidence["valid"]
                page.goto(url + "/matrix")
                with page.expect_download() as download:
                    page.get_by_role("link", name="CSV", exact=True).click()
                download.value.save_as(str(artifact / "synthetic-export.csv"))
                page.goto(url)
                page.screenshot(path=str(artifact / "dashboard-desktop.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.screenshot(path=str(artifact / "dashboard-mobile.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
                assert not errors, errors
                result = {
                    "dataset": "synthetic_new",
                    "browser": browser.version,
                    "candidate_count": rows["count"],
                    "audit_events": integrity["events"],
                    "verified_anchors_checked": evidence["verified_anchors_checked"],
                    "invalid_verified_anchors": len(evidence["invalid"]),
                    "javascript_errors": errors,
                    "paid_calls": 0,
                    "correction_versions_preserved": 2,
                    "duration_seconds": round(time.monotonic() - started, 2),
                }
                context.close()
                browser.close()
        finally:
            if os.name == "nt" and process.poll() is None:
                # Windows venv launchers can own a child interpreter holding SQLite handles.
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            time.sleep(0.25)
    # A successful result includes teardown and temporary-database removal.
    result["temporary_database_removed"] = True
    (artifact / "browser-qa.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
