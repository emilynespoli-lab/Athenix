"""Orquestração da PoC: leitura → (OCR) → comparação → itens → cobertura → artefatos.

Artefatos determinísticos (JSON/MD, sem relógio) são separados do registro operacional
(`run_log.json`), de modo que duas execuções idênticas produzam os mesmos hashes.
"""

import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .. import llm
from . import compare as comparison
from . import reader, semantic

DISCLAIMER = (
    "Cobertura de páginas/dispositivos NÃO mede precisão jurídica nem recall de obrigações: "
    "não há conjunto de referência validado. Itens são candidatos, todos pendentes de revisão humana."
)


def _dump(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def coverage(read, items, discarded):
    pages, units = read["pages"], read["extraction"]["units"]
    verified = [a for i in items for a in i["anchors"] if a["state"] == "verified"]
    total = sum(len(i["anchors"]) for i in items)
    return {
        "document": read["document"],
        "pages": {
            "total": len(pages),
            "by_state": dict(Counter(p["state"] for p in pages)),
            "by_source": dict(Counter(p["source"] for p in pages)),
            "not_extracted": [p["number"] for p in pages if p["state"] == reader.MISSING],
        },
        "text": {"characters": len(read["extraction"]["text"])},
        "structure": {
            "units": len(units),
            "by_kind": dict(Counter(u["kind"] for u in units)),
            "units_without_page": sum(not u["pages"] for u in units),
            "tables_detected": len(read["tables"]),
            "warnings": read["extraction"]["warnings"],
        },
        "items": {
            "total": len(items),
            "by_type": dict(Counter(i["type"] for i in items)),
            "by_validation_state": dict(Counter(i["validation_state"] for i in items)),
            "anchors_total": total,
            "anchors_verified": len(verified),
            "discarded_candidates": len(discarded),
        },
        "disclaimer": DISCLAIMER,
    }


def _md_coverage(cov):
    rows = "\n".join(f"| {k} | {v} |" for k, v in sorted(cov["pages"]["by_state"].items()))
    return (
        f"## {cov['document']['file']}\n\nSHA-256 `{cov['document']['sha256']}`\n\n"
        f"| estado da página | páginas |\n| --- | --- |\n{rows}\n\n"
        f"- Páginas sem texto extraído: {cov['pages']['not_extracted'] or 'nenhuma'}\n"
        f"- Unidades normativas: {cov['structure']['units']}; tabelas detectadas: "
        f"{cov['structure']['tables_detected']}\n"
        f"- Itens: {cov['items']['total']} {cov['items']['by_type']}; âncoras verificadas "
        f"{cov['items']['anchors_verified']}/{cov['items']['anchors_total']}\n\n"
    )


def _md_comparison(cmp):
    c = cmp["counts"]
    lines = [
        "# Comparação dos PDFs\n",
        f"A: `{cmp['a']['file']}` (`{cmp['a']['sha256'][:16]}…`)  \n"
        f"B: `{cmp['b']['file']}` (`{cmp['b']['sha256'][:16]}…`)\n",
        "| categoria | unidades |\n| --- | --- |",
        *(f"| {k} | {v} |" for k, v in c.items()),
        "",
        cmp["note"],
        "",
        "Divergências com `possible_ocr_error=true` podem ser erro de leitura, não diferença real.",
    ]
    return "\n".join(lines) + "\n"


def run(a_path, b_path, out, settings, ocr=None, ai=False, call=llm.call_model):
    started = time.monotonic()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    raw_dir = out / "ai_raw"
    log = {"events": [], "versions": {}, "errors": []}
    state = {"spent": Decimal(0), "calls": []}

    def event(stage, **data):
        log["events"].append({"stage": stage, "at": datetime.now(timezone.utc).isoformat(), **data})

    reads = []
    for path in (a_path, b_path):
        try:
            result = reader.read_pdf(path, settings)
            missing = [p["number"] for p in result["pages"] if p["state"] == reader.MISSING]
            if missing and ocr:
                event("ocr_start", file=Path(path).name, pages=len(missing))
                try:
                    result = reader.read_pdf(path, settings, ocr(path, missing))
                except Exception as error:  # OCR falho não pode apagar a leitura base
                    log["errors"].append(
                        {"stage": "ocr", "file": Path(path).name, "error": repr(error)}
                    )
            event("read", file=Path(path).name, pages=len(result["pages"]))
            reads.append(result)
        except ValueError as error:
            log["errors"].append({"stage": "read", "file": Path(path).name, "error": str(error)})
            raise
    cmp = comparison.compare(*reads)
    event("compare", counts=cmp["counts"])
    covs, manifest = [], {}
    for result in reads:
        doc, extraction, pages = result["document"], result["extraction"], result["pages"]
        items, discarded = semantic.deterministic_items(doc, extraction, pages)
        if ai:
            raw_dir.mkdir(exist_ok=True)
            more, dropped = semantic.ai_items(
                doc, extraction, pages, settings, state, call, raw_dir
            )
            items, discarded = items + more, discarded + dropped
        stem = Path(doc["file"]).stem
        _dump(out / f"extraction_{stem}.json", result)
        _dump(out / f"items_{stem}.json", {"document": doc, "items": items, "discarded": discarded})
        cov = coverage(result, items, discarded)
        covs.append(cov)
        event("items", file=doc["file"], total=len(items))
    _dump(out / "documents.json", [r["document"] for r in reads])
    _dump(out / "comparison.json", cmp)
    _dump(out / "coverage.json", covs)
    (out / "comparison.md").write_text(_md_comparison(cmp), encoding="utf-8", newline="\n")
    (out / "coverage.md").write_text(
        "# Cobertura e lacunas\n\n" + DISCLAIMER + "\n\n" + "".join(_md_coverage(c) for c in covs),
        encoding="utf-8",
        newline="\n",
    )
    for file in sorted(out.glob("*.json")) + sorted(out.glob("*.md")):
        if file.name not in {"run_log.json", "manifest.json"}:
            manifest[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    _dump(out / "manifest.json", manifest)
    from importlib.metadata import version

    log["versions"] = {n: version(n) for n in ("pdfplumber", "httpx")}
    log["ai"] = state.get("ai", {"status": "not_requested" if not ai else "unknown"})
    log["ai_calls"] = state["calls"]
    log["cost_usd_total"] = str(state["spent"])
    log["budget_usd"] = settings.run_budget_usd
    log["seconds"] = round(time.monotonic() - started, 2)
    _dump(out / "run_log.json", log)
    return {"manifest": manifest, "coverage": covs, "comparison": cmp["counts"], "log": log}
