# Chronos — Functional Specification (FS)

Status: Phase-1 baseline (Wave A hardened)  
Version: 1.0  
Last Updated: 2026-04-21

## Contents

- 1. Overview
- 2. Architecture Overview
- 3. Requirement-to-Design Mapping
- 4. Detailed Flows
- 5. Data Model
- 6. Interfaces
- 6.1 OpenAPI-First API Contracts
- 7. Quality Attributes and NFRs
  - 7.1 Compliance & Security
- 8. Deployment & Operations
- 8.1 12-Factor Application Style (How we apply it)
- 8.2 Contributor Checklist (12-Factor)
- 9. Open Issues
- 10. Traceability
  - 10.1 Requirements Traceability Matrix

This specification translates the Customer Requirements Specification (CRS) into a solution design suitable for implementation and testing. It provides architecture, components, data models, interfaces, security, quality attributes, and requirement-to-design traceability.

## 1. Overview

- Problem statement: Manual, opaque, error-prone Excel-based planning and paper-based approvals.
- Solution approach: Web-based, modular planning system with automated scheduling, digital approvals, and integrations; Linux-first, open source (AGPLv3).
- Scope confirmation: Aligns with CRS sections 3–8; defers non-goals to CRS if any.

## 2. Architecture Overview

- Runtime: Linux servers; containerized services (Docker); optional orchestration (Kubernetes).
- Style: Service-oriented (microservices where justified) with clear module boundaries.
- Logical components:
  - Web frontend: browser-based UI served via an nginx web server; communicates exclusively with the middleware/API layer.
  - Middleware / API layer: single logical entry point for the frontend; orchestrates business logic and coordinates calls to backend services, PostgreSQL, and the planner/scheduler.
  - Backend services: domain-focused services implementing identity, leave management, scheduling, notifications, reporting, etc.
  - Planner / scheduler: specialized component for automated planning, constraint solving, and background jobs, invoked via the middleware/API layer.
- Core services (initial cut, refined):
  - Identity & Access (RBAC, OAuth2/SSO integration)
  - User & Org (users, teams, departments)
  - Leave Service (requests, approvals, delegation)
  - Scheduling Engine (shift rules, preferences, constraints)
  - Notifications (SMTP, push/webhook dispatch)
  - Reporting & Analytics (read models, exports)
  - Middleware/API Gateway/Edge (REST/GraphQL, rate limits, versioning; bridges frontend, backend services, database, and planner)
- Data: PostgreSQL 18 as primary relational store; schema per service; migrations versioned.
- Deployment & network topology:
  - Docker-based deployment with separate internal networks for `backend` and `frontend`.
  - `db` service runs PostgreSQL 18 on the `backend` network; configuration and credentials are provided via environment files (`infrastructure/docker/.env.dev` for local development, `infrastructure/docker/.env.prod` for production; the prod file is gitignored and holds real secrets).
  - `frontend` service hosts the nginx-based web application on the `frontend` network. The nginx web server is not exposed directly to the host and has no published ports; it can only be reached from within the Docker network.
  - A dedicated middleware/API component connects the `frontend` container with backend services and the PostgreSQL database on the `backend` network and provides access to the planner/scheduler.
  - An external reverse proxy (to be selected, e.g., Traefik, nginx, Caddy, or HAProxy) terminates TLS and forwards incoming HTTP(S) traffic from the public network to the internal nginx web server in the `frontend` container; it is the only component exposed to the outside world.
- Observability: Prometheus metrics, structured logs, Grafana dashboards; integration points for Zabbix as per monitoring requirements.

## 3. Requirement-to-Design Mapping (excerpt)

- F1 User management → Identity & Access, User & Org services; RBAC model.
- F2 Leave management → Leave Service (CRUD, state machine, SLAs).
- F3 Delegate search → Leave Service + scheduling constraints (availability, skills, workload).
- F4 Approval workflow → Leave Service workflow engine (Employee → Delegate → Team Lead → HR).
- F5 Shift planning → Scheduling Engine (rules, preferences, fairness; pluggable solver for AI/optimization).
- F6 Preferences → User profile + Scheduling Engine inputs.
- F7 External factors → Calendars/holidays, projects, service hours as constraints in Scheduling Engine.
- F8 Notifications → Notifications service (SMTP, optional push/webhooks; templating).
- F9 Reporting → Reporting service (materialized views; CSV/Excel/PDF exports).
- F10 Interfaces/API → API Gateway; REST/GraphQL surface; OpenAPI/SDL definitions.
- F11 Calendar integration → ICS exports; optional CalDAV adapter.
- F12 Roles & permissions → RBAC policies enforced at gateway and service level.
- F13 Sickness recording → Leave Service using `LeaveRequest` with `type = SICK`; supports short-term/spontaneous sickness, capturing at least start/end dates and certificate presence without storing medical details.
- F14 Sickness substitution → Scheduling Engine + Leave Service; sickness events trigger recalculation of affected `ShiftAssignment` records and automatic proposal of suitable substitutes based on availability, skills, and workload.
- F15 Sickness reporting → Reporting & Analytics; aggregates sickness-related `LeaveRequest`/`CalendarEvent` data into per-employee/team views for selected periods (e.g., month, year).

## 4. Detailed Flows (high level)

- Leave request (Employee): create → select dates → auto-delegate proposal → submit → approvals → notify.
- Sickness notification (Employee / Team lead / HR): record sickness (often same-day) with start date (and expected end date if known) → mark affected shifts as unstaffed → trigger automatic substitute search → update plan and notify affected parties.
- Shift plan generation (Planner/Team lead): define horizon → import constraints (holidays, projects) → run solver → review conflicts → publish.
- Approval workflow: stage transitions with SLAs and reminders; override/escalation paths.

## 5. Data Model (initial)

- Key entities: User, Team, Department, Shift, ShiftAssignment, LeaveRequest, Delegate, Project, CalendarEvent, Preference.
- Integrity: relational constraints, validations; audit fields; soft delete where needed.

### 5.1 Entity Catalog (skeleton)

Entity | Key Attributes | Relationships | Notes
--- | --- | --- | ---
User | id (UUID, PK); email (unique, not null); first_name; last_name; locale; time_zone; role; department_id (FK); team_id (FK); created_at; updated_at; deleted_at | 1:N Department → User; 1:N Team → User | Unique: email; FKs: department_id → Department(id) ON SET NULL, team_id → Team(id) ON SET NULL; Index: (department_id), (team_id), (email); Soft-delete via deleted_at
Team | id (UUID, PK); name (unique per department); department_id (FK); created_at; updated_at; deleted_at | 1:N Team → User; N:1 Team → Department | Unique: (department_id, name); FK: department_id → Department(id) ON CASCADE UPDATE/RESTRICT DELETE; Index: (department_id)
Department | id (UUID, PK); name (unique); created_at; updated_at; deleted_at | 1:N Department → Team; 1:N Department → User | Unique: name; Index: (name)
Project | id (UUID, PK); code (unique); name; created_at; updated_at; deleted_at | 1:N Project → Shift | Unique: code; Index: (code)
Shift | id (UUID, PK); service_date (date); shift_type (enum: EARLY,LATE,OTHER); start_time; end_time; team_id (FK); project_id (FK, nullable); created_at; updated_at; deleted_at | N:1 Shift → Team; N:1 Shift → Project; 1:N Shift → ShiftAssignment | Unique: (team_id, service_date, shift_type); FKs: team_id → Team(id) ON CASCADE; project_id → Project(id) ON SET NULL; Index: (service_date), (team_id, service_date)
ShiftAssignment | id (UUID, PK); shift_id (FK); user_id (FK); assigned_at; created_at; updated_at; deleted_at | N:1 ShiftAssignment → Shift; N:1 ShiftAssignment → User | Unique: (shift_id, user_id); FKs: shift_id → Shift(id) ON CASCADE; user_id → User(id) ON RESTRICT; Index: (shift_id), (user_id)
LeaveRequest | id (UUID, PK); requester_id (FK User); approver_delegate_id (FK User, nullable); approver_tl_id (FK User, nullable); approver_hr_id (FK User, nullable); type (enum: VACATION,SICK,OTHER); reason (text, nullable); start_date; end_date; status (state: DRAFT,SUBMITTED,DELEGATE_REVIEW,TL_REVIEW,HR_REVIEW,APPROVED,REJECTED,CANCELLED,OVERRIDDEN); submitted_at; decided_at; created_at; updated_at; deleted_at | N:1 → User (requester/approvers); 1:N LeaveRequest → CalendarEvent (derived) | Constraints: start_date ≤ end_date; no overlap per requester and type when status ∈ {SUBMITTED..APPROVED}; FK actions: requester_id ON RESTRICT; approver_* ON SET NULL; Index: (requester_id), (start_date), (status); Partition: by year on start_date (range); `type = SICK` is used to represent sickness periods (including short-term/spontaneous), which feed substitution logic and sickness reporting; no medical diagnosis is stored.
Delegate | id (UUID, PK); principal_id (FK User); delegate_user_id (FK User); valid_from; valid_to; created_at; updated_at; deleted_at | N:1 → User (principal); N:1 → User (delegate) | Unique: (principal_id, delegate_user_id, valid_from, valid_to); FK actions: ON CASCADE UPDATE/RESTRICT DELETE; Index: (principal_id), (delegate_user_id), (valid_from, valid_to)
CalendarEvent | id (UUID, PK); user_id (FK); event_type (enum: HOLIDAY,LEAVE,SHIFT,OTHER); starts_at; ends_at; source (enum: SYSTEM,EXTERNAL); external_ref (nullable); created_at; updated_at; deleted_at | N:1 → User; Optional link to LeaveRequest or Shift | Index: (user_id), (starts_at), (event_type); Partition: by month on starts_at (range)
Preference | id (UUID, PK); user_id (FK); preference_type (enum: SHIFT_TIME,DAY_OFF,PROJECT); payload (JSONB); effective_from; effective_to; created_at; updated_at; deleted_at | N:1 → User | Unique: (user_id, preference_type, effective_from); Index: (user_id), GIN (payload)

Partitioning & Archival Strategy:

- High-volume tables (LeaveRequest by year on start_date; CalendarEvent by month on starts_at) are partitioned to improve query and retention operations.
- Archival: finalized LeaveRequest and related CalendarEvent older than configurable retention (e.g., 24 months) are moved to archive schema/tables; indexes preserved for export/reporting; PII is minimized or pseudonymized per §7.1.
- Foreign keys from partitions reference parent tables via partition-aware constraints.

## 6. Interfaces

- REST/GraphQL for frontend and integrations; versioned; standard error model.
- LDAP/SSO (OAuth2/OpenID Connect) for authentication; roles mapped to claims.
- SMTP for email; templated messages.
- ICS/CalDAV (optional) for calendar sync; ICS export baseline.
- Webhooks for external triggers and automations.

### 6.1 OpenAPI-First API Contracts

Chronos follows an API-first approach: the OpenAPI specification is the source of truth for HTTP APIs.

- Spec ownership: each service owns and maintains its OpenAPI spec; the middleware/API gateway aggregates or proxies them.
- Spec location (convention): `docs/api/openapi/<service>/openapi.yaml` (one spec per service, versioned with code).
- Viewing: use any OpenAPI viewer (Swagger UI, Redoc) or editor preview to render the spec.
- Validation/linting (optional): run a linter before changes are merged.


Contributor guidance:
- Update the spec first (or alongside) any endpoint change; keep request/response schemas in sync with implementation.
- Changes that break compatibility must bump the API version and be called out in release notes.

## 7. Quality Attributes and NFRs

- Availability: 99% (normal operations); health checks; graceful degradation.
- Reliability: No data loss on transient network failures; transactional operations and retries for critical flows (leave requests, approvals, shift publishing).
- Security: TLS everywhere; least-privilege RBAC; DSGVO/GDPR-compliant storage of personal data; encrypted secrets.
- Usability & accessibility: Responsive web UI with clear role-specific views (Employee, Team Lead, HR, Admin); basic WCAG-aligned colors, contrast, and keyboard navigation.
- Localization: UI texts externalized; default language English; German locale prepared (resource bundles, locale-specific formatting).
- Scalability: horizontal scale via containers; stateless services where possible.
- Testability: unit/integration/E2E tests; CI/CD pipeline; seed data for staging.
- Maintainability: modular codebases; clear service contracts; API versioning.
- Portability: container-based runtime on Linux; no hard dependency on non-Linux hosts.
- Standards & formats: Where feasible, implementation and documentation follow relevant ISO standards (e.g., ISO/IEC 27001 for information security), and APIs/logs use ISO 8601 for dates and times (UTC in transport).

### 7.1 Compliance & Security

1) Immutable Audit Trail (approvals/rejections/overrides/config changes)
- Must record append-only audit events for: leave approvals/rejections, workflow overrides, role/permission changes, configuration changes (e.g., shift rules), and data exports/deletions.
- Each event must capture: actor (user id and role), timestamp (UTC), action type, reason/comment (if provided), target entity and id, and before_state/after_state (JSON snapshots with minimal necessary fields; exclude secrets/PII not needed for audit).
- Storage must be tamper-evident: either WORM storage, cryptographic hash chaining per event, or database-level immutability controls. Events are not updatable or deletable by application code; redaction is handled via separate redaction records linked to the event.
- Access must be RBAC-restricted; search/filter by actor, action, date range; export to CSV/JSON for compliance review.
- Retention must be configurable per organization and data category; defaults: 24 months for operational audit; longer if required by law/policy.
- Acceptance criteria:
  - Triggering each workflow action (approve/reject/override/config change) creates an audit event with all required fields.
  - Attempted update/delete of an audit event is rejected and logged.
  - Hash chain validation detects any tampering in a sample audit log.
  - Authorized roles can query and export filtered audit logs; unauthorized roles are denied.

2) User Data Export
- Must provide user-initiated export of their personal data: identity profile (PII), leave history, preferences, and calendar items derived from their data.
- Export formats: machine-readable JSON (authoritative) and CSV for tabular data; ICS for calendar events. Exports must include schema version and generation timestamp.
- Export delivery: asynchronous job with signed, time-limited download URL; notify user on completion.
- SLA: export must be available within 30 days of request (configurable; typically minutes for standard volumes).
- Acceptance criteria:
  - API `POST /api/v1/users/{id}/export` enqueues an export; `GET /api/v1/users/{id}/export/{job_id}` returns status and download link when ready.
  - Export contains expected records and fields for a test user; checksums included.
  - Access to another user’s export is denied; links expire as configured.

3) User Data Deletion/Termination
- Must support account termination workflow: deactivate user (immediate login block), schedule deletion of personal data after configurable retention (default: 30 days cooling-off, then erase); maintain minimal legally required records.
- Deletion scope: PII in User, Preferences, and personal CalendarEvents. LeaveRequest and ShiftAssignment may be retained in aggregated or pseudonymized form to preserve operational history; direct identifiers must be removed or replaced.
- Referential behavior: FK references to deleted users must be set to NULL or replaced by pseudonymous keys; audit trail remains immutable but may be logically restricted by access policies.
- A deletion ledger must record request time, executor, scope, outcome, and items affected.
- Acceptance criteria:
  - API `POST /api/v1/users/{id}/erase` initiates deletion; status endpoint reports progress/outcome.
  - After deletion, PII fields are removed/pseudonymized; attempts to retrieve profile data return not found or redacted.
  - References in LeaveRequest and ShiftAssignment are NULL/pseudonymous; reporting still functions on aggregates.

4) PII Attributes, Purpose, Minimization, and Consent
- Required PII attributes: first_name, last_name, email, (optional) phone; organizational attributes: department_id, team_id, role. Do not store sensitive categories unless strictly necessary and justified.
- Purpose limitation: collect only attributes necessary for scheduling, approvals, notifications, and access control. No unrelated processing.
- Minimization rules: default to opt-in for optional features (e.g., push notifications, external calendar sharing); avoid free-form PII where structured fields suffice.
- Consent capture: consent statements must be explicit, versioned, and displayed at the point of collection; changes (grant/withdraw) must be logged as audit events with actor, timestamp, policy version, and scope.
- Data protection by design: default privacy settings conservative; configuration for retention, export, and deletion documented and testable.
- Acceptance criteria:
  - Consent change produces an audit event; current consent state is reflected in user profile and enforced by services.
  - Attempting to process data beyond stated purposes is blocked by policy checks (simulated in tests).
  - PII fields are present only where required; redaction appears in logs/exports as specified.

## 8. Deployment & Operations

- Dev: Docker Compose; Prod: Helm (optional); env vars for config; secrets via vault/K8s secrets.
- Backups: daily automated Postgres backups; restore drill documented (RPO/RTO).
- Monitoring: Prometheus metrics and Grafana dashboards; integration with Zabbix (e.g., via exporters/bridges) for central monitoring; structured logs; alerting.

### 8.1 12-Factor Application Style (How we apply it)

Chronos aims to follow 12-factor principles to keep services portable, testable, and operable across environments.

- Configuration is provided via environment variables; local defaults can use `.env` files, but secrets do not live in the repo.
- Services are stateless; state lives in PostgreSQL or external backing services (e.g., SMTP, object storage, queues).
- Backing services are treated as attached resources and are reachable via env-configured URLs/credentials.
- Logs are written to stdout/stderr as structured events for centralized collection and analysis.
- Build/release/run are separated: build immutable container images, release with env-specific config, run the same image in all environments.

### 8.2 Contributor Checklist (12-Factor)

- Use environment variables for all runtime configuration; do not hard-code credentials or endpoints.
- Keep services stateless; persist state in backing services, not local files.
- Emit structured logs to stdout/stderr; avoid file-based logging.
- Treat databases, SMTP, and external APIs as attached resources configured by env vars.
- Ensure builds are reproducible and releases only change configuration, not code.

## 9. Open Issues

- Select optimization approach (rule-based, MILP/CP-SAT, or hybrid) for Scheduling Engine.
- Push notifications mechanism (web push vs. mobile app) — scope decision.
- CalDAV support depth vs. ICS-only for v1.
