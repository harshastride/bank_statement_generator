#!/bin/bash
# ── First-time SSL setup with Certbot ──────────────────────────
# Run this ONCE on your server to obtain the initial Let's Encrypt certificate.
# After this, docker-compose handles auto-renewal via the certbot service.
#
# Prerequisites:
#   - DNS A record for bypass.skillxen.com pointing to this server
#   - Ports 80 and 443 open
#   - Docker and docker-compose installed

set -e

DOMAIN="bypass.skillxen.com"
EMAIL="${1:-admin@skillxen.com}"

echo "=== StatementGen SSL Setup ==="
echo "Domain: $DOMAIN"
echo "Email:  $EMAIL"
echo ""

# Step 1: Start with HTTP-only nginx (no SSL certs yet)
echo "[1/4] Starting services with HTTP-only config..."
cp nginx/nginx-init.conf nginx/nginx-active.conf

docker compose up -d --build app

docker run --rm \
  -v "$(pwd)/nginx/nginx-active.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v statementgen_certbot-webroot:/var/www/certbot \
  -v statementgen_certbot-certs:/etc/letsencrypt \
  --network "$(basename $(pwd))_default" \
  -p 80:80 \
  --name statementgen-nginx-init \
  -d nginx:alpine

echo "[2/4] Waiting for nginx to start..."
sleep 3

# Step 2: Run certbot to get the certificate
echo "[3/4] Requesting certificate from Let's Encrypt..."
docker run --rm \
  -v statementgen_certbot-webroot:/var/www/certbot \
  -v statementgen_certbot-certs:/etc/letsencrypt \
  certbot/certbot certonly \
    --webroot \
    -w /var/www/certbot \
    -d "$DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --non-interactive

# Step 3: Stop temp nginx, start full stack with SSL
echo "[4/4] Certificate obtained! Starting full stack with SSL..."
docker stop statementgen-nginx-init 2>/dev/null || true
rm -f nginx/nginx-active.conf

docker compose up -d

echo ""
echo "=== Done! ==="
echo "App is live at: https://$DOMAIN"
echo "Certificates will auto-renew via the certbot container."
echo ""
echo "To check cert status:  docker compose exec certbot certbot certificates"
echo "To force renewal:      docker compose exec certbot certbot renew --force-renewal"
