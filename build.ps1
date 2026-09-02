$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

python -m pip install --disable-pip-version-check -r requirements.txt pyinstaller==6.15.0
python -m PyInstaller --noconfirm --clean RewardVision.spec

$localDotnet = Join-Path $env:LOCALAPPDATA "Microsoft\dotnet"
if ((Test-Path -LiteralPath $localDotnet) -and -not $env:DOTNET_ROOT) {
    $env:DOTNET_ROOT = $localDotnet
}
$wix = Get-Command wix.exe -ErrorAction SilentlyContinue
if (-not $wix) { throw "WiX CLI is required. Install it with: dotnet tool install --global wix" }

New-Item -ItemType Directory -Force -Path release | Out-Null
& $wix.Source build installer\RewardVision.wxs -arch x64 -o release\RewardVision.msi
Write-Host "Built release\RewardVision.msi"
