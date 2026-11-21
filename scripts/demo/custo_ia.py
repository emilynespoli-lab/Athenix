"""Custo de IA registrado nos caches versionados (athenix/data/*.json). Não chama IA nem rede.

Cada execução paga grava no próprio cache o modelo, o preço usado (com fonte e data) e o custo.
Uma mesma execução pode cobrir as duas normas e aparecer em dois arquivos: aqui ela conta uma vez
(chave = custo + data). Execuções cujo custo não ficou gravado num arquivo versionado não
entram na soma e são listadas como "sem registro".

Uso (raiz do repositório):
    python scripts/demo/custo_ia.py
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "athenix" / "data"


def execucoes():
    vistas = {}
    for arquivo in sorted(DATA.glob("*.json")):
        d = json.loads(arquivo.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            continue
        custo = d.get("custo_total_da_execucao_usd") or d.get("custo_usd")
        if custo is not None:
            chave = (str(custo), d.get("gerado_em"))
            item = vistas.setdefault(
                chave,
                {"custo": Decimal(str(custo)), "arquivos": [], "data": d.get("gerado_em")},
            )
            item["arquivos"].append(arquivo.name)
            item["chamadas"] = d.get("chamadas")
            item["preco"] = "informado (a confirmar no portal)"
        # Cache de tipos: o uso fica em "uso" (rodada inicial) e em "a_definir.uso" (complemento),
        # calculado ao preço-teto, que é limite superior e não o preço real.
        for nome, bloco in (("tipos", d), ("a_definir", d.get("a_definir") or {})):
            uso = bloco.get("uso") if isinstance(bloco, dict) else None
            if isinstance(uso, dict) and "custo_ao_preco_teto_usd" in uso:
                vistas[(str(uso["custo_ao_preco_teto_usd"]), arquivo.name + nome)] = {
                    "custo": Decimal(str(uso["custo_ao_preco_teto_usd"])),
                    "arquivos": [f"{arquivo.name} ({nome})"],
                    "data": bloco.get("gerado_em"),
                    "chamadas": uso.get("chamadas"),
                    "preco": "preço-teto (limite superior)",
                }
    return list(vistas.values())


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    itens = execucoes()
    sem_registro = [
        f.name
        for f in sorted(DATA.glob("*.json"))
        if f.name.startswith(
            ("ia_cache", "titulos", "recomendacoes", "evite", "sugestoes", "tipos_ia")
        )
        and not any(f.name in " ".join(i["arquivos"]) for i in itens)
    ]
    print("| Execução (arquivos) | Data | Chamadas | Custo (US$) | Preço |")
    print("| :-- | :-- | --: | --: | :-- |")
    for i in sorted(itens, key=lambda x: x["data"] or ""):
        print(
            f"| {', '.join(i['arquivos'])} | {i['data'] or '—'} | {i['chamadas'] or '—'} "
            f"| {i['custo']:.4f} | {i['preco']} |"
        )
    total = sum(i["custo"] for i in itens)
    print(f"\nTotal registrado nos caches versionados: US$ {total:.4f} ({len(itens)} execuções)")
    print("Sem custo registrado no arquivo: " + (", ".join(sem_registro) or "nenhum"))


if __name__ == "__main__":
    main()
