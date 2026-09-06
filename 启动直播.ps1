param([int]$Room = 837764, [int]$Port = 17870)
$ErrorActionPreference = 'Stop'
if ($Room -le 0 -or $Port -lt 1 -or $Port -gt 65535) {throw '请填写有效房间号和端口'}
$liveRoot = $PSScriptRoot
$liveBase = "http://127.0.0.1:$Port"
$livePython = Join-Path $liveRoot '.venv\Scripts\python.exe'
# Codex MSIX can redirect AppData. Resolve the existing file before passing its
# directory to an independent desktop process, which has no package redirection.
$liveCredentials = & $livePython -c "from companion.secrets import data_dir; print((data_dir() / 'provider.key').resolve().parent)"
if ($LASTEXITCODE -ne 0) {throw '无法定位本机加密凭据目录'}
$liveElectron = Join-Path $liveRoot 'node_modules\electron\dist\electron.exe'
$liveRun = Join-Path $liveRoot 'artifacts\runtime-bilibili'
New-Item -ItemType Directory -Force -Path $liveRun | Out-Null

function Start-LiveProcess([string]$Command) {
    # WMI owns these app processes, so ending a Codex terminal turn does not
    # terminate the live session. Console helpers start with hidden windows.
    $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}
    $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine=$Command; CurrentDirectory=$liveRoot; ProcessStartupInformation=$startup
    }
    if ($result.ReturnValue -ne 0) {throw "启动失败，Win32 code=$($result.ReturnValue)"}
    return $result.ProcessId
}

$backendReady = $false
try {$backendReady = (Invoke-RestMethod "$liveBase/api/health" -TimeoutSec 2).ok} catch {}
$launched = @{}
if (-not $backendReady) {
    $launched.backend = Start-LiveProcess "`"$livePython`" probes/live2d_preview.py --port $Port --avatar changzheng --credential-dir `"$liveCredentials`""
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        try {if ((Invoke-RestMethod "$liveBase/api/health" -TimeoutSec 2).ok) {$backendReady=$true;break}} catch {}
        Start-Sleep -Milliseconds 250
    }
}
if (-not $backendReady) {throw '本地直播服务未就绪'}
$state=Invoke-RestMethod "$liveBase/api/state"
if ($state.scene -ne 'live') {
    Invoke-RestMethod -Method Post "$liveBase/api/session" -ContentType 'application/json' -Body '{"scene":"live"}' | Out-Null
}
$receivers=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'python.exe' -and $_.CommandLine -like '*-m companion.bilibili*'})
$matchingReceivers=@($receivers | Where-Object {
    $_.CommandLine -match "--room\s+$Room(?:\s|$)" -and
    $_.CommandLine -match ('--target\s+'+[regex]::Escape($liveBase)+'(?:\s|$)')
})
if ($receivers.Count -gt 0 -and $matchingReceivers.Count -eq 0) {throw '已有其他直播间接收器运行，未修改它；请先核对房间与端口。'}
if (-not $receivers) {
    $launched.receiver=Start-LiveProcess "`"$livePython`" -m companion.bilibili --room $Room --target $liveBase"
} else {
    $launched.receiver=@($matchingReceivers.ProcessId)
}
$players=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'electron.exe' -and $_.CommandLine -like '*--changzheng-view=/stage?audio=1*' -and $_.CommandLine -notlike '*--type=*'})
$liveStatus=Invoke-RestMethod "$liveBase/api/live/status"
if (-not $players -and -not $liveStatus.player_connected) {
    $launched.player=Start-LiveProcess "`"$liveElectron`" `"$liveRoot`" --changzheng-url=$liveBase --changzheng-view=/stage?audio=1"
} elseif ($players) {
    $launched.player=@($players.ProcessId)
}
@{room=$Room;port=$Port;started=(Get-Date -Format o);processes=$launched} | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $liveRun 'processes.json') -Encoding utf8
Write-Output "直播启动步骤已完成：$liveBase/stage；房间 $Room。以网页上的弹幕和声音状态为准。"
