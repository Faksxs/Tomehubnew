#!/bin/bash
set -e

echo "=== TomeHub Backend Startup ==="

# Step 1: Discover public IP
echo "[1/4] Discovering public IP..."
PUBLIC_IP=$(curl -s --max-time 10 ifconfig.me || curl -s --max-time 10 icanhazip.com || curl -s --max-time 10 api.ipify.org)

if [ -z "$PUBLIC_IP" ]; then
    echo "ERROR: Could not discover public IP!"
    exit 1
fi

echo "      Public IP: $PUBLIC_IP"

# Step 2: Generate Caddyfile
echo "[2/4] Generating Caddyfile..."
DOMAIN="${PUBLIC_IP}.nip.io"

echo "${DOMAIN} {" > /etc/caddy/Caddyfile
echo "    reverse_proxy localhost:5000" >> /etc/caddy/Caddyfile
echo "}" >> /etc/caddy/Caddyfile

echo "      Domain: https://${DOMAIN}"
cat /etc/caddy/Caddyfile

# Step 3: Start Caddy in background
echo "[3/4] Starting Caddy..."
caddy start --config /etc/caddy/Caddyfile --adapter caddyfile

# Step 4: Start Flask backend (foreground)
echo "[4/4] Starting Flask backend..."
echo "=== Ready! Backend available at https://${DOMAIN} ==="
exec python -m gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app
