import pytest
from hypothesis import given, strategies as st

from athenix.db import digest
from athenix.evidence import recheck, verify


def corpus(
    first="As distribuidoras deverão manter todos os registros.",
    second="As transmissoras deverão enviar os dados completos.",
):
    text = first + "\n" + second
    units = [
        {"id": "a", "text": first, "start": 0, "end": len(first)},
        {"id": "b", "text": second, "start": len(first) + 1, "end": len(text)},
    ]
    return text, units, digest(text.encode())


def test_exact_independent_recalculation():
    text, units, hashed = corpus()
    anchor = verify(units[0]["text"], "a", units, hashed)
    assert anchor["state"] == "verified"
    assert recheck(anchor, text, units)
    anchor["end"] -= 1
    assert not recheck(anchor, text, units)


def test_other_unit_stays_pending():
    _, units, hashed = corpus()
    anchor = verify(units[1]["text"], "a", units, hashed)
    assert anchor["state"] == "pending"
    assert anchor["unit_id"] == "a"
    assert anchor["candidates"] == ["b"]


@pytest.mark.parametrize(
    "quote",
    [
        "As distribuidoras deverão menter todos os registros.",
        "Devem guardar a documentação integral.",
    ],
)
def test_changed_word_or_paraphrase_invalid(quote):
    _, units, hashed = corpus()
    assert verify(quote, "a", units, hashed)["state"] == "invalid"


def test_short_ambiguous_and_unknown():
    _, units, hashed = corpus()
    assert verify("registros", "a", units, hashed)["state"] == "pending"
    assert verify(units[0]["text"], "missing", units, hashed)["state"] == "invalid"
    text, units, hashed = corpus(
        "A distribuidora deverá enviar dados. A distribuidora deverá enviar dados."
    )
    assert verify("A distribuidora deverá enviar dados.", "a", units, hashed)["state"] == "pending"


def test_normalization_maps_back_without_accent_or_case_folding():
    text, units, hashed = corpus("A distribuidora deverá   manter “registros” – completos.")
    anchor = verify('A distribuidora deverá manter "registros" - completos.', "a", units, hashed)
    assert anchor["method"] == "normalized"
    assert anchor["quote"] == units[0]["text"]
    assert recheck(anchor, text, units)
    assert (
        verify('A distribuidora devera manter "registros" - completos.', "a", units, hashed)[
            "state"
        ]
        == "invalid"
    )


@given(
    st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")), min_size=18, max_size=150
    )
)
def test_unicode_anchor_property(value):
    text, units, hashed = corpus(value, "outro dispositivo")
    anchor = verify(value, "a", units, hashed)
    assert recheck(anchor, text, units)
