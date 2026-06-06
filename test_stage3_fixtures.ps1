$fixtures = Get-ChildItem -Path "test_fixtures" -Filter "*.json" | Sort-Object Name

if ($fixtures.Count -eq 0) {
    Write-Host "No fixtures found in test_fixtures/" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path "test_results" | Out-Null

# Helper to build a summary string from concepts
function Build-Summary($concepts) {
    $parts = @()
    if ($concepts.symptoms.Count -gt 0) { 
        $parts += "Symptoms: " + ($concepts.symptoms -join "; ") 
    }
    if ($concepts.diagnoses_mentioned.Count -gt 0) { 
        $parts += "Diagnoses: " + ($concepts.diagnoses_mentioned -join "; ") 
    }
    if ($concepts.medications_discussed.Count -gt 0) { 
        $parts += "Medications: " + ($concepts.medications_discussed -join "; ") 
    }
    if ($concepts.procedures_ordered.Count -gt 0) { 
        $parts += "Procedures: " + ($concepts.procedures_ordered -join "; ") 
    }
    if ($concepts.history_relevant.Count -gt 0) { 
        $parts += "History: " + ($concepts.history_relevant -join "; ") 
    }
    if ($concepts.vitals_exam_findings.Count -gt 0) { 
        $parts += "Exam: " + ($concepts.vitals_exam_findings -join "; ") 
    }
    return $parts -join ". "
}

foreach ($fixture in $fixtures) {
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "STAGE 3 TEST: $($fixture.Name)" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan

    $fixtureObj = Get-Content $fixture.FullName -Raw | ConvertFrom-Json
    $summary = Build-Summary $fixtureObj.concepts

    Write-Host "Constructed summary: $summary" -ForegroundColor DarkGray
    Write-Host ""

    $body = @{
        concepts = $fixtureObj.concepts
        words = @()
        summary = $summary
        code_range = ""
    } | ConvertTo-Json -Depth 10

    try {
        $result = Invoke-RestMethod -Uri "http://localhost:8000/suggest-codes" `
            -Method Post -ContentType "application/json" -Body $body -ErrorAction Stop
    } catch {
        Write-Host "FAILED - $($_.Exception.Message)" -ForegroundColor Red
        if ($_.ErrorDetails.Message) {
            Write-Host "Server said: $($_.ErrorDetails.Message)"
        }
        continue
    }

    $suggestions = $result.suggestions
    Write-Host "Final selected codes: $($suggestions.Count)" -ForegroundColor Yellow

    if ($suggestions.Count -eq 0) {
        Write-Host "  (no codes selected)" -ForegroundColor DarkGray
    }

    foreach ($sug in $suggestions) {
        Write-Host ""
        Write-Host "  $($sug.code) - $($sug.description)" -ForegroundColor White
        if ($sug.evidence) {
            foreach ($ev in $sug.evidence) {
                Write-Host "      Evidence: `"$($ev.phrase)`"" -ForegroundColor Gray
            }
        }
    }

    $outputFile = "test_results/stage3_$($fixture.BaseName).json"
    $result | ConvertTo-Json -Depth 10 | Out-File -Encoding utf8 -FilePath $outputFile
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "All tests complete. Detailed results in test_results/stage3_*.json" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green