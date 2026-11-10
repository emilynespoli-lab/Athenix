import calendar
import re
from datetime import date, timedelta

from .structure import DATE, parse_date

PERIOD = re.compile(
    r"\b(\d+)\s*(?:\([^)]{1,60}\)\s*)?(dias?(?:\s+úteis|\s+corridos)?|meses|mês|anos?)\b", re.I
)


def landmark(text):
    lower = text.lower()
    if re.search(r"publicação\s+d[ao]s?\s+(?:instru|portaria|ato|orienta|procedimento)", lower):
        return "event", "Publicação de instruções/ato futuro"
    if re.search(
        r"(?:após|antes|contad[oa]s?|a partir).{0,25}(?:evento|ocorrência|solicitação|recebimento)",
        lower,
    ):
        return "event", text.strip()
    if "publicação" in lower:
        return "publication", "Publicação da norma"
    if "vigência" in lower or "entrada em vigor" in lower:
        return "effective", "Vigência da norma"
    return "unknown", "Marco não identificado"


def unique_date(dates, kind):
    candidates = {d["date"] for d in dates if d["kind"] == kind}
    return next(iter(candidates)) if len(candidates) == 1 else None


def compute(quantity, unit, base, direction=1, convention="last_day"):
    if unit.startswith("dia"):
        return base + timedelta(days=direction * quantity)
    months = quantity * (12 if unit.startswith("ano") else 1) * direction
    absolute = base.year * 12 + base.month - 1 + months
    year, month = divmod(absolute, 12)
    month += 1
    last = calendar.monthrange(year, month)[1]
    if base.day > last and convention == "next_day":
        return date(year, month, last) + timedelta(days=1)
    return date(year, month, min(base.day, last))


def rules(text, unit_id, dates, inherited="", clarification=False, target_dates=None):
    result = []
    periods = list(PERIOD.finditer(text))
    for index, match in enumerate(periods):
        left = max(text.rfind(".", 0, match.start()) + 1, text.rfind(";", 0, match.start()) + 1)
        end = periods[index + 1].start() if index + 1 < len(periods) else len(text)
        # A semicolon or sentence end closes this temporal clause.
        tail = re.split(r"[.;\n]", text[match.end() : end], maxsplit=1)[0]
        local = text[left : match.end()] + tail
        kind, label = landmark(local)
        inherited_used = False
        if kind == "unknown" and inherited:
            kind, label = landmark(inherited)
            inherited_used = kind != "unknown"
        quantity, unit = int(match.group(1)), match.group(2).lower()
        direction = -1 if re.search(r"\bantes\b", local, re.I) else 1
        record = {
            "unit_id": unit_id,
            "quantity": quantity,
            "unit": unit,
            "landmark": kind,
            "event": label,
            "quote": local.strip(),
            "direction": direction,
            "convention": "exclude_start_last_day_v1",
            "inherited": inherited_used,
            "date": None,
            "state": "not_calculated",
        }
        relevant_dates = (target_dates or []) if clarification else dates
        base = unique_date(relevant_dates, kind)
        if "úteis" in unit:
            reason = "Calendário de feriados versionado ausente"
        elif kind == "event":
            record["state"] = "awaiting_event"
            reason = label + "; sem data até o evento"
        elif not base:
            reason = "Marco desconhecido ou datas conflitantes; nenhuma data presumida"
        else:
            try:
                record["date"] = compute(
                    quantity, unit, date.fromisoformat(base), direction
                ).isoformat()
                record["state"] = "provisional"
                record["base"] = base
                reason = "Calculado; convenção ainda não confirmada por pessoa"
            except (ValueError, OverflowError):
                reason = "Quantidade fora do intervalo suportado"
        record["explanation"] = (
            f"{quantity} {unit}; marco: {label}; base: {base or 'desconhecida'}; "
            f"direção: {'antes' if direction < 0 else 'após'}; "
            f"convenção: exclui início, mês limitado ao último dia (v1). {reason}."
        )
        result.append(record)
    if not periods:
        for match in DATE.finditer(text):
            parsed = parse_date(match)
            if parsed and re.search(
                r"até|prazo|limite", text[max(0, match.start() - 35) : match.start()], re.I
            ):
                result.append(
                    {
                        "unit_id": unit_id,
                        "quantity": None,
                        "unit": "fixed_date",
                        "landmark": "fixed",
                        "date": parsed,
                        "state": "provisional",
                        "quote": match.group(),
                        "convention": "explicit_date_v1",
                        "explanation": f"Data fixa explícita: {parsed}; fundamento: {unit_id}; confirmação humana pendente.",
                    }
                )
    return result
