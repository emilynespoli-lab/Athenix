"""Os exemplos são montados por concatenação para que este arquivo não dispare o próprio verificador."""

import pytest

from scripts.check_secrets import scan

HEX = "0123456789abcdef" * 3
ALNUM = "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv1Wx2Yz3"


@pytest.mark.parametrize(
    "content,kind",
    [
        ("token = 'gh" + "p_" + ALNUM + "'", "token GitHub"),
        ("x = github" + "_pat_" + ALNUM, "token GitHub"),
        ("ATHENIX_API" + "_KEY=" + HEX[:32], "chave Azure"),
        ('headers = {"api-' + 'key": "' + HEX[:32] + '"}', "chave Azure"),
        ("DefaultEndpointsProtocol=https;Account" + "Key=" + ALNUM + "abcd==", "chave de storage Azure"),
        ("postgresql://athenix:" + "s3nhaForte" + "@db:5432/x", "connection string com senha"),
        ("Server=tcp:x.database.windows.net;Database=d;Pass" + "word=s3nhaForte;", "connection string ADO com senha"),
    ],
)  # fmt: skip
def test_detects_new_secret_kinds(tmp_path, content, kind):
    (tmp_path / "config.py").write_text(content, encoding="utf-8")
    assert scan(tmp_path) == [f"config.py ({kind})"]


def test_ignores_hashes_placeholders_and_non_utf8(tmp_path):
    (tmp_path / "fontes.json").write_text('{"sha256": "' + HEX * 2 + '"}', encoding="utf-8")
    (tmp_path / "compose.yaml").write_text(
        "url: postgresql+psycopg://athenix:${ATHENIX_DB_PASSWORD}@db:5432/athenix\n"
        "doc: postgresql://usuario:<senha>@host/db\n",
        encoding="utf-8",
    )
    (tmp_path / "ato.htm").write_bytes("Decreto nº 12.068 — publicação".encode("cp1252"))
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("ATHENIX_API" + "_KEY=" + HEX[:32])
    assert scan(tmp_path) == []
