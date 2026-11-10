import re

from .db import digest

TRANSLATION = {c: '"' for c in "“”„‟"} | {c: "'" for c in "‘’"} | {c: "-" for c in "–—"}


def normalize(text):
    chars, positions = [], []
    for index, character in enumerate(text):
        converted = " " if character.isspace() else TRANSLATION.get(character, character)
        if converted == " " and chars and chars[-1] == " ":
            continue
        chars.append(converted)
        positions.append(index)
    return "".join(chars), positions


def locations(quote, text):
    if not quote:
        return []
    return [match.start() for match in re.finditer(re.escape(quote), text)]


def verify(quote, unit_id, units, text_hash, minimum=16):
    unit = next((u for u in units if u["id"] == unit_id), None)
    result = {
        "unit_id": unit_id,
        "proposed_quote": quote,
        "state": "invalid",
        "candidates": [],
        "text_hash": text_hash,
    }
    if not unit:
        return result | {"reason": "unidade inexistente"}
    normalized_quote, _ = normalize(quote)
    if len(normalized_quote.strip()) < minimum:
        return result | {"state": "pending", "reason": "trecho curto demais"}
    original = locations(quote, unit["text"])
    normalized_text, positions = normalize(unit["text"])
    normalized_hits = locations(normalized_quote, normalized_text)
    hits = original or normalized_hits
    if len(hits) == 1:
        start = hits[0] if original else positions[hits[0]]
        end = (
            (start + len(quote)) if original else positions[hits[0] + len(normalized_quote) - 1] + 1
        )
        literal = unit["text"][start:end]
        return result | {
            "state": "verified",
            "method": "exact" if original else "normalized",
            "start": unit["start"] + start,
            "end": unit["start"] + end,
            "quote": literal,
            "quote_hash": digest(literal.encode()),
            "prefix": unit["text"][max(0, start - 32) : start],
            "suffix": unit["text"][end : end + 32],
        }
    if len(hits) > 1:
        return result | {"state": "pending", "reason": "trecho repetido: posição ambígua"}
    for other in units:
        candidate_text, _ = normalize(other["text"])
        if other["id"] != unit_id and normalized_quote in candidate_text:
            result["candidates"].append(other["id"])
    if result["candidates"]:
        return result | {"state": "pending", "reason": "trecho localizado em outra unidade"}
    return result | {"reason": "trecho não localizado literalmente"}


def recheck(anchor, text, units):
    if anchor.get("state") != "verified":
        return False
    literal = text[anchor["start"] : anchor["end"]]
    unit = next((u for u in units if u["id"] == anchor["unit_id"]), None)
    return bool(
        unit
        and unit["start"] <= anchor["start"] < anchor["end"] <= unit["end"]
        and literal == anchor["quote"]
        and digest(literal.encode()) == anchor["quote_hash"]
        and digest(text.encode()) == anchor["text_hash"]
    )
