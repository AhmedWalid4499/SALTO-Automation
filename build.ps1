# Builds the SALTO Buddy installer.
#
#   .\build.ps1            -> releases\SALTO-Buddy-Setup-<version>.exe
#
# To publish an update on GitHub use release.ps1 (it calls this script).
param()
# PyInstaller logs to stderr, which PS 5.1 treats as errors under "Stop": rely on exit codes instead
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$version = (Select-String -Path "salto\version.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Building SALTO Buddy $version" -ForegroundColor Cyan

if (-not (Test-Path "assets\app.ico")) { py assets\make_icon.py }

# geckodriver to bundle (Selenium Manager caches it on first run from source)
$gecko = Get-ChildItem "$env:USERPROFILE\.cache\selenium\geckodriver" -Recurse -Filter geckodriver.exe -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $gecko) { throw "geckodriver not found: run 'py cli.py <order>' once from source so Selenium downloads it." }

# build outside OneDrive: sync locks files in build folders
$work = Join-Path $env:LOCALAPPDATA "SaltoBuddy\build"
$dist = Join-Path $work "dist"

py -m PyInstaller --noconfirm --clean --windowed --name "SALTO Buddy" `
    --icon "$PSScriptRoot\assets\app.ico" `
    --collect-all selenium `
    --add-data "$PSScriptRoot\salto\extract.js;salto" `
    --add-data "$PSScriptRoot\assets\app.ico;assets" `
    --add-binary "$($gecko.FullName);." `
    --distpath "$dist" --workpath "$work\tmp" --specpath "$work" app.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found" }
New-Item -ItemType Directory -Force releases | Out-Null
& $iscc /Q "/DAppVersion=$version" "/DDistDir=$dist" "/O$PSScriptRoot\releases" installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

$setup = Join-Path $PSScriptRoot "releases\SALTO-Buddy-Setup-$version.exe"
Write-Host "Done: $setup" -ForegroundColor Green
