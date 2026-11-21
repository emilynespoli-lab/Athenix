"""Métricas de eficiência das duas normas da demo, medidas agora (sem IA, sem rede).

Para cada norma: páginas, unidades estruturais, dispositivos classificados, deveres da distribuidora,
prazos (com data, recorrentes, dependentes de evento), deveres com citação verificada e o tempo do
comando único (`python -m athenix processar`), mediana de N execuções.

Uso (raiz do repositório):
    python scripts/demo/medir_normas.py [--execucoes 3]

Imprime uma tabela em Markdown, pronta para `docs/pitch/metricas.md`. Não grava nada no repositório:
os JSONs das execuções vão para uma pasta temporária.
"""

import argparse
import contextlib
import io
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import warnings
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

NORMAS = [
    ("RN ANEEL 1.137/2025", "tests/norma_poc/ren20251137.pdf"),
    ("REN ANEEL 1.174/2026", "tests/fontes_impacto/dou/dou_ren20261174.html"),
]
COM_DATA = ("vencida", "90dias", "depois")


def cronometrar(arquivo, execucoes, pasta):
    """Tempo de parede do comando único, inclusive a partida do Python (o que o usuário espera)."""
    tempos = []
    saida = Path(pasta) / (Path(arquivo).stem + ".json")
    env = {**os.environ, "ATHENIX_AI_MODE": "off", "PYTHONWARNINGS": "ignore"}
    for _ in range(execucoes):
        t0 = time.perf_counter()
        subprocess.run(
            [sys.executable, "-m", "athenix", "processar", arquivo, "--saida", str(saida)],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
        )
        tempos.append(time.perf_counter() - t0)
    return tempos, saida


def medir(arquivo, plano_json):
    import json

    from athenix.evidence import recheck
    from exportar_plano_demo import processar

    with contextlib.redirect_stdout(io.StringIO()):
        rows, extraction, _ = processar(ROOT / arquivo)
    texto, unidades = extraction["text"], extraction["units"]
    por_id = {u["id"]: u for u in unidades}
    # Unidade com ao menos uma âncora que confere de novo, agora: com posição, o trecho literal, a
    # posição na unidade, o hash do trecho e o hash do texto (recheck); sem posição (citação refeita
    # pela primeira frase do dispositivo, plano.ancorar_pendentes), o trecho literal dentro da unidade.
    conferidas, por_frase = set(), set()
    for r in rows:
        for a in r["anchors"]:
            if a.get("state") != "verified":
                continue
            if "start" in a:
                if recheck(a, texto, unidades):
                    conferidas.add(a["unit_id"])
            elif a["quote"] in por_id[a["unit_id"]]["text"]:
                conferidas.add(a["unit_id"])
                por_frase.add(a["unit_id"])
    plano = json.loads(Path(plano_json).read_text(encoding="utf-8"))
    deveres = plano["obrigacoes"]
    situacao = plano["resumo"]["por_situacao"]

    def citado(o):
        if not o["trecho"] or o["unidade"] not in conferidas:
            return False
        return " ".join(o["trecho"].split()) in " ".join(por_id[o["unidade"]]["text"].split())

    return {
        "paginas": len(extraction["pages"]),
        "unidades": len(unidades),
        "classificados": plano["resumo"]["identificadas"],
        "deveres": len(deveres),
        "com_data": sum(situacao[s] for s in COM_DATA),
        "vencidas": situacao["vencida"],
        "recorrentes": situacao["recorrente"],
        "evento": situacao["evento"],
        "sem_prazo": situacao["sem_prazo"],
        "citados": sum(citado(o) for o in deveres),
        "por_frase": sum(citado(o) and o["unidade"] in por_frase for o in deveres),
        "sha256": plano["norma"]["sha256"],
    }


def maquina():
    return (
        f"{platform.system()} {platform.release()} ({platform.version()}), "
        f"{platform.processor() or platform.machine()}, {os.cpu_count()} núcleos lógicos, "
        f"Python {platform.python_version()}"
    )


def main():
    warnings.filterwarnings("ignore")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execucoes", type=int, default=3)
    args = parser.parse_args()
    os.environ["ATHENIX_AI_MODE"] = "off"
    linhas = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta:
        for titulo, arquivo in NORMAS:
            tempos, plano_json = cronometrar(arquivo, args.execucoes, pasta)
            m = medir(arquivo, plano_json)
            linhas.append((titulo, arquivo, tempos, m))
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    print(f"Medido em {date.today().isoformat()}, commit {commit}.")
    print(f"Máquina: {maquina()}.")
    print(f"Comando: python scripts/demo/medir_normas.py --execucoes {args.execucoes}\n")
    cab = ["Métrica"] + [t for t, *_ in linhas]
    print("| " + " | ".join(cab) + " |")
    print("| :-- | " + " | ".join("--:" for _ in linhas) + " |")
    campos = [
        ("Páginas do arquivo oficial", "paginas"),
        ("Unidades estruturais (artigo, parágrafo, inciso, alínea, item)", "unidades"),
        ("Dispositivos classificados (dever, faculdade, outro agente)", "classificados"),
        ("Deveres da distribuidora", "deveres"),
        ("… com data de prazo (vencida ou futura)", "com_data"),
        ("… já vencidos na data da medição", "vencidas"),
        ("… recorrentes", "recorrentes"),
        ("… dependentes de um evento", "evento"),
        ("… sem prazo no texto", "sem_prazo"),
        ("Deveres com citação literal conferida de novo na medição", "citados"),
        ("… dos quais pela primeira frase do dispositivo (sem posição)", "por_frase"),
    ]
    for rotulo, chave in campos:
        print(f"| {rotulo} | " + " | ".join(str(m[chave]) for *_, m in linhas) + " |")
    print(
        "| Tempo do comando único, mediana (s) | "
        + " | ".join(f"{statistics.median(t):.1f}" for _, _, t, _ in linhas)
        + " |"
    )
    print(
        "| Execuções (s) | "
        + " | ".join(", ".join(f"{x:.1f}" for x in t) for _, _, t, _ in linhas)
        + " |"
    )
    print()
    for titulo, arquivo, _, m in linhas:
        print(f"- {titulo}: `{arquivo}`, SHA-256 `{m['sha256']}`")


if __name__ == "__main__":
    main()
