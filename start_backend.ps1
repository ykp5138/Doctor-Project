param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [switch]$NoReload
)

$ErrorActionPreference = 'Stop'
$backendPython = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $backendPython)) {
    throw 'Project Python was not found. Create venv and install the project dependencies first.'
}

# Use the project environment even when this PowerShell has not activated it.
# UTF-8 also applies to the WhisperX and AssemblyAI child processes.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$backendArguments = @('-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', "$Port")
if (-not $NoReload) {
    $backendArguments += '--reload'
}

Push-Location -LiteralPath $PSScriptRoot
try {
    & $backendPython @backendArguments
    $backendExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $backendExitCode
