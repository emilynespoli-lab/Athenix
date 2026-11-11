"""Integridade do gabarito: nenhum trecho esperado pode ser inventado ou ambíguo."""

import pytest

from scripts.avaliar import flat, gold, reference_text, sources

CHECKS = {"obrigacao", "nao_obrigacao", "prazo", "autoria", "vigencia", "revogacao", "remissao"}


@pytest.fixture(scope="module")
def references():
    return {doc_id: flat(reference_text(doc)) for doc_id, doc in sources().items()}


def test_every_quote_exists_once_in_its_source(references):
    spec = gold()
    assert isinstance(spec["revisado_por_humano"], bool)
    assert 10 <= len(spec["casos"]) <= 20
    assert len({c["id"] for c in spec["casos"]}) == len(spec["casos"])
    for case in spec["casos"]:
        text = references[case["doc"]]
        assert text.count(flat(case["trecho"])) == 1, case["id"]
        for extra in case.get("evidencias", []):
            assert flat(extra) in text, (case["id"], extra)
        assert case["esperado"] and set(case["esperado"]) <= CHECKS, case["id"]


def test_gold_covers_more_than_one_norm_and_transmission():
    spec = gold()
    docs = sources()
    assert len({c["doc"] for c in spec["casos"]}) >= 3
    assert {docs[c["doc"]]["tipo"] for c in spec["casos"]} >= {
        "resolucao_normativa",
        "resolucao_homologatoria",
        "decreto",
    }
    assert any("transmissoras" in docs[c["doc"]]["afeta"] for c in spec["casos"])
