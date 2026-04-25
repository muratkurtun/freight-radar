#!/usr/bin/env bash
# Restore a Postgres dump produced by pg_backup.sh.
#
# Usage:
#   ./pg_restore.sh /opt/or-backups/or_20260424-030000.sql.gz
#
# DESTRUCTIVE: drops and recreates the target database.

set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <path-to-dump.sql.gz>"
    exit 1
fi

FILE="$1"
CONTAINER="or_postgres"

ENV_FILE="$(dirname "$(dirname "$(dirname "$(readlink -f "$0")")")")/.env"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }

: "${POSTGRES_USER:?POSTGRES_USER not set}"
: "${POSTGRES_DB:?POSTGRES_DB not set}"

echo "About to DROP and recreate ${POSTGRES_DB} from ${FILE}."
read -r -p "Type the database name to confirm: " CONFIRM
[ "$CONFIRM" = "$POSTGRES_DB" ] || { echo "aborted"; exit 1; }

docker exec -i "$CONTAINER" psql -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};" \
    -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

gunzip -c "$FILE" | docker exec -i "$CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

echo "Restore complete."
