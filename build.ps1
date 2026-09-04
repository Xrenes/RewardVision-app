$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

# --- 1. Frozen app ---------------------------------------------------------
python -m pip install --disable-pip-version-check -q -r requirements.txt pyinstaller==6.15.0
python -m PyInstaller --noconfirm --clean --log-level WARN RewardVision.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }

$exe = Join-Path $projectDir "dist\RewardVision\RewardVision.exe"
if (-not (Test-Path $exe)) { throw "Build produced no exe at $exe" }

# Sanity: the runtime C++ libraries Qt needs must be somewhere in the
# bundle (spec puts them at _internal root; PySide6 also carries copies).
$internal = Join-Path $projectDir "dist\RewardVision\_internal"
foreach ($dll in @("VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll")) {
    $hit = Get-ChildItem -Path $internal -Recurse -Filter $dll -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $hit) { throw "Runtime library not found anywhere in bundle: $dll" }
}
Write-Host "VC++ runtime DLLs present in bundle."

# --- 2. MSI --------------------------------------------------------------
$localDotnet = Join-Path $env:LOCALAPPDATA "Microsoft\dotnet"
if ((Test-Path -LiteralPath $localDotnet) -and -not $env:DOTNET_ROOT) {
    $env:DOTNET_ROOT = $localDotnet
}
$wix = Get-Command wix.exe -ErrorAction SilentlyContinue
if (-not $wix) { throw "WiX CLI is required. Install it with: dotnet tool install --global wix" }

New-Item -ItemType Directory -Force -Path release | Out-Null
& $wix.Source build installer\RewardVision.wxs `
    -arch x64 `
    -bindpath "appdir=$(Join-Path $projectDir 'dist\RewardVision')" `
    -o release\RewardVision.msi
if ($LASTEXITCODE -ne 0) { throw "WiX build failed ($LASTEXITCODE)" }

$msi = Join-Path $projectDir "release\RewardVision.msi"
$size = [math]::Round((Get-Item $msi).Length / 1MB, 1)
Write-Host "Built release\RewardVision.msi ($size MB)"
