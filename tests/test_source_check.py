"""Defeito 10: citação só é verificada se existir na fonte original lida por outro motor."""

import codecs

import pytest

from athenix.config import Settings
from athenix.poc import reader
from athenix.poc.semantic import deterministic_items
from athenix.structure import SUSPECT, decode_html, extract
from scripts.avaliar import flat, reference_text, sources


@pytest.fixture(scope="module")
def docs():
    return sources()  # confere o SHA-256 de cada fonte contra tests/gabarito/fontes.json


def false_verified(items, reference):
    """Âncoras verificadas cujo trecho não existe na fonte (referência independente do extrator)."""
    verified = [a for i in items for a in i["anchors"] if a["state"] == "verified"]
    return len(verified), sum(flat(a["quote"]) not in reference for a in verified)


def test_planalto_html_has_no_mojibake_nor_false_verified(docs):
    doc = docs["dec12068"]
    assert doc["sha256"] == "74f0e0d54568761a373291a350161c7ddab6094918d5158b0d9287f44a849ee0"
    extraction = extract(doc["content"], "text/html", Settings(), "norm")
    # Antes: BeautifulSoup adivinhava windows-1250 → 634 sinais de mojibake, 124/128 falsas verificadas.
    assert len(SUSPECT.findall(extraction["text"])) == 0
    assert "DECRETO Nº 12.068, DE 20 DE JUNHO DE 2024" in extraction["text"]
    assert extraction["source"]["trusted"]
    pages = [p | {"state": "faithful", "reasons": []} for p in extraction["pages"]]
    items, _ = deterministic_items(
        {"file": "D12068.htm", "sha256": doc["sha256"]}, extraction, pages
    )
    verified, wrong = false_verified(items, flat(reference_text(doc)))
    assert wrong == 0 and verified >= 150  # depois: 160 verificadas, 0 falsas


def test_pdf_table_or_formula_not_confirmed_stays_pending(docs):
    doc = docs["reh20243348"]
    assert doc["sha256"] == "c074ee9a23af3a633819135bd7c9b7a21106fb7a617f815af7de2a99e68e0f5c"
    read = reader.read_pdf(doc["path"], Settings())
    items, _ = deterministic_items(read["document"], read["extraction"], read["pages"])
    verified, wrong = false_verified(items, flat(reference_text(doc)))
    # Antes: 31 verificadas, 1 falsa (fórmula lida em outra ordem). Depois: 30 verificadas, 0 falsas.
    assert (verified, wrong) == (30, 0)
    pending = [a for i in items for a in i["anchors"] if a["state"] == "pending"]
    assert pending and all("leitura independente" in a["reason"] for a in pending)


def test_wrong_declared_charset_never_yields_verified_quotes():
    # UTF-8 declarado como windows-1252: decodifica sem erro, mas sai "Ã§" → nada é verificado.
    page = "<html><head><meta charset='windows-1252'></head><body>Art. 1º A concessionária deverá enviar a declaração de conformidade.</body></html>"
    extraction = extract(page.encode("utf-8"), "text/html", Settings())
    assert not extraction["source"]["trusted"]
    assert any("corrompido" in w for w in extraction["warnings"])
    items, _ = deterministic_items({"file": "x", "sha256": "x"}, extraction, [
        p | {"state": "faithful", "reasons": []} for p in extraction["pages"]
    ])  # fmt: skip
    anchors = [a for i in items for a in i["anchors"]]
    assert anchors and all(a["state"] == "pending" for a in anchors)


@pytest.mark.parametrize(
    "content,header,expected",
    [
        (codecs.BOM_UTF8 + "<html>ção</html>".encode(), "windows-1252", ("utf-8-sig", "BOM")),
        ("<html>ção</html>".encode("cp1252"), "ISO-8859-1", ("windows-1252", "cabeçalho HTTP")),
        ("<meta charset=utf-8>ção".encode(), None, ("utf-8", "meta")),
        ("<meta http-equiv='Content-Type' content='text/html; charset=iso-8859-1'>ç".encode("cp1252"), None, ("windows-1252", "meta")),
        ("<html>ção</html>".encode(), None, ("utf-8", "UTF-8 estrito")),
        ("<html>ção</html>".encode("cp1252"), None, ("windows-1252", "padrão legado")),
    ],
)  # fmt: skip
def test_charset_precedence_bom_header_meta_utf8_legacy(content, header, expected):
    text, encoding, method = decode_html(content, header)
    assert (encoding, method) == expected and "ç" in text
