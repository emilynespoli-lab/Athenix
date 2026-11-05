"""Extração e segmentação independentes; offsets no texto canônico, sem reparos ocultos."""

import io
import re
from importlib.metadata import version

from bs4 import BeautifulSoup

from .db import digest

ARTICLE = re.compile(r'^\s*[“"]?\s*Art\.?\s*(\d+(?:[º°])?(?:-[A-Z])?)\.?\s*', re.I)
PARAGRAPH = re.compile(r'^\s*[“"]?\s*(§\s*\d+[º°]?|Parágrafo único)\.?\s*', re.I)
CLAUSE = re.compile(r"^\s*([IVXLCDM]+)\s*[–—-]\s+")
LETTER = re.compile(r"^\s*([a-z])\)\s+")
ITEM = re.compile(r"^\s*(\d+(?:-[A-Z])?)\.\s+")
ANNEX = re.compile(r'^\s*[“"]?\s*ANEXO\s+([IVXLCDM\d]+)', re.I)
TABLE = re.compile(r"^\s*Tabela\s+(\d+)", re.I)
ACT = re.compile(
    r"(?:Resolução(?:\s+Normativa)?|Lei|Decreto|Portaria)\s*(?:n[º°o.]*)?\s*[\d.]+(?:/\d{4})?", re.I
)
MONTHS = {
    name: i + 1
    for i, name in enumerate(
        (
            "janeiro",
            "fevereiro",
            "março",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        )
    )
}
DATE = re.compile(
    r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b|\b(\d{1,2})\s+de\s+("
    + "|".join(MONTHS)
    + r")\s+de\s+(\d{4})\b",
    re.I,
)


def detect_media(content, limit):
    if not content or len(content) > limit:
        raise ValueError("Arquivo vazio ou acima do limite de 10 MiB.")
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    beginning = content[:4096].decode("utf-8-sig", errors="replace").lstrip()
    if re.search(r"<(?:!doctype\s+html|html|head|body|article|main)\b", beginning, re.I):
        return "text/html"
    raise ValueError("Conteúdo não reconhecido. Envie PDF ou HTML; a extensão não define o tipo.")


def parse_date(match):
    from datetime import date

    a, b, c, d, e, f = match.groups()
    try:
        return date(int(c or f), int(b) if b else MONTHS[e.lower()], int(a or d)).isoformat()
    except ValueError:
        return None


def act_dates(text):
    found = []
    for match in DATE.finditer(text):
        context = text[max(0, match.start() - 100) : match.start()].lower()
        kind = None
        if re.search(r"publica(?:d[ao]|ção)|diário oficial|\bdou\b", context):
            kind = "publication"
        elif re.search(r"vig[êe]ncia|entra em vigor", context):
            kind = "effective"
        elif re.search(r"assina|brasília|resolução[^\n]{0,60}\bde\s*$", context):
            kind = "signature"
        parsed = parse_date(match)
        if kind and parsed:
            start = max(0, text.rfind("\n", 0, match.start()) + 1)
            end = text.find("\n", match.end())
            end = len(text) if end < 0 else end
            found.append(
                {"kind": kind, "date": parsed, "start": start, "end": end, "quote": text[start:end]}
            )
    return found


def segment(text, pages, faq=False):
    markers = []
    quoted = False
    target = None
    stack = []
    offset = 0
    in_table = False
    warnings = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if not quoted:
            acts = ACT.findall(line)
            if acts and re.search(r"altera|redação|passa|fica|resolução", line, re.I):
                target = acts[-1]
        starts_quote = stripped.startswith(("“", '"'))
        owner = target if quoted or starts_quote else "self"
        kind, label, depth, matched = None, None, 0, None
        question = re.match(r"^\s*(\d+\.\d+)\s+", line) if faq else None
        if question:
            kind, label, depth = "question", question.group(1), 2
        for pattern, candidate_kind, level in (
            (ARTICLE, "article", 1),
            (PARAGRAPH, "paragraph", 2),
            (ANNEX, "annex", 1),
            (TABLE, "table", 5),
            (CLAUSE, "clause", 3),
            (ITEM, "item", 4),
            (LETTER, "letter", 4),
        ):
            if question:
                break
            matched = pattern.match(line)
            if matched:
                if in_table and candidate_kind in {"letter", "clause"}:
                    continue
                kind, label, depth = candidate_kind, matched.group(1), level
                break
        if not kind and re.search(r"[=∑∫]|\b[fF]\s*\([^)]*\)\s*=", line):
            kind, label, depth = "formula", str(len(markers) + 1), 5
        if kind == "letter":
            # No PRODIST as alíneas pertencem ao item numerado; na LC 95 ficam sob o inciso.
            context = next(
                (
                    m
                    for m in reversed(stack)
                    if m["owner"] == owner
                    and m["kind"] in {"item", "clause", "paragraph", "article", "annex"}
                ),
                None,
            )
            if context and context["kind"] == "item":
                depth = context["depth"] + 1
        if kind:
            if kind != "table" and kind in {"article", "paragraph", "item", "annex"}:
                in_table = False
            if kind == "table":
                in_table = True
            while stack and (stack[-1]["depth"] >= depth or stack[-1]["owner"] != owner):
                stack.pop()
            parent = stack[-1]["id"] if stack else None
            identifier = f"u{len(markers) + 1:04d}"
            marker = {
                "id": identifier,
                "kind": kind,
                "label": label,
                "depth": depth,
                "parent": parent,
                "owner": owner or "unresolved",
                "start": offset,
            }
            markers.append(marker)
            stack.append(marker)
            if owner is None:
                warnings.append("Bloco citado com norma-alvo não resolvida: " + identifier)
        for character in line:
            if character == "“":
                quoted = True
            elif character == "”":
                quoted = False
            elif character == '"':
                quoted = not quoted
        offset += len(line)
    if not markers or markers[0]["start"] > 0:
        markers.insert(
            0,
            {
                "id": "preamble",
                "kind": "unstructured",
                "label": "Preâmbulo",
                "depth": 0,
                "parent": None,
                "owner": "self",
                "start": 0,
            },
        )
    for index, marker in enumerate(markers):
        marker["end"] = markers[index + 1]["start"] if index + 1 < len(markers) else len(text)
        marker["text"] = text[marker["start"] : marker["end"]]
        marker["pages"] = [
            p["number"] for p in pages if p["start"] < marker["end"] and p["end"] > marker["start"]
        ]
    if not any(m["kind"] == "article" or (faq and m["kind"] == "question") for m in markers):
        warnings.append("Estrutura LC 95 não reconhecida; conteúdo não estruturado exige revisão.")
    if quoted:
        warnings.append("Aspas sem fechamento: autoria do bloco precisa de conferência.")
    return markers, warnings


def extract(content, media, settings, role=None):
    warnings, links = [], []
    pieces = []
    faq = role == "clarification"
    if media == "text/html":
        soup = BeautifulSoup(content, "html.parser")
        title = soup.title.get_text() if soup.title else ""
        faq = faq or bool(re.search(r"\bFAQ\b|perguntas frequentes", title, re.I))
        for tag in soup(["script", "style", "noscript", "iframe", "object", "svg"]):
            tag.decompose()
        main_content = (
            soup.find(id="content-core")
            or soup.find("main")
            or soup.find("article")
            or soup.body
            or soup
        )
        for index, link in enumerate(main_content.find_all("a", href=True)):
            links.append(
                {
                    "id": f"link-{index}",
                    "url": link["href"],
                    "label": link.get_text(" ", strip=True),
                    "page": 1,
                    "state": "identified",
                }
            )
        pieces = [main_content.get_text("\n", strip=True)]
        extractor = "beautifulsoup4/" + version("beautifulsoup4") + ":main-v1"
    else:
        import pdfplumber

        extractor = "pdfplumber/" + version("pdfplumber")
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                if len(pdf.pages) > settings.max_pages:
                    raise ValueError("PDF excede o limite de páginas.")
                for page in pdf.pages:
                    pieces.append(page.extract_text() or "")
                    if not pieces[-1].strip():
                        warnings.append(f"Página {page.page_number} sem texto: requer OCR.")
                    for annotation in page.hyperlinks:
                        links.append(
                            {
                                "id": f"link-{len(links)}",
                                "url": annotation.get("uri", ""),
                                "label": "Link do PDF",
                                "page": page.page_number,
                                "bbox": [annotation.get(k) for k in ("x0", "top", "x1", "bottom")],
                                "state": "identified",
                            }
                        )
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(
                "PDF corrompido, protegido ou não suportado; original preservado."
            ) from error
    return from_pieces(pieces, links, warnings, extractor, settings, faq)


def from_pieces(pieces, links, warnings, extractor, settings, faq=False):
    """Monta o resultado a partir do texto de cada página; usado também pelo pipeline com OCR."""
    pages = []
    text = "\n\f\n".join(pieces)
    if len(text) > settings.max_text:
        raise ValueError("Texto extraído excede o limite de segurança.")
    offset = 0
    for number, piece in enumerate(pieces, start=1):
        pages.append(
            {
                "number": number,
                "start": offset,
                "end": offset + len(piece),
                "characters": len(piece),
            }
        )
        offset += len(piece) + 3
    units, structural_warnings = segment(text, pages, faq)
    warnings.extend(structural_warnings)
    if re.search(r"ignore.{0,40}instru|system prompt|revele.{0,20}senha", text, re.I):
        warnings.append("Possível prompt injection: conteúdo tratado como dado não confiável.")
    if any(u["kind"] in {"table", "formula"} for u in units):
        warnings.append("Tabelas e fórmulas preservadas como texto; exigem conferência visual.")
    references = []
    for unit in units:
        for match in re.finditer(
            r"\b(?:art\.?\s*\d+[º°]?(?:-[A-Z])?|Anexo\s+[IVXLCDM]+|Tabela\s+\d+)",
            unit["text"],
            re.I,
        ):
            references.append(
                {
                    "unit_id": unit["id"],
                    "quote": match.group(),
                    "target": None,
                    "state": "unresolved",
                }
            )
    return {
        "text": text,
        "text_hash": digest(text.encode()),
        "extractor": extractor,
        "pages": pages,
        "units": units,
        "links": links,
        "warnings": warnings,
        "dates": act_dates(text),
        "references": references,
    }
