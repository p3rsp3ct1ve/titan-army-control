$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { throw 'Install Python 3.12 with Tk/Tcl first' }
$version = (& $python -c "from TitanArmyControl.version import VERSION; print(VERSION)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $version) { throw 'Application version is missing' }
& $python -m venv .venv-windows
if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment' }
& .\.venv-windows\Scripts\python.exe -m pip install --upgrade pip pyinstaller pillow pystray
if ($LASTEXITCODE -ne 0) { throw 'Could not install build dependencies' }
& .\.venv-windows\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath "dist\windows-$version" TitanArmyControl.spec
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
Write-Host "Built dist\windows-$version\TitanArmyControl.exe"
