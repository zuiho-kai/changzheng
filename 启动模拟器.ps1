$ErrorActionPreference = 'Stop'
$simRoot = $PSScriptRoot
$simPython = Join-Path $simRoot '.venv\Scripts\python.exe'
$simBase = 'http://127.0.0.1:17874'
$simReady = $false
try {$simReady = (Invoke-RestMethod "$simBase/api/health" -TimeoutSec 2).mode -eq 'offline-simulator'} catch {}
if (-not $simReady) {
    $simStartup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}
    $simResult = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine="`"$simPython`" `"$simRoot\simulator\server.py`""; CurrentDirectory=$simRoot; ProcessStartupInformation=$simStartup
    }
    if ($simResult.ReturnValue -ne 0) {throw '模拟器启动失败'}
    for ($simTry=0; $simTry -lt 40; $simTry++) {
        try {if ((Invoke-RestMethod "$simBase/api/health" -TimeoutSec 2).mode -eq 'offline-simulator') {$simReady=$true;break}} catch {}
        Start-Sleep -Milliseconds 250
    }
}
if (-not $simReady) {throw '模拟器未就绪，请检查 17874 端口'}
Start-Process "$simBase/sim"
Write-Output "模拟器：$simBase/sim；编辑 simulator/workspace 后点击刷新排练版本。"
