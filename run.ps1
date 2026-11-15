$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m venv backend\.venv
& backend\.venv\Scripts\pip.exe install -e backend
Push-Location frontend
npm install
Pop-Location

Push-Location backend
& .\.venv\Scripts\python.exe -m app.seed --reset
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000"
Pop-Location

Push-Location frontend
npm run dev
Pop-Location
