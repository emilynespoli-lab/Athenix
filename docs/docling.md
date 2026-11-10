# Docling na PoC (OCR e análise de layout)

Uso opcional, só para páginas **sem camada de texto** (ex.: `dou.pdf`, 43 páginas, todas imagens).
O texto digital (ex.: `ren20251137.pdf`) continua vindo do `pdfplumber`, sem OCR.

## O que é necessário

| Item | Detalhe |
| --- | --- |
| Python | 3.10+ (testado em 3.11) |
| Pacotes | `pip install -r requirements-docling.txt` (`docling` + `onnxruntime`; o `docling` **não** instala o `onnxruntime`, exigido pelo RapidOCR) |
| Tamanho | ~GB de dependências (PyTorch CPU, transformers, OpenCV). Use venv **separado** do `.venv` do projeto |
| Modelos | Baixados do Hugging Face na 1ª execução (layout, TableFormer, OCR). Exige internet uma vez; defina `HF_HOME` fora do OneDrive |
| Windows | Instale em caminho **curto** (ex.: `C:\dl\v`). Em pastas profundas o `pip` falha com `Errno 2` por limite de 260 caracteres (ou habilite *Long Paths*) |
| Execução | `ATHENIX_DOCLING_PYTHON` aponta o interpretador com Docling; o pipeline chama `scripts/docling_ocr.py` em subprocesso |

```powershell
python -m venv C:\dl\v
C:\dl\v\Scripts\python.exe -m pip install -r requirements-docling.txt
$env:HF_HOME='C:\dl\hf'; $env:ATHENIX_DOCLING_PYTHON='C:\dl\v\Scripts\python.exe'
.\.venv\Scripts\python.exe -m athenix poc --ocr docling --out artifacts/poc
```

Sem Docling, `--ocr none` (padrão) registra as páginas como `not_extracted`; nada é descartado em silêncio.

## O que o Docling entrega e o que não entrega

- Texto por bloco com bbox em pontos PDF; tabelas (TableFormer); regiões de fórmula/figura (análise de layout).
- Confiança de OCR **por página** (`ocr_score`), não por linha. Todas as linhas da página herdam esse valor.
- Imagens das páginas OCR em `artifacts/poc/pages/<arquivo>/` para conferência visual humana.
- Fórmulas **não** são lidas (enriquecimento desabilitado): páginas com região de fórmula ficam `needs_review`.
- OCR nunca é `faithful`: o menor estado possível é `uncertain`. Exemplo observado: "uso" lido como "usO".
