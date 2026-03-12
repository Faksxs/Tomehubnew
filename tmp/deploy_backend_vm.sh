#!/bin/bash
set -e

IMAGE="${1:-ams.ocir.io/axrluoxw8q8k/tomehub/backend:latest}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backend deployment..."
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Using image: $IMAGE"

docker pull "$IMAGE" || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stopping old container..."
docker rm -f tomehub-backend 2>/dev/null || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting new container..."
docker run -d \
  --name tomehub-backend \
  --restart unless-stopped \
  --network infra_tomehub-network \
  -p 80:80 \
  -p 443:443 \
  -v /home/ubuntu/tomehub/apps/backend/wallet:/app/wallet:ro \
  -v /home/ubuntu/tomehub/apps/backend/secrets:/app/secrets:ro \
  -v /home/ubuntu/tomehub/apps/backend/oci_private_key.pem:/app/oci_private_key.pem:ro \
  -v tomehub_upload_data:/app/uploads \
  -v infra_caddy_data:/root/.local/share/caddy \
  --env-file /home/ubuntu/tomehub/apps/backend/.env \
  -e ENVIRONMENT=production \
  -e APP_ENV=production \
  -e APP_DEBUG=0 \
  -e REDIS_URL=redis://tomehub-redis:6379/0 \
  -e OCI_KEY_FILE=/app/oci_private_key.pem \
  "$IMAGE"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Waiting for container to become healthy..."
sleep 10
docker ps -a | grep tomehub-backend || true
curl -s http://127.0.0.1:5000/ || true
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Deployment complete!"