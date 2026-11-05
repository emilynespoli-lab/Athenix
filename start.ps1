$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o ambiente Python.' }
    & '.venv/Scripts/python.exe' -m pip install -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'Falha na instalação das dependências.' }
}
Write-Output 'Athenix: acesse http://127.0.0.1:8000 e configure sua conta no primeiro acesso.'
& '.venv/Scripts/python.exe' -m athenix serve
