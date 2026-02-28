[CmdletBinding()]
param(
    [string]$RegistryRepo = "ams.ocir.io/axrluoxw8q8k/tomehub/backend",
    [string]$ContextDir = "apps\backend",
    [string]$DockerfilePath = "apps\backend\Dockerfile",
    [string]$Tag,
    [switch]$PushLatest
)

$ErrorActionPreference = "Stop"

function Get-DefaultTag {
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss")
    $gitSha = "nogit"

    try {
        $gitSha = (git rev-parse --short HEAD 2>$null).Trim()
        if ([string]::IsNullOrWhiteSpace($gitSha)) {
            $gitSha = "nogit"
        }
    }
    catch {
        $gitSha = "nogit"
    }

    return "$timestamp-$gitSha"
}

if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = Get-DefaultTag
}

$taggedImage = "$RegistryRepo`:$Tag"
$latestImage = "$RegistryRepo`:latest"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "OCIR Backend Build + Push" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Registry Repo : $RegistryRepo" -ForegroundColor Gray
Write-Host "Image Tag     : $Tag" -ForegroundColor Gray
Write-Host "Context       : $ContextDir" -ForegroundColor Gray
Write-Host "Dockerfile    : $DockerfilePath" -ForegroundColor Gray

Write-Host "`n=========================================" -ForegroundColor Cyan
Write-Host "1. Building image: $taggedImage" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
docker build -t $taggedImage -f $DockerfilePath $ContextDir

Write-Host "`n=========================================" -ForegroundColor Cyan
Write-Host "2. Pushing image: $taggedImage" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
docker push $taggedImage

if ($PushLatest) {
    Write-Host "`n=========================================" -ForegroundColor Cyan
    Write-Host "3. Updating floating latest tag (optional)" -ForegroundColor Cyan
    Write-Host "=========================================" -ForegroundColor Cyan
    docker tag $taggedImage $latestImage
    docker push $latestImage
}

Write-Host "`n=========================================" -ForegroundColor Green
Write-Host "SUCCESS: OCIR image pushed." -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host "Immutable tag: $Tag" -ForegroundColor Green

Write-Host "`nNext (recommended deploy path):" -ForegroundColor Yellow
Write-Host "1) VM deploy helper script:" -ForegroundColor Yellow
Write-Host "   .\scripts\deploy_oracle_vm_backend.ps1 -Host 158.101.213.120 -User ubuntu -KeyPath ""C:\path\to\key.pem"" -Tag $Tag" -ForegroundColor Yellow
Write-Host "2) Or manual on VM (inside ~/tomehub/infra):" -ForegroundColor Yellow
Write-Host "   printf ""BACKEND_IMAGE_REPO=$RegistryRepo`nBACKEND_IMAGE_TAG=$Tag`n"" > .env" -ForegroundColor Yellow
Write-Host "   docker compose pull backend" -ForegroundColor Yellow
Write-Host "   docker compose up -d backend" -ForegroundColor Yellow
Write-Host "   docker image prune -f" -ForegroundColor Yellow
Write-Host "=========================================" -ForegroundColor Green
