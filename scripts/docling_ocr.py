"""OCR e análise de layout com Docling para páginas sem camada de texto.

Roda no interpretador que tiver Docling instalado (ver docs/docling.md), isolado do projeto:
    python scripts/docling_ocr.py ENTRADA.pdf PRIMEIRA ULTIMA SAIDA.json [PASTA_IMAGENS]
Saída: {"engine", "pages": {n: {"lines", "review", "ocr_score", "layout"}}}. Cada linha de OCR traz
confiança própria e bbox em pontos PDF (origem no canto superior esquerdo). Usa as linhas do OCR
(não os parágrafos do layout, que às vezes fundem a página inteira em um bloco) e as tabelas do
TableFormer, uma linha por linha de tabela.
"""

import json
import math
import sys
from collections import Counter
from importlib.metadata import version
from pathlib import Path

FORMULA, TABLE = "formula", "table"


def _box(box, height):
    if box.coord_origin.value != "TOPLEFT":
        box = box.to_top_left_origin(height)
    return [round(v, 2) for v in (box.l, box.t, box.r, box.b)]


def main(pdf, first, last, out, images=None):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.doc.document import TableItem

    options = PdfPipelineOptions()
    options.do_ocr = True
    options.do_table_structure = True
    options.generate_page_images = bool(images)
    options.ocr_options = RapidOcrOptions(force_full_page_ocr=True)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    result = converter.convert(pdf, page_range=(first, last))
    document = result.document
    heights = {n: p.size.height for n, p in document.pages.items()}
    pages = {}
    for page in result.pages:
        number = page.page_no
        score = result.confidence.pages[number].ocr_score
        score = None if score is None or math.isnan(score) else round(float(score), 4)
        clusters = getattr(getattr(page, "predictions", None), "layout", None)
        clusters = getattr(clusters, "clusters", []) or []
        labels = Counter(c.label.value for c in clusters)
        review = []
        if labels[FORMULA]:
            review.append(
                f"{labels[FORMULA]} região(ões) de fórmula: OCR de fórmula não habilitado"
            )
        lines, seen = [], set()
        for cluster in clusters:
            if cluster.label.value == TABLE:
                continue  # as células da tabela entram pelas linhas do TableFormer abaixo
            for cell in cluster.cells:
                text, bbox = cell.text.strip(), _box(cell.to_bounding_box(), heights[number])
                if not text or (text, *bbox) in seen:
                    continue
                seen.add((text, *bbox))
                conf = None if cell.confidence is None else round(float(cell.confidence), 4)
                lines.append(
                    {"text": text, "bbox": bbox, "conf": conf, "kind": cluster.label.value}
                )
        pages[number] = {
            "lines": lines,
            "review": review,
            "ocr_score": score,
            "layout": dict(labels),
        }
        if images and page.image is not None:
            Path(images).mkdir(parents=True, exist_ok=True)
            try:
                page.image.save(Path(images) / f"p{number:03d}.png")
            except Exception as error:  # imagem é auxílio de conferência; não derruba o OCR
                review.append(f"imagem da página não salva: {type(error).__name__}")
    counters = Counter()
    for item, _ in document.iterate_items():
        if not isinstance(item, TableItem) or not item.prov:
            continue
        number = item.prov[0].page_no
        if number not in pages:
            continue
        counters[number] += 1
        bbox = _box(item.prov[0].bbox, heights[number])
        for index, row in enumerate(item.data.grid):
            pages[number]["lines"].append(
                {
                    "text": " | ".join(cell.text.strip() for cell in row),
                    "bbox": bbox,
                    "conf": pages[number]["ocr_score"],  # TableFormer: só há nota da página
                    "kind": "table_row",
                    "table_id": f"p{number}-t{counters[number]}",
                    "row": index,
                }
            )
    for entry in pages.values():
        # Ordem de leitura de coluna única: de cima para baixo, esquerda para direita.
        entry["lines"].sort(key=lambda ln: (ln["bbox"][1], ln["bbox"][0]))
    engine = f"docling/{version('docling')}+rapidocr/{version('rapidocr')}"
    Path(out).write_text(
        json.dumps(
            {"engine": engine, "pages": pages}, ensure_ascii=False, indent=1, sort_keys=True
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], *sys.argv[5:6])
