"""Extrai, pelo pipeline do Athenix, os parâmetros de penalidade da REN 846 e das normas que a
alteram, e grava o arquivo versionado usado pelo módulo de impacto.

Uso:
  python scripts/extrair_parametros.py                      # regrava athenix/data/penalidades_ren846.json
  python scripts/extrair_parametros.py --dump saida.json    # também despeja todos os dispositivos

Exige os PDFs em tests/fontes_impacto/ (fora do repositório público até confirmar os termos de
uso do Leis.org). Nenhum valor é digitado: percentuais são lidos do trecho citado.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from athenix.config import Settings  # noqa: E402
from athenix.evidence import verify  # noqa: E402
from athenix.impacto import ALTERA, PARAMETROS, termos  # noqa: E402
from athenix.poc import reader  # noqa: E402
from athenix.temporal import NUMBERS  # noqa: E402

FONTES = ROOT / "tests" / "fontes_impacto"
DOCS = {
    "846": (FONTES / "ren2019846_compilada.pdf", "REN 846/2019 (texto compilado)"),
    "1137": (ROOT / "tests/norma_poc/ren20251137.pdf", "RN 1.137/2025"),
    "1148": (FONTES / "ren20261148.pdf", "REN 1.148/2026"),
    "1174": (FONTES / "ren20261174.pdf", "REN 1.174/2026 (texto compilado)"),
}
FOOTER = re.compile(r"\s*Leis\.org/aneel - [^\n]*(?:\n\s*\d+/\d+)?|\n\s*\d+/\d+\s*(?=\n|$)")
LABEL = re.compile(
    r"^\s*(?:Art\.?\s*\d+[º°]?(?:-[A-Z])?\.?|§\s*\d+[º°]?|Parágrafo único\.|[IVXLCDM]+\s*-|[a-z]\))\s*"
)
# Ignora faixas ("1% a 5% (um a cinco por cento)"): o extenso descreve a faixa inteira.
PCT = re.compile(r"(?<!%\sa\s)(\d+(?:,\d+)?)\s*%\s*\(([^)]+)\)")
PERCENT = re.compile(r"(\d+(?:,\d+)?)\s*%")
FRACTION = {"décimos": 10, "centésimos": 100, "milésimos": 1000}
ORIGEM = re.compile(
    r"\(Reda[çc][ãa]o (?:dada|acrescida) pela Resolu[çc][ãa]o\s+Normativa\s+n[º°]\s*(\d+/\d+)\)"
)

# Parâmetro → dispositivo da REN 846 compilada. O valor sai do trecho, nunca deste arquivo.
SPEC = {
    "sujeicao_penalidades": ("5º", "Infrações sujeitam o agente às penalidades do art. 5º"),
    "advertencia": ("6º", "Advertência no lugar da multa (piso zero)"),
    "teto_legal": ("7º", "Teto legal por infração (fora da REN 846)"),
    "sem_repasse": ("7º > Parágrafo único", "Multa não pode ser repassada à tarifa"),
    "base_grupos": ("8º", "Percentuais incidem sobre a base do art. 21"),
    "limite_grupo_I": ("8º > I", "Limite do Grupo I"),
    "limite_grupo_II": ("8º > II", "Limite do Grupo II"),
    "limite_grupo_III": ("8º > III", "Limite do Grupo III"),
    "limite_grupo_IV": ("8º > IV", "Limite do Grupo IV"),
    "limite_grupo_V": ("8º > V", "Limite do Grupo V"),
    "multa_diaria": (
        "15 > § 2º",
        "Multa diária por obrigação de fazer: até 30 dias, até 2% da base",
    ),
    "base_rol": ("21", "Base de cálculo: ROL dos 12 meses anteriores ao AI"),
    "base_rap": ("21 > § 3º", "Base de transmissora fora de operação: RAP"),
    "base_segmento": ("21 > § 6º", "Base do segmento da infração"),
    "ordem_calculo": ("22 > § 1º", "Valor base + agravantes − atenuantes"),
    "pisos_tetos": ("22 > § 2º", "Valor base por metodologia própria; pisos e tetos"),
    "metodologia_afastavel": ("22 > § 6º", "Metodologia do valor base pode ser afastada"),
    "agravante_reincidencia": ("23 > I", "Agravante por reincidência específica"),
    "agravante_tn": ("23 > II", "Agravante por Termo de Notificação não atendido"),
    "agravante_antecedentes": ("23 > III", "Agravante por antecedentes (teto)"),
    "antecedentes_a": ("23 > III > a", "Faixa de antecedentes a)"),
    "antecedentes_b": ("23 > III > b", "Faixa de antecedentes b)"),
    "antecedentes_c": ("23 > III > c", "Faixa de antecedentes c)"),
    "antecedentes_d": ("23 > III > d", "Faixa de antecedentes d)"),
    "antecedentes_e": ("23 > III > e", "Faixa de antecedentes e)"),
    "agravantes_somam": ("23 > § 2º", "Agravantes se somam"),
    "atenuantes_nao_cumulativas": ("24", "Atenuantes não se acumulam"),
    "atenuante_espontanea": ("24 > I", "Atenuante: cessação espontânea antes da fiscalização"),
    "atenuante_tn": ("24 > II", "Atenuante: cessação até o prazo do TN"),
    "reducao_renuncia": ("38 > § 2º", "Redução por renúncia ao recurso"),
}


def words(text):
    tokens = [t for t in re.split(r"\s+e\s+|\s+", text.lower()) if t]
    return sum(NUMBERS[t] for t in tokens) if all(t in NUMBERS for t in tokens) else None


def spelled(text):
    """Valor de 'cento e vinte e cinco milésimos por cento', 'zero vírgula zero um por cento'."""
    text = re.sub(r"\s*por\s+cento\s*$", "", text.strip().lower())
    for name, div in FRACTION.items():
        if text.endswith(name):
            n = words(text[: -len(name)])
            return None if n is None else n / div
    if "vírgula" in text:
        whole, frac = [p.strip() for p in text.split("vírgula")]
        zeros = len(re.match(r"(zero\s+)*", frac + " ").group(0).split())
        rest = re.sub(r"^(zero\s+)*", "", frac)
        w = 0 if whole == "zero" else words(whole)
        f = words(rest) if rest else 0
        if w is None or f is None:
            return None
        return w + f / 10 ** (zeros + len(str(f)))
    return words(text)


def mismatches(text):
    out = []
    for m in PCT.finditer(text):
        digits = float(m.group(1).replace(",", "."))
        value = spelled(m.group(2))
        if value is None or abs(value - digits) > 1e-9:
            out.append(
                {"algarismo": m.group(1) + "%", "extenso": m.group(2), "extenso_lido": value}
            )
    return out


def label_path(unit, by_id):
    labels = []
    while unit:
        labels.append(unit["label"])
        unit = by_id.get(unit["parent"])
    return " > ".join(reversed(labels))


def cite(unit, extraction):
    """Cita o dispositivo em pedaços contíguos (o rodapé da página interrompe o texto)."""
    parts = [p.strip() for p in FOOTER.split(unit["text"]) if p and p.strip()]
    cited, anchors, note = [], [], None
    for i, part in enumerate(parts):
        anchor = verify(
            part,
            unit["id"],
            extraction["units"],
            extraction["text_hash"],
            source=extraction["source"],
        )
        if (
            anchor["state"] != "verified"
            and i == 0
            and LABEL.match(part)
            and not unit.get("struck")
        ):
            # pdfium lê o selo "Art. N" fora do lugar: confirma o texto sem o rótulo.
            retry = verify(
                LABEL.sub("", part, count=1),
                unit["id"],
                extraction["units"],
                extraction["text_hash"],
                source=extraction["source"],
            )
            if retry["state"] == "verified":
                anchor, note = retry, "rótulo do dispositivo não confirmado pela 2ª leitura"
        cited.append(" ".join(part.split()))
        anchors.append(anchor)
    verified = bool(anchors) and all(a["state"] == "verified" for a in anchors)
    return {
        "trecho": " […] ".join(cited),
        "ancora": "verified" if verified else (anchors[0]["state"] if anchors else "invalid"),
        "motivo": next((a["reason"] for a in anchors if a.get("reason")), None),
        "nota": note,
        "revogado": unit.get("struck"),
    }


def read(name):
    path, title = DOCS[name]
    content = path.read_bytes()
    extraction = reader.read_pdf(path, Settings())["extraction"]
    by_id = {u["id"]: u for u in extraction["units"]}
    units = [u | {"path": label_path(u, by_id)} for u in extraction["units"]]
    effective = [d for d in extraction["dates"] if d["kind"] == "effective"]
    if len({d["date"] for d in effective}) > 1:
        # Datas de vigência distintas (ex.: vigência de outro ato citada): fica a da publicação.
        effective = [d for d in effective if d.get("basis") == "publication"]
    return {
        "titulo": title,
        "arquivo": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(content).hexdigest(),
        "vigencia": effective[0]["date"] if len({d["date"] for d in effective}) == 1 else None,
        "extraction": extraction,
        "units": units,
    }


def group_of(units, article):
    caput = next(u for u in units if u["path"] == article)
    match = re.search(r"Grupo\s+([IV]+)\b", caput["text"])
    return match.group(1) if match else None


def build(docs):
    ren = docs["846"]
    by_path = {}
    for unit in ren["units"]:
        by_path.setdefault(unit["path"], []).append(unit)
    parametros = {}
    for pid, (path, description) in SPEC.items():
        # Redação revogada nunca entra: entre redações do mesmo dispositivo, fica a não riscada.
        candidates = by_path.get(path, [])
        current = [u for u in candidates if not u.get("struck")]
        unit = (current or candidates)[0]
        entry = cite(unit, ren["extraction"])
        if len(current) != 1:
            entry |= {"ancora": "pending", "motivo": f"{len(current)} redações vigentes: conferir"}
        trecho = entry["trecho"]
        parametros[pid] = {
            "descricao": description,
            "dispositivo": "Art. " + path.replace(" > ", ", "),
            **entry,
            "percentuais": [float(v.replace(",", ".")) for v in PERCENT.findall(trecho)],
            "fonte": "846",
        }
    infracoes = []
    for unit in ren["units"]:
        match = re.fullmatch(r"(9º|10|11|12|13) > ([IVXLC]+)", unit["path"])
        if not match or unit.get("struck"):
            continue
        entry = cite(unit, ren["extraction"])
        origem = ORIGEM.search(entry["trecho"])
        infracoes.append(
            {
                "dispositivo": f"Art. {match.group(1)}, {match.group(2)}",
                "grupo": group_of(ren["units"], match.group(1)),
                **entry,
                "origem": f"RN {origem.group(1)}" if origem else "redação original",
                "termos": termos(ORIGEM.sub("", entry["trecho"])),
            }
        )
    # D1: o inciso XXIII do art. 11 tem duas redações em atos diferentes; nenhuma é escolhida.
    leituras = []
    for name in ("1137", "1148"):
        doc = docs[name]
        unit = next(u for u in doc["units"] if u["path"] == "11 > XXIII")
        leituras.append(
            {"ato": doc["titulo"], "vigencia_desde": doc["vigencia"]}
            | cite(unit, doc["extraction"])
        )
    alteracoes = []
    for name in ("1137", "1148", "1174"):
        doc = docs[name]
        for unit in doc["units"]:
            if re.search(ALTERA, " ".join(unit["text"].split())):
                alteracoes.append(
                    {
                        "ato": doc["titulo"],
                        "vigencia_desde": doc["vigencia"],
                        "dispositivo": "Art. " + unit["path"],
                    }
                    | cite(unit, doc["extraction"])
                )
    alertas = []
    for name, doc in docs.items():
        for unit in doc["units"]:
            if unit.get("struck"):
                continue
            for problem in mismatches(unit["text"]):
                alertas.append(
                    {
                        "tipo": "algarismo_extenso",
                        "ato": doc["titulo"],
                        "dispositivo": "Art. " + unit["path"].replace(" > ", ", "),
                        "detalhe": f'{problem["algarismo"]} escrito como "{problem["extenso"]}"',
                    }
                    | cite(unit, doc["extraction"])
                )
    return {
        "versao": 1,
        "gerado_por": "scripts/extrair_parametros.py (pipeline Athenix, sem valores digitados)",
        "fontes": {
            name: {k: doc[k] for k in ("titulo", "arquivo", "sha256", "vigencia")}
            | {
                "origem": "Leis.org (compilação de terceiro): fonte secundária"
                if name != "1137"
                else "ANEEL (texto compilado já no repositório)"
            }
            for name, doc in docs.items()
        },
        "nao_estimaveis": [
            "Metodologia de cálculo do valor base da multa (Art. 22, §§ 2º e 6º): não está no repositório.",
            "Teto legal por infração (Art. 7º remete à legislação): lei não está no repositório.",
            "Perda de receita por Parcela Variável (PVI/PVRO) de transmissoras: norma de PV não fornecida.",
            "Efeitos no Fator X da distribuidora (REN 1.148/2026, PRORET 2.5/2.5-A): anexos não fornecidos.",
            "Alterações da REN 1.162/2026 e Despacho 1.293/2026: atos não fornecidos.",
            "Custo de adequação: depende de dados internos da empresa.",
        ],
        "parametros": parametros,
        "infracoes": infracoes,
        "duvidas": [
            {
                "id": "D1",
                "dispositivo": "Art. 11, XXIII",
                "texto": "Duas redações para o mesmo inciso em atos diferentes; o compilado mostra só a da RN 1.137. Dúvida para especialista.",
                "leituras": leituras,
            },
            {
                "id": "D5",
                "dispositivo": "Arts. 8º e 23",
                "texto": "A norma não diz se o resultado após agravantes continua limitado ao teto do grupo: calculados os dois cenários.",
            },
        ],
        "alteracoes_da_regua": alteracoes,
        "alertas_fonte": alertas,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--saida", default=str(PARAMETROS))
    parser.add_argument("--dump")
    args = parser.parse_args()
    docs = {name: read(name) for name in DOCS}
    result = build(docs)
    Path(args.saida).write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    if args.dump:
        dump = {
            name: [
                {"path": u["path"], "kind": u["kind"], **cite(u, doc["extraction"])}
                for u in doc["units"]
            ]
            for name, doc in docs.items()
        }
        Path(args.dump).write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    pending = [k for k, v in result["parametros"].items() if v["ancora"] != "verified"]
    print(
        f"{len(result['parametros'])} parâmetros ({len(pending)} não verificados: {pending}),",
        f"{len(result['infracoes'])} infrações, {len(result['alteracoes_da_regua'])} alterações,",
        f"{len(result['alertas_fonte'])} alertas da fonte",
    )


if __name__ == "__main__":
    main()
