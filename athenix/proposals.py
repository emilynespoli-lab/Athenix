"""Geradores e verificação. Heurísticas são sinais auditáveis, nunca parecer."""

import re

from .db import digest
from .evidence import recheck, verify
from .temporal import PERIOD, rules

DUTY = re.compile(
    r"\b(?:dever[áã](?:o)?|devem|deve|é obrigatóri[oa]|ficam? obrigad[oa]s?|é vedad[oa]|não poder[áã]o?|poder[áã]o?|podem"
    # "têm 90 (noventa) dias ... para": prazo concedido é dever; exige unidade temporal logo após.
    r"|t[êe]m\s+(?:o\s+prazo\s+de\s+)?\d+\s*(?:\([^)]{1,40}\)\s*)?(?:dias|meses|anos))\b",
    re.I,
)
EXCEPTION = re.compile(r"\b(?:exceto|salvo|ressalvad[oa]s?)\b[^.;\n]*", re.I)
CONDITION = re.compile(r"\b(?:caso|desde que|se houver|quando)\b[^.;\n]*", re.I)


# Fim de frase: ";" ou ":" antes de espaço, ou "." após palavra minúscula e antes de maiúscula
# (não corta "Art. 17", "110." nem "1.137").
BOUNDARY = re.compile(r"[;:](?=\s)|(?<=[a-zà-úç]{3})\.(?=\s+[A-ZÀ-Ú])")


def modality(text):
    if re.search(r"vedad|não poder[áã]o?", text, re.I):
        return "prohibition"
    return "permission" if re.search(r"\bpoder[áã]o?\b|\bpodem\b", text, re.I) else "duty"


def modalities(text):
    """Todas as modalidades expressas no trecho (um dispositivo pode ter dever e permissão)."""
    found = set()
    for match in DUTY.finditer(text):
        token = match.group(0).lower()
        if token.startswith(("não", "é vedad")):
            found.add("prohibition")
        else:
            found.add("permission" if token.startswith("pod") else "duty")
    return found


def sentences(text):
    spans, start = [], 0
    for match in BOUNDARY.finditer(text):
        spans.append(text[start : match.end()])
        start = match.end()
    spans.append(text[start:])
    return [span.strip() for span in spans if span.strip()]


def rule_candidates(extraction):
    units = extraction["units"]
    by_id = {u["id"]: u for u in units}
    candidates = []
    for unit in units:
        if not unit["text"].strip() or unit["kind"] in {"formula", "table", "heading"}:
            continue
        if re.search(r"ignore.{0,40}instru|system prompt", unit["text"], re.I):
            continue
        parent = by_id.get(unit["parent"])
        own = DUTY.search(unit["text"])
        inherited = (
            not own
            and parent
            and DUTY.search(parent["text"])
            and unit["kind"] in {"clause", "letter", "item"}
        )
        if not own and not inherited and not re.search(r"\bprazo\s+é\s+de", unit["text"], re.I):
            continue
        pieces = [unit["text"].strip()]
        if own:
            deontic = [s for s in sentences(unit["text"]) if DUTY.search(s)]
            if unit["text"].rstrip().endswith(":") and any(
                u["parent"] == unit["id"] for u in units
            ):
                # A última frase enumera e é herdada pelos filhos; as demais não podem se perder.
                pieces = deontic[:-1]
            elif len({modality(s) for s in deontic}) > 1:
                pieces = deontic  # dever e permissão juntos: um candidato por frase
        for piece in pieces:
            context = enumerating(parent["text"]) if inherited else piece
            candidates.append(
                {
                    "subject": subject_of(context),
                    "modality": modality(context),
                    "action": piece,
                    "object": "não identificado",
                    "conditions": [m.group() for m in CONDITION.finditer(piece)],
                    "exceptions": [m.group() for m in EXCEPTION.finditer(piece)],
                    "evidence": [{"unit_id": unit["id"], "quote": piece}]
                    + (
                        [{"unit_id": parent["id"], "quote": parent["text"].strip()}]
                        if inherited
                        else []
                    ),
                    "suggested_rules": [],
                }
            )
    return candidates


def enumerating(text):
    """Frase do caput que introduz a enumeração herdada pelos filhos."""
    last = sentences(text)[-1] if text.strip() else ""
    return last if DUTY.search(last) else text


LEADING_LABEL = re.compile(
    r'^\s*[“"]?\s*(?:Art\.?\s*\d+(?:-[A-Z])?[º°]?\.?|§\s*\d+[º°]?\.?|Parágrafo único\.?'
    r"|[IVXLCDM]+\s*[–—-]|[a-z]\)|\d+(?:-[A-Z])?\.)\s*"
)


def subject_of(context):
    """Sujeito literal antes do verbo, sem rótulo do dispositivo nem oração adverbial inicial."""
    match = DUTY.search(context)
    if not match:
        return "não identificado"
    subject = LEADING_LABEL.sub("", context[: match.start()]).strip()
    # "Ao acionar o mecanismo…, a distribuidora cessionária" → "a distribuidora cessionária".
    head, _, last = subject.rpartition(",")
    if head and re.match(r"\s*(?:o|a|os|as)\s+\w", last, re.I):
        subject = last.strip()
    return "não identificado" if not subject or len(subject) > 180 else subject


def validate_item(item, allowed_ids):
    if not isinstance(item, dict):
        raise ValueError("Item não é objeto JSON")
    required = ("subject", "modality", "action", "object", "conditions", "exceptions", "evidence")
    if any(k not in item for k in required):
        raise ValueError("Campos obrigatórios ausentes")
    if not all(
        isinstance(item[k], str) and item[k].strip() for k in ("subject", "action", "object")
    ):
        raise ValueError("Sujeito, ação e objeto precisam de texto")
    if item["modality"] not in {"duty", "prohibition", "permission"}:
        raise ValueError("Modalidade inválida")
    for name in ("conditions", "exceptions"):
        if not isinstance(item[name], list) or any(not isinstance(v, str) for v in item[name]):
            raise ValueError(f"{name}: lista de textos obrigatória")
    evidence = item["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("Evidência obrigatória")
    for anchor in evidence:
        if (
            not isinstance(anchor, dict)
            or not isinstance(anchor.get("quote"), str)
            or not anchor["quote"].strip()
        ):
            raise ValueError("Trecho literal obrigatório")
        if anchor.get("unit_id") not in allowed_ids:
            raise ValueError("Unidade inexistente ou fora do escopo")
        if re.search(
            r"ignore.{0,40}instru|system prompt|revele.{0,20}senha", anchor["quote"], re.I
        ):
            raise ValueError("Instrução potencialmente maliciosa não é fundamento normativo")
    # Discard fields such as AI due_date. Only the deterministic engine creates dates.
    return {k: item[k] for k in required} | {"suggested_rules": item.get("suggested_rules", [])}


def evaluate(item, extraction, role="norm", target_dates=None, generator="rules"):
    units = extraction["units"]
    by_id = {u["id"]: u for u in units}
    item = validate_item(item, set(by_id))
    anchors = [
        verify(
            e["quote"],
            e["unit_id"],
            units,
            extraction["text_hash"],
            source=extraction.get("source"),
        )
        for e in item["evidence"]
    ]
    objections, deadlines = [], []

    def contest(kind, severity, state, anchor, explanation):
        # An objective finding has an independently verified literal basis.
        if anchor["state"] != "verified":
            return
        objections.append(
            {
                "id": digest([kind, anchor["unit_id"], anchor["quote"]])[:20],
                "kind": kind,
                "severity": severity,
                "state": state,
                "evidence": anchor,
                "explanation": explanation,
                "source": "deterministic",
            }
        )

    for anchor in anchors:
        unit = by_id[anchor["unit_id"]]
        if anchor["state"] != "verified":
            continue
        literal = anchor["quote"]
        parent = by_id.get(unit["parent"])
        inherited = parent["text"] if parent else ""
        deadlines.extend(
            rules(
                literal,
                unit["id"],
                extraction["dates"],
                inherited,
                role == "clarification",
                target_dates,
            )
        )
        explicit_modal = DUTY.search(literal)
        if explicit_modal and item["modality"] not in modalities(literal):
            contest(
                "unsupported_modality",
                "critical",
                "confirmed",
                anchor,
                "Modalidade proposta diverge da expressão literal identificada.",
            )
        if (
            not explicit_modal
            and not DUTY.search(inherited)
            and re.search(r"entende-se|define-se|para os fins|significa", literal, re.I)
        ):
            contest(
                "unsupported_duty",
                "critical",
                "confirmed",
                anchor,
                "Definição sem comando deôntico reconhecido; não sustenta o dever proposto.",
            )
        if explicit_modal:
            stated = re.sub(
                r"^Art\.?\s*\d+[º°]?\.?\s*", "", literal[: explicit_modal.start()]
            ).strip()
            if (
                stated
                and item["subject"] != "não identificado"
                and item["subject"].casefold() not in literal.casefold()
            ):
                contest(
                    "subject_mismatch",
                    "high",
                    "inconclusive",
                    anchor,
                    "Sujeito proposto não aparece literalmente; exige revisão semântica.",
                )
        for match in EXCEPTION.finditer(literal):
            if not any(match.group().casefold() in e.casefold() for e in item["exceptions"]):
                contest(
                    "ignored_exception",
                    "high",
                    "confirmed",
                    anchor,
                    "Exceção explícita não foi preservada no campo de exceções.",
                )
        for match in CONDITION.finditer(literal):
            if not any(match.group().casefold() in c.casefold() for c in item["conditions"]):
                contest(
                    "omitted_condition",
                    "high",
                    "confirmed",
                    anchor,
                    "Condição textual não foi preservada no campo de condições.",
                )
        if role == "clarification":
            contest(
                "clarification_only",
                "high",
                "inconclusive",
                anchor,
                "Fundamentação em esclarecimento; confirmar na norma vinculada.",
            )
        pending_dependencies = not extraction["links"] or any(
            link["state"] != "interpreted" for link in extraction["links"]
        )
        if re.search(r"\b(?:anexo|tabela|módulo)\b", literal, re.I) and pending_dependencies:
            contest(
                "unavailable_dependency",
                "high",
                "inconclusive",
                anchor,
                "Dependência tabular/normativa requer confirmação visual ou documento adicional.",
            )
        if len(list(PERIOD.finditer(literal))) > 1 or len({a["unit_id"] for a in anchors}) > 2:
            contest(
                "grouped_actions",
                "high",
                "inconclusive",
                anchor,
                "Mais de uma regra ou múltiplos fundamentos: conferir atomicidade e vínculo temporal.",
            )
        for suggestion in item.get("suggested_rules", []):
            if not isinstance(suggestion, dict) or suggestion.get("unit_id") != unit["id"]:
                continue
            actual = [d for d in deadlines if d["unit_id"] == unit["id"]]
            if actual and suggestion.get("quantity") not in [d["quantity"] for d in actual]:
                contest(
                    "incorrect_period",
                    "critical",
                    "confirmed",
                    anchor,
                    "Quantidade temporal proposta diverge das quantidades literais.",
                )
            if actual and suggestion.get("landmark") not in [d["landmark"] for d in actual]:
                contest(
                    "wrong_landmark",
                    "critical",
                    "confirmed",
                    anchor,
                    "Marco proposto diverge do marco localizado no trecho da regra.",
                )
    # Keep one immutable finding per evidence/type and one deadline per rule.
    objections = list({o["id"]: o for o in objections}.values())
    reasons = [a.get("reason", "") for a in anchors if a["state"] != "verified"]
    reasons += [o["explanation"] for o in objections if o["state"] != "rejected"]
    reasons += [d["explanation"] for d in deadlines if d["state"] == "not_calculated"]
    if any(a["state"] == "invalid" for a in anchors) or any(
        o["severity"] == "critical" and o["state"] == "confirmed" for o in objections
    ):
        band = "blocked"
    elif reasons:
        band = "attention"
    else:
        band = "ready"
    return item | {
        "anchors": anchors,
        "deadlines": deadlines,
        "objections": objections,
        "band": band,
        "reasons": reasons,
        "generator": generator,
        "status": "detected"
        if generator == "rules"
        else ("pending_review" if generator == "human" else "suggested"),
    }


def assert_reviewable(data, extraction, resolved):
    if not data["anchors"] or not all(
        recheck(a, extraction["text"], extraction["units"]) for a in data["anchors"]
    ):
        raise ValueError("Validação bloqueada: há evidência inválida ou pendente.")
    unresolved = [
        o for o in data["objections"] if o["state"] == "confirmed" and o["id"] not in resolved
    ]
    if unresolved:
        raise ValueError(
            "Validação bloqueada: resolva as contestações confirmadas com decisão motivada."
        )
