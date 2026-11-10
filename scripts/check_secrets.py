"""Verificação local de padrões inequívocos; não pretende detectar todo segredo possível."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = {
    ".venv",
    ".local",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "artifacts",
    ".hypothesis",
}
PATTERNS = [
    r"sk-(?:proj-)?[A-Za-z0-9_-]{30,}",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
]


def main():
    hits = []
    for file in ROOT.rglob("*"):
        if any(p in EXCLUDED for p in file.relative_to(ROOT).parts) or not file.is_file():
            continue
        if file.suffix not in {
            ".py",
            ".json",
            ".md",
            ".toml",
            ".yaml",
            ".yml",
            ".html",
            ".txt",
            ".ps1",
        }:
            continue
        content = file.read_text(encoding="utf-8-sig")
        if any(re.search(pattern, content) for pattern in PATTERNS):
            hits.append(str(file.relative_to(ROOT)))
    if hits:
        raise SystemExit("Padrão de segredo encontrado em: " + ", ".join(hits))
    print("Nenhum padrão de chave OpenAI ou chave privada encontrado nos arquivos verificáveis.")


if __name__ == "__main__":
    main()
