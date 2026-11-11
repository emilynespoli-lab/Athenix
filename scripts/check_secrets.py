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
    "node_modules",
    "dist",
}
SUFFIXES = {
    ".py", ".json", ".md", ".toml", ".yaml", ".yml", ".html", ".htm", ".txt", ".ps1",
    ".js", ".ts", ".tsx", ".ini", ".cfg", ".sh", ".env",
}  # fmt: skip
PATTERNS = {
    "chave OpenAI": r"sk-(?:proj-)?[A-Za-z0-9_-]{30,}",
    "chave privada": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "token GitHub": r"\bgh[pousr]_[A-Za-z0-9]{36,}|\bgithub_pat_[A-Za-z0-9_]{22,}",
    # Chave Azure é hex/base62 sem prefixo: só com contexto, para não confundir com hashes.
    "chave Azure": r"(?i)(?:api[-_]?key|azure[-_]?\w*key|subscription-key)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9]{32,}",
    "chave de storage Azure": r"AccountKey=[A-Za-z0-9+/]{40,}={0,2}|[?&]sig=[A-Za-z0-9%+/]{30,}",
    # Senha embutida em URL; ${VAR} (compose) e <placeholder> são aceitos.
    "connection string com senha": r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:(?!\$\{|<)[^\s@/]{3,}@",
    "connection string ADO com senha": r"(?i)(?:server|host|data source)=[^;\n]+;[^\n\"']*?(?:password|pwd)=(?!\$\{)[^;\s\"']+",
}  # fmt: skip


def scan(root):
    hits = []
    for file in sorted(root.rglob("*")):
        parts = file.relative_to(root).parts
        if any(p in EXCLUDED for p in parts) or not file.is_file():
            continue
        if file.suffix not in SUFFIXES and not file.name.startswith(".env"):
            continue
        # Fontes oficiais podem vir em windows-1252: ler sem falhar.
        content = file.read_text(encoding="utf-8-sig", errors="replace")
        for name, pattern in PATTERNS.items():
            if re.search(pattern, content):
                hits.append(f"{file.relative_to(root)} ({name})")
    return hits


def main():
    hits = scan(ROOT)
    if hits:
        raise SystemExit("Padrão de segredo encontrado em: " + ", ".join(hits))
    print("Nenhum padrão de segredo conhecido encontrado: " + ", ".join(PATTERNS) + ".")


if __name__ == "__main__":
    main()
