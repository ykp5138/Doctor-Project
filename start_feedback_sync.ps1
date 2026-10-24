param(
    [ValidateRange(1, 3600)]
    [int]$Interval = 10
)

$ErrorActionPreference = 'Stop'
$feedbackPython = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $feedbackPython)) {
    throw 'Project Python was not found. Create venv and install the project dependencies first.'
}
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
& $feedbackPython (Join-Path $PSScriptRoot 'sync_feedback.py') --watch --interval $Interval
exit $LASTEXITCODE
