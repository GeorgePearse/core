#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_FILE="${REPO_ROOT}/migrations/full_ddl.sql"

DB_NAME="genesis_ddl_export"
DB_USER="postgres"
DB_PASSWORD="postgres"
CONTAINER_NAME="genesis-ddl-export-$$"
PG_PORT=54399

cleanup() {
    echo "Cleaning up..."
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Starting temporary Postgres container..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -e POSTGRES_DB="$DB_NAME" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD="$DB_PASSWORD" \
    -p "${PG_PORT}:5432" \
    postgres:15 >/dev/null

echo "Waiting for Postgres to be ready..."
for i in $(seq 1 30); do
    if docker exec "$CONTAINER_NAME" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Postgres did not become ready in time" >&2
        exit 1
    fi
    sleep 1
done

echo "Running Liquibase migrations..."
cd "${REPO_ROOT}/migrations"
liquibase \
    --url="jdbc:postgresql://localhost:${PG_PORT}/${DB_NAME}" \
    --username="$DB_USER" \
    --password="$DB_PASSWORD" \
    --changeLogFile=changelogs/db.changelog-master.yaml \
    update
cd "${REPO_ROOT}"

echo "Exporting schema via pg_dump..."
docker exec "$CONTAINER_NAME" pg_dump \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --schema-only \
    --no-owner \
    --no-privileges \
    --exclude-table='databasechangelog*' \
    | sed '/^\\restrict/d; /^\\unrestrict/d; /^SELECT pg_catalog/d; /^SET default_table_access_method/d' \
    > "$OUTPUT_FILE"

echo "DDL exported to ${OUTPUT_FILE}"
