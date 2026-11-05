"""Reexecuta a verificação do FAQ público novo a partir de manifesto e bytes preservados."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    from athenix.config import Settings
    from athenix.evidence import recheck
    from athenix.proposals import evaluate, rule_candidates
    from athenix.structure import extract

    manifest = json.loads((ROOT / "docs/public_source.json").read_text(encoding="utf-8"))
    path = (ROOT / manifest["file"]).resolve()
    if not path.is_relative_to((ROOT / ".local/public").resolve()):
        raise SystemExit("Manifesto aponta para fora do corpus local esperado.")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
        raise SystemExit("Hash do documento diverge do manifesto.")
    extracted = extract(raw, "text/html", Settings(), "clarification")
    items = rule_candidates(extracted)
    results = [evaluate(item, extracted, "clarification") for item in items]
    anchors = [a for result in results for a in result["anchors"] if a["state"] == "verified"]
    report = {
        "source": manifest,
        "text_sha256": extracted["text_hash"],
        "extractor": extracted["extractor"],
        "question_units": sum(u["kind"] == "question" for u in extracted["units"]),
        "rule_candidates": len(items),
        "verified_anchors": len(anchors),
        "invalid_verified_anchors": sum(
            not recheck(a, extracted["text"], extracted["units"]) for a in anchors
        ),
        "deadlines_with_date_without_target_norm": sum(
            bool(d["date"]) for r in results for d in r["deadlines"]
        ),
        "all_unit_slices_equal": all(
            u["text"] == extracted["text"][u["start"] : u["end"]] for u in extracted["units"]
        ),
        "paid_calls": 0,
        "legal_quality_evaluated": False,
    }
    folder = ROOT / "artifacts"
    folder.mkdir(exist_ok=True)
    (folder / "public-faq-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "source"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
