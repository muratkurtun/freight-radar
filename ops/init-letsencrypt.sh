#!/usr/bin/env bash
# One-time Let's Encrypt bootstrap.
#
# Nginx refuses to start if the cert files referenced by its config
# don't exist. The standard workaround is:
#   1. generate a self-signed dummy cert so nginx can boot,
#   2. start nginx so it can serve the HTTP-01 challenge,
#   3. delete the dummy and request the real cert via certbot webroot,
#   4. reload nginx to pick up the real cert.
#
# Run this ONCE on a fresh server, after DNS for $DOMAIN points here
# and after `docker compose -f docker-compose.prod.yml build`.
#
# Re-running is safe but wasteful — certbot's own renewal loop (in
# docker-compose.prod.yml) handles subsequent renewals automatically.

set -euo pipefail

if [ -z "${1:-}" ] || [ -z "${2:-}" ]; then
    echo "Usage: $0 <domain> <email>"
    echo "Example: $0 opportunityradar.com you@opportunityradar.com"
    exit 1
fi

DOMAIN="$1"
EMAIL="$2"
STAGING="${STAGING:-0}"   # STAGING=1 uses Let's Encrypt staging for dry-run.

COMPOSE="docker compose -f docker-compose.prod.yml"

echo "### 1/4  dummy cert for ${DOMAIN}"
$COMPOSE run --rm --entrypoint "sh -c '\
  mkdir -p /etc/letsencrypt/live/${DOMAIN} && \
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout /etc/letsencrypt/live/${DOMAIN}/privkey.pem \
    -out    /etc/letsencrypt/live/${DOMAIN}/fullchain.pem \
    -subj   /CN=localhost'" certbot

echo "### 2/4  start nginx"
$COMPOSE up -d nginx

echo "### 3/4  delete dummy & request real cert"
$COMPOSE run --rm --entrypoint "sh -c '\
  rm -rf /etc/letsencrypt/live/${DOMAIN} \
         /etc/letsencrypt/archive/${DOMAIN} \
         /etc/letsencrypt/renewal/${DOMAIN}.conf'" certbot

STAGING_ARG=""
[ "$STAGING" = "1" ] && STAGING_ARG="--staging"

$COMPOSE run --rm --entrypoint "certbot certonly --webroot \
  -w /var/www/certbot \
  --email ${EMAIL} \
  -d ${DOMAIN} -d www.${DOMAIN} \
  --rsa-key-size 2048 \
  --agree-tos --no-eff-email \
  ${STAGING_ARG}" certbot

echo "### 4/4  reload nginx"
$COMPOSE exec nginx nginx -s reload

echo
echo "Done. Cert issued for ${DOMAIN} and www.${DOMAIN}."
echo "Renewal runs automatically every 12h inside the certbot container."
