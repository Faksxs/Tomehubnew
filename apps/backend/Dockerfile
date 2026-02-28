# TomeHub Backend Dockerfile
# Python Flask API with Caddy for auto-HTTPS (self-discovering IP)

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/firebase-admin.json

# Set working directory
WORKDIR /app

# Install system dependencies including Caddy, curl, and libzbar0 (for pyzbar barcode scanning)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    gnupg \
    libzbar0 \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list \
    && apt-get update \
    && apt-get install -y caddy \
    && rm -rf /var/lib/apt/lists/*

# Create Caddy config directory
RUN mkdir -p /etc/caddy

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Fix Windows line endings and make entrypoint executable
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Create uploads directory for temporary files
RUN mkdir -p /app/uploads

# Expose ports: 80 (HTTP redirect), 443 (HTTPS), 5000 (internal Flask)
EXPOSE 80 443 5000

# Health check via HTTPS
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:5000/ || exit 1

# Use entrypoint script to discover IP, generate Caddyfile, and start services
ENTRYPOINT ["/app/entrypoint.sh"]
