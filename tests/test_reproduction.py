from athenix.proposals import evaluate, rule_candidates
from athenix.reproduction import bundle
from athenix.structure import extract
from athenix.config import Settings


def test_deterministic_content_excludes_operational_ids_and_mode():
    raw = b"<html><p>Art. 1 As empresas devem manter registros completos.</p></html>"
    extracted = extract(raw, "text/html", Settings())
    item = rule_candidates(extracted)[0]
    first = evaluate(item, extracted, generator="ai")
    second = evaluate(item, extracted, generator="replay")
    second["run_id"] = "outro-id-operacional"
    a = bundle("arquivo", extracted["text_hash"], [first])
    b = bundle("arquivo", extracted["text_hash"], [second])
    assert a == b
    second["action"] = "interpretação alterada"
    assert bundle("arquivo", extracted["text_hash"], [second])["sha256"] != a["sha256"]
