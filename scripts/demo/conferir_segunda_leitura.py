"""Catálogo de infrações da REN 846 (Athenix) x segunda leitura independente (outro modelo de IA).

O catálogo do Athenix (`athenix/data/penalidades_ren846.json`) sai das regras sobre o texto
compilado oficial. A segunda leitura foi feita por outro modelo, sem acesso ao código, sobre o mesmo
PDF; a resposta bruta fica fora do Git (`.review/gpt/`), porque respostas brutas de IA não são
publicadas. Este script compara dispositivo a dispositivo (artigo, inciso, alínea) e o grupo (I a V).

Uso (raiz do repositório):
    python scripts/demo/conferir_segunda_leitura.py [--leitura .review/gpt/extracao_regulatoria_rodada_01.json]
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOGO = ROOT / "athenix" / "data" / "penalidades_ren846.json"
LEITURA = ROOT / ".review" / "gpt" / "extracao_regulatoria_rodada_01.json"
ARQUIVO = "atren2019846.pdf"


def chave(dispositivo):
    """'Art. 9º, I' e 'Art. 9, inciso I; página 4' viram ('9', 'I', '')."""
    s = dispositivo.split(";")[0]
    art = re.search(r"Art\.?\s*(\d+(?:-[A-Z])?)", s, re.I)
    inc = re.search(r"(?:inciso\s+|,\s*)([IVXL]+)\b", s)
    ali = re.search(r"(?:al[ií]nea\s+|,\s*)([a-z])\b", s)
    return (art.group(1) if art else s, inc.group(1) if inc else "", ali.group(1) if ali else "")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--leitura", default=str(LEITURA))
    args = parser.parse_args()
    leitura = Path(args.leitura)
    if not leitura.exists():
        print(f"Segunda leitura não encontrada em {leitura} (fica fora do Git).")
        return 2
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))["infracoes"]
    athenix = {chave(x["dispositivo"]): x["grupo"] for x in catalogo}
    docs = json.loads(leitura.read_text(encoding="utf-8"))["documentos"]
    doc = next(d for d in docs if d["arquivo"] == ARQUIVO)
    outra = {chave(x["dispositivo"]): x["grupo"] for x in doc["penalidades_ou_infracoes"]}
    comum = athenix.keys() & outra.keys()
    diferente = sorted(k for k in comum if athenix[k] != outra[k])
    print(f"REN 846, arts. 9º a 13 ({ARQUIVO})")
    print(
        f"  catálogo Athenix: {len(athenix)} · segunda leitura: {len(outra)} · em comum: {len(comum)}"
    )
    print(
        f"  mesmo grupo: {len(comum) - len(diferente)} de {len(comum)} · grupo diferente: {diferente}"
    )
    print(f"  só no Athenix: {sorted(athenix.keys() - outra.keys())}")
    print(f"  só na segunda leitura: {sorted(outra.keys() - athenix.keys())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
