#!/bin/bash
set -e

echo "=== TomeHub Backend Startup ==="

# Step 1: Generate Caddyfile
echo "[1/3] Generating Caddyfile..."
DOMAIN="api.tomehub.nl" # ✅ Public Domain for Auto-HTTPSain

echo "${DOMAIN} {" > /etc/caddy/Caddyfile
echo "    reverse_proxy localhost:5000" >> /etc/caddy/Caddyfile
echo "}" >> /etc/caddy/Caddyfile

echo "      Domain: https://${DOMAIN}"
cat /etc/caddy/Caddyfile

# Step 2: Start Caddy in background
echo "[2/3] Starting Caddy..."
caddy start --config /etc/caddy/Caddyfile --adapter caddyfile

# Step 3: Start Python backend (foreground)
echo "[3/3] Starting Python backend..."
echo "=== Ready! Backend available internally at http://localhost:5000 ==="
exec python -m gunicorn -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app
