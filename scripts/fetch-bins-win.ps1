# Fetch ffmpeg (gyan.dev full build: libass, zimg) and whisper.cpp (CPU) into build\bin. Idempotent.
# Vulkan build of whisper.cpp is a later improvement.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $Root "build\bin"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("autoedit-bins-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
$ProgressPreference = "SilentlyContinue"
try {
  if (-not (Test-Path (Join-Path $Out "ffmpeg.exe"))) {
    $zip = Join-Path $Tmp "ffmpeg.zip"
    Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath (Join-Path $Tmp "ff")
    foreach ($n in "ffmpeg.exe", "ffprobe.exe") {
      $f = Get-ChildItem -Path (Join-Path $Tmp "ff") -Recurse -Filter $n | Select-Object -First 1
      Copy-Item $f.FullName (Join-Path $Out $n)
    }
  }
  if (-not (Test-Path (Join-Path $Out "whisper-cli.exe"))) {
    $zip = Join-Path $Tmp "whisper.zip"
    Invoke-WebRequest -Uri "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.5/whisper-bin-x64.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath (Join-Path $Tmp "wh")
    $cli = Get-ChildItem -Path (Join-Path $Tmp "wh") -Recurse -Filter "whisper-cli.exe" | Select-Object -First 1
    Copy-Item (Join-Path $cli.DirectoryName "*.dll") $Out -Force
    Copy-Item $cli.FullName (Join-Path $Out "whisper-cli.exe")
  }
  $filters = & (Join-Path $Out "ffmpeg.exe") -hide_banner -filters | ForEach-Object { ($_ -split "\s+")[2] }
  foreach ($f in "zscale","tonemap","subtitles","loudnorm","amix","geq","bilateral","maskedmerge","boxblur","eq") {
    if ($filters -notcontains $f) { throw "ffmpeg lacks filter $f" }
  }
  & (Join-Path $Out "whisper-cli.exe") --help *> $null
  if ($LASTEXITCODE -ne 0) { throw "whisper-cli --help failed" }
  Write-Host "OK: $Out"
} finally {
  Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
