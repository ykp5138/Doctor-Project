$fixtures = Get-ChildItem -Path "test_fixtures" -Filter "*.json" | Sort-Object Name

if ($fixtures.Count -eq 0) {
    Write-Host "No fixtures found in test_fixtures/" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path "test_results" | Out-Null

foreach ($fixture in $fixtures) {
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "TEST: $($fixture.Name)" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan

    $outputFile = "test_results/$($fixture.BaseName)_result.json"

    curl.exe -s -X POST http://localhost:8000/retrieve-test -H "Content-Type: application/json" -d "@$($fixture.FullName)" -o $outputFile

    if (-not (Test-Path $outputFile)) {
        Write-Host "FAILED - no output file" -ForegroundColor Red
        continue
    }

    $result = Get-Content $outputFile -Raw | ConvertFrom-Json
    $candidates = $result.candidates

    Write-Host "Query count: $($result.query_count)"
    Write-Host "Total candidates: $($candidates.Count)"
    Write-Host ""
    Write-Host "Top 10:" -ForegroundColor Yellow

    $top10 = $candidates | Select-Object -First 10
    foreach ($c in $top10) {
        $scoreStr = "{0:N3}" -f $c.score
        $codeStr = $c.code.PadRight(10)
        Write-Host "  $scoreStr  $codeStr  $($c.description)"
    }

    Write-Host ""
    Write-Host "Chapter distribution:" -ForegroundColor Yellow
    $chapters = $candidates | ForEach-Object {
        if ($_.code -match '^([A-Z])') { $matches[1] }
    } | Group-Object | Sort-Object Count -Descending

    foreach ($ch in $chapters) {
        Write-Host "  $($ch.Name): $($ch.Count) codes"
    }
}

Write-Host ""
Write-Host "Done. Full results in test_results/" -ForegroundColor Green