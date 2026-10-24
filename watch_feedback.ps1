param(
    [string]$Path = 'C:\DoctorProjectData\feedback\feedback.jsonl',
    [ValidateRange(1, 60)]
    [int]$Interval = 1
)

# Open and close the file on each read, allowing atomic updates on Windows.
$lastFeedbackText = $null
while ($true) {
    try {
        $feedbackText = if (Test-Path -LiteralPath $Path) {
            Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction Stop
        } else { '' }
        if ($feedbackText -ne $lastFeedbackText) {
            Write-Output ('Current feedback updated at ' + (Get-Date -Format 'HH:mm:ss'))
            $feedbackRows = @(foreach ($feedbackLine in ($feedbackText -split '\r?\n')) {
                if ($feedbackLine.Trim()) {
                    try {
                        $feedbackRecord = $feedbackLine | ConvertFrom-Json -ErrorAction Stop
                        [pscustomobject]@{
                            Code = $feedbackRecord.code
                            Choice = if ($feedbackRecord.is_correct) { 'Correct' } else { 'Incorrect' }
                            Recording = $feedbackRecord.transcript_base
                        }
                    } catch { }
                }
            })
            $feedbackRows | Format-Table -AutoSize | Out-Host
            $lastFeedbackText = $feedbackText
        }
    } catch [System.IO.IOException] {
        # A concurrent replacement can briefly make a read unavailable; retry.
    }
    Start-Sleep -Seconds $Interval
}
