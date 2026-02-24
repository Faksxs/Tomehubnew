#!/bin/bash
set -e

echo "=== TomeHub Backend Startup ==="

# Step 1: Generate Caddyfile
echo "[1/3] Preparing Caddy config..."
DOMAIN="${CADDY_DOMAIN:-api.tomehub.nl}"
ACME_CA="${CADDY_ACME_CA:-}"
ACME_EMAIL="${CADDY_ACME_EMAIL:-}"

# Use Caddy default ACME issuer behavior (Let's Encrypt by default).
# Avoid forcing ZeroSSL because it requires an email address for account pre-registration.
{
  if [ -n "${ACME_CA}" ] || [ -n "${ACME_EMAIL}" ]; then
    echo "{"
    if [ -n "${ACME_EMAIL}" ]; then
      echo "    email ${ACME_EMAIL}"
    fi
    if [ -n "${ACME_CA}" ]; then
      echo "    acme_ca ${ACME_CA}"
    fi
    echo "}"
    echo ""
  fi
  echo "${DOMAIN} {"
  echo "    reverse_proxy localhost:5000"
  echo "}"
} > /etc/caddy/Caddyfile

echo "      Domain: https://${DOMAIN}"
cat /etc/caddy/Caddyfile

# Step 2: Start Caddy in background
echo "[2/3] Starting Caddy..."
caddy start --config /etc/caddy/Caddyfile --adapter caddyfile

# Step 3: Start Python backend (foreground)
echo "[3/3] Starting Python backend..."
echo "=== Ready! Backend available internally at http://localhost:5000 ==="
exec python -m gunicorn -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:5000 --workers 2 --timeout 120 --access-logfile - --error-logfile - --log-level info app:app
