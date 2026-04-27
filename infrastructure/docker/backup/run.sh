#!/bin/sh
# Daily pg_dump backup sidecar for the Chronos prod stack.
#
# Runs pg_dump every BACKUP_INTERVAL_SECONDS (default 86400 = daily), writes
# a timestamped pg_restore-compatible archive into BACKUP_DIR (default
# /backups), and prunes the directory to keep only the BACKUP_RETENTION_COUNT
# (default 30) most recent files. Uses -Fc (custom format, compressed) so the
# restore path is a single pg_restore invocation — see docs/backup-restore.md.
#
# Credentials are picked up from PG* env vars that the compose file injects
# from .env.prod; there is no .pgpass file in the container.

set -eu

INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
KEEP="${BACKUP_RETENTION_COUNT:-30}"
DEST="${BACKUP_DIR:-/backups}"

mkdir -p "${DEST}"
echo "backup sidecar starting: interval=${INTERVAL}s keep=${KEEP} dest=${DEST}"

while :; do
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  out="${DEST}/chronos-${ts}.dump"
  tmp="${out}.tmp"
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "${now} dumping ${PGDATABASE:-chronos}@${PGHOST:-db} -> ${out}"
  if pg_dump -Fc --no-owner --no-acl > "${tmp}"; then
    mv "${tmp}" "${out}"
    bytes=$(wc -c < "${out}" | tr -d ' ')
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) dump ok (${bytes} bytes)"
  else
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) dump FAILED — will retry after ${INTERVAL}s" >&2
    rm -f "${tmp}"
  fi
  # Prune: keep newest KEEP files, delete the rest.
  ls -1t "${DEST}"/chronos-*.dump 2>/dev/null \
    | tail -n +"$((KEEP + 1))" \
    | xargs -r rm -f --
  sleep "${INTERVAL}"
done
