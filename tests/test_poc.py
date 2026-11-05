"""PoC de extração: rastreabilidade, hierarquia, comparação, orçamento e repetibilidade."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from athenix import llm
from athenix.config import Settings
from athenix.evidence import recheck
from athenix.poc import compare, reader, semantic
from athenix.poc.run import run
from pdf_helpers import lines_pdf, synthetic_pdf

NORMA = Path(__file__).parent / "norma_poc"
REN = NORMA / "ren20251137.pdf"

LINES = [
    "Art. 1 As distribuidoras devem:",
    "I - manter registros por 20 dias contados da publicacao;",
    "a) enviar relatorio anual;",
    "Art. 2 Revoga-se o inciso VIII do art. 621 da Resolucao Normativa n 1.000.",
]


def make(tmp_path, name, pages):
    path = tmp_path / name
    path.write_bytes(lines_pdf(pages))
    return path


def azure_settings(**extra):
    return Settings(
        model="gpt-5-mini",
        api_key="chave-falsa",
        azure_endpoint="https://exemplo.openai.azure.com/",
        input_price="0.25",
        output_price="2.00",
        price_source="https://exemplo.test/precos",
        price_date="2026-01-01",
        **extra,
    )


def test_identity_hash_and_invalid_input(tmp_path):
    path = make(tmp_path, "a.pdf", [LINES])
    result = reader.read_pdf(path, Settings())
    assert result["document"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    bad = tmp_path / "ruim.pdf"
    bad.write_bytes(b"nao e pdf")
    with pytest.raises(ValueError, match="não é PDF"):
        reader.read_pdf(bad, Settings())
    broken = tmp_path / "quebrado.pdf"
    broken.write_bytes(b"%PDF-1.4\nlixo")
    with pytest.raises(ValueError, match="corrompido"):
        reader.read_pdf(broken, Settings())


def test_hierarchy_and_literal_anchors(tmp_path):
    result = reader.read_pdf(make(tmp_path, "a.pdf", [LINES]), Settings())
    extraction = result["extraction"]
    kinds = [(u["kind"], u["label"]) for u in extraction["units"] if u["kind"] != "unstructured"]
    assert kinds == [("article", "1"), ("clause", "I"), ("letter", "a"), ("article", "2")]
    by_id = {u["id"]: u for u in extraction["units"]}
    clause = next(u for u in extraction["units"] if u["kind"] == "clause")
    assert by_id[clause["parent"]]["kind"] == "article"
    items, _ = semantic.deterministic_items(result["document"], extraction, result["pages"])
    assert items
    for item in items:
        for anchor in item["anchors"]:
            if anchor["state"] == "verified":
                assert recheck(anchor, extraction["text"], extraction["units"])
        if item["literal_text"]:
            loc = item["locator"]
            assert extraction["text"][loc["start"] : loc["end"]] == item["literal_text"]
            assert reader.boxes(result["pages"], loc["start"], loc["end"])  # coordenadas no PDF
        assert item["validation_state"] in {"pending_human_review", "anchor_unverified"}
    types = {i["type"] for i in items}
    assert {"obligation", "deadline", "revocation", "reference"} <= types
    # Interpretação nunca substitui o texto: campos separados.
    obligation = next(i for i in items if i["type"] == "obligation")
    assert obligation["literal_text"] and obligation["interpretation"]["action"]


def test_page_without_text_is_never_silent(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(synthetic_pdf(scanned=True))
    result = reader.read_pdf(path, Settings())
    assert result["pages"][0]["state"] == reader.MISSING
    assert "OCR" in result["pages"][0]["reasons"][0]
    fake = {
        1: [
            {
                "text": "Art. 1 As empresas devem manter registros.",
                "bbox": [0, 0, 1, 1],
                "conf": 0.99,
            }
        ]
    }
    ok = reader.read_pdf(path, Settings(), fake)["pages"][0]
    assert (ok["state"], ok["source"]) == (reader.UNCERTAIN, "ocr")  # OCR nunca é "fiel"
    fake[1][0]["conf"] = 0.5
    assert reader.read_pdf(path, Settings(), fake)["pages"][0]["state"] == reader.REVIEW
    # A camada de texto prevalece quando existe.
    text_pdf = make(tmp_path, "t.pdf", [LINES])
    page = reader.read_pdf(text_pdf, Settings(), {1: fake[1]})["pages"][0]
    assert page["source"] == "text_layer"


def test_compare_classifies_without_choosing_a_source(tmp_path):
    a = reader.read_pdf(
        make(
            tmp_path,
            "a.pdf",
            [LINES + ["Art. 4 A concessionaria deve publicar o balanco patrimonial."]],
        ),
        Settings(),
    )
    changed = [line.replace("20 dias", "30 dias") for line in LINES] + [
        "Art. 3 O ONS deve enviar dados mensalmente a ANEEL."
    ]
    b = reader.read_pdf(make(tmp_path, "b.pdf", [changed]), Settings())
    cmp = compare.compare(a, b)
    counts = cmp["counts"]
    assert counts["only_a"] >= 1 and counts["only_b"] >= 1 and counts["divergent"] >= 1
    assert counts["equal"] >= 1  # Art. 1 e Art. 2 idênticos
    assert any("30" in json.dumps(d["changes"]) for d in cmp["divergent"])
    assert "Sem preferência" in cmp["note"]


def test_ocr_divergence_is_flagged_as_possible_reading_error(tmp_path):
    a = reader.read_pdf(
        make(tmp_path, "a.pdf", [["Art. 1 As empresas devem manter registros completos."]]),
        Settings(),
    )
    scan = tmp_path / "s.pdf"
    scan.write_bytes(synthetic_pdf(scanned=True))
    ocr = {
        1: [
            {
                "text": "Art. 1 As empresas devem manter registros compietos.",
                "bbox": [0, 0, 1, 1],
                "conf": 0.9,
            }
        ]
    }
    b = reader.read_pdf(scan, Settings(), ocr)
    divergent = compare.compare(a, b)["divergent"]
    assert divergent and divergent[0]["possible_ocr_error"] is True


def test_azure_target_and_payload():
    settings = azure_settings()
    url, headers = llm.target(settings)
    assert url.startswith(
        "https://exemplo.openai.azure.com/openai/deployments/gpt-5-mini/chat/completions?api-version="
    )
    assert headers == {"api-key": "chave-falsa"}
    payload = llm.request_payload("gpt-5-mini", [], "low")
    assert payload["reasoning_effort"] == "low" and "store" not in payload
    assert "store" in llm.request_payload("m", [])  # OpenAI inalterado


def reply(items, prompt=1000, completion=500):
    content = json.dumps({"items": items})
    return {
        "status": "complete",
        "raw": {
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        },
    }


def ai_setup(tmp_path):
    result = reader.read_pdf(make(tmp_path, "a.pdf", [LINES]), Settings())
    return result["document"], result["extraction"], result["pages"]


def test_ai_budget_stops_before_exceeding(tmp_path):
    doc, extraction, pages = ai_setup(tmp_path)
    calls = []
    run_state = {"spent": Decimal(0), "calls": []}
    # Teto minúsculo: a reserva conservadora de qualquer chamada já o ultrapassa.
    settings = azure_settings(run_budget_usd="0.0001")
    items, _ = semantic.ai_items(
        doc, extraction, pages, settings, run_state, lambda s, p: calls.append(p)
    )
    assert not calls and not items
    assert run_state["ai"]["status"] == "stopped_by_budget"
    assert run_state["calls"][0]["status"] == "budget_stop"


def test_ai_hallucinated_quote_never_becomes_literal_text(tmp_path):
    doc, extraction, pages = ai_setup(tmp_path)
    fabricated = {
        "subject": "As distribuidoras",
        "modality": "duty",
        "action": "pagar multa de R$ 1.000.000",
        "object": "multa",
        "conditions": [],
        "exceptions": [],
        "evidence": [
            {
                "unit_id": "u0002",
                "quote": "As distribuidoras devem pagar multa de R$ 1.000.000 por dia",
            }
        ],
        "suggested_rules": [],
    }
    state = {"spent": Decimal(0), "calls": []}
    items, _ = semantic.ai_items(
        doc, extraction, pages, azure_settings(), state, lambda s, p: reply([fabricated])
    )
    assert items, "item inválido deve ser registrado, não sumir"
    for item in items:
        assert item["literal_text"] is None
        assert item["validation_state"] == "anchor_unverified"
    assert Decimal(state["spent"]) == llm.cost(llm.price_config(azure_settings()), 1000, 500)


def test_ai_unknown_usage_charges_the_reservation(tmp_path):
    doc, extraction, pages = ai_setup(tmp_path)
    state = {"spent": Decimal(0), "calls": []}
    semantic.ai_items(
        doc,
        extraction,
        pages,
        azure_settings(),
        state,
        lambda s, p: {"status": "unknown_result", "raw": None},
    )
    assert state["spent"] > 0  # custo desconhecido nunca vira zero
    assert state["ai"]["status"] == "stopped_on_unknown_result"  # sem retentativa


def test_pipeline_is_repeatable_and_reports_gaps(tmp_path):
    scan = tmp_path / "dou.pdf"
    scan.write_bytes(synthetic_pdf(scanned=True))
    settings = Settings()
    first = run(REN, scan, tmp_path / "o1", settings)
    second = run(REN, scan, tmp_path / "o2", settings)
    assert first["manifest"] == second["manifest"]  # mesmos hashes de artefatos
    coverage = {c["document"]["file"]: c for c in first["coverage"]}
    assert coverage["dou.pdf"]["pages"]["not_extracted"] == [1]  # lacuna explícita
    assert coverage["ren20251137.pdf"]["pages"]["total"] == 31
    items = json.loads((tmp_path / "o1" / "items_ren20251137.json").read_text(encoding="utf-8"))[
        "items"
    ]
    assert len({i["id"] for i in items}) == len(items)
    log = json.loads((tmp_path / "o1" / "run_log.json").read_text(encoding="utf-8"))
    assert log["ai"]["status"] == "not_requested" and log["cost_usd_total"] == "0"
    # Hierarquia da norma real: item 105 e as alíneas do item 107.
    labels = [(i["dispositivo"]) for i in items]
    assert any("item 105" in d for d in labels)
    assert any(d.endswith("item 107 › alínea k)") or "item 107 › alínea k)" in d for d in labels)


FAKE_OCR = {
    "engine": "fake/1",
    "pages": {
        "1": {
            "lines": [
                {
                    "text": "Art. 1 As empresas devem manter registros completos.",
                    "bbox": [0, 0, 9, 9],
                    "conf": 0.99,
                },
                {
                    "text": "Item | Prazo",
                    "bbox": [0, 20, 9, 30],
                    "conf": 0.9,
                    "table_id": "p1-t1",
                    "row": 0,
                },
                {
                    "text": "Plano | 30 dias",
                    "bbox": [0, 20, 9, 30],
                    "conf": 0.9,
                    "table_id": "p1-t1",
                    "row": 1,
                },
            ],
            "review": ["1 região(ões) de fórmula: OCR de fórmula não habilitado"],
            "ocr_score": 0.97,
            "layout": {},
        }
    },
}


def test_docling_adapter_caches_and_fails_loudly(tmp_path, monkeypatch):
    from athenix.poc import ocr

    path = tmp_path / "scan.pdf"
    path.write_bytes(synthetic_pdf(scanned=True))
    calls = []

    def fake_run(command, check):
        calls.append(command)
        Path(command[6]).write_text(json.dumps(FAKE_OCR), encoding="utf-8")

    monkeypatch.setattr(ocr.subprocess, "run", fake_run)
    first = ocr.docling_ocr(path, [1], cache_dir=tmp_path / "cache")
    assert first[1]["engine"] == "fake/1" and len(calls) == 1
    monkeypatch.setattr(ocr.subprocess, "run", lambda *a, **k: 1 / 0)  # cache: sem novo OCR
    assert ocr.docling_ocr(path, [1], cache_dir=tmp_path / "cache") == first

    def broken(command, check):
        raise OSError("sem docling")

    monkeypatch.setattr(ocr.subprocess, "run", broken)
    with pytest.raises(RuntimeError, match="indisponível"):
        ocr.docling_ocr(path, [1], cache_dir=tmp_path / "vazio")


def test_ocr_page_keeps_tables_review_notes_and_engine(tmp_path):
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(synthetic_pdf(scanned=True))
    ocr = {1: FAKE_OCR["pages"]["1"] | {"engine": "fake/1"}}
    result = reader.read_pdf(scan, Settings(), ocr)
    page = result["pages"][0]
    assert page["source"] == "ocr" and page["state"] == reader.REVIEW
    assert any("fórmula" in r for r in page["reasons"])
    assert (
        result["tables"][0]["header"] == ["Item", "Prazo"]
        and result["tables"][0]["rows"][1][1] == "30 dias"
    )
    assert "fake/1" in result["extraction"]["extractor"]


def test_pipeline_survives_ocr_failure_and_logs_it(tmp_path):
    scan = tmp_path / "dou.pdf"
    scan.write_bytes(synthetic_pdf(scanned=True))

    def broken(path, pages):
        raise RuntimeError("OCR Docling indisponível")

    out = run(REN, scan, tmp_path / "o", Settings(), ocr=broken)
    log = json.loads((tmp_path / "o" / "run_log.json").read_text(encoding="utf-8"))
    assert log["errors"][0]["stage"] == "ocr"
    coverage = {c["document"]["file"]: c for c in out["coverage"]}
    assert coverage["dou.pdf"]["pages"]["not_extracted"] == [1]  # lacuna continua explícita


def test_independent_verifier_passes_and_detects_tampering(tmp_path):
    import subprocess
    import sys

    path = make(tmp_path, "a.pdf", [LINES])
    other = make(tmp_path, "b.pdf", [LINES[:2]])
    out = tmp_path / "o"
    run(path, other, out, Settings())
    script = Path(__file__).parent.parent / "scripts" / "verify_poc.py"
    originals = str(tmp_path)

    def verify():
        return subprocess.run(
            [sys.executable, "-I", str(script), str(out), originals], capture_output=True
        )

    assert verify().returncode == 0
    items = out / "items_a.json"
    data = json.loads(items.read_text(encoding="utf-8"))
    next(i for i in data["items"] if i["literal_text"])["literal_text"] = "texto inventado"
    items.write_text(json.dumps(data), encoding="utf-8")
    assert verify().returncode == 1  # manifesto e trecho literal deixam de bater
    path.write_bytes(path.read_bytes() + b"\n")  # original alterado
    assert verify().returncode == 1
