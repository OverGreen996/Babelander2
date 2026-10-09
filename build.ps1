param([string]$PythonPath = (Join-Path $PSScriptRoot '.venv/Scripts/python.exe'))
$ErrorActionPreference = 'Stop'
$releaseVersion = ([regex]::Match([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'babelander/__init__.py')), "__version__ = '([^']+)'" )).Groups[1].Value
if (-not $releaseVersion) { throw '無法讀取版本。' }
$releaseDist = Join-Path $PSScriptRoot "dist/releases/$releaseVersion"
if (-not (Test-Path -LiteralPath $PythonPath)) { throw '先依 README 建立 Python 3.12 虛擬環境。' }
$env:BABELANDER_V2_CLEAN_ENV = '1'
# Prevent unrelated tools on PATH (e.g. Poppler's ICU) from replacing Windows'
# ICU DLL. Qt 6.11 imports Windows' unversioned ICU entry points.
$previousBuildPath = $env:PATH
$env:PATH = "$(Split-Path $PythonPath);$env:WINDIR/System32;$env:WINDIR"
try {
& $PythonPath -m PyInstaller --clean --noconfirm --name Babelander2 --windowed --onedir `
    --distpath "$releaseDist" --workpath "$PSScriptRoot/build/work" --specpath "$PSScriptRoot/build" `
    --paths "$PSScriptRoot" --collect-submodules babelander --collect-all rapidocr --collect-data onnxruntime --collect-data opencc `
    --add-data "$PSScriptRoot/babelander/theme.qss;babelander" "$PSScriptRoot/main.py"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 建置失敗。' }
} finally { $env:PATH = $previousBuildPath }
Write-Output (Join-Path $releaseDist 'Babelander2/Babelander2.exe')
