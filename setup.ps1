param([string]$PythonPath = "")
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
Set-Location -LiteralPath $appRoot
$venvPython = Join-Path $appRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    $runtimePython = Join-Path $appRoot '.runtime\python311\python\python.exe'
    if ($PythonPath -ne '') {
        $runtimePython = (Resolve-Path -LiteralPath $PythonPath).Path
    } elseif (-not (Test-Path -LiteralPath $runtimePython)) {
        Write-Host 'Preparing an isolated Python 3.11 runtime inside this folder...'
        $runtimeRoot = Join-Path $appRoot '.runtime'
        New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
        $archivePath = Join-Path $runtimeRoot 'python311.tar.gz'
        $pythonUrl = 'https://github.com/astral-sh/python-build-standalone/releases/download/20260929/cpython-3.11.16%2B20260929-x86_64-pc-windows-msvc-install_only.tar.gz'
        Invoke-WebRequest -Uri $pythonUrl -OutFile $archivePath
        $digest = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
        if ($digest -ne 'FE8C767E9D9B19F6780B8A843FE68F6C52C4E9771B1D4DB3B4AF4D8883D49530') {
            throw 'Python runtime checksum did not match.'
        }
        $destination = Join-Path $runtimeRoot 'python311'
        New-Item -ItemType Directory -Path $destination -Force | Out-Null
        & tar.exe -xzf $archivePath -C $destination
        if ($LASTEXITCODE -ne 0) { throw 'Could not unpack Python.' }
    }
    & $runtimePython -c "import sys; assert sys.version_info[:2] == (3, 11), 'Python 3.11 is required'"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 is required.' }
    $setupTemporaryDirectory = Join-Path $appRoot 'build\setup-temp'
    New-Item -ItemType Directory -Path $setupTemporaryDirectory -Force | Out-Null
    $setupPreviousTemp = $env:TEMP
    $setupPreviousTmp = $env:TMP
    try {
        $env:TEMP = $setupTemporaryDirectory
        $env:TMP = $setupTemporaryDirectory
        & $runtimePython -m venv (Join-Path $appRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated environment.' }
    } finally {
        $env:TEMP = $setupPreviousTemp
        $env:TMP = $setupPreviousTmp
    }
}
& $venvPython -m pip install -r (Join-Path $appRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $venvPython (Join-Path $appRoot 'tools\build_resources.py')
if ($LASTEXITCODE -ne 0) { throw 'Resource compilation failed.' }
Write-Host 'Ready. Open run.cmd, run_admin.cmd, run_light.cmd or run_dark.cmd.'
