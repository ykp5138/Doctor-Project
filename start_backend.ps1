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

# Windows can otherwise allow two Uvicorn reloaders to share the same port.
$backendPortProbe = [System.Net.Sockets.Socket]::new(
    [System.Net.Sockets.AddressFamily]::InterNetwork,
    [System.Net.Sockets.SocketType]::Stream,
    [System.Net.Sockets.ProtocolType]::Tcp
)
try {
    $backendPortProbe.ExclusiveAddressUse = $true
    $backendPortProbe.Bind([System.Net.IPEndPoint]::new([System.Net.IPAddress]::Loopback, $Port))
} catch {
    $portError = $_.Exception.GetBaseException()
    if ($portError -is [System.Net.Sockets.SocketException] -and
        $portError.SocketErrorCode -eq [System.Net.Sockets.SocketError]::AddressAlreadyInUse) {
        throw "Port $Port on 127.0.0.1 is already in use. Stop the previous backend with Ctrl+C in its terminal, then run this script again. The default --reload already reloads Python changes; you do not need to launch another backend to refresh it."
    }
    throw
} finally {
    $backendPortProbe.Dispose()
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
