"""Verificador independente dos artefatos da PoC: só stdlib, sem importar o pipeline.

    python scripts/verify_poc.py artifacts/poc [tests/norma_poc]
Confere: manifesto, hashes dos originais, ids únicos, trechos literais no texto canônico (offsets,
hash do trecho e do texto), páginas válidas e coerência das unidades. Sai com código 1 se falhar.
"""

import hashlib
import json
import sys
from pathlib import Path


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(out, originals=None):
    out, errors, stats = Path(out), [], {"items": 0, "anchors": 0, "units": 0}
    manifest = load(out / "manifest.json")
    for name, expected in manifest.items():
        if sha((out / name).read_bytes()) != expected:
            errors.append(f"manifesto: hash divergente em {name}")
    documents = {d["file"]: d for d in load(out / "documents.json")}
    for file, doc in documents.items():
        if originals and sha((Path(originals) / file).read_bytes()) != doc["sha256"]:
            errors.append(f"original alterado ou diferente: {file}")
        stem = Path(file).stem
        extraction = load(out / f"extraction_{stem}.json")
        data = load(out / f"items_{stem}.json")
        text, units = extraction["extraction"]["text"], extraction["extraction"]["units"]
        if sha(text) != extraction["extraction"]["text_hash"]:
            errors.append(f"{file}: hash do texto canônico não confere")
        pages = {p["number"] for p in extraction["pages"]}
        by_id = {u["id"]: u for u in units}
        for unit in units:
            stats["units"] += 1
            if text[unit["start"] : unit["end"]] != unit["text"]:
                errors.append(f"{file}: unidade {unit['id']} difere do recorte do texto")
            if not set(unit["pages"]) <= pages:
                errors.append(f"{file}: unidade {unit['id']} cita página inexistente")
        ids = [i["id"] for i in data["items"]]
        if len(ids) != len(set(ids)):
            errors.append(f"{file}: ids de itens repetidos")
        for item in data["items"]:
            stats["items"] += 1
            if item["document"]["sha256"] != doc["sha256"]:
                errors.append(f"{file}: item {item['id']} aponta para outro documento")
            if item["validation_state"] == "validated":
                errors.append(f"{file}: item {item['id']} marcado validado sem revisão humana")
            unit = by_id.get(item["locator"]["unit_id"])
            if unit is None or item["pages"] != unit["pages"]:
                errors.append(f"{file}: item {item['id']} com unidade/páginas incoerentes")
            for anchor in item["anchors"]:
                stats["anchors"] += 1
                if anchor["state"] != "verified":
                    continue
                literal = text[anchor["start"] : anchor["end"]]
                owner = by_id.get(anchor["unit_id"])  # âncora herdada pertence à unidade do pai
                ok = (
                    owner is not None
                    and literal == anchor["quote"]
                    and sha(literal) == anchor["quote_hash"]
                    and sha(text) == anchor["text_hash"]
                    and owner["start"] <= anchor["start"] < anchor["end"] <= owner["end"]
                )
                if not ok:
                    errors.append(f"{file}: âncora de {item['id']} não reproduz o trecho literal")
            if item["literal_text"] is not None and item["literal_text"] not in text:
                errors.append(f"{file}: literal_text de {item['id']} ausente do texto canônico")
    print(json.dumps({"stats": stats, "errors": errors[:20], "error_count": len(errors)}))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
