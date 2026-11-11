"""Etapa 1 (itens 9 e 10): prazos e obrigações que mudam o resultado da demo e do impacto."""

import pytest

from athenix.config import Settings
from athenix.structure import act_dates, extract
from athenix.temporal import landmark, rules
from scripts.avaliar import sources

PUB = [{"kind": "publication", "date": "2024-06-21"}]


@pytest.mark.parametrize(
    "text,amount,kind,direction",
    [
        ("deverá assiná-lo no prazo de noventa dias, contado da convocação", 90, "event", 1),
        ("no prazo de cento e vinte dias, contado da publicação deste Decreto", 120, "publication", 1),
        ("com a antecedência de, no mínimo, trinta e seis meses do advento do termo", 36, "event", -1),
        ("por até vinte e quatro meses, contados do respectivo termo contratual", 24, "event", 1),
        ("no prazo de 30 (trinta) dias, contado da publicação da minuta do termo aditivo", 30, "event", 1),
    ],
)  # fmt: skip
def test_number_words_and_own_vs_other_publication(text, amount, kind, direction):
    [record] = rules(text, "u", PUB)
    assert (record["quantity"], record["landmark"], record["direction"]) == (
        amount,
        kind,
        direction,
    )
    # Só a publicação da própria norma gera data; publicação de outro ato aguarda o evento.
    assert (record["date"] is not None) == (kind == "publication")


def test_wrapped_line_keeps_landmark():
    # Antes: a quebra de linha cortava "da publicação" e o marco ficava desconhecido.
    [record] = rules(
        "no prazo de cento e vinte dias, contado\n\t\tda publicação deste Decreto.", "u", PUB
    )
    assert (record["landmark"], record["date"]) == ("publication", "2024-10-19")


@pytest.mark.parametrize(
    "text,kind",
    [
        ("contados da publicação das instruções pela ANEEL", "event"),
        ("contados da publicação do procedimento", "event"),
        ("a partir da publicação, para implementar", "publication"),
        ("contados da publicação desta Resolução", "publication"),
        ("a partir do primeiro mês de vigência dos termos aditivos", "event"),
        ("na data de entrada em vigor", "effective"),
    ],
)
def test_landmark_distinguishes_own_act_from_other_events(text, kind):
    assert landmark(text)[0] == kind


def test_place_and_date_is_signature_not_publication():
    text = "Art. 23. Este Decreto entra em vigor na data de sua publicação.\nBrasília, 20 de junho de 2024.\nEste texto não substitui o publicado no DOU de 21.6.2024."
    assert [(d["kind"], d["date"]) for d in act_dates(text)] == [
        ("signature", "2024-06-20"),
        ("publication", "2024-06-21"),
        ("effective", "2024-06-21"),
    ]


def test_real_decree_deadlines_from_number_words():
    doc = sources()["dec12068"]
    assert doc["sha256"] == "74f0e0d54568761a373291a350161c7ddab6094918d5158b0d9287f44a849ee0"
    extraction = extract(doc["content"], "text/html", Settings(), "norm")
    found = {
        (d["quantity"], d["landmark"], d["date"])
        for unit in extraction["units"]
        for d in rules(unit["text"], unit["id"], extraction["dates"])
    }
    # Antes: nenhuma quantidade por extenso era lida (0 prazos de 90/120/36 no Decreto).
    assert {(90, "event", None), (120, "publication", "2024-10-19"), (36, "event", None)} <= found
