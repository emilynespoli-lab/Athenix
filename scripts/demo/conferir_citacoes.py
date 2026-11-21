"""Confere as citações do plano publicado contra o arquivo oficial, com um extrator independente.

O produto lê PDF com pdfplumber e segmenta pelo próprio extrator. Aqui o texto de referência sai de
outro caminho: pypdfium2 para PDF e html.parser (biblioteca padrão) para o HTML do DOU, sem reutilizar
os segmentos do produto. Cada trecho citado em `landing/src/content/plano-*.json` (deveres, outros
dispositivos e "sem dever identificado") precisa aparecer no texto de referência, ignorando só
espaços e quebras de linha (os extratores quebram linhas em pontos diferentes). Também confere o
SHA-256 do arquivo contra o que o plano declara.

Uso (raiz do repositório):
    python scripts/demo/conferir_citacoes.py
Sai com código 1 se alguma citação não for encontrada.
"""

import hashlib
import json
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANOS = [
    ("landing/src/content/plano-rn1137.json", "tests/norma_poc/ren20251137.pdf"),
    ("landing/src/content/plano-ren1174.json", "tests/fontes_impacto/dou/dou_ren20261174.html"),
]
LISTAS = ("obrigacoes", "outros_dispositivos", "sem_dever_identificado")


class _Texto(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes, self._pular = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._pular += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._pular -= 1

    def handle_data(self, data):
        if not self._pular:
            self.partes.append(data)


def texto_de(arquivo):
    if arquivo.suffix.lower() == ".pdf":
        import pypdfium2

        pdf = pypdfium2.PdfDocument(str(arquivo))
        try:
            return "\n".join(pagina.get_textpage().get_text_range() for pagina in pdf)
        finally:
            pdf.close()
    leitor = _Texto()
    leitor.feed(arquivo.read_bytes().decode("utf-8", errors="replace"))
    return " ".join(leitor.partes)


def compacto(texto):
    """Sem espaço algum e em NFC: compara letras, acentos e pontuação, não a quebra de linha."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", texto))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    falhas = 0
    for plano_json, fonte in PLANOS:
        plano = json.loads((ROOT / plano_json).read_text(encoding="utf-8"))
        arquivo = ROOT / fonte
        sha = hashlib.sha256(arquivo.read_bytes()).hexdigest()
        referencia = compacto(texto_de(arquivo))
        print(f"{plano['norma']['titulo']} · {fonte}")
        hash_ok = sha == plano["norma"]["sha256"]
        print(f"  SHA-256 do arquivo = declarado no plano: {'sim' if hash_ok else 'NÃO'}")
        falhas += not hash_ok
        for lista in LISTAS:
            trechos = [o for o in plano[lista] if o.get("trecho")]
            ausentes = [o for o in trechos if compacto(o["trecho"]) not in referencia]
            print(
                f"  {lista}: {len(trechos) - len(ausentes)} de {len(trechos)} trechos encontrados"
            )
            for o in ausentes:
                print(f"    não encontrado: {o['id']} {o.get('dispositivo')}")
            falhas += len(ausentes)
    print("Resultado:", "todas as citações conferem" if not falhas else f"{falhas} problema(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
