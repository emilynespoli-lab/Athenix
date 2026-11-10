"""Artefato determinístico de resultados, separado dos IDs e instantes operacionais."""

from .db import canonical, digest


def result_content(data):
    anchor_fields = (
        "unit_id",
        "state",
        "method",
        "start",
        "end",
        "quote",
        "proposed_quote",
        "text_hash",
        "reason",
        "candidates",
    )

    def anchor_content(anchor):
        return {key: anchor[key] for key in anchor_fields if key in anchor}

    return {
        key: data[key]
        for key in (
            "subject",
            "modality",
            "action",
            "object",
            "conditions",
            "exceptions",
            "band",
            "reasons",
        )
    } | {
        "anchors": [anchor_content(a) for a in data["anchors"]],
        "deadlines": data["deadlines"],
        "objections": [
            {key: o[key] for key in ("kind", "severity", "state", "explanation")}
            | {"evidence": anchor_content(o["evidence"])}
            for o in data["objections"]
        ],
    }


def bundle(file_hash, text_hash, interpretations):
    items = sorted([result_content(data) for data in interpretations], key=canonical)
    content = {
        "contract": "athenix-deterministic-v1",
        "file_sha256": file_hash,
        "text_sha256": text_hash,
        "items": items,
    }
    return {"sha256": digest(content), "content": content}
