# Windows 11 Local Environment Setup using uv
$ErrorActionPreference = "Stop"

Write-Host "Checking for uv..."
if (!(Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found. Installing uv..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
}

Write-Host "Syncing Python dependencies with uv..."
uv sync

Write-Host "Starting local infrastructure (Redis, PostgreSQL) via Docker Compose..."
docker-compose up -d redis db

Write-Host "Setup complete."
Write-Host "Run 'uv run uvicorn src.agent_session.api.routes:app --reload' to start the local API server."