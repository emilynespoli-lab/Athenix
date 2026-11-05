"""PDFs sintéticos para exercitar a extração de texto e os avisos de OCR."""


def synthetic_pdf(scanned=False):
    stream = (
        b"q 0 0 20 20 re f Q"
        if scanned
        else b"BT /F1 12 Tf 40 780 Td (Art. 1 As empresas devem manter registros completos.) Tj ET"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    result = b"%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(result))
        result += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(result)
    result += f"xref\n0 {len(offsets)}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        result += f"{offset:010d} 00000 n \n".encode()
    return (
        result
        + f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )


def lines_pdf(pages):
    """PDF sintético com texto ASCII: `pages` é uma lista de listas de linhas (uma lista por página)."""
    count = len(pages)
    font = 3 + 2 * count
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{3 + 2 * i} 0 R".encode() for i in range(count))
        + b"] /Count "
        + str(count).encode()
        + b" >>",
    ]
    for index, lines in enumerate(pages):
        body = (
            b"BT /F1 12 Tf 40 780 Td "
            + b" ".join(
                b"0 -16 Td ("
                + line.encode("ascii").replace(b"(", rb"\(").replace(b")", rb"\)")
                + b") Tj"
                for line in lines
            )
            + b" ET"
        )
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font} 0 R >> >> "
            f"/Contents {4 + 2 * index} 0 R >>".encode()
        )
        objects.append(
            b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    result, offsets = b"%PDF-1.4\n", [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(result))
        result += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(result)
    result += f"xref\n0 {len(offsets)}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        result += f"{offset:010d} 00000 n \n".encode()
    trailer = f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return result + trailer.encode()
