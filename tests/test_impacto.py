"""Módulo de impacto: valores fixos, nenhum número sem premissa e fonte, perfil vazio."""

import copy
import hashlib
from datetime import date
from pathlib import Path

import pytest

from athenix import impacto

PARAMS = impacto.carregar()
HOJE = "2026-11-11"


def row(action, deadlines=(), modality="duty", subject="As distribuidoras", rid="o1"):
    return {
        "id": rid,
        "action": action,
        "subject": subject,
        "modality": modality,
        "status": "detected",
        "evidence": [{"unit_id": "u1", "quote": action}],
        "anchors": [{"state": "verified", "unit_id": "u1", "quote": action}],
        "deadlines": list(deadlines),
        "document_id": "d1",
        "document_title": "Norma",
    }


PLANO = row("As distribuidoras devem manter Plano de Contingência atualizado e publicado.")


def avaliar(rows, **form):
    return impacto.avaliar(PARAMS, rows, impacto.perfil({"data_referencia": HOJE} | form))


def test_parameter_file_only_has_verified_current_wordings():
    for pid, p in PARAMS["parametros"].items():
        assert p["ancora"] == "verified" and not p["revogado"], pid
    limits = [PARAMS["parametros"][f"limite_grupo_{g}"]["percentuais"] for g in impacto.GRUPOS]
    # Lidos do texto do Art. 8º da REN 846 compilada (sha256 d8b6fae9…), não digitados.
    assert limits == [[0.125], [0.25], [0.5], [1.0], [2.0]]
    fontes = Path(__file__).parent / "fontes_impacto"
    for fonte in PARAMS["fontes"].values():
        path = Path(__file__).parents[1] / fonte["arquivo"]
        if path.exists():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == fonte["sha256"]
        else:
            assert path.parent == fontes  # só os PDFs do Leis.org podem faltar (fora do repo)


def test_fixed_values_explicit_group_with_base_and_premises():
    item = avaliar([PLANO], segmento="distribuicao", base="1.000.000,00", reincidencias="1",
                   fracao_valor_base="50")["itens"][0]  # fmt: skip
    m = item["multa"]
    assert [e["dispositivo"] for e in item["enquadramentos"]] == ["Art. 12, XXVI"]
    assert m["grupos"] == ["IV"] and m["agravantes_pct"] == 40
    assert m["maximo"] == {"com_teto": 1.0, "sem_teto": pytest.approx(1.4)}
    assert m["provavel"] == {"com_teto": pytest.approx(0.7), "sem_teto": pytest.approx(0.7)}
    assert m["reais"]["maximo"] == {"com_teto": 10000.0, "sem_teto": pytest.approx(14000.0)}
    assert m["reais"]["provavel"]["com_teto"] == pytest.approx(7000.0)
    assert item["confianca"] == "médio"  # grupo só por coincidência de termos


def test_fixed_values_all_aggravating_and_cap_scenarios():
    form = dict(base="1000000", reincidencias="3", tn_nao_atendidos="2", antecedentes="2",
                soma_antecedentes_pct="1,5", fracao_valor_base="50", atenuante="espontanea",
                grupo_o1="IV")  # fmt: skip
    m = avaliar([PLANO], **form)["itens"][0]["multa"]
    # 120% (reincidência, teto) + 2 × 15% (TN) + 2 × 4% (antecedentes, faixa b) = 158%.
    assert m["agravantes_pct"] == pytest.approx(158)
    assert m["maximo"]["sem_teto"] == pytest.approx(2.58)
    assert m["maximo"]["com_teto"] == 1.0
    # Provável: 0,5% × 2,58 = 1,29% → com teto 1% → atenuante de 95%.
    assert m["provavel"]["com_teto"] == pytest.approx(0.05)
    assert m["provavel"]["sem_teto"] == pytest.approx(0.0645)
    assert avaliar([PLANO], **form)["itens"][0]["confianca"] == "alto"


def test_empty_profile_gives_wide_range_in_percent_and_low_confidence():
    result = avaliar([row("A distribuidora deve enviar o relatório mensal à ANEEL.")])
    item = result["itens"][0]
    m = item["multa"]
    assert m["grupos"] == list(impacto.GRUPOS)
    assert (m["piso_teto_pct"], m["teto_pct"], m["minimo_pct"]) == (0.125, 2.0, 0.0)
    assert m["provavel"] is None and "reais" not in m
    assert item["confianca"] == "baixo"
    assert "base de cálculo não informada" in item["motivo_confianca"]
    assert "informe a base" in result["frases"][0]


@pytest.mark.parametrize("broken", ["pending", "revoked"])
def test_no_value_without_verified_current_source(broken):
    params = copy.deepcopy(PARAMS)
    if broken == "pending":
        params["parametros"]["limite_grupo_IV"]["ancora"] = "pending"
    else:
        params["parametros"]["limite_grupo_IV"]["revogado"] = "revoked"
    result = impacto.avaliar(params, [PLANO], impacto.perfil({"base": "1000"}))
    assert result["itens"][0]["multa"]["estimavel"] is False
    assert result["ranking"] == []


def test_every_premise_points_to_a_parameter_or_the_user():
    form = dict(base="1000", reincidencias="1", antecedentes="1", fracao_valor_base="10",
                atenuante="ate_tn", grupo_o1="II")  # fmt: skip
    m = avaliar([PLANO], **form)["itens"][0]["multa"]
    for premissa in m["premissas"]:
        assert premissa["parametro"] in PARAMS["parametros"], premissa


def test_unverified_obligation_is_out_of_calculation():
    unverified = row("A distribuidora deve publicar o plano.") | {"anchors": [{"state": "pending"}]}
    item = avaliar([unverified], base="1000")["itens"][0]
    assert item["multa"]["estimavel"] is False and item["confianca"] == "baixo"


def test_classification_and_applicability():
    p = impacto.perfil({"segmento": "transmissao"})
    assert (
        impacto.classificar(row("pode utilizar rádio", modality="permission"), "", p)[0][0]
        == "nenhuma"
    )
    cats = [
        c
        for c, _ in impacto.classificar(
            row("deve implantar sistema e informar à ANEEL"), "Parcela Variável", p
        )
    ]
    assert cats == ["multa", "adequacao", "receita", "fiscalizacao"]
    assert impacto.aplicabilidade(row("x", subject="As distribuidoras"), p)[0] is False
    assert impacto.aplicabilidade(row("x", subject="A transmissora"), p)[0] is True


def test_urgency_and_priority_rule():
    vencida = row("deve A", [{"date": "2026-01-28", "state": "provisional"}], rid="a")
    proxima = row("deve B", [{"date": "2026-12-01", "state": "provisional"}], rid="b")
    sem_data = row("deve C", [{"state": "awaiting_event"}], rid="c")
    result = avaliar([sem_data, proxima, vencida])
    assert [i["row"]["id"] for i in result["ranking"]] == ["a", "b", "c"]
    assert "há 287 dias" in result["ranking"][0]["urgencia"]["texto"]
    assert "faltam 20 dias" in result["ranking"][1]["urgencia"]["texto"]
    assert result["frases"][0].startswith("Faça isto primeiro: deve A")


@pytest.mark.parametrize(
    "form",
    [
        {"segmento": "geracao"},
        {"base": "-1"},
        {"grupo_x": "VI"},
        {"reincidencias": "1,5"},
        {"base": "nan"},
    ],
)
def test_profile_validation(form):
    with pytest.raises(ValueError):
        impacto.perfil(form)


def test_brazilian_number_format():
    assert impacto.perfil({"base": "R$ 1.234.567,89"})["base"] == pytest.approx(1234567.89)
    assert impacto.perfil({"data_referencia": HOJE})["data_referencia"] == date(2026, 11, 11)
