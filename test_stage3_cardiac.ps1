$ErrorActionPreference = "Stop"

Write-Host "Step 1: Calling /replay to get concepts and words..." -ForegroundColor Cyan
$replayBody = @{
    base = "23e1b612a69c4388807604add9aa2777_MOV"
    patient_name = "Test Patient"
} | ConvertTo-Json

$replayResult = Invoke-RestMethod -Uri "http://localhost:8000/replay" `
    -Method Post -ContentType "application/json" -Body $replayBody

Write-Host "  Got concepts and $($replayResult.words.Count) words" -ForegroundColor Green

Write-Host ""
Write-Host "Step 2: Calling /suggest-codes with concepts (RAG path)..." -ForegroundColor Cyan
$suggestBody = @{
    concepts = $replayResult.concepts
    words = $replayResult.words
    summary = $replayResult.summary
    code_range = ""
} | ConvertTo-Json -Depth 10

$suggestResult = Invoke-RestMethod -Uri "http://localhost:8000/suggest-codes" `
    -Method Post -ContentType "application/json" -Body $suggestBody

Write-Host "  Got $($suggestResult.suggestions.Count) suggestions" -ForegroundColor Green

Write-Host ""
Write-Host "================================================================" -ForegroundColor Yellow
Write-Host "FINAL SELECTED ICD-10 CODES" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Yellow

foreach ($sug in $suggestResult.suggestions) {
    Write-Host ""
    Write-Host "  $($sug.code) - $($sug.description)" -ForegroundColor White
    foreach ($ev in $sug.evidence) {
        $indices = if ($ev.word_indices.Count -gt 0) { "[$($ev.word_indices -join ',')]" } else { "[no match]" }
        Write-Host "      Evidence: `"$($ev.phrase)`" -> $indices" -ForegroundColor Gray
    }
}

Write-Host ""
$suggestResult | ConvertTo-Json -Depth 10 | Out-File -Encoding utf8 "test_results/stage3_cardiac.json"
Write-Host "Full output saved to test_results/stage3_cardiac.json" -ForegroundColor Green