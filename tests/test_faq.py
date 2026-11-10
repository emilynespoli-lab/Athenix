from athenix.config import Settings
from athenix.proposals import evaluate, rule_candidates
from athenix.structure import extract


def test_main_content_and_questions_without_menu_contamination():
    raw = """<html><head><title>FAQ sintético</title></head><body><nav>Você deve acessar a conta</nav><main><div id="content-core"><p>1.1 Qual é a obrigação?</p><p>As distribuidoras deverão manter os registros completos.</p><p>1.2 Qual é o prazo?</p><p>O prazo é de até 20 dias contados da publicação.</p></div></main></body></html>""".encode()
    extracted = extract(raw, "text/html", Settings(), "clarification")
    assert "acessar a conta" not in extracted["text"]
    assert len([u for u in extracted["units"] if u["kind"] == "question"]) == 2
    assert all(u["text"] == extracted["text"][u["start"] : u["end"]] for u in extracted["units"])
    items = rule_candidates(extracted)
    assert len(items) == 2
    results = [evaluate(item, extracted, "clarification") for item in items]
    assert all(
        any(o["kind"] == "clarification_only" for o in result["objections"]) for result in results
    )
    assert all(d["date"] is None for result in results for d in result["deadlines"])
