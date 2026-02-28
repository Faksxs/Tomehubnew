[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$VmHost,

    [Parameter(Mandatory = $true)]
    [string]$KeyPath,

    [string]$User = "ubuntu",
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [string]$RegistryRepo = "ams.ocir.io/axrluoxw8q8k/tomehub/backend",
    [string]$RemoteComposeDir = "/home/ubuntu/tomehub/infra",
    [string]$ApiHealthUrl = "https://api.tomehub.nl/",
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"

$remoteScript = @'
set -euo pipefail

COMPOSE_DIR="__COMPOSE_DIR__"
INFRA_ENV="$COMPOSE_DIR/.env"
REGISTRY_REPO="__REGISTRY_REPO__"
IMAGE_TAG="__IMAGE_TAG__"
API_HEALTH_URL="__API_HEALTH_URL__"
SKIP_SMOKE_TEST="__SKIP_SMOKE_TEST__"

mkdir -p "$COMPOSE_DIR"

tmp_env="$(mktemp)"
if [ -f "$INFRA_ENV" ]; then
  grep -vE '^(BACKEND_IMAGE_REPO|BACKEND_IMAGE_TAG)=' "$INFRA_ENV" > "$tmp_env" || true
fi
printf 'BACKEND_IMAGE_REPO=%s\nBACKEND_IMAGE_TAG=%s\n' "$REGISTRY_REPO" "$IMAGE_TAG" >> "$tmp_env"
mv "$tmp_env" "$INFRA_ENV"

cd "$COMPOSE_DIR"
echo "[deploy] Using image: ${REGISTRY_REPO}:${IMAGE_TAG}"
echo "[deploy] docker compose pull backend"
docker compose pull backend

echo "[deploy] docker compose up -d backend"
docker compose up -d backend

echo "[deploy] docker compose ps backend"
docker compose ps backend

echo "[deploy] docker image prune -f"
docker image prune -f >/dev/null || true

if [ "$SKIP_SMOKE_TEST" != "true" ]; then
  echo "[deploy] Smoke test: $API_HEALTH_URL"
  http_code="$(curl -fsS -o /dev/null -w '%{http_code}' "$API_HEALTH_URL")"
  echo "[deploy] Smoke test HTTP $http_code"
fi
'@

$remoteScript = $remoteScript.Replace("__COMPOSE_DIR__", $RemoteComposeDir)
$remoteScript = $remoteScript.Replace("__REGISTRY_REPO__", $RegistryRepo)
$remoteScript = $remoteScript.Replace("__IMAGE_TAG__", $Tag)
$remoteScript = $remoteScript.Replace("__API_HEALTH_URL__", $ApiHealthUrl)
$remoteScript = $remoteScript.Replace("__SKIP_SMOKE_TEST__", ($(if ($SkipSmokeTest) { "true" } else { "false" })))
$remoteScript = $remoteScript -replace "`r`n", "`n"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "OCIR Pull Deploy (VM)" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Target VM     : $User@$VmHost" -ForegroundColor Gray
Write-Host "Remote Dir    : $RemoteComposeDir" -ForegroundColor Gray
Write-Host "Registry Repo : $RegistryRepo" -ForegroundColor Gray
Write-Host "Image Tag     : $Tag" -ForegroundColor Gray
Write-Host "Smoke URL     : $ApiHealthUrl" -ForegroundColor Gray

$remoteScript | ssh -i $KeyPath "$User@$VmHost" "bash -s"

Write-Host "`nDeploy completed for tag: $Tag" -ForegroundColor Green
Write-Host "Rollback example (previous tag):" -ForegroundColor Yellow
Write-Host "  .\scripts\deploy_oracle_vm_backend.ps1 -VmHost $VmHost -User $User -KeyPath `"$KeyPath`" -Tag <previous-tag>" -ForegroundColor Yellow
