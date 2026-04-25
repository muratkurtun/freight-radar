#!/usr/bin/env bash
# Nightly Postgres dump.
#
# Cron entry (as the deploy user):
#   0 3 * * *  /opt/opportunity-radar/ops/backup/pg_backup.sh >> /var/log/or-backup.log 2>&1
#
# Retention: 7 daily dumps. Off-site copy is an exercise for the
# reader — `rclone copy $DEST remote:or-backups/` against a Hetzner
# Storage Box is the cheapest option.

set -euo pipefail

DEST="${BACKUP_DIR:-/opt/or-backups}"
KEEP="${KEEP_DAYS:-7}"
CONTAINER="or_postgres"

mkdir -p "$DEST"
TS="$(date +%Y%m%d-%H%M%S)"
FILE="$DEST/or_${TS}.sql.gz"

# Read DB creds from the same .env docker-compose uses, so we don't
# duplicate secrets.
ENV_FILE="$(dirname "$(dirname "$(dirname "$(readlink -f "$0")")")")/.env"
if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    set -a; . "$ENV_FILE"; set +a
fi

: "${POSTGRES_USER:?POSTGRES_USER not set}"
: "${POSTGRES_DB:?POSTGRES_DB not set}"

echo "[$(date -Iseconds)] dumping ${POSTGRES_DB} -> ${FILE}"
docker exec "$CONTAINER" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --format=plain --no-owner --no-privileges \
    | gzip -9 > "$FILE"

echo "[$(date -Iseconds)] pruning backups older than ${KEEP} days"
find "$DEST" -type f -name 'or_*.sql.gz' -mtime "+${KEEP}" -delete

echo "[$(date -Iseconds)] done; current backups:"
ls -lh "$DEST" | tail -n +2
