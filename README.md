### Chronos  
### Intelligent Shift & Vacation Planning System

[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](./LICENSE)
[![CLA Required](https://img.shields.io/badge/CLA-Required-orange.svg)](./CLA.md)
![Status: In Development](https://img.shields.io/badge/Status-In%20Development-yellow)
![Platform: Linux-first](https://img.shields.io/badge/Platform-Linux--first-lightgrey)

---

## 🧭 Overview

**Chronos** is a modern, web-based planning and scheduling  
system designed as a replacement for:

- manual Excel-based duty planning  
- paper-based vacation & approval processes  
- non-transparent scheduling procedures  

Chronos provides:

- ✔ Digital approval workflows  
- ✔ Transparent, auditable planning  
- ✔ Fair, constraint-aware scheduling  
- ✔ A Linux-first, open source-friendly architecture  
- ✔ Modular frontend & backend components  
- ✔ A foundation for future automation and optimization  

---

## 📚 Documentation

Project documentation is kept in the `docs/` directory:

- **Customer Requirements Specification**  
  `docs/customer-requirements-specification.md`

- **Functional Specification**  
  `docs/functional-specification.md`  
  Key sections: [Interfaces & OpenAPI](docs/functional-specification.md#6-interfaces) · [Deployment & 12-Factor](docs/functional-specification.md#8-deployment--operations)

- **Architecture (Phase 1)**  
  `docs/architecture.md`

- **Authentication (Phase 1)**  
  `docs/authentication.md`

More design and architecture documents will follow as the project grows.

---

## 🏗 Architecture Overview (Phase 1)

Phase 1 runs as a small set of containers: reverse-proxy, frontend, middleware/api, scheduler/worker, and Postgres. The API is OpenAPI-first and authentication uses session cookies (internal users only).

```mermaid
flowchart LR
  Client -->|HTTPS /api/*| RP
  RP -->|HTTP| FE -->|HTTP /api/*| API
  RP -->|HTTP /api/*| API -->|SQL| DB
  API -.->|job trigger| Worker -->|SQL| DB
```

See `docs/architecture.md` and `docs/authentication.md` for details.

---

## 🔧 Development Setup

Phase 1 runs as a single `docker compose` stack. Dev defaults are committed in `infrastructure/docker/.env.dev`; production secrets live in `infrastructure/docker/.env.prod` which is **gitignored**.

```bash
git clone https://github.com/VoltKraft/Chronos.git
cd Chronos/infrastructure/docker

# Build + start all five services (Traefik, frontend, api, worker, db)
./up.sh up --build

# Seed a realistic demo dataset (includes an admin with password `admin-pass-1`)
docker compose -f compose.dev.yaml --env-file .env.dev exec api \
  python -m app.cli seed-demo

# Or create a single admin manually (prompted for password)
docker compose -f compose.dev.yaml --env-file .env.dev exec api \
  python -m app.cli create-admin --email admin@chronos.local

# Verify
curl -i http://localhost/healthz
```

Once the stack is up, the SPA is at <http://localhost/>. Traefik routes `/api/*`, `/auth/*`, `/healthz`, `/readyz` to the API; everything else goes to the frontend.

### Useful CLI subcommands

Run them via `docker compose … exec api python -m app.cli <cmd>`:

| Command | Purpose |
| --- | --- |
| `create-admin --email ...` | Bootstrap a superuser. |
| `seed-demo` | Load a full demo org (1 dept, 1 team, 6 users, preferences, draft leave). |
| `set-role --email ... --role hr` | Promote/demote a user. |
| `verify-audit` | Recompute the audit hash chain; non-zero exit on tamper. |
| `dump-openapi --output docs/api/openapi/api/openapi.yaml` | Refresh the committed OpenAPI contract. |
| `dump-route-matrix --format markdown` | Emit a method × path × guard matrix for RBAC audits. |

For the full inventory of containers, images, and endpoints see [`docs/architecture.md`](docs/architecture.md#implementation-status-phase-1).

---

## 👥 Contributing & Contributor License Agreement (CLA)

Contributions are welcome and encouraged!

To maintain long-term legal clarity and ensure the project can evolve,
**all contributors must agree to the project's Contributor License Agreement (CLA)**.

By signing the CLA, you:

- assign copyright of your contributions to the Project Owner  
- allow the project to be relicensed in the future  
- ensure all historical versions remain under **AGPL-3.0-only**

Please see:

- [`CLA.md`](./CLA.md)  
- [`CONTRIBUTING.md`](./CONTRIBUTING.md)

for details on contribution workflow and legal requirements.

---

## 🛡 License

This project is owned by **Jan Paulzen (VoltKraft)**.  
The source code is licensed under the:

**GNU Affero General Public License v3.0 (AGPL-3.0-only)**

This ensures the project:

- remains free and open source  
- protects user freedoms in networked environments  
- prevents proprietary forks  
- requires public access to source code when deployed as a service  

For full license text, see:  
➡️ [`LICENSE`](./LICENSE)

---

## 🧩 Project Goals (Roadmap Snapshot)

- [x] Full shift planning workflow (rule-based round-robin planner)
- [x] Vacation request workflow
- [x] Approval chains (delegate → team lead → HR)
- [x] Rule-based scheduling engine (preference- & availability-aware)
- [x] Employee preferences & constraints
- [x] Audit logs for all actions (SHA-256 hash chain, verifiable)
- [x] Sickness workflow (F13) + substitution flagging (F14)
- [x] Reporting & CSV/ICS exports (F9, F11, F15)
- [x] GDPR data export (F7 §7.1)
- [x] Role-specific SPA (Employee, Team Lead, HR, Admin)
- [x] Docker-based deployment (5-container compose stack)
- [x] Wave A P0 security hardening — rate-limit + lockout, session
  rotation + idle timeout, Argon2id + password policy + forced rotation,
  cross-team leak fix, CSRF double-submit, UTC timestamps, audit
  coverage spider (see `docs/roadmap.md` for H-01..H-10)
- [x] Prod TLS (ACME) + `Host(...)` guards + security headers on Traefik (H-06)
- [x] pg_dump backup sidecar + restore runbook (O-02) — see
  [`docs/backup-restore.md`](docs/backup-restore.md)
- [x] Integration test harness over a throwaway Postgres (O-03) —
  `pytest tests/integration`; harness uses `testcontainers[postgres]`
  locally and GitHub Actions' `services: postgres:18-alpine` in CI
- [ ] OpenID Connect (OIDC) integration
- [ ] Multi-tenant support
- [ ] Kubernetes-ready architecture
- [ ] MILP-based optimal shift solver

*(Roadmap will move into GitHub Projects later.)*

---

## 💬 Contact & Community

Issues and feature requests are welcome via GitHub Issues.
Pull Requests are accepted once the [`CLA.md`](./CLA.md)  is accepted.


---

## ⭐ Support the Project

If you find Chronos useful, consider leaving a star on GitHub ⭐
It helps visibility and supports continued development.
