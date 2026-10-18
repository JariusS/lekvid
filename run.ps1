# Quick Start Script for Windows PowerShell
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Antigravity Liquidity Sweep Trading Bot v2.0" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "❌ Python not found in PATH! Please install Python 3.10+." -ForegroundColor Red
    exit 1
}

# 2. Check Virtual Environment
if (-not (Test-Path ".venv")) {
    Write-Host "📦 Creating virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
}

Write-Host "⚙️ Activating virtual environment..." -ForegroundColor Green
& .\.venv\Scripts\Activate.ps1

# 3. Check Dependencies
Write-Host "📥 Installing / Updating dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet

# 4. Check .env
if (-not (Test-Path ".env")) {
    Write-Host "⚠️ .env file not found! Copying from .env.example..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host "❗ Please fill in your API keys in .env before running live mode!" -ForegroundColor Yellow
}

# 5. Pre-flight tests
Write-Host "🧪 Running automated test suite..." -ForegroundColor Cyan
python -m pytest tests/ -v

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Unit tests failed! Execution aborted." -ForegroundColor Red
    exit 1
}

Write-Host "🚀 Launching bot in SIMULATED / DRY-RUN mode..." -ForegroundColor Green
python main.py --mode live --dry-run --symbol BTCUSDT
