param([string]$PythonPath, [switch]$SelfTest)
$ErrorActionPreference = 'Stop'
if (-not $PythonPath) {
    $PythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        $PythonPath = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    }
}
if (-not (Test-Path -LiteralPath $PythonPath)) { throw '請指定 Python 3.12 x64：-PythonPath 路徑' }
if ($SelfTest) {
    & $PythonPath (Join-Path $PSScriptRoot 'verify.py')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonPath (Join-Path $PSScriptRoot 'verify_assets.py')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonPath (Join-Path $PSScriptRoot 'verify_pipeline.py')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonPath (Join-Path $PSScriptRoot 'verify_layout.py')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonPath (Join-Path $PSScriptRoot 'verify_equipment.py')
}
else { & $PythonPath (Join-Path $PSScriptRoot 'main.py') }
exit $LASTEXITCODE
