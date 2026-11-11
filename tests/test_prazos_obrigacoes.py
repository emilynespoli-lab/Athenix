"""Etapa 1 (itens 9 e 10): prazos e obrigações que mudam o resultado da demo e do impacto."""

import pytest

from athenix.config import Settings
from athenix.poc import reader
from athenix.poc.semantic import deterministic_items
from athenix.structure import act_dates, extract, segment
from athenix.temporal import landmark, rules
from scripts.avaliar import quality, sources

PUB = [{"kind": "publication", "date": "2024-06-21"}]
REN_SHA256 = "4a581592e981158bb9a9ebbbed10a019d3c06399fd2890389bf88f3609cc5887"


@pytest.fixture(scope="module")
def ren():
    doc = sources()["ren20251137"]
    assert doc["sha256"] == REN_SHA256
    read = reader.read_pdf(doc["path"], Settings())
    items, _ = deterministic_items(read["document"], read["extraction"], read["pages"])
    return read, items


def test_inherited_deadline_counted_once(ren):
    _, items = ren
    # Antes: alíneas a)–m) do item 132 repetiam os 60 dias do caput (12 prazos duplicados).
    assert quality(items)["prazos_duplicados"] == 0
    sixty = [i for i in items if i["type"] == "deadline" and i["interpretation"]["quantity"] == 60]
    assert len({i["locator"]["unit_id"] for i in sixty}) == len(sixty)


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


@pytest.mark.parametrize(
    "text,expected",
    [
        ("deverão informar à ANEEL e ao ONS, em janeiro e, sempre que houver alteração", "em janeiro"),
        ("devem realizar comunicações formais, com periodicidade anual, aos representantes", "com periodicidade anual"),
        ("Os indicadores devem ser apurados mensalmente, considerando o mês civil", "mensalmente"),
        ("deverá ser revisado a cada ano pela distribuidora", "a cada ano"),
    ],
)  # fmt: skip
def test_periodic_obligation_has_own_representation(text, expected):
    [record] = [r for r in rules(text, "u", PUB) if r["unit"] == "periodic"]
    assert (record["event"], record["state"], record["date"]) == (expected, "recurring", None)


def test_month_with_year_is_not_recurring():
    assert not [
        r for r in rules("deverá entregar em janeiro de 2026", "u", PUB) if r["unit"] == "periodic"
    ]


def test_real_reh_january_report_is_recurring():
    doc = sources()["reh20243348"]
    assert doc["sha256"] == "c074ee9a23af3a633819135bd7c9b7a21106fb7a617f815af7de2a99e68e0f5c"
    read = reader.read_pdf(doc["path"], Settings())
    items, _ = deterministic_items(read["document"], read["extraction"], read["pages"])
    periodic = [i["interpretation"]["event"] for i in items if i["type"] == "deadline"
                and i["interpretation"]["unit"] == "periodic"]  # fmt: skip
    # Antes: 0 prazos recorrentes; o § 1º do Art. 3º (informar "em janeiro") ficava sem prazo.
    assert "em janeiro" in periodic


def test_heading_closes_previous_unit_and_is_not_penalty():
    text = (
        "Art. 1º A distribuidora deve manter canais exclusivos.\n"
        "Seção VII\nDas Sanções e Penalidades\n"
        "Art. 2º Constitui infração o descumprimento do art. 1º.\n"
        "Seção 4.9 deste Módulo, as distribuidoras devem seguir o plano.\n"
    )
    units, _ = segment(text, [{"number": 1, "start": 0, "end": len(text)}])
    by_label = {u["label"]: u for u in units}
    assert "Penalidades" not in by_label["1º"]["text"]
    assert by_label["Seção VII"]["kind"] == "heading" and by_label["2º"]["parent"] is None
    assert "Seção 4.9" not in by_label  # frase quebrada no início da linha não é título


def test_real_penalty_only_from_own_text(ren):
    _, items = ren
    penalties = [i for i in items if i["type"] == "penalty"]
    # Antes: 4 (o § 7º do Art. 371-A herdava "Seção VII Das Sanções e Penalidades"). Depois: 3.
    assert len(penalties) == 3
    assert all("Constitui infração" in i["literal_text"] for i in penalties)


def test_heading_never_swallows_normative_text():
    # Art. quebrado pelo HTML ("Art. \n 2º") após o título não pode sumir da detecção.
    text = "CAPÍTULO I\nDOS CRITÉRIOS DE\nAVALIAÇÃO\nArt. \n\t2º A concessionária deverá enviar os dados anuais.\n"
    units, _ = segment(text, [{"number": 1, "start": 0, "end": len(text)}])
    heading = next(u for u in units if u["kind"] == "heading")
    assert "deverá" not in heading["text"] and "AVALIAÇÃO" in heading["text"]
    assert any("deverá" in u["text"] and u["kind"] != "heading" for u in units)


def test_duty_and_permission_in_same_unit_are_both_kept():
    from athenix.proposals import rule_candidates

    page = (
        "<html><body><p>Art. 3º A comunicação ao consumidor deve ser realizada por SMS em até uma hora."
        " Adicionalmente, as distribuidoras podem utilizar os seguintes canais:</p>"
        "<p>a) aplicativo próprio;</p><p>b) rádio.</p>"
        "<p>Art. 4º Conforme o Art. 3º, o relatório deve ser enviado ao ONS.</p></body></html>"
    )
    found = [
        (c["modality"], c["action"])
        for c in rule_candidates(extract(page.encode(), "text/html", Settings()))
    ]
    # Antes: o caput enumera ("…canais:") e era descartado inteiro, levando junto o dever do SMS.
    assert (
        "duty",
        "Art. 3º A comunicação ao consumidor deve ser realizada por SMS em até uma hora.",
    ) in found
    assert [m for m, a in found if a.startswith(("a)", "b)"))] == ["permission", "permission"]
    # "Art. 3º" no meio da frase não é fim de frase.
    assert ("duty", "Art. 4º Conforme o Art. 3º, o relatório deve ser enviado ao ONS.") in found


def test_real_items_106_and_110_keep_their_duties(ren):
    _, items = ren
    duties = [
        " ".join((i["literal_text"] or "").split()) for i in items if i["type"] == "obligation"
    ]
    # Antes: item 110 sem dever; item 106 inteiro classificado como permissão.
    assert any(d.startswith("110. A comunicação de que trata o item 105 deve") for d in duties)
    assert any(
        d.startswith("106. As distribuidoras de energia devem disponibilizar") for d in duties
    )


@pytest.mark.parametrize(
    "context,expected",
    [
        ("132. Ao acionar o mecanismo de Cessão Emergencial de recursos, a distribuidora cessionária deve enviar", "a distribuidora cessionária"),
        ("b) a cessionária deverá manter dossiê", "a cessionária"),
        ("II - As concessionárias deverão informar", "As concessionárias"),
        ("Art 10. A Agência poderá instituir Comitê", "A Agência"),
        ("As distribuidoras, permissionárias e cooperativas devem enviar", "As distribuidoras, permissionárias e cooperativas"),
    ],
)  # fmt: skip
def test_subject_without_label_or_leading_clause(context, expected):
    from athenix.proposals import subject_of

    assert subject_of(context) == expected


def test_real_subjects_have_no_labels(ren):
    _, items = ren
    # Antes: 135 sujeitos começavam por rótulo ("132.", "a)", "I -"). Depois: 0.
    assert quality(items)["sujeitos_com_rotulo"] == 0
