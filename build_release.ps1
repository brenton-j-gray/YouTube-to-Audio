Param(
    [string]$AppName = "YouTubeToAudio"
)

$ErrorActionPreference = "Stop"

Write-Host "Installing/updating Python dependencies..."
python -m pip install -r requirements.txt
python -m pip install -U pyinstaller

Write-Host "Building standalone Windows executable..."
$pyArgs = @(
    "--noconfirm"
    "--clean"
    "--onefile"
    "--windowed"
    "--name"
    $AppName
    "--add-data"
    "payment-qrcode.png;."
)
if ((Test-Path "ffmpeg/ffmpeg.exe") -and (Test-Path "ffmpeg/ffprobe.exe")) {
    Write-Host "Bundling local ffmpeg binaries from ./ffmpeg ..."
    $pyArgs += @("--add-data", "ffmpeg;ffmpeg")
}
else {
    Write-Host "No ./ffmpeg binaries found; build will require system ffmpeg on target machines."
}
$pyArgs += "yt_to_audio.pyw"
pyinstaller @pyArgs

if (!(Test-Path "release")) {
    New-Item -ItemType Directory -Path "release" | Out-Null
}

Copy-Item -Path "dist/$AppName.exe" -Destination "release/$AppName.exe" -Force
Copy-Item -Path "README.md" -Destination "release/README.md" -Force

$zipPath = "release/$AppName-windows-x64.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-Archive -Path "release/$AppName.exe", "release/README.md" -DestinationPath $zipPath

Write-Host ""
Write-Host "Release package created:"
Write-Host " - release/$AppName.exe"
Write-Host " - $zipPath"
Write-Host ""
if ((Test-Path "ffmpeg/ffmpeg.exe") -and (Test-Path "ffmpeg/ffprobe.exe")) {
    Write-Host "Bundled ffmpeg/ffprobe detected and included."
}
else {
    Write-Host "Reminder: target machines still need ffmpeg + ffprobe on PATH."
}
