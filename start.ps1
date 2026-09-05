$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$localDir = Join-Path $env:LOCALAPPDATA 'Changzheng'
New-Item -ItemType Directory -Force -Path $localDir | Out-Null
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
    & $pythonExe -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependencies could not be installed.' }
}
$healthy = $false
$reply = $null
try {
    $reply = Invoke-RestMethod 'http://127.0.0.1:17861/api/health' -TimeoutSec 2
} catch {}
if ($null -ne $reply) {
    $healthy = $reply.app -eq 'changzheng'
    if (-not $healthy) { throw 'Port 17861 is used by another application.' }
}
if (-not $healthy) {
    $backend = Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','companion.app:app','--host','127.0.0.1','--port','17861','--no-access-log') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localDir 'server.log') -RedirectStandardError (Join-Path $localDir 'server-error.log')
    Set-Content -LiteralPath (Join-Path $localDir 'server.pid') -Value $backend.Id
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 250
        try {
            $reply = Invoke-RestMethod 'http://127.0.0.1:17861/api/health' -TimeoutSec 1
            if ($reply.app -eq 'changzheng') { $healthy = $true; break }
        } catch {}
        if ($backend.HasExited) { break }
    }
    if (-not $healthy) { throw "Backend startup failed. See $localDir\server-error.log" }
}
$electronExe = Join-Path $PSScriptRoot 'node_modules\electron\dist\electron.exe'
$electronInstaller = Join-Path $PSScriptRoot 'node_modules\electron\install.js'
if (-not (Test-Path -LiteralPath $electronExe) -and (Test-Path -LiteralPath $electronInstaller)) {
    & node $electronInstaller
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Desktop component download failed; opening the browser version.' }
}
if (Test-Path -LiteralPath $electronExe) {
    & $electronExe $PSScriptRoot
} else {
    Start-Process 'http://127.0.0.1:17861'
}
