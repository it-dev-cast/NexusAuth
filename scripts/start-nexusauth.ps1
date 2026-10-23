# Auto-start script for the nexusAuth dev server.
# Registered to run at Windows logon via the "NexusAuth-AutoStart" Scheduled Task.
# Safe to run manually too - just double-click or `powershell -File start-nexusauth.ps1`.

$ProjectDir = "C:\Users\Dell\Desktop\nexusAuth"
Set-Location $ProjectDir

Write-Host "Starting nexusAuth dev server from $ProjectDir ..."
Write-Host "UI:  http://127.0.0.1:8000/ui"
Write-Host "Docs: http://127.0.0.1:8000/docs"
Write-Host ""

& "$ProjectDir\.venv\Scripts\python.exe" -m uvicorn main:app --reload --port 8000
