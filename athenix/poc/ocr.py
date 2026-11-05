"""OCR via Docling em processo separado (o Docling é pesado e opcional; ver docs/docling.md).

O interpretador vem de ATHENIX_DOCLING_PYTHON (padrão: o atual). O resultado bruto fica em cache
(`ocr_<sha256>.json`) para que reexecuções sejam repetíveis e não repitam minutos de OCR.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

WORKER = Path(__file__).resolve().parents[2] / "scripts" / "docling_ocr.py"


def docling_ocr(path, pages, cache_dir=None, images_dir=None):
    """Retorna {página: {"lines", "review", "ocr_score", "layout"}} só para `pages`."""
    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    # O nome do cache inclui o hash do worker: mudar o script invalida resultados antigos.
    version = hashlib.sha256(WORKER.read_bytes()).hexdigest()[:8]
    cache = Path(cache_dir) / f"ocr_{sha[:16]}_{version}.json" if cache_dir else None
    if cache and cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        python = os.getenv("ATHENIX_DOCLING_PYTHON", sys.executable)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ocr.json"
            command = [
                python,
                "-I",
                str(WORKER),
                str(path),
                str(min(pages)),
                str(max(pages)),
                str(out),
            ]
            if images_dir:
                command.append(str(images_dir))
            try:
                subprocess.run(command, check=True)  # progresso do Docling segue no stderr
            except (OSError, subprocess.CalledProcessError) as error:
                raise RuntimeError(f"OCR Docling indisponível ou falhou: {error}") from error
            data = json.loads(out.read_text(encoding="utf-8"))
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
            )
    wanted = set(pages)
    return {
        int(n): v | {"engine": data["engine"]} for n, v in data["pages"].items() if int(n) in wanted
    }
