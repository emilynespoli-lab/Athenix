"""D4: redação revogada (riscada no PDF compilado) nunca vira obrigação, citação verificada nem
parâmetro de cálculo; riscado parcial fica pendente."""

from pathlib import Path

import pytest
from pdf_helpers import lines_pdf

from athenix.config import Settings
from athenix.evidence import verify
from athenix.poc import reader
from athenix.proposals import rule_candidates
from athenix.structure import extract, locate_struck

LINES = [
    "Art. 1 A distribuidora deve enviar o relatorio em 30 dias.",
    "Art. 2 A multa sera de ate 5% da base de calculo vigente.",
    "Art. 2 A multa sera de ate 2% da base de calculo vigente.",
    "Art. 3 A transmissora deve informar o ONS em 10 dias uteis.",
    "Art. 4 A distribuidora deve publicar o plano anual de",
    "contingencia no sitio eletronico.",
]
STRUCK = {(0, 1), (0, 3), (0, 4)}  # Art. 2 antigo, Art. 3 inteiro, só a 1ª linha do Art. 4


def by_text(units, start):
    return next(u for u in units if " ".join(u["text"].split()).startswith(start))


@pytest.mark.parametrize("path", ["extract", "reader"])
def test_struck_text_is_revoked_or_pending(tmp_path, path):
    content = lines_pdf([LINES], struck=STRUCK)
    if path == "extract":
        extraction = extract(content, "application/pdf", Settings())
    else:
        (tmp_path / "riscado.pdf").write_bytes(content)
        extraction = reader.read_pdf(tmp_path / "riscado.pdf", Settings())["extraction"]
    units = extraction["units"]
    old, new = (
        by_text(units, "Art. 2 A multa sera de ate 5%"),
        by_text(units, "Art. 2 A multa sera de ate 2%"),
    )
    assert old["struck"] == "revoked" and "struck" not in new
    assert by_text(units, "Art. 3")["struck"] == "revoked"
    assert by_text(units, "Art. 4")["struck"] == "partial"
    assert "struck" not in by_text(units, "Art. 1")

    def anchor(unit):
        return verify(
            unit["text"].strip(),
            unit["id"],
            units,
            extraction["text_hash"],
            source=extraction["source"],
        )

    assert anchor(new)["state"] == "verified"
    assert anchor(old)["state"] == "pending" and "revogada" in anchor(old)["reason"]
    assert anchor(by_text(units, "Art. 4"))["state"] == "pending"
    # Antes: o Art. 3 riscado virava dever da transmissora. Depois: nenhum candidato dele.
    revoked = {u["id"] for u in units if u.get("struck") == "revoked"}
    candidates = rule_candidates(extraction)
    assert not [c for c in candidates if c["evidence"][0]["unit_id"] in revoked]
    assert any(c["action"].startswith("Art. 1") for c in candidates)
    assert any("Texto riscado no PDF" in w for w in extraction["warnings"])


def test_unlocated_struck_text_makes_page_pending():
    assert locate_struck("Art. 1 texto vigente", [["inexistente"]]) is None
    assert locate_struck("a b\nc d", [["c", "d"]]) == [(4, 7)]


REN846 = Path(__file__).parent / "fontes_impacto" / "ren2019846_compilada.pdf"


@pytest.mark.skipif(not REN846.exists(), reason="PDF do Leis.org fora do repositório público")
def test_real_ren846_revoked_wordings():
    # sha256 d8b6fae9…; antes: as duas redações de cada parágrafo saíam "verificadas" (12 revogadas
    # citáveis como vigentes). Depois: 12 marcadas como revogadas, 0 parciais.
    units = reader.read_pdf(REN846, Settings())["extraction"]["units"]
    for old, new in [
        ("§ 8º Tratando-se das entidades responsáveis pela operação do sistema, pela", "§ 8º Tratando-se das entidades responsáveis pela operação do sistema ou pela"),
        ("§ 9º Nos casos de infrações cometidas", "§ 9º Tratando-se da entidade responsável pela gestão"),
        ("§ 2º O infrator que renunciar expressamente ao direito de interpor recurso fará jus", "§ 2º O infrator que renunciar expressamente ao direito de interpor recurso, no prazo"),
    ]:  # fmt: skip
        assert by_text(units, old)["struck"] == "revoked"
        assert "struck" not in by_text(units, new)
    assert sum(u.get("struck") == "revoked" for u in units) == 12
    assert not [u for u in units if u.get("struck") == "partial"]
    # Art. 12, X tem o mesmo texto do Art. 11, X revogado, mas está vigente.
    current = [u for u in units if u["text"].startswith("X - deixar de investir")]
    assert sorted(u.get("struck", "vigente") for u in current) == ["revoked", "vigente"]
