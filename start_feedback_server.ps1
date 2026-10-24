param(
    [string]$ListenAddress = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$Port = 8001
)

$ErrorActionPreference = 'Stop'
$feedbackPython = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
$feedbackSettings = Join-Path $PSScriptRoot '.env.feedback.local'
if (-not (Test-Path -LiteralPath $feedbackPython)) {
    throw 'Project Python was not found. Create venv and install the project dependencies first.'
}
if (-not (Test-Path -LiteralPath $feedbackSettings)) {
    throw 'Copy .env.feedback.example to .env.feedback.local and set a random FEEDBACK_API_TOKEN first. See FEEDBACK_SETUP.md.'
}

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$feedbackArguments = @(
    '-m', 'uvicorn', 'feedback_server:app',
    '--host', $ListenAddress, '--port', "$Port",
    '--env-file', $feedbackSettings
)

Push-Location -LiteralPath $PSScriptRoot
try {
    & $feedbackPython @feedbackArguments
    $feedbackExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $feedbackExitCode
