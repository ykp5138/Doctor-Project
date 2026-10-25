param(
    [ValidateRange(1, 20)]
    [int]$Repeats = 1,
    [switch]$Holdout
)

$ErrorActionPreference = 'Stop'
$evaluationPython = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $evaluationPython)) {
    throw 'Create the project venv and install its dependencies first.'
}
# Stage 3 requires spoken words to validate evidence. The old retrieval fixtures
# contain concepts only. The regression corpus supplies explicit synthetic
# transcripts, expected codes, and words with stable indices.
$evaluationArguments = @('-X', 'utf8', '-u', 'evaluate_icd_accuracy.py',
    '--variants', 'legacy', 'enhanced_mean', 'enhanced_cls', '--repeats', "$Repeats",
    '--fail-on-regression', 'enhanced_cls')
if ($Holdout) {
    $evaluationArguments += @('--holdout', '--output', 'outputs/icd_accuracy/holdout.json')
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $evaluationPython @evaluationArguments
    $evaluationExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $evaluationExitCode
