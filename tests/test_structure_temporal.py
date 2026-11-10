from datetime import date

import pytest

from athenix.config import Settings
from athenix.structure import detect_media, extract, segment
from athenix.temporal import compute, rules


def test_html_identity_preserves_canonical_and_ignores_scripts():
    a = extract(
        b"<html><body>Art. 1 A distribuidora deve manter registros.</body><script>x=1</script></html>",
        "text/html",
        Settings(),
    )
    b = extract(
        b"<html><body>Art. 1 A distribuidora deve manter registros.</body><script>x=2</script></html>",
        "text/html",
        Settings(),
    )
    assert a["text_hash"] == b["text_hash"]
    assert all(u["text"] == a["text"][u["start"] : u["end"]] for u in a["units"])


@pytest.mark.parametrize("opener,closer", [("“", "”"), ('"', '"')])
def test_amendment_closes_before_own_article(opener, closer):
    text = f"Art. 1º A Resolução Normativa nº 9001 passa a vigorar com a redação:\n{opener}Art. 23-A. As empresas deverão enviar dados.\nANEXO IV\nTexto citado.{closer}\nArt. 2º As distribuidoras deverão manter registros.\n"
    units, _ = segment(text, [{"number": 1, "start": 0, "end": len(text)}])
    articles = [u for u in units if u["kind"] == "article"]
    assert len([u for u in articles if u["owner"] == "self"]) == 2
    assert articles[1]["owner"] != "self"
    assert articles[-1]["owner"] == "self"


def test_formula_denominator_and_table_letter_not_legal_units():
    text = "Art. 1º Regras:\n44. ...\nTabela 48\ns) valor tabular\n45. ...\nTabela 49\nCoeficiente = numerador\n730\n46. ...\nTabela 50\n"
    units, _ = segment(text, [{"number": 1, "start": 0, "end": len(text)}])
    assert not any(u["kind"] == "letter" for u in units)
    assert not any(u["label"] == "730" for u in units)
    by_id = {u["id"]: u for u in units}
    assert [by_id[u["parent"]]["label"] for u in units if u["kind"] == "table"] == [
        "44",
        "45",
        "46",
    ]


@pytest.mark.parametrize(
    "raw,media", [(b"%PDF-1.7\n", "application/pdf"), (b"<html>texto</html>", "text/html")]
)
def test_media_uses_content(raw, media):
    assert detect_media(raw, 100) == media


@pytest.mark.parametrize("raw", [b"", b"PKZIP", b"x" * 101])
def test_invalid_upload(raw):
    with pytest.raises(ValueError):
        detect_media(raw, 100)


def test_duplicate_annex_links_and_unstructured_warning():
    result = extract(
        b'<html>texto<a href="x">Anexo IV</a><a href="y">Anexo IV</a></html>',
        "text/html",
        Settings(),
    )
    assert len(result["links"]) == 2
    assert any("Estrutura" in w for w in result["warnings"])


def test_pdf_corrupt_error():
    with pytest.raises(ValueError, match="corrompido"):
        extract(b"%PDF-1.7\nconteudo-invalido", "application/pdf", Settings())


@pytest.mark.parametrize(
    "quantity,unit,base,expected",
    [
        (20, "dias", "2026-11-04", "2026-11-24"),
        (2, "meses", "2026-11-04", "2027-01-04"),
        (1, "meses", "2027-01-31", "2027-02-28"),
        (1, "anos", "2024-02-29", "2025-02-28"),
    ],
)
def test_dates_synthetic_arithmetic(quantity, unit, base, expected):
    assert compute(quantity, unit, date.fromisoformat(base)).isoformat() == expected


def test_event_and_retention_do_not_share_landmark():
    values = rules(
        "As empresas deverão manter por 5 anos; enviar em 30 dias contados da publicação das instruções.",
        "u",
        [{"kind": "publication", "date": "2026-11-04"}],
    )
    assert len(values) == 2
    assert values[0]["landmark"] == "unknown"
    assert values[1]["state"] == "awaiting_event"
    assert all(v["date"] is None for v in values)


def test_clarification_uses_norm_not_page_and_missing_target_is_unknown():
    page = [{"kind": "publication", "date": "2026-09-01"}]
    norm = [{"kind": "publication", "date": "2026-01-10"}]
    text = "O prazo é de 20 dias contados da publicação."
    value = rules(text, "u", page, clarification=True, target_dates=norm)[0]
    assert value["date"] == "2026-01-30"
    assert value["state"] == "provisional"
    assert rules(text, "u", page, clarification=True)[0]["date"] is None


def test_inheritance_business_days_direction_and_missing_publication():
    dates = [{"kind": "publication", "date": "2026-11-04"}]
    assert (
        rules("I - enviar em 20 dias", "u", dates, "contados da publicação:")[0]["date"]
        == "2026-11-24"
    )
    assert rules("enviar em 10 dias úteis da publicação", "u", dates)[0]["date"] is None
    assert rules("até 20 dias antes da publicação", "u", dates)[0]["date"] == "2026-10-15"
    assert rules("vigência em 20 dias após publicação", "u", [])[0]["date"] is None


def test_conflicting_dates_do_not_select_first():
    dates = [{"kind": "publication", "date": d} for d in ("2026-11-04", "2026-11-05")]
    assert rules("20 dias da publicação", "u", dates)[0]["date"] is None
