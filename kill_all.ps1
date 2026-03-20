# Kill all processes related to csv-data-summarizer project
# Usage: .\kill_all.ps1

Write-Host "=== Killing csv-data-summarizer processes ===" -ForegroundColor Red

# Pattern to match project-related processes
$projectPath = "D:\csv-data-summarizer"

# Get all processes related to this project
$processes = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match $projectPath -or
    $_.CommandLine -match 'uvicorn.*server.app:app' -or
    $_.CommandLine -match 'vite' -or
    $_.ExecutablePath -match 'csv-data-summarizer' -or
    ($_.Name -eq 'node.exe' -and $_.CommandLine -match 'vite')
}

if ($processes) {
    Write-Host "`nFound $($processes.Count) processes:" -ForegroundColor Yellow

    foreach ($proc in $processes) {
        Write-Host "  Killing PID $($proc.ProcessId): $($proc.Name)"

        # Kill entire process tree
        taskkill /F /PID $proc.ProcessId /T 2>$null
    }

    Start-Sleep 1

    # Also kill any orphaned multiprocessing workers
    $orphans = Get-Process python* -ErrorAction SilentlyContinue | Where-Object {
        $info = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue
        $info -and $info.CommandLine -match 'multiprocessing.spawn'
    }

    foreach ($orphan in $orphans) {
        Write-Host "  Killing orphan PID $($orphan.Id)"
        Stop-Process -Id $orphan.Id -Force -ErrorAction SilentlyContinue
    }

    Write-Host "`nDone! All processes killed." -ForegroundColor Green
} else {
    Write-Host "No related processes found." -ForegroundColor Green
}

# Check port status
Write-Host "`n=== Port Status ===" -ForegroundColor Cyan
8000, 8001, 5173 | ForEach-Object {
    $port = $_
    $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conn) {
        Write-Host "Port $port : Still occupied" -ForegroundColor Red
    } else {
        Write-Host "Port $port : Free" -ForegroundColor Green
    }
}
