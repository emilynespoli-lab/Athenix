"""Fontes do módulo de impacto (REN 846 e alteradoras): integridade e estrutura citável."""

import hashlib
import json
from pathlib import Path

import pytest

from athenix.config import Settings
from athenix.poc import reader
from athenix.structure import segment

DIR = Path(__file__).parent / "fontes_impacto"
# PDFs do Leis.org ficam fora do repositório público até confirmar os termos de uso.
SEM_PDF = pytest.mark.skipif(
    not (DIR / "ren2019846_compilada.pdf").exists(), reason="PDF do Leis.org fora do repositório"
)


@SEM_PDF
def test_hashes_match_provenance():
    for doc in json.loads((DIR / "fontes.json").read_text(encoding="utf-8"))["documentos"]:
        assert hashlib.sha256((DIR / doc["arquivo"]).read_bytes()).hexdigest() == doc["sha256"]


def test_lowercase_art_at_line_start_is_a_remission_not_an_article():
    text = (
        "Art. 16. Constitui infração:\n"
        "I - a realização de obras, observado o disposto no\n"
        "art. 8º da Lei nº 9.074, de 7 de julho de 1995; e\n"
        "§ 1º O descumprimento implicará multa diária.\n"
    )
    units, _ = segment(text, [{"number": 1, "start": 0, "end": len(text)}])
    by_id = {u["id"]: u for u in units}
    assert [u["label"] for u in units if u["kind"] == "article"] == ["16"]
    paragraph = next(u for u in units if u["label"] == "§ 1º")
    assert by_id[paragraph["parent"]]["label"] == "16"


@pytest.fixture(scope="module")
def ren846():
    read = reader.read_pdf(DIR / "ren2019846_compilada.pdf", Settings())
    units = read["extraction"]["units"]
    return units, {u["id"]: u for u in units}


@SEM_PDF
def test_real_embargo_daily_fine_is_cited_under_art_16(ren846):
    units, by_id = ren846
    # Antes: "art. 8º da Lei nº 9.074" virava artigo e o § 1º do Art. 16 era citado como "Art. 8º § 1º".
    unit = next(
        u
        for u in units
        if u["text"].startswith("§ 1º Na hipótese da aplicação das penalidades de embargo")
    )
    assert by_id[unit["parent"]]["label"] == "16"
    assert [u["label"] for u in units if u["kind"] == "article"].count("8º") == 1


@pytest.mark.parametrize(
    "text,value",
    [
        ("cento e vinte e cinco milésimos por cento", 0.125),
        ("vinte e cinco centésimos por cento", 0.25),
        ("cinco décimos por cento", 0.5),
        ("zero vírgula zero um por cento", 0.01),
        ("zero vírgula vinte e cinco por cento", 0.25),
        ("cento e vinte por cento", 120),
    ],
)
def test_spelled_percentages(text, value):
    from scripts.extrair_parametros import spelled

    assert spelled(text) == pytest.approx(value)


def test_digits_vs_words_mismatch_is_flagged():
    from scripts.extrair_parametros import mismatches

    # Texto real da REN 846 compilada, Art. 45-I, § 4º.
    assert mismatches("Será acrescido o valor de 25% (cinco por cento) para cada antecedente")
    assert not mismatches("I - 40% (quarenta por cento) para cada caso de reincidência")
    assert not mismatches("III - de 1% a 5% (um a cinco por cento) para cada caso")
