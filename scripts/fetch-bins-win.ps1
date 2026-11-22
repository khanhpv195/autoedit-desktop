# Fetch ffmpeg (Gyan full build 9.1 via its GitHub mirror: libass, zimg) and whisper.cpp (CPU) into build\bin. Idempotent.
# gyan.dev/ffmpeg/builds/ffmpeg-release-full.zip went 404; the GitHub mirror is pinned by version and SHA256.
# whisper.cpp v1.9.5 ships no binaries; build tag b5454 is the same commit (d1be6fd) and has them.
# Vulkan build of whisper.cpp is a later improvement.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $Root "build\bin"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("autoedit-bins-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
$ProgressPreference = "SilentlyContinue"
$FfmpegUrl = "https://github.com/GyanD/codexffmpeg/releases/download/9.1/ffmpeg-9.1-full_build.zip"
$FfmpegSha = "f9a83be8f97b8989a223a15e4af234accd0842bacf7c126af5a3aae759785e48"
$WhisperUrl = "https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-x64.zip"
$WhisperSha = "6ba69e3482d7826214f90a6a9c84ca07782aec1e1d0c6a7c30c994fd5d816ccb"
function Get-Checked($Url, $Sha, $Dest) {
  Invoke-WebRequest -Uri $Url -OutFile $Dest
  $got = (Get-FileHash -Algorithm SHA256 $Dest).Hash.ToLower()
  if ($got -ne $Sha) { throw "SHA256 mismatch for $Url : $got" }
}
try {
  if (-not (Test-Path (Join-Path $Out "ffmpeg.exe"))) {
    $zip = Join-Path $Tmp "ffmpeg.zip"
    Get-Checked $FfmpegUrl $FfmpegSha $zip
    Expand-Archive -Path $zip -DestinationPath (Join-Path $Tmp "ff")
    foreach ($n in "ffmpeg.exe", "ffprobe.exe") {
      $f = Get-ChildItem -Path (Join-Path $Tmp "ff") -Recurse -Filter $n | Select-Object -First 1
      Copy-Item $f.FullName (Join-Path $Out $n)
    }
  }
  if (-not (Test-Path (Join-Path $Out "whisper-cli.exe"))) {
    $zip = Join-Path $Tmp "whisper.zip"
    Get-Checked $WhisperUrl $WhisperSha $zip
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
