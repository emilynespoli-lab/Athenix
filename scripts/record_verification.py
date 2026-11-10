"""Registra os artefatos locais e um hash do código, sem presumir commit Git."""

import hashlib
import json
import platform
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    files = {}
    for directory in ("athenix", "tests", "scripts", "migrations"):
        for file in sorted((root / directory).rglob("*")):
            if file.suffix not in {".py", ".html", ".js", ".css", ".mako"}:
                continue
            content = file.read_bytes().replace(b"\r\n", b"\n")
            files[file.relative_to(root).as_posix()] = hashlib.sha256(content).hexdigest()
    source_hash = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    artifact = root / "artifacts"
    suites = ET.parse(artifact / "tests.xml").getroot().findall("testsuite")
    summary = {
        key: sum(int(suite.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    report = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "os": platform.system(),
        "source_sha256_lf": source_hash,
        "source_files": files,
        "git_commit": None,
        "git_reason": "Git não inicializado por instrução do responsável",
        "junit": summary,
        "paid_test_calls": 0,
    }
    for name in ("browser-qa", "public-faq-check"):
        file = artifact / (name + ".json")
        if file.exists():
            report[name] = json.loads(file.read_text(encoding="utf-8"))
    (artifact / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"junit": summary, "source_sha256_lf": source_hash}))


if __name__ == "__main__":
    main()
