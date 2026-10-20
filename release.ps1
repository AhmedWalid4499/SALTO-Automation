# Publishes a new SALTO Buddy version on GitHub.
#
#   1. Bump __version__ in salto\version.py (e.g. 1.2.0 -> 1.3.0)
#   2. .\release.ps1 -Notes "What changed"      (or -NotesFile notes.md for longer notes)
#
# It builds the installer, commits + pushes the code, tags vX.Y.Z and creates a
# GitHub release with the installer attached. Every installed SALTO Buddy sees
# the new release the next time it starts and offers "Update available".
# Needs the GitHub CLI signed in once:  gh auth login
param([string]$Notes = "", [string]$NotesFile = "")
if ($NotesFile) { $Notes = Get-Content $NotesFile -Raw -Encoding utf8 }
if (-not $Notes) { throw "Give -Notes ""What changed"" or -NotesFile <file>" }
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$version = (Select-String -Path "salto\version.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$tag = "v$version"
gh auth status *> $null
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not signed in. Run: gh auth login" }
git rev-parse -q --verify "refs/tags/$tag" *> $null
if ($LASTEXITCODE -eq 0) { throw "Tag $tag already exists: bump __version__ in salto\version.py first." }

& "$PSScriptRoot\build.ps1"
if ($LASTEXITCODE -ne 0 -and -not $?) { throw "Build failed" }
$setup = Join-Path $PSScriptRoot "releases\SALTO-Buddy-Setup-$version.exe"
if (-not (Test-Path $setup)) { throw "Installer not found: $setup" }

git add -A
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {   # skip if already committed
    $msgTmp = Join-Path $env:TEMP "salto-buddy-commit.txt"
    Set-Content -Path $msgTmp -Value "Release $tag`n`n$Notes" -Encoding utf8
    git commit -F $msgTmp
}
git tag $tag
git push origin HEAD --tags
if ($LASTEXITCODE -ne 0) { throw "git push failed" }

# notes go through a file: Windows PowerShell mangles quotes inside arguments to native programs
$notesTmp = Join-Path $env:TEMP "salto-buddy-notes-$version.md"
Set-Content -Path $notesTmp -Value $Notes -Encoding utf8
gh release create $tag $setup --title "SALTO Buddy $version" --notes-file $notesTmp --latest
if ($LASTEXITCODE -ne 0) { throw "gh release create failed" }
Write-Host "Released $tag" -ForegroundColor Green
