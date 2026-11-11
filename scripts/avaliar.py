"""Avalia o pipeline determinístico contra tests/gabarito. Mede; não certifica.

O texto de referência não usa o extrator do sistema: PDF pelo pypdfium2 (motor diferente do
pdfplumber do extrator) e HTML pelo HTMLParser da biblioteca padrão com a codificação conferida à
mão em fontes.json. A comparação ignora espaços, pois os motores divergem só neles.
Uso: python scripts/avaliar.py [--rotulo baseline] [--saida artifacts/avaliacao]
"""

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "tests" / "gabarito"
DEONTIC = {"obligation", "permission", "prohibition"}
BLOCK = {"p", "br", "div", "tr", "li", "table", "h1", "h2", "h3", "h4", "h5", "h6"}
UNIFY = str.maketrans({c: '"' for c in "“”„‟"} | {c: "'" for c in "‘’"} | {c: "-" for c in "–—"})


def flat(text):
    text = unicodedata.normalize("NFC", text or "").translate(UNIFY)
    return re.sub(r"\s+", "", text).casefold()


def overlaps(a, b):
    a, b = flat(a), flat(b)
    return bool(a and b) and (a in b or b in a)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        self.skip += tag in {"script", "style"}
        if tag in BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        self.skip -= tag in {"script", "style"}
        if tag in BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def sources():
    meta = json.loads((GOLD / "fontes.json").read_text(encoding="utf-8"))
    docs = {}
    for doc in meta["documentos"]:
        path = (GOLD / doc["arquivo"]).resolve()
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != doc["sha256"]:
            raise SystemExit(f"Hash divergente: {path.name}")
        docs[doc["id"]] = doc | {"path": path, "content": content}
    return docs


def reference_text(doc):
    if doc["formato"] == "text/html":
        parser = _Text()
        parser.feed(doc["content"].decode(doc["codificacao"].split()[0]))
        return "".join(parser.parts)
    import pypdfium2

    pdf = pypdfium2.PdfDocument(doc["content"])
    try:
        return "\n".join(page.get_textpage().get_text_range() for page in pdf)
    finally:
        pdf.close()


def gold():
    return json.loads((GOLD / "gabarito.json").read_text(encoding="utf-8"))


def run_system(doc):
    from athenix.config import Settings
    from athenix.poc import reader, semantic
    from athenix.structure import extract

    settings = Settings()
    document = {"file": doc["path"].name, "sha256": doc["sha256"]}
    if doc["formato"] == "application/pdf":
        read = reader.read_pdf(doc["path"], settings)
        extraction, pages = read["extraction"], read["pages"]
    else:
        extraction = extract(doc["content"], "text/html", settings, "norm")
        pages = [p | {"state": "faithful", "reasons": []} for p in extraction["pages"]]
    items, _ = semantic.deterministic_items(document, extraction, pages)
    return extraction, items


def _owner(value):
    return "self" if value == "self" else re.sub(r"\D", "", value or "")


def check(case, extraction, items):
    """Retorna {verificação: (acerto, detalhe)} para cada campo esperado do caso."""
    expected, trecho = case["esperado"], case["trecho"]
    # Um item cobre o trecho se qualquer âncora verificada dele (inclusive a do caput herdado) o cobre.
    near = [
        i
        for i in items
        if any(overlaps(trecho, a["quote"]) for a in i["anchors"] if a.get("state") == "verified")
    ]
    out = {}
    if "obrigacao" in expected:
        want = expected["obrigacao"]
        found = [
            (i["interpretation"]["modality"], i["interpretation"]["subject"])
            for i in near
            if i["type"] in DEONTIC
        ]
        ok = any(
            m == want["modalidade"]
            and ("sujeito" not in want or want["sujeito"].casefold() in s.casefold())
            for m, s in found
        )
        out["obrigacao"] = (ok, found or "nenhum item deôntico no trecho")
    if expected.get("nao_obrigacao"):
        wrong = [i["type"] for i in near if i["type"] in DEONTIC]
        out["nao_obrigacao"] = (not wrong, wrong or "nenhum")
    if "prazo" in expected:
        want = expected["prazo"]
        found = [i["interpretation"] for i in near if i["type"] == "deadline"]
        if "periodico" in want:
            ok = any(d.get("unit") == "periodic" for d in found)
        elif want.get("sem_data"):
            ok = not any(d.get("date") for d in found)
        else:
            ok = any(
                d.get("quantity") == want["quantidade"]
                and str(d.get("unit", "")).startswith(want["unidade"][:3])
                and d.get("landmark") == want["marco"]
                and d.get("date") == want["data"]
                for d in found
            )
        brief = [
            (d.get("quantity"), d.get("unit"), d.get("landmark"), d.get("date")) for d in found
        ]
        out["prazo"] = (ok, brief or "nenhum prazo no trecho")
    if "autoria" in expected:
        head = flat(trecho)[:60]
        units = [u for u in extraction["units"] if head in flat(u["text"])]
        owners = sorted({_owner(u["owner"]) for u in units})
        out["autoria"] = (owners == [expected["autoria"]], owners or "trecho não localizado")
    if "vigencia" in expected:
        want = expected["vigencia"]["data"]
        dates = [
            d["date"]
            for d in extraction["dates"]
            # A citação de data é a linha inteira; basta conter o início do trecho.
            if d["kind"] == "effective"
            and (flat(trecho)[:40] in flat(d["quote"]) or overlaps(trecho, d["quote"]))
        ]
        ok = want in dates if want else not dates
        out["vigencia"] = (ok, dates or "nenhuma data de vigência")
    if expected.get("revogacao"):
        ok = any(i["type"] == "revocation" for i in near)
        out["revogacao"] = (ok, "revocation" if ok else "sem item de revogação")
    if "remissao" in expected:
        refs = [i["reference"] for i in near if i["type"] == "reference"]
        ok = any(r.get("target") for r in refs)
        out["remissao"] = (ok, [r.get("target") for r in refs] or "sem remissão no trecho")
    return out


def evaluate():
    docs, spec = sources(), gold()
    results, global_items = [], {}
    for doc_id, doc in docs.items():
        extraction, items = run_system(doc)
        reference = flat(reference_text(doc))
        anchors = [a for i in items for a in i["anchors"]]
        verified = [a for a in anchors if a["state"] == "verified"]
        global_items[doc_id] = {
            "itens": len(items),
            "citacoes_corretas": sum(
                bool(i["literal_text"]) and flat(i["literal_text"]) in reference for i in items
            ),
            "sem_fonte": sum(
                not i["literal_text"] or i["validation_state"] != "pending_human_review"
                for i in items
            ),
            "ancoras": {
                s: sum(a["state"] == s for a in anchors) for s in ("verified", "pending", "invalid")
            },
            # Verificada pelo sistema, mas o trecho não existe na fonte lida por outro motor.
            "falsas_verificadas": sum(flat(a["quote"]) not in reference for a in verified),
        }
        for case in (c for c in spec["casos"] if c["doc"] == doc_id):
            checks = check(case, extraction, items)
            results.append(
                {
                    "id": case["id"],
                    "doc": doc_id,
                    "dispositivo": case["dispositivo"],
                    "verificacoes": {
                        k: {"acerto": v[0], "obtido": v[1]} for k, v in checks.items()
                    },
                }
            )
    by_check = {}
    for result in results:
        for name, value in result["verificacoes"].items():
            hits, total = by_check.get(name, (0, 0))
            by_check[name] = (hits + value["acerto"], total + 1)
    total_items = sum(g["itens"] for g in global_items.values()) or 1
    return {
        "gabarito_revisado_por_humano": spec["revisado_por_humano"],
        "casos": results,
        "por_verificacao": {k: {"acertos": h, "total": t} for k, (h, t) in by_check.items()},
        "casos_totalmente_corretos": sum(
            all(v["acerto"] for v in r["verificacoes"].values()) for r in results
        ),
        "por_documento": global_items,
        "taxa_citacoes_corretas": round(
            sum(g["citacoes_corretas"] for g in global_items.values()) / total_items, 4
        ),
        "taxa_sem_fonte": round(
            sum(g["sem_fonte"] for g in global_items.values()) / total_items, 4
        ),
        "aviso": "Gabarito sem revisão humana; precisão local (só dispositivos anotados), não global.",
    }


def markdown(report, label):
    lines = [
        f"# Avaliação — {label}\n",
        report["aviso"] + "\n",
        "| verificação | acertos |",
        "| --- | --- |",
    ]
    lines += [
        f"| {k} | {v['acertos']}/{v['total']} |" for k, v in report["por_verificacao"].items()
    ]
    lines += [
        "",
        f"Casos totalmente corretos: {report['casos_totalmente_corretos']}/{len(report['casos'])}  ",
        f"Citações literais encontradas na fonte (todos os itens): {report['taxa_citacoes_corretas']:.1%}  ",
        f"Itens sem âncora verificada: {report['taxa_sem_fonte']:.1%}\n",
        "| caso | dispositivo | falhas |",
        "| --- | --- | --- |",
    ]
    for r in report["casos"]:
        fails = [f"{k}: {v['obtido']}" for k, v in r["verificacoes"].items() if not v["acerto"]]
        lines.append(f"| {r['id']} | {r['dispositivo']} | {'; '.join(map(str, fails)) or 'ok'} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rotulo", default="atual")
    parser.add_argument("--saida", default=str(ROOT / "artifacts" / "avaliacao"))
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    report = evaluate()
    out = Path(args.saida)
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=1, default=str)
    (out / f"{args.rotulo}.json").write_text(text + "\n", encoding="utf-8")
    (out / f"{args.rotulo}.md").write_text(markdown(report, args.rotulo), encoding="utf-8")
    print(json.dumps(report["por_verificacao"], ensure_ascii=False))
    print("casos corretos:", report["casos_totalmente_corretos"], "/", len(report["casos"]))
    print(
        "citações corretas:",
        report["taxa_citacoes_corretas"],
        "sem fonte:",
        report["taxa_sem_fonte"],
    )


if __name__ == "__main__":
    main()
