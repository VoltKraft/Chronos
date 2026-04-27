# Backup & Restore (Phase 1)

> Audience: operator / on-call engineer running the Chronos prod stack.
> Scope: PostgreSQL logical backups produced by the `backup` sidecar in
> `infrastructure/docker/compose.prod.yaml`. Object storage / volume-level
> snapshots are out of scope.

## 1. What the backup sidecar does

`infrastructure/docker/backup/run.sh` runs inside a `postgres:18-alpine`
container and executes `pg_dump -Fc --no-owner --no-acl` every
`BACKUP_INTERVAL_SECONDS` (default 86400 = daily). Each dump lands in
`/backups/chronos-<UTC timestamp>.dump` inside the `chronos_backups`
volume; after each successful run the sidecar prunes the directory to the
`BACKUP_RETENTION_COUNT` most recent files (default 30).

The dump format (`-Fc`, PostgreSQL custom archive) is:

- already compressed — do **not** gzip the files again;
- restore-only via `pg_restore` — `psql <file.dump` will not work;
- portable across minor versions of PostgreSQL 18 and forward-compatible
  to PostgreSQL 19 (per upstream policy — verify before a cross-major
  restore).

Credentials come from the `PG*` env vars the compose file injects from
`.env.prod` (`PGHOST=db`, `PGUSER=${POSTGRES_USER}`, …). No `.pgpass` file
lives inside the container.

## 2. Verifying backups are happening

```bash
# List the rotated files; the newest should be less than a day old.
docker compose -f compose.prod.yaml --env-file .env.prod exec backup \
  sh -c 'ls -lh /backups | tail -5'

# Tail the sidecar log to see the next "dump ok (<bytes>)" message.
docker compose -f compose.prod.yaml --env-file .env.prod logs --tail=50 -f backup

# A healthy day's log line looks like:
#   2026-04-21T03:00:01Z dumping chronos@db -> /backups/chronos-20260421T030001Z.dump
#   2026-04-21T03:00:07Z dump ok (4213887 bytes)
```

If a dump fails the sidecar logs the error, deletes the half-written file,
and tries again on the next `BACKUP_INTERVAL_SECONDS`. It does not crash —
check the log for repeated `dump FAILED` lines.

## 3. Copying a backup out of the volume

```bash
# Pick the file you want.
FILE=chronos-20260421T030001Z.dump

# Copy it from the named volume to the host.
docker compose -f compose.prod.yaml --env-file .env.prod cp \
  backup:/backups/$FILE ./$FILE

# Move it off-host immediately — the compose volume is not an off-site copy.
```

For a genuine offsite story wire this into `rsync`, `rclone`, or your
object-storage upload of choice from a cron on the docker host. The
sidecar deliberately does not implement remote upload — that belongs to
the host's backup toolchain, not a container that only needs DB
credentials.

## 4. Restore drill — throwaway Postgres (recommended first)

Restore the dump into a disposable PG container and smoke-test the data
before you ever replace the live DB.

```bash
# 1. Pick a dump file you've copied to the host.
FILE=./chronos-20260421T030001Z.dump

# 2. Start a throwaway PG 18 on a high port with no persistent volume.
docker run --rm --name chronos_restore_test \
  -e POSTGRES_PASSWORD=restoretest \
  -e POSTGRES_DB=chronos_restore \
  -e POSTGRES_USER=chronos \
  -p 55432:5432 -d postgres:18-alpine

# 3. Wait for it to be accepting connections.
until docker exec chronos_restore_test pg_isready -U chronos; do sleep 1; done

# 4. Restore into the empty DB. --clean + --if-exists makes it idempotent,
#    --no-owner + --no-acl ignore the source cluster's role names.
docker cp "$FILE" chronos_restore_test:/tmp/dump
docker exec -e PGPASSWORD=restoretest chronos_restore_test \
  pg_restore -U chronos -d chronos_restore \
    --clean --if-exists --no-owner --no-acl /tmp/dump

# 5. Smoke checks — sizes and an audit-chain probe.
docker exec -e PGPASSWORD=restoretest chronos_restore_test \
  psql -U chronos -d chronos_restore -c \
  "SELECT COUNT(*) AS users FROM users;
   SELECT COUNT(*) AS audit_events FROM audit_events;
   SELECT MAX(seq) AS max_audit_seq FROM audit_events;"

# 6. Optional: run verify-audit against the restored DB.
docker run --rm --network host \
  -e DATABASE_URL="postgresql+psycopg://chronos:restoretest@127.0.0.1:55432/chronos_restore" \
  -e SESSION_SECRET="drill-not-prod-secret-drill-not-prod-secret-xxxx" \
  chronos_api:latest_stable python -m app.cli verify-audit

# 7. Tear down.
docker stop chronos_restore_test
```

`verify-audit` returning `"ok": true` proves the SHA-256 hash chain
survived the dump/restore round-trip — the same check `docker compose …
exec api python -m app.cli verify-audit` runs in prod.

## 5. Restore drill — replace the live DB (last resort)

**This destroys the current prod data.** Take a fresh dump *first*, copy
it off-host, and announce the outage. Then:

```bash
cd infrastructure/docker

# 1. Stop everything that writes to the DB.
docker compose -f compose.prod.yaml --env-file .env.prod stop api worker backup

# 2. Drop and recreate the database from inside the db container.
docker compose -f compose.prod.yaml --env-file .env.prod exec db \
  psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS $POSTGRES_DB;"
docker compose -f compose.prod.yaml --env-file .env.prod exec db \
  psql -U "$POSTGRES_USER" -c "CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER;"

# 3. Push the dump into the db container and restore.
FILE=chronos-20260421T030001Z.dump
docker compose -f compose.prod.yaml --env-file .env.prod cp \
  backup:/backups/$FILE /tmp/$FILE
docker compose -f compose.prod.yaml --env-file .env.prod cp \
  /tmp/$FILE db:/tmp/$FILE
docker compose -f compose.prod.yaml --env-file .env.prod exec db \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --clean --if-exists --no-owner --no-acl /tmp/$FILE

# 4. Bring the app back.
docker compose -f compose.prod.yaml --env-file .env.prod start api worker backup

# 5. Verify.
docker compose -f compose.prod.yaml --env-file .env.prod exec api \
  python -m app.cli verify-audit
curl -I https://$PUBLIC_HOST/healthz
```

If `verify-audit` fails after a restore, the chain is broken — treat the
restored DB as evidence of tampering (or an incomplete dump) and escalate
before serving traffic.

## 6. RPO / RTO guidance

- **RPO**: equal to `BACKUP_INTERVAL_SECONDS` (default 24 h). Shorten by
  lowering the interval or adding WAL archiving / a replica — neither is
  configured in Phase 1.
- **RTO**: restore time scales with dump size. A 500-MB custom-format
  archive typically restores in <2 minutes on a warm cluster; the Chronos
  schema fits this profile for a small org. Budget 15 minutes end-to-end
  including the smoke checks in §4.

## 7. What is *not* backed up

- Traefik ACME state (`chronos_traefik_acme`) — Let's Encrypt will
  re-issue on restart.
- The `chronos_traefik_dynamic` volume — regenerated from the template by
  the `traefik-config` init container on every compose up.
- Any on-host state outside the compose volumes. If you host the compose
  stack yourself, rely on your host's filesystem snapshots for this.
