
Write-Host "Starting CLI container (interactive mode)..." -ForegroundColor Green
Write-Host "Press Ctrl+D or type 'exit' to quit" -ForegroundColor Green
Write-Host ""
Write-Host "Volume mounts:" -ForegroundColor Yellow
Write-Host "  - Current directory -> /uploads (for file uploads)" -ForegroundColor Yellow
Write-Host "  - .\downloads -> /downloads (for file downloads)" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path "downloads")) {
    New-Item -ItemType Directory -Path "downloads" | Out-Null
}

docker run -it --rm `
    --network dfs-network `
    -v "${PWD}:/uploads" `
    -v "${PWD}/downloads:/downloads" `
    -w /uploads `
    redcloud-cli:latest
