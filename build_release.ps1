Param(
    [string]$AppName = "YouTubeToAudio",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

function Resolve-PythonExe {
    Param([string]$RequestedPythonExe)

    if ($RequestedPythonExe) {
        if (!(Test-Path $RequestedPythonExe)) {
            throw "Python executable was not found: $RequestedPythonExe"
        }
        return (Resolve-Path $RequestedPythonExe).Path
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source) {
        return $pythonCommand.Source
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.14-64\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "Python was not found. Install Python or run: .\build_release.ps1 -PythonExe `"C:\Path\To\python.exe`""
}

$PythonExe = Resolve-PythonExe $PythonExe
Write-Host "Using Python: $PythonExe"

Write-Host "Installing/updating Python dependencies..."
& $PythonExe -m pip install -r requirements.txt
& $PythonExe -m pip install -U pyinstaller

Write-Host "Building standalone Windows executable..."
$pythonBase = & $PythonExe -c "import sys; print(sys.base_prefix)"
$tclDir = Join-Path $pythonBase "tcl\tcl8.6"
$tkDir = Join-Path $pythonBase "tcl\tk8.6"

$pyArgs = @(
    "--noconfirm"
    "--clean"
    "--onefile"
    "--windowed"
    "--name"
    $AppName
    "--add-data"
    "payment-qrcode.png;."
    "--hidden-import"
    "tkinter"
    "--hidden-import"
    "tkinter.filedialog"
    "--hidden-import"
    "tkinter.font"
    "--hidden-import"
    "tkinter.messagebox"
    "--hidden-import"
    "tkinter.scrolledtext"
    "--hidden-import"
    "tkinter.ttk"
)
if ((Test-Path $tclDir) -and (Test-Path $tkDir)) {
    Write-Host "Bundling Tcl/Tk runtime from $pythonBase ..."
    $pyArgs += @("--add-data", "$tclDir;tcl/tcl8.6")
    $pyArgs += @("--add-data", "$tkDir;tcl/tk8.6")
}
else {
    Write-Host "Tcl/Tk runtime folders were not found under $pythonBase."
}
if ((Test-Path "ffmpeg/ffmpeg.exe") -and (Test-Path "ffmpeg/ffprobe.exe")) {
    Write-Host "Bundling local ffmpeg binaries from ./ffmpeg ..."
    $pyArgs += @("--add-data", "ffmpeg;ffmpeg")
}
else {
    Write-Host "No ./ffmpeg binaries found; build will require system ffmpeg on target machines."
}
$pyArgs += "yt_to_audio.pyw"
& $PythonExe -m PyInstaller @pyArgs

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
