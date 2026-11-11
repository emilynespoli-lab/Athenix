"""Extrai, pelo pipeline do Athenix, os dispositivos da REN 846 e das normas que a alteram.

Uso: python scripts/extrair_parametros.py artifacts/parametros.json
Cada dispositivo sai com citação literal, estado da âncora (segunda leitura) e alertas:
algarismo x extenso divergente e texto riscado (redação revogada) no PDF compilado.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pdfplumber  # noqa: E402

from athenix.config import Settings  # noqa: E402
from athenix.evidence import key, verify  # noqa: E402
from athenix.poc import reader  # noqa: E402
from athenix.temporal import NUMBERS  # noqa: E402

DOCS = {
    "846": ROOT / "tests/fontes_impacto/ren2019846_compilada.pdf",
    "1137": ROOT / "tests/norma_poc/ren20251137.pdf",
    "1148": ROOT / "tests/fontes_impacto/ren20261148.pdf",
    "1174": ROOT / "tests/fontes_impacto/ren20261174.pdf",
}
FOOTER = re.compile(r"\s*Leis\.org/aneel - [^\n]*(?:\n\s*\d+/\d+)?|\n\s*\d+/\d+\s*(?=\n|$)")
LABEL = re.compile(
    r"^\s*(?:Art\.?\s*\d+[º°]?(?:-[A-Z])?\.?|§\s*\d+[º°]?|Parágrafo único\.|[IVXLCDM]+\s*-|[a-z]\))\s*"
)
# Ignora faixas ("1% a 5% (um a cinco por cento)"): o extenso descreve a faixa inteira.
PCT = re.compile(r"(?<!%\sa\s)(\d+(?:,\d+)?)\s*%\s*\(([^)]+)\)")
FRACTION = {"décimos": 10, "centésimos": 100, "milésimos": 1000}


def words(text):
    tokens = [t for t in re.split(r"\s+e\s+|\s+", text.lower()) if t]
    return sum(NUMBERS[t] for t in tokens) if all(t in NUMBERS for t in tokens) else None


def spelled(text):
    """Valor de 'cento e vinte e cinco milésimos por cento', 'zero vírgula zero um por cento'."""
    text = re.sub(r"\s*por\s+cento\s*$", "", text.strip().lower())
    for name, div in FRACTION.items():
        if text.endswith(name):
            n = words(text[: -len(name)])
            return None if n is None else n / div
    if "vírgula" in text:
        whole, frac = [p.strip() for p in text.split("vírgula")]
        zeros = len(re.match(r"(zero\s+)*", frac + " ").group(0).split())
        rest = re.sub(r"^(zero\s+)*", "", frac)
        w = 0 if whole == "zero" else words(whole)
        f = words(rest) if rest else 0
        if w is None or f is None:
            return None
        return w + f / 10 ** (zeros + len(str(f)))
    return words(text)


def mismatches(text):
    out = []
    for m in PCT.finditer(text):
        digits = float(m.group(1).replace(",", "."))
        value = spelled(m.group(2))
        if value is None or abs(value - digits) > 1e-9:
            out.append(
                {"algarismo": m.group(1) + "%", "extenso": m.group(2), "extenso_lido": value}
            )
    return out


def struck_spans(path):
    """Linhas horizontais finas cruzando o meio dos caracteres = texto riscado (redação revogada).

    shortcut: o dispositivo é marcado pelo início do texto; redação nova com o mesmo início da
    antiga, ou texto idêntico em outro artigo, sai marcado também. Evoluir: marcar na extração.
    """
    found = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            rules = [ln for ln in page.lines if abs(ln["top"] - ln["bottom"]) < 1.5]
            if not rules:
                continue
            for w in page.extract_words():
                mid = (w["top"] + w["bottom"]) / 2
                if any(
                    r["x0"] <= w["x0"] and w["x1"] <= r["x1"] + 1 and abs(r["top"] - mid) < 3
                    for r in rules
                ):
                    found.append(w["text"])
    return key(" ".join(found))


def label_path(unit, by_id):
    labels = []
    while unit:
        labels.append(unit["label"])
        unit = by_id.get(unit["parent"])
    return " > ".join(reversed(labels))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    report = {}
    for name, path in DOCS.items():
        content = path.read_bytes()
        read = reader.read_pdf(path, Settings())
        ex = read["extraction"]
        by_id = {u["id"]: u for u in ex["units"]}
        struck = struck_spans(path)
        units = []
        for u in ex["units"]:
            # Rodapé da página no meio do dispositivo: cita cada pedaço contíguo e verifica um a um.
            parts = [p.strip() for p in FOOTER.split(u["text"]) if p and p.strip()]
            cited, states = [], []
            for i, part in enumerate(parts):
                anchor = verify(
                    part, u["id"], ex["units"], ex.get("text_hash"), source=ex.get("source")
                )
                if anchor["state"] != "verified" and i == 0 and LABEL.match(part):
                    # pdfium lê o selo "Art. N" fora do lugar: confirma o texto sem o rótulo.
                    bare = LABEL.sub("", part, count=1)
                    retry = verify(
                        bare, u["id"], ex["units"], ex.get("text_hash"), source=ex.get("source")
                    )
                    if retry["state"] == "verified":
                        anchor = retry | {
                            "note": "rótulo do dispositivo não confirmado pela 2ª leitura"
                        }
                cited.append(" ".join(part.split()))
                states.append(anchor)
            state = (
                "verified"
                if states and all(a["state"] == "verified" for a in states)
                else (states[0]["state"] if states else "invalid")
            )
            units.append(
                {
                    "path": label_path(u, by_id),
                    "kind": u["kind"],
                    "quote": " […] ".join(cited),
                    "state": state,
                    "reason": next((a.get("reason") for a in states if a.get("reason")), None),
                    "note": next((a.get("note") for a in states if a.get("note")), None),
                    "struck": bool(struck)
                    and len(key(cited[0] if cited else "")) > 20
                    and key(cited[0])[:60] in struck,
                    "pct_mismatch": mismatches(u["text"]),
                }
            )
        report[name] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "units": units,
            "struck_chars": len(struck),
        }
    out = sys.argv[1]
    Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, r in report.items():
        states = {}
        for u in r["units"]:
            states[u["state"]] = states.get(u["state"], 0) + 1
        print(
            name,
            r["sha256"][:12],
            "unidades",
            len(r["units"]),
            states,
            "riscado",
            r["struck_chars"],
            "riscadas",
            sum(u["struck"] for u in r["units"]),
        )
        for u in r["units"]:
            if u["pct_mismatch"]:
                print("  DIVERGÊNCIA algarismo×extenso", u["path"], u["pct_mismatch"])


if __name__ == "__main__":
    main()
