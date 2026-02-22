$ErrorActionPreference = "Stop"

$IMAGE_NAME = "ams.ocir.io/axrluoxw8q8k/tomehub/backend:latest"
$CONTEXT_DIR = "apps\backend"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "1. Building Docker image: $IMAGE_NAME" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
docker build -t $IMAGE_NAME -f "$CONTEXT_DIR\Dockerfile" $CONTEXT_DIR

Write-Host "`n=========================================" -ForegroundColor Cyan
Write-Host "2. Pushing Docker image to OCIR..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
docker push $IMAGE_NAME

Write-Host "`n=========================================" -ForegroundColor Green
Write-Host "SUCCESS: Image pushed to OCIR." -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host "Now SSH into your Oracle server and run the following in the project directory:" -ForegroundColor Yellow
Write-Host "  docker-compose pull backend" -ForegroundColor Yellow
Write-Host "  docker-compose up -d backend" -ForegroundColor Yellow
Write-Host "  docker image prune -f" -ForegroundColor Yellow
Write-Host "=========================================" -ForegroundColor Green
