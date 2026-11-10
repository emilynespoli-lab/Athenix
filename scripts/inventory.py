"""Inventário de versões e metadados de licença, sem caminhos locais ou credenciais."""

import importlib.metadata
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    records = []
    qa = {"playwright", "pyee", "greenlet"}
    for distribution in sorted(
        importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower()
    ):
        meta = distribution.metadata
        declared = meta.get("License-Expression") or meta.get("License", "").split("\n")[0]
        classifiers = [s for s in meta.get_all("Classifier", []) if s.startswith("License ::")]
        records.append(
            {
                "name": meta["Name"],
                "version": distribution.version,
                "license_metadata": declared or classifiers or "não declarada nos metadados",
                "project_urls": meta.get_all("Project-URL", []),
                "scope": "QA do navegador"
                if meta["Name"].lower() in qa
                else "ambiente principal e testes",
            }
        )
    (root / "docs" / "terceiros.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"Inventariadas {len(records)} distribuições; metadados não substituem os textos de licença."
    )


if __name__ == "__main__":
    main()
