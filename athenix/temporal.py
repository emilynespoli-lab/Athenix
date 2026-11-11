import calendar
import re
from datetime import date, timedelta

from .structure import DATE, parse_date

NUMBERS = {
    **dict.fromkeys(("um", "uma"), 1), **dict.fromkeys(("dois", "duas"), 2),
    **dict.fromkeys(("três", "tres"), 3), "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
    "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13,
    **dict.fromkeys(("catorze", "quatorze"), 14), "quinze": 15, "dezesseis": 16,
    "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20, "trinta": 30, "quarenta": 40,
    "cinquenta": 50, "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90,
    **dict.fromkeys(("cem", "cento"), 100), **dict.fromkeys(("duzentos", "duzentas"), 200),
    **dict.fromkeys(("trezentos", "trezentas"), 300), "quatrocentos": 400, "quinhentos": 500,
    "seiscentos": 600, "setecentos": 700, "oitocentos": 800, "novecentos": 900,
}  # fmt: skip
_WORD = "|".join(sorted(NUMBERS, key=len, reverse=True))
# Quantidade em algarismos ("90 (noventa) dias") ou por extenso ("cento e vinte dias").
PERIOD = re.compile(
    rf"\b(\d+|(?:{_WORD})(?:\s+e\s+(?:{_WORD}))*)\s*(?:\([^)]{{1,60}}\)\s*)?"
    r"(dias?(?:\s+úteis|\s+corridos)?|meses|mês|anos?)\b",
    re.I,
)
# Publicação/vigência da própria norma ("da publicação", "desta Resolução") × de outro ato
# ("da publicação das instruções", "da minuta"), que é evento futuro sem data.
OWN_MARK = re.compile(
    r"\b(publicação|vigência|entrada em vigor)(?:\s+(dest[ae]|d[aoe]s?)\s+(\w+))?", re.I
)
EVENT = re.compile(
    r"\b(?:contad[oa]s?|a\s+partir|após|antes|advento)\b[^.;]{0,30}?\bd[aoe]s?\s+\w+", re.I
)


def quantity(token):
    if token.isdigit():
        return int(token)
    return sum(NUMBERS[word] for word in re.split(r"\s+e\s+", token.lower()))


def landmark(text):
    mark = OWN_MARK.search(text)
    if mark:
        connector, noun = (mark.group(2) or "").lower(), (mark.group(3) or "").lower()
        if not connector or connector.startswith("dest") or noun == "presente":
            if mark.group(1).lower() == "publicação":
                return "publication", "Publicação da norma"
            return "effective", "Vigência da norma"
        return "event", mark.group(0)[:1].upper() + mark.group(0)[1:]
    event = EVENT.search(text)
    if event:
        return "event", event.group(0).strip()
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
        # Ponto ou ponto e vírgula fecham a cláusula; quebra de linha do PDF/HTML não.
        tail = re.split(r"[.;]", text[match.end() : end], maxsplit=1)[0]
        local = text[left : match.end()] + tail
        kind, label = landmark(local)
        inherited_used = False
        if kind == "unknown" and inherited:
            kind, label = landmark(inherited)
            inherited_used = kind != "unknown"
        amount, unit = quantity(match.group(1)), match.group(2).lower()
        direction = -1 if re.search(r"\bantes\b|\bantecedência\b", local, re.I) else 1
        record = {
            "unit_id": unit_id,
            "quantity": amount,
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
                    amount, unit, date.fromisoformat(base), direction
                ).isoformat()
                record["state"] = "provisional"
                record["base"] = base
                reason = "Calculado; convenção ainda não confirmada por pessoa"
            except (ValueError, OverflowError):
                reason = "Quantidade fora do intervalo suportado"
        record["explanation"] = (
            f"{amount} {unit}; marco: {label}; base: {base or 'desconhecida'}; "
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
