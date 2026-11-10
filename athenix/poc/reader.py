"""Leitura documental da PoC: identidade, hash e texto por página com estado de fidelidade.

Nada é descartado em silêncio: página sem texto vira `not_extracted`, imagem em página com
texto e tabelas viram `needs_review`, e texto vindo de OCR é sempre `uncertain` no mínimo.
"""

import hashlib
import io
from importlib.metadata import version
from pathlib import Path

import pdfplumber

from ..structure import from_pieces

FAITHFUL, UNCERTAIN, MISSING, REVIEW = "faithful", "uncertain", "not_extracted", "needs_review"
_RANK = {FAITHFUL: 0, UNCERTAIN: 1, REVIEW: 2, MISSING: 3}
LOW_CONFIDENCE = 0.85  # shortcut: limiar empírico de OCR, calibrar com conjunto rotulado


def worst(*states):
    return max(states, key=_RANK.__getitem__)


def identify(path):
    content = Path(path).read_bytes()
    if not content.startswith(b"%PDF-"):
        raise ValueError(f"{path}: conteúdo não é PDF (assinatura %PDF- ausente).")
    return content, {
        "file": Path(path).name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }


def _tables(page):
    found = []
    for index, table in enumerate(page.find_tables(), start=1):
        rows = table.extract()
        found.append(
            {
                "id": f"p{page.page_number}-t{index}",
                "page": page.page_number,
                "bbox": [round(v, 2) for v in table.bbox],
                "header": rows[0] if rows else [],
                "rows": rows,
                # Células reconstruídas por geometria não são certificadas.
                "state": UNCERTAIN,
            }
        )
    return found


def _page_lines(page, ocr_page):
    """Linhas com bbox [x0, top, x1, bottom] em pontos PDF, e a origem do texto."""
    if ocr_page is not None:
        return "ocr", [
            dict(ln) for ln in (ocr_page["lines"] if isinstance(ocr_page, dict) else ocr_page)
        ]
    lines = [
        {"text": ln["text"], "bbox": [ln["x0"], ln["top"], ln["x1"], ln["bottom"]], "conf": None}
        for ln in page.extract_text_lines()
        if ln["text"].strip()
    ]
    return "text_layer", lines


def _ocr_tables(number, lines):
    grouped = {}
    for ln in lines:
        if ln.get("table_id"):
            grouped.setdefault(ln["table_id"], []).append(ln)
    return [
        {
            "id": table_id,
            "page": number,
            "bbox": rows[0]["bbox"],
            "header": rows[0]["text"].split(" | "),
            "rows": [r["text"].split(" | ") for r in rows],
            "state": UNCERTAIN,
        }
        for table_id, rows in grouped.items()
    ]


def read_pdf(path, settings, ocr=None):
    """`ocr`: {página: lista de linhas | {"lines", "review", "ocr_score"}} ou None. Dicionário puro."""
    content, document = identify(path)
    pieces, pages, tables, links, offset = [], [], [], [], 0
    try:
        pdf = pdfplumber.open(io.BytesIO(content))
    except Exception as error:
        raise ValueError(
            f"{document['file']}: PDF corrompido, protegido ou não suportado."
        ) from error
    with pdf:
        if len(pdf.pages) > settings.max_pages:
            raise ValueError(f"{document['file']}: PDF excede o limite de páginas.")
        for page in pdf.pages:
            number = page.page_number
            # Só consulta o OCR quando não há camada de texto; a camada digital prevalece.
            ocr_page = (ocr or {}).get(number) if not page.chars else None
            source, lines = _page_lines(page, ocr_page)
            notes = ocr_page.get("review", []) if isinstance(ocr_page, dict) else []
            text = "\n".join(line["text"] for line in lines)
            cursor = 0
            for line in lines:
                line["start"] = offset + cursor
                line["end"] = line["start"] + len(line["text"])
                cursor += len(line["text"]) + 1
            reasons, state = [], FAITHFUL
            images = len(page.images)
            page_tables = _tables(page) if page.chars else []
            if not page.chars and (ghost := len(page.find_tables())):
                reasons.append(f"{ghost} região(ões) tabular(es) gráfica(s) sem texto; requer OCR")
            if not text.strip():
                state = MISSING
                reasons.append(f"sem texto extraível; {images} imagem(ns); requer OCR/inspeção")
            elif source == "ocr":
                confidences = [ln["conf"] for ln in lines if ln.get("conf") is not None]
                state = UNCERTAIN
                reasons.append("texto proveniente de OCR")
                if not confidences:
                    state = REVIEW
                    reasons.append("OCR sem confiança por linha")
                elif min(confidences) < LOW_CONFIDENCE:
                    state = REVIEW
                    low = sum(c < LOW_CONFIDENCE for c in confidences)
                    reasons.append(f"{low} linha(s) com confiança < {LOW_CONFIDENCE}")
                if isinstance(ocr_page, dict):
                    reasons.append(f"pontuação de OCR da página: {ocr_page.get('ocr_score')}")
                if notes:
                    state = REVIEW
                    reasons.extend(notes)
            elif images:
                state = REVIEW
                reasons.append(f"{images} imagem(ns) na página: conteúdo visual não extraído")
            if page_tables:
                state = worst(state, REVIEW)
                reasons.append(f"{len(page_tables)} tabela(s) reconstruída(s) por geometria")
            page_tables += _ocr_tables(number, lines)
            if page_tables and source == "ocr":
                state = worst(state, REVIEW)
                reasons.append(
                    f"{len(page_tables)} tabela(s) por OCR/TableFormer, células não certificadas"
                )
            tables.extend(page_tables)
            for link in page.hyperlinks:
                links.append(
                    {
                        "id": f"link-{len(links)}",
                        "url": link.get("uri", ""),
                        "label": "Link do PDF",
                        "page": number,
                        "state": "identified",
                    }
                )
            pieces.append(text)
            pages.append(
                {
                    "number": number,
                    "source": source if text.strip() else "none",
                    "state": state,
                    "reasons": reasons,
                    "characters": len(text),
                    "images": images,
                    "width": float(page.width),
                    "height": float(page.height),
                    "lines": lines,
                }
            )
            offset += len(text) + 3  # separador "\n\f\n" de from_pieces
    engines = sorted({v.get("engine", "ocr") for v in (ocr or {}).values() if isinstance(v, dict)})
    extractor = f"pdfplumber/{version('pdfplumber')}" + "".join(
        f"+{e}" for e in engines or (["ocr"] if ocr else [])
    )
    extraction = from_pieces(pieces, links, [], extractor, settings)
    return {"document": document, "pages": pages, "tables": tables, "extraction": extraction}


def boxes(pages, start, end):
    """Linhas (página, bbox, texto) que se sobrepõem ao intervalo [start, end) do texto canônico."""
    return [
        {"page": p["number"], "bbox": ln["bbox"], "text": ln["text"]}
        for p in pages
        for ln in p["lines"]
        if ln["start"] < end and ln["end"] > start
    ]
