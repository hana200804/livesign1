param(
    [ValidateRange(1024, 65535)][int]$Port = 8766
)

$ErrorActionPreference = 'Stop'
$liveSignRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$liveSignPython = Join-Path $liveSignRoot '.venv\Scripts\python.exe'
$liveSignPrivate = Join-Path $liveSignRoot 'data\private'
$liveSignCache = Join-Path $liveSignRoot 'data\cache'
$liveSignPage = Join-Path $liveSignPrivate 'review\routes\index.html'
$liveSignUrl = "http://127.0.0.1:$Port/review/routes/index.html"

if (-not (Test-Path -LiteralPath $liveSignPython)) {
    throw 'Chưa có .venv. Hãy tạo môi trường theo README trước.'
}
if (-not (Test-Path -LiteralPath $liveSignPage)) {
    & $liveSignPython -m survey --root $liveSignRoot build-review
    if ($LASTEXITCODE -ne 0) { throw 'Chưa tạo được trang duyệt. Kiểm tra mẫu ảnh đã khóa.' }
}

try {
    $liveSignResponse = Invoke-WebRequest -Uri $liveSignUrl -TimeoutSec 3
    if ($liveSignResponse.Content -like '*LiveSign*Duyệt ảnh khảo sát*') {
        Write-Output "Trang duyệt đang chạy: $liveSignUrl"
        return
    }
    throw "Cổng $Port đang được ứng dụng khác dùng. Chọn -Port khác."
} catch [System.Net.WebException], [System.Net.Http.HttpRequestException], [System.Threading.Tasks.TaskCanceledException] {
    # Chưa có máy chủ đáp ứng: mở tiến trình nền chỉ nghe trên loopback.
}

New-Item -ItemType Directory -Path $liveSignCache -Force | Out-Null
$liveSignServer = Start-Process -FilePath $liveSignPython -ArgumentList @(
    '-u', '-m', 'http.server', "$Port", '--bind', '127.0.0.1', '--directory',
    ('"' + $liveSignPrivate + '"')
) -WindowStyle Hidden -WorkingDirectory $liveSignRoot -RedirectStandardOutput (
    Join-Path $liveSignCache "review-$Port.stdout.log"
) -RedirectStandardError (
    Join-Path $liveSignCache "review-$Port.stderr.log"
) -PassThru
$liveSignServer.Id | Set-Content -LiteralPath (Join-Path $liveSignCache "review-$Port.pid")

for ($liveSignAttempt = 0; $liveSignAttempt -lt 10; $liveSignAttempt++) {
    try {
        $liveSignResponse = Invoke-WebRequest -Uri $liveSignUrl -TimeoutSec 2
        if ($liveSignResponse.Content -like '*LiveSign*Duyệt ảnh khảo sát*') {
            Write-Output "Mở trình duyệt tại: $liveSignUrl"
            Write-Output "Máy chủ chạy nền, PID $($liveSignServer.Id). Ảnh giữ trên máy."
            return
        }
    } catch [System.Net.WebException], [System.Net.Http.HttpRequestException], [System.Threading.Tasks.TaskCanceledException] {
        Start-Sleep -Milliseconds 200
    }
}
throw "Chưa mở được máy chủ. Xem log review-$Port.stderr.log trong data/cache."
