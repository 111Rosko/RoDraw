<#
    Builds RoDraw end to end: icon -> executable -> installer.

        powershell -ExecutionPolicy Bypass -File build\build.ps1

    Options:
        -SkipIcon       reuse the existing rodraw.ico
        -SkipInstaller  stop after the exe (no Inno Setup needed)

    Output:
        dist\RoDraw\RoDraw.exe                     the application
        installer\Output\RoDraw-Setup-1.3.2.exe    the installer
#>
[CmdletBinding()]
param(
    [switch]$SkipIcon,
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "RoDraw build -- $root" -ForegroundColor Cyan

# --- 1. icon ---------------------------------------------------------------
if (-not $SkipIcon) {
    Write-Host "`n[1/4] Generating icon..." -ForegroundColor Yellow
    python tools\make_icon.py
    if ($LASTEXITCODE -ne 0) { throw "Icon generation failed." }
} else {
    Write-Host "`n[1/4] Skipping icon." -ForegroundColor DarkGray
}

# --- 2. executable ---------------------------------------------------------
Write-Host "`n[2/4] Building executable..." -ForegroundColor Yellow
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build\work build\RoDraw.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$exe = Join-Path $root 'dist\RoDraw\RoDraw.exe'
if (-not (Test-Path $exe)) { throw "Expected $exe but it is missing." }
$mb = [math]::Round(((Get-ChildItem 'dist\RoDraw' -Recurse |
        Measure-Object -Property Length -Sum).Sum / 1MB), 1)
Write-Host "      dist\RoDraw  ($mb MB)" -ForegroundColor Green

# --- 3. smoke test ---------------------------------------------------------
# Launch the thing and confirm it actually reaches the screen. A build can
# import-error on startup and still look fine to a "did the process survive?"
# check, because the crash dialog keeps the process alive.
Write-Host "`n[3/4] Smoke-testing the executable..." -ForegroundColor Yellow
python tools\smoke_test.py
if ($LASTEXITCODE -ne 0) {
    throw "The built executable failed to start. Not packaging a broken build."
}

# --- 4. installer ----------------------------------------------------------
if ($SkipInstaller) {
    Write-Host "`n[4/4] Skipping installer." -ForegroundColor DarkGray
    Write-Host "`nDone." -ForegroundColor Cyan
    return
}

Write-Host "`n[4/4] Building installer..." -ForegroundColor Yellow

$iscc = $null
$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
foreach ($c in $candidates) { if (Test-Path $c) { $iscc = $c; break } }
if (-not $iscc) {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}

if (-not $iscc) {
    Write-Warning "Inno Setup 6 not found, so no installer was built."
    Write-Host   "Install it with:  winget install -e --id JRSoftware.InnoSetup"
    Write-Host   "then re-run:      powershell -ExecutionPolicy Bypass -File build\build.ps1 -SkipIcon"
    Write-Host   "`nThe application itself is ready in dist\RoDraw." -ForegroundColor Green
    return
}

& $iscc 'installer\RoDraw.iss'
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

# The portable archive must be built here rather than zipped by hand: the
# first upload went out as the bare launcher exe, which cannot start without
# the folder beside it.
$version = (Select-String -Path 'rodraw\__init__.py' -Pattern '__version__ = "(.+)"'
           ).Matches[0].Groups[1].Value
$zip = "installer\Output\RoDraw-$version-portable.zip"
Get-ChildItem 'installer\Output\RoDraw-*-portable.zip' -ErrorAction SilentlyContinue |
    Remove-Item
Compress-Archive -Path 'dist\RoDraw\*' -DestinationPath $zip -CompressionLevel Optimal

$setup = Get-ChildItem 'installer\Output\*.exe' -ErrorAction SilentlyContinue |
         Select-Object -First 1
if ($setup) {
    $smb = [math]::Round($setup.Length / 1MB, 1)
    $zmb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
    Write-Host "`nDone." -ForegroundColor Cyan
    Write-Host "  Application : dist\RoDraw\RoDraw.exe"
    Write-Host "  Installer   : $($setup.FullName)  ($smb MB)" -ForegroundColor Green
    Write-Host "  Portable    : $zip  ($zmb MB)" -ForegroundColor Green
    Write-Host "`nSHA256, for the download page:"
    Get-FileHash $setup.FullName -Algorithm SHA256 |
        ForEach-Object { Write-Host "  $($setup.Name)`n    $($_.Hash.ToLower())" }
    Get-FileHash $zip -Algorithm SHA256 |
        ForEach-Object { Write-Host "  $(Split-Path $zip -Leaf)`n    $($_.Hash.ToLower())" }
}
