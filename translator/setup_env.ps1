# Builds the dedicated venv for manga-image-translator.
# Idempotent: safe to re-run after a partial or failed install.
#
# Everything lives on D: - interpreter, venv, wheels, models, HF cache.
# D:\Code\.venv (the shared env) is deliberately left alone: this project pins
# openai==1.63.0 / httpx==0.27.2 / pydantic==2.5.0 / numpy==1.26.4, which would
# downgrade transformers 5.x and break the other projects sharing that env.

$ErrorActionPreference = 'Stop'

$Root       = $PSScriptRoot
$BasePython = 'D:\Code\python312\python.exe'
$VenvPy     = Join-Path $Root '.venv\Scripts\python.exe'
$Upstream   = Join-Path $Root 'manga-image-translator'

# Keep every cache off C:
$env:PIP_CACHE_DIR = Join-Path $Root '.pip-cache'
$env:HF_HOME       = Join-Path $Root 'hf-cache'

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

if (-not (Test-Path $BasePython)) { throw "base interpreter not found: $BasePython" }
if (-not (Test-Path $Upstream))   { throw "upstream repo not found: $Upstream" }

Step 'venv'
if (-not (Test-Path $VenvPy)) {
    & $BasePython -m venv (Join-Path $Root '.venv')
}
& $VenvPy -m pip install --upgrade pip setuptools wheel

Step 'torch (cu124)'
# Installed ahead of requirements.txt so the plain `torch` / `torchvision` lines
# there resolve as already-satisfied instead of pulling the CPU-only build.
& $VenvPy -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124

Step 'requirements (pydensecrf filtered out)'
# pydensecrf is a Cython/C++ source-only dist with no wheel for Windows+py3.12.
# Filtered here rather than edited out of the repo, so `git pull` stays clean.
# The pydensecrf-shim installed below satisfies the import.
$reqSrc = Join-Path $Upstream 'requirements.txt'
$reqOut = Join-Path $Root '.requirements-filtered.txt'
Get-Content $reqSrc | Where-Object { $_ -notmatch '^\s*pydensecrf' } | Set-Content $reqOut -Encoding utf8
& $VenvPy -m pip install -r $reqOut

Step 'pydensecrf shim'
& $VenvPy -m pip install (Join-Path $Root 'shims\pydensecrf-shim')

Step 'pipeline extras'
# img2pdf streams pre-encoded JPEGs into the PDF, so build_pdf.py never holds
# ~390 decoded pages in memory.
& $VenvPy -m pip install img2pdf

Step 'verify'
& $VenvPy (Join-Path $Root 'verify_env.py')

Write-Host "`nenv ready: $VenvPy" -ForegroundColor Green
