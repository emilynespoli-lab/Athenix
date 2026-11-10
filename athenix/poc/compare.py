"""Comparação de duas extrações da mesma norma. Nunca escolhe uma fonte: só classifica e expõe.

Casamento por chave estrutural (norma-alvo + caminho de dispositivos); texto comparado após
normalização reversível (espaços, aspas, travessões). Divergência em que um lado veio de OCR é
rotulada à parte, pois pode ser erro de leitura e não diferença real entre as versões.
"""

import difflib
import re
from collections import Counter

from ..evidence import normalize

EQUAL = 1.0
NEAR = 0.9  # shortcut: limiar de equivalência incerta, calibrar com pares rotulados
SKIP = {"unstructured"}


def _owner(value):
    return "self" if value == "self" else re.sub(r"\D", "", value)


def _path(unit, by_id):
    parts = []
    while unit:
        parts.append(f"{unit['kind']}:{unit['label']}")
        unit = by_id.get(unit["parent"])
    return "/".join(reversed(parts))


def _norm(text):
    # Hifenização de quebra de linha e espaços não alteram o dispositivo.
    flat = normalize(re.sub(r"-\n(?=[a-zà-ú])", "", text))[0]
    return re.sub(r"\s+", " ", flat).strip().casefold()


def _keyed(extraction, pages):
    units = extraction["units"]
    by_id = {u["id"]: u for u in units}
    source = {p["number"]: p["source"] for p in pages}
    seen, out = Counter(), {}
    for unit in units:
        if unit["kind"] in SKIP:
            continue
        base = (_owner(unit["owner"]), _path(unit, by_id))
        seen[base] += 1
        key = base + (seen[base],)  # ocorrência: o mesmo número pode repetir (ex.: tabelas "...")
        out[key] = unit | {
            "norm": _norm(unit["text"]),
            "from_ocr": any(source.get(n) == "ocr" for n in unit["pages"]),
        }
    return out


def _brief(unit):
    return {
        "unit_id": unit["id"],
        "kind": unit["kind"],
        "label": unit["label"],
        "owner": unit["owner"],
        "pages": unit["pages"],
        "start": unit["start"],
        "end": unit["end"],
        "from_ocr": unit["from_ocr"],
    }


def _changes(a, b, limit=5, context=3):
    """Diferenças por palavra, com algumas palavras de contexto para leitura humana."""
    wa, wb = a.split(), b.split()
    matcher = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    return [
        {
            "a": " ".join(wa[max(i1 - context, 0) : i2 + context])[:200],
            "b": " ".join(wb[max(j1 - context, 0) : j2 + context])[:200],
        }
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ][:limit]


def compare(first, second):
    """`first`/`second`: saída de `reader.read_pdf`."""
    ka = _keyed(first["extraction"], first["pages"])
    kb = _keyed(second["extraction"], second["pages"])
    result = {"equal": [], "divergent": [], "uncertain": [], "only_a": [], "only_b": []}
    for key in ka.keys() & kb.keys():
        a, b = ka[key], kb[key]
        ratio = difflib.SequenceMatcher(None, a["norm"], b["norm"], autojunk=False).ratio()
        entry = {
            "key": "|".join(map(str, key)),
            "a": _brief(a),
            "b": _brief(b),
            "ratio": round(ratio, 4),
        }
        if a["norm"] == b["norm"]:
            result["equal"].append(entry)
        else:
            entry["changes"] = _changes(a["norm"], b["norm"])
            entry["possible_ocr_error"] = a["from_ocr"] or b["from_ocr"]
            result["divergent"].append(entry)
    rest_a = {k: v for k, v in ka.items() if k not in kb}
    rest_b = {k: v for k, v in kb.items() if k not in ka}
    taken = set()
    for key, a in rest_a.items():
        best, best_key = 0.0, None
        for other, b in rest_b.items():
            if other in taken or abs(len(a["norm"]) - len(b["norm"])) > 0.3 * max(
                len(a["norm"]), 1
            ):
                continue
            ratio = difflib.SequenceMatcher(None, a["norm"], b["norm"], autojunk=False).ratio()
            if ratio > best:
                best, best_key = ratio, other
        if best_key is not None and best >= NEAR and a["norm"]:
            taken.add(best_key)
            result["uncertain"].append(
                {
                    "key_a": "|".join(map(str, key)),
                    "key_b": "|".join(map(str, best_key)),
                    "a": _brief(a),
                    "b": _brief(rest_b[best_key]),
                    "ratio": round(best, 4),
                    "reason": "texto semelhante com chave estrutural diferente",
                }
            )
        else:
            result["only_a"].append({"key": "|".join(map(str, key)), "a": _brief(a)})
    result["only_b"] = [
        {"key": "|".join(map(str, k)), "b": _brief(v)} for k, v in rest_b.items() if k not in taken
    ]
    for group in result.values():
        group.sort(key=lambda e: str(e.get("key") or e.get("key_a")))
    return {
        "a": first["document"],
        "b": second["document"],
        "counts": {k: len(v) for k, v in result.items()},
        "readable_problems": {
            side["document"]["file"]: [
                {"page": p["number"], "state": p["state"], "reasons": p["reasons"]}
                for p in side["pages"]
                if p["state"] != "faithful"
            ]
            for side in (first, second)
        },
        **result,
        "note": "Sem preferência de fonte: divergências e exclusividades ficam para revisão humana.",
    }
