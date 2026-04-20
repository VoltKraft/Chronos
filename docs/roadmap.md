# Chronos Roadmap — Hardening & Phase 2 Plan

> Audience: autonomous agent teams picking up independent work items.
> Status as of 2026-04-20. Drops OIDC to the final wave per project direction
> (external IdP only — no internal OIDC provider).

## Working rules for all waves

- **Branch per item:** `feat/<id>-<slug>` off `WIP`. One PR per item unless an item
  explicitly says "bundle with X".
- **Definition of done:** acceptance criteria met + pytest green (+ new tests)
  + `python -m app.cli dump-openapi` re-run and committed if routes/shapes change
  + CI green (build + pytest + openapi drift + image builds).
- **Security review:** any item in Wave A or any auth/audit change requires the
  `security-review` skill before merge.
- **Do not introduce:** token-based auth, an internal OIDC provider, or new
  external auth primitives before Wave D. Keep Starlette session cookie as the
  local session.
- **Audit invariant:** every state-changing endpoint calls
  `app.services.audit.append` inside the same transaction. No raw INSERTs.
- **Concurrency:** items with the same `[area: ...]` tag touch overlapping
  code — coordinate via the agent-team lead. Items in different areas are
  independent and can run in parallel.

Item IDs are stable (`H-01`, `F-02`, `O-03`, `D-01`, …); reference them in
commits (`feat(H-01): …`).

---

## Wave A — Security hardening (P0, ship first)

No Wave-B item may merge until Wave A is complete. These are all small, surgical
fixes on top of `WIP`.

### H-01 — Lock `/api/workflows` to HR/admin [area: api/routers]
**Why:** any logged-in employee can create/update/delete approval workflows
today. Frontend hides the page; API does not enforce.
**Files:** `services/api/app/routers/workflows.py` (lines 57, 84, 89, 109).
**Do:** swap `Depends(current_user)` for `Depends(require_hr_or_admin())` on
POST/PUT/DELETE; leave GET on `current_user`.
**Also:** call `audit.append(event_type="workflow.{created,updated,deleted}", ...)`
inside each mutating handler *before* commit.
**Accept:** new pytest cases in `tests/test_permissions.py` prove a `tl` role
gets 403 on POST/PUT/DELETE `/api/workflows`; an `admin` gets 200; audit row
exists after mutation.

### H-02 — Login rate-limit + lockout [area: api/auth]
**Why:** brute-force is possible; no limit anywhere.
**Files:** `services/api/app/routers/auth.py`, `services/api/app/models/user.py`,
`services/api/app/services/auth_rate_limit.py` (new), new Alembic migration.
**Do:** add `failed_login_count INT NOT NULL DEFAULT 0` and
`locked_until TIMESTAMPTZ` columns on `users`. On failed login increment;
after N (env `AUTH_MAX_FAILED_ATTEMPTS`, default 5) set
`locked_until = now() + AUTH_LOCKOUT_SECONDS` (default 900). Reject with
generic 401 while locked. Reset counter on success. Add a **per-IP**
SlowAPI limiter (`10/minute`) as a secondary defence, wired as a FastAPI
dependency only on `/auth/login`.
**Accept:** pytest covers: counter increments, lockout triggers at N, generic
401 message doesn't leak lock state, counter resets on success. Timing-side-
channel safe (constant-time compare already in `security.verify_password`).

### H-03 — Regenerate session on login, add idle timeout [area: api/auth]
**Why:** session fixation risk (`routers/auth.py:44` writes into existing
session dict without rotating).
**Do:** on successful login: `request.session.clear()`, generate a new
`sid` (uuid4 hex), set `request.session["sid"] = sid`, then `uid`, `role`.
Add a middleware or pre-handler that checks `last_seen_at` in the session;
if now - last_seen > `SESSION_IDLE_SECONDS` (default 1800), clear & 401.
Update `last_seen_at` on every authenticated request.
**Files:** `services/api/app/main.py`, `services/api/app/deps.py`,
`services/api/app/routers/auth.py`, `services/api/app/config.py`.
**Accept:** pytest: two sequential logins produce different `sid`; idle past
threshold returns 401; active session keeps rolling.

### H-04 — Password policy + force-rotate default creds [area: api]
**Why:** only `min_length=8`; demo seed hard-codes weak passwords.
**Do:** add `app/services/password_policy.py` enforcing:
- length ≥ 12
- at least 3 of 4: lower, upper, digit, symbol
- rejects top-1k breached list (bundle `pwnedpasswords-top1k.txt` into image)

Apply in: `routers/users.py` (create/update/reset-password), `cli.create-admin`,
`cli.seed-demo`. On `create-admin` and `seed-demo`, set
`users.must_change_password = TRUE` (new bool column) and enforce this in a
new `/auth/force-change-password` endpoint that the frontend routes to on
first login.
**Accept:** unit tests for each rule; demo seed produces users with
`must_change_password=TRUE`; login still succeeds but `/auth/me` carries the
flag and the SPA redirects to the change-password page.

### H-05 — Cross-team leak in `/shifts/{id}/substitutes` [area: api/routers]
**Why:** permission predicate uses OR where it should use AND; any TL can
peek across teams.
**Files:** `services/api/app/routers/shifts.py` (around line 280).
**Do:** replace `not a and not b` logic with correct scope check: TL sees
only their own team; HR/admin see all.
**Accept:** pytest: tl_a vs assignment in team_b gets 403; tl_a vs team_a gets
200; hr across teams gets 200.

### H-06 — Prod TLS + Host guards on Traefik [area: infra]
**Why:** `traefik/dynamic.prod/services.yaml` has `tls: {}` with no cert
resolver; no `Host(...)` on the catch-all — arbitrary Host headers accepted.
**Files:** `infrastructure/docker/traefik/traefik.yaml`,
`infrastructure/docker/traefik/dynamic.prod/services.yaml`,
`infrastructure/docker/compose.prod.yaml`, `.env.prod.example` (new).
**Do:** add ACME certificate resolver (HTTP-01 by default) with staging + prod
endpoints behind an env flag; require `Host(\`${CHRONOS_HOST}\`)` on both
routers; bind dashboard to loopback only via an `entrypoints.web_internal`
interface (or drop dashboard entirely in prod).
**Accept:** `curl -H 'Host: evil.example' https://…` returns 404; cert issues
successfully against Let's Encrypt staging in a rehearsal.

### H-07 — Audit coverage for config mutations [area: api/services]
**Why:** FS §7.1 requires all configuration changes in the audit chain.
Currently Preferences, Delegates, and role changes are covered; Workflows
(fixed in H-01), and some org mutations (department/team create, user import)
are not.
**Do:** inventory all `POST/PUT/PATCH/DELETE` handlers; each must call
`audit.append` with an event_type convention `<entity>.<verb>` (e.g.
`department.created`). Add a pytest that spiders `app.main.app.routes` and
diffs against an allow-list of audit-exempt endpoints.
**Accept:** test fails when an audited endpoint is added without an
`audit.append` call; baseline coverage doc in `docs/audit-events.md`
(auto-generated).

### H-08 — Replace `datetime.utcnow()` everywhere [area: api]
**Why:** deprecated in 3.12, timezone-naïve, risks wrong audit timestamps.
**Files:** `routers/exports.py:66`, `routers/workflows.py:116`, any others
found via grep.
**Do:** use `datetime.now(timezone.utc)`.
**Accept:** `grep -rn 'datetime\.utcnow'` in `services/` returns nothing; CI
adds a ruff rule `DTZ003` to prevent regression.

### H-09 — SESSION_SECRET entropy check + prod guard [area: api/config]
**Why:** nothing stops a prod deployment with a dev default secret.
**Do:** in `app/config.py`, on `ENV != "dev"` reject `SESSION_SECRET` if
length < 48 or Shannon entropy < 4.0; abort startup with clear error.
**Accept:** unit test verifies rejection; `.env.prod.example` carries a
comment showing how to generate a value (`python -c "import secrets;
print(secrets.token_urlsafe(48))"`).

### H-10 — CSRF tokens on unsafe methods [area: api]
**Why:** same-site=Lax is not enough long-term; preview of future cross-site
embedding.
**Do:** double-submit pattern: on login issue a random `XSRF-TOKEN` cookie
(not HttpOnly); require header `X-CSRF-Token` match on POST/PUT/PATCH/DELETE;
frontend `api/client.ts` reads the cookie and echoes the header. Exempt
`/auth/login` and `/healthz`/`/readyz`.
**Accept:** pytest: POST without header gets 403; POST with mismatched
header gets 403; correct pair passes.

---

## Wave B — FS feature completeness (P1)

Start only after Wave A merges. Items are mostly independent; parallelise.

### F-01 — GDPR erase endpoint [area: api/services/gdpr]
**Why:** FS §7.1 promises `POST /api/v1/users/{id}/erase`; only soft-delete
exists today (`routers/users.py:191`).
**Do:** add `services/api/app/services/gdpr.py` with `erase_user(user_id)`:
- hard-delete `password_hash`, `preferences`, `notification_subscriptions`
- overwrite `first_name`, `last_name`, `email` with a stable pseudonym
  (`erased-<short-hash>@chronos.invalid`)
- keep audit rows intact (FS forbids tampering with chain) but replace PII in
  `actor_user_id` references only in the `audit_events.payload` JSON — keep
  the FK
- append a `user.erased` audit event
- return a deletion ledger receipt (id, timestamp, hash)

Admin-only. **Irreversible.** Two-step confirmation (header
`X-Confirm-Irreversible: true`).
**Accept:** pytest covers successful erase, re-login prohibited, audit row
preserved with receipt, re-erase is idempotent. Receipt format documented
in `docs/gdpr.md` (new).

### F-02 — Async export with signed URL [area: api/services/export]
**Why:** `exports.py` returns a synchronous JSON blob — fine for small, not
for large org-wide exports FS §7.1 anticipates.
**Do:** add `exports.job` model + migration; add `POST /api/exports/users/{id}`
(202 + job id); worker job materialises a JSON bundle to
`/var/chronos/exports/<uuid>.json.gz`; `GET /api/exports/{job_id}` returns a
signed URL (HMAC-SHA256, TTL 3600s, single-use token).
**Accept:** pytest + worker integration test; signed URL rejects after TTL;
reused token returns 410.

### F-03 — School schedules & customer service hours [area: api/models]
**Why:** F7 nominally covered but there's no data model for non-holiday
planning factors.
**Do:** add `PlanningCalendar` and `BusinessHours` models + CRUD endpoints;
`services.shift.plan_period` consumes them; preferences page exposes school
terms per user (opt-in).
**Accept:** integration test — a week with school holidays + reduced business
hours produces a coverage report that matches a fixture.

### F-04 — CalDAV publication [area: api]
**Why:** F11 promised ICS + CalDAV; only ICS is delivered.
**Do:** expose a read-only CalDAV endpoint at `/caldav/…` using a minimal
implementation on top of the existing ICS generator; Basic Auth scoped to a
per-user CalDAV token (stored hashed).
**Accept:** `curl` with `PROPFIND` returns a valid multistatus; common Mac
Calendar / Thunderbird subscription flows work in a manual smoke.

### F-05 — Consent capture [area: api]
**Why:** FS §7.1 requires consent records (privacy policy version, timestamp,
withdrawal).
**Do:** `Consent` model with `policy_version`, `granted_at`,
`withdrawn_at`; force-prompt on login when `policy_version < CURRENT`; endpoint
to withdraw; audit events `consent.{granted,withdrawn}`.
**Accept:** pytest + SPA test; admin dashboard surfaces aggregate
grant/withdraw counts.

### F-06 — Notifications channels & subscriptions [area: api+worker]
**Why:** F8/CRS §8 promised push/webhooks; only SMTP exists.
**Do:** add `NotificationChannel` enum (`email`, `webhook`) and
`NotificationSubscription` model; worker dispatches per-subscription; webhook
payloads signed with HMAC (`Chronos-Signature: t=…,v1=…`).
**Accept:** integration test: leave approval fires one email and one webhook
to a test receiver; signature verifies; failed webhook retries with
exponential backoff.

---

## Wave C — Ops & quality (P2)

Can run in parallel with Wave B. No hard dependency on B, but H-06 must be in
before C-01's TLS smoke.

### O-01 — Prometheus `/metrics` + structured logs [area: api+worker]
**Why:** FS §2 names Prometheus/Grafana/Zabbix; nothing ships.
**Do:** add `prometheus-fastapi-instrumentator` to API, worker exports a
simple text endpoint on `:9100`. Switch `logging.basicConfig` to `structlog`
with JSON output. Traefik scrape config in `compose.dev.yaml`.
**Accept:** `/metrics` returns counters; Grafana dashboard JSON checked into
`infrastructure/grafana/`.

### O-02 — pg_dump sidecar + restore runbook [area: infra]
**Why:** FS §8 requires daily backups + RPO/RTO story. None exists.
**Do:** add `backup` service to `compose.prod.yaml` running `pg_dump` into a
mounted `/backups/` volume with timestamped files; daily cron via
`tini`/`supercronic`. Retention 30 days. Document restore steps in
`docs/backup-restore.md` and verify by a rehearsal on a throwaway env.
**Accept:** a backup file appears after the configured schedule; documented
`pg_restore` call reproduces data into an empty DB.

### O-03 — Integration test harness [area: tests]
**Why:** only pure-logic tests exist; auth, audit, router flows unverified.
**Do:** add `tests/integration/` that spins up a throwaway Postgres via
`pytest-docker` (or testcontainers), runs Alembic, exercises representative
flows (login → create leave → approve → check audit → export). Keep pure-logic
tests in `tests/unit/`.
**Accept:** `pytest tests/integration -q` green in CI; runtime under 90s;
adds a GitHub Actions matrix row.

### O-04 — Frontend tests [area: frontend]
**Why:** no `*.test.tsx` exists.
**Do:** adopt Vitest + React Testing Library; cover `AuthProvider`, a role
guard, one workflow editor save round-trip, and the leave inbox approve
button. No visual snapshots — behavioural only.
**Accept:** `npm test` green; CI step added.

### O-05 — CI: lint, typecheck, audit, secret scan [area: ci]
**Why:** current CI only runs pytest + build. A missed `ruff` or leaked
secret will ship.
**Do:** add ruff + mypy (non-blocking at first, blocking after baseline),
`pip-audit`, `npm audit --audit-level=high`, `gitleaks`, and a weekly
dependency-review job.
**Accept:** CI workflow shows new jobs; baseline report checked in.

### O-06 — Docs drift fix + per-endpoint matrix [area: docs]
**Why:** `docs/architecture.md` "Implementation Status" table is stale (lists
only workflows/auth/health). Mislead agents and reviewers.
**Do:** regenerate the table from `app.main.app.routes` via a new
`python -m app.cli dump-route-matrix --output docs/api-endpoints.md`;
reference it from `docs/architecture.md`; CI fails on drift.
**Accept:** committed matrix reflects the 14 routers; CI drift check in
place.

### O-07 — Worker healthcheck + graceful shutdown [area: worker]
**Why:** no HEALTHCHECK; SIGTERM handling unclear.
**Do:** expose a `:9101/healthz` from the worker (200 iff last poll succeeded
in last 2×interval); add `HEALTHCHECK` to `services/worker/Dockerfile`;
trap SIGTERM to finish current job then exit.
**Accept:** `docker compose ps` shows healthy/unhealthy transitions; `kill
-TERM` on the worker returns within 1s.

### O-08 — i18n (de-DE first) [area: frontend]
**Why:** CRS §5 promised German; UI is English only.
**Do:** wire `react-i18next` with `en` and `de` resource bundles; cover all
visible strings; language inferred from `users.locale` (server-provided);
fallback `en`. Document string-freeze process.
**Accept:** `/login?lang=de` shows German; switching in profile persists.

### O-09 — Accessibility baseline [area: frontend]
**Why:** no WCAG work visible.
**Do:** axe-core run in CI via Playwright (smoke on login, dashboard, leave
inbox); fix top-10 violations (contrast, form labels, focus order, skip-link).
**Accept:** CI axe run reports zero criticals on the three pages.

---

## Wave D — External OIDC (deferred to final)

Only begin after A/B/C are solid and internal users have been used in prod
for a real cycle. **Chronos becomes a Relying Party to an external IdP
(e.g. Keycloak, Auth0, Entra ID). No internal IdP code.**

### D-01 — OIDC RP with Authorization Code + PKCE [area: api]
**Why:** federate identity without replacing the local session.
**Do:**
- add env vars `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`,
  `OIDC_REDIRECT_URI`; feature-flag behind `OIDC_ENABLED=true`
- `GET /auth/oidc/start` → redirect to IdP with PKCE challenge and signed
  `state`
- `GET /auth/oidc/callback` → exchange code (using PKCE verifier), validate
  `iss`, `aud`, `exp`, `nonce`; map `sub` or `email` to local `users` row
  (create on first login behind admin-approved allowlist), then
  `request.session["uid"] = user.id` — **same session cookie as password
  login**
- keep `/auth/login` (password) working in parallel; make it toggleable per
  user (`users.auth_provider` enum: `local`, `oidc`)
**Accept:** integration test against `mock-oidc-provider`; password login
still works; manual smoke against Keycloak; `/auth/me` response identical
shape either way.

### D-02 — Per-user provider enforcement [area: api]
**Why:** prevent a local password from being set for an OIDC-bound user.
**Do:** `users.auth_provider` default `local`; admin UI toggles to `oidc`;
setting `oidc` clears + locks the password field; setting `local` forces a
password reset. No dual-mode per user.
**Accept:** pytest covers transitions; audit events for both directions.

### D-03 — Token storage policy [area: api]
**Why:** avoid leaking IdP access tokens.
**Do:** do not persist IdP access/refresh tokens unless a downstream API
calls them. If ever needed, encrypt at rest with `SESSION_SECRET`-derived
KEK via `cryptography.Fernet`; never log.
**Accept:** security-review pass; key rotation runbook in
`docs/oidc.md` (new).

---

## Appendix — effort & ownership heuristics

| Tag         | Size | Rough complexity               |
|-------------|------|--------------------------------|
| S           | <1d  | one file + tests               |
| M           | 1–3d | multi-file + migration + tests |
| L           | 3–7d | cross-cutting + docs + infra   |

Suggested agent-team split:

- **Team Argon (security):** H-01, H-02, H-03, H-04, H-05, H-09, H-10
- **Team Ingress (infra):** H-06, O-02, O-07
- **Team Ledger (audit/GDPR):** H-07, H-08, F-01, F-05
- **Team Signal (ops):** O-01, O-03, O-04, O-05, O-06
- **Team Canvas (frontend):** O-08, O-09 + any UI touches from F-* items
- **Team Atlas (FS completeness):** F-02, F-03, F-04, F-06
- **Team Federate (deferred):** D-01, D-02, D-03 — kicks off only after A-C

Items within a team are serial by default unless they name different files;
items across teams are concurrent.
