#!/bin/bash
set -e

echo "=== TomeHub Backend Startup ==="

# Step 1: Generate Caddyfile (force Let's Encrypt; avoid ZeroSSL fallback)
echo "[1/3] Preparing Caddy config..."
DOMAIN="${CADDY_DOMAIN:-api.tomehub.nl}"
CADDY_ACME_CA="${CADDY_ACME_CA:-https://acme-v02.api.letsencrypt.org/directory}"
ZERO_SSL_CLEANUP="${ZERO_SSL_CLEANUP:-true}"

if [ "${ZERO_SSL_CLEANUP}" = "true" ]; then
  echo "      Cleaning previous ZeroSSL state..."
  rm -rf /data/caddy/certificates/acme.zerossl.com* || true
  rm -rf /data/caddy/acme/acme.zerossl.com* || true
fi

{
  echo "{" 
  echo "    acme_ca ${CADDY_ACME_CA}"
  if [ -n "${CADDY_EMAIL}" ]; then
    echo "    email ${CADDY_EMAIL}"
  fi
  echo "}"
  echo ""
  echo "${DOMAIN} {"
  echo "    reverse_proxy localhost:5000"
  echo "}"
} > /etc/caddy/Caddyfile

echo "      Domain: https://${DOMAIN}"
echo "      ACME CA: ${CADDY_ACME_CA}"
cat /etc/caddy/Caddyfile

# Step 2: Start Caddy in background
echo "[2/3] Starting Caddy..."
caddy start --config /etc/caddy/Caddyfile --adapter caddyfile

# Step 3: Start Python backend (foreground)
echo "[3/3] Starting Python backend..."
echo "=== Ready! Backend available internally at http://localhost:5000 ==="
exec python -m gunicorn -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:5000 --workers 2 --timeout 120 --access-logfile - --error-logfile - --log-level info app:app
