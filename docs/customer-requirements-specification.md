# Chronos — Customer Requirements Specification (CRS)

Version: 1.3  
Date: 2026-04-21  

## 1. Goal Definition

### 1.1 Initial Situation

The adopting organization currently uses an Excel spreadsheet for shift and leave planning, which can only be edited by one person at a time. Leave requests are submitted on paper and must be manually approved by a delegate and then by HR. This results in:

- Long processing times
- Lack of transparency
- Planning errors and double bookings
- High manual administrative effort
- No central data repository

### 1.2 Objectives

Chronos is a digital, web-based tool that:

- Automates shift, leave, and sickness planning
- Digitalizes approval workflows
- Considers employee preferences and operational requirements
- Increases transparency and efficiency
- Enables future potential for AI-based automatic optimizations
- Runs fully on Linux and is open source

## 2. Product Use

### 2.1 Application Domain

Chronos will be used as an internal company tool at the adopting organization. It is released as open source so other companies can adopt it on the same terms.

Target groups:

- Employees (request submission and personal overview)
- Team leads / department heads (planning and approvals)
- HR (analytics, administration, governance)
- System administrators (maintenance, deployment, monitoring)

### 2.2 Operating Conditions

- Runs on Linux servers
- Used via web browser (desktop and mobile)
- Access via internal corporate network, VPN or a secure reverse proxy
- Deployed in Docker containers (optional orchestration via Kubernetes)

## 3. Product Overview

Chronos is a browser-based, modular planning system covering the following areas:

- Shift planning — automatic creation of early and late shifts considering employee preferences, projects, customer service hours, school schedules, and public holidays.
- Leave management — digital leave requests with automatic delegate suggestion and approval workflow.
- Sickness & absence management — recording employee sickness periods (including short-term/spontaneous sickness), managing required documentation, and ensuring suitable substitutes are assigned.
- Notification system — automatic email or push notifications on status changes.
- Reporting — statistics and analytics for shift times, leave, utilization.
- Integrations — API integration with existing systems (e.g., time tracking).
- Security and access control — role-based access control (RBAC).

## 4. Product Functions (What the system shall do)

| No. | Area                | Description |
|-----|---------------------|-------------|
| F1  | User management     | Manage user accounts, roles, and permissions. |
| F2  | Leave management    | Digital submission, approval, and management of leave. |
| F3  | Delegate search     | Automatic suggestions for potential substitutes. |
| F4  | Approval workflow   | Multi-stage process (Employee → Delegate → Team Lead → HR). |
| F5  | Shift planning      | Automatic assignment of early/late shifts based on defined rules. |
| F6  | Preferences         | Employees can specify individual shift preferences. |
| F7  | External factors    | Consider school schedules, holidays, projects, customer service. |
| F8  | Notifications       | Email or push notifications on changes. |
| F9  | Reporting           | Clear views of leave, shifts, and absences. |
| F10 | Interfaces/API      | REST/GraphQL APIs for external systems. |
| F11 | Calendar integration| Export and sync via ICS/CalDAV. |
| F12 | Roles & permissions | Role-based access restrictions. |
| F13 | Sickness recording  | Record sickness periods for employees, including short-term/spontaneous sickness, with basic documentation (e.g., start/end dates, certificate presence). |
| F14 | Sickness substitution | Automatically identify and assign substitutes for shifts affected by sickness, considering skills, availability, and workload. |
| F15 | Sickness reporting  | Provide overviews of sickness days per employee/team and time period (e.g., month, year) for HR and management. |

## 5. User Interface Requirements

- Design: Modern web interface, responsive for desktop and mobile
- Usability: Intuitive operation, clear role-specific views (Employee, Team Lead, HR)
- Accessibility: Basic WCAG conformance (colors, contrast, keyboard navigation)
- Localization: Primarily English, German version prepared

## 6. Non-functional Requirements

- Operating system: Linux (server), browser-based (client)
- Open source: Released under AGPLv3
- Architecture: Microservice architecture using Docker containers
- Scalability: Horizontal scaling via containerization
- Security: TLS encryption, OAuth2/SSO support
- Backup: scheduled automated database backups
- Monitoring: Integration with Zabbix
- Maintainability: Logical separation of backend, frontend, and database
- Testability: Automated tests and a CI/CD pipeline

## 7. Data Requirements

- Relational database (PostgreSQL preferred)
- Data models: employees, teams, departments, shifts, leave, sickness/absences, delegates, projects
- Data integrity via constraints and validations
- Export functions (CSV, Excel, PDF)

## 8. Interface Requirements

- REST/GraphQL API for the frontend and external applications
- SSO integration with existing user directory
- SMTP for email notifications
- ICS/CalDAV (optional) for calendar integration
- Webhooks for external triggers and automations

## 9. Quality Requirements

- Reliability: No data loss on network failures
- Usability: Low learning curve, simple navigation
- Security: DSGVO/GDPR-compliant storage of personal data
- Portability: Runs on Linux systems, container-based
- Maintainability: Modular structure, easy updates via Docker or Podman
- Standards: Implementation and documentation shall follow relevant ISO
  standards (e.g., ISO/IEC 27001 for information security, ISO 8601 for date and time formats).

## 10. Acceptance Criteria

The project is considered successfully delivered when:

- Shift and leave planning is fully digital and automated.
- All user roles (Employee, Team Lead, HR, Admin) are usable.
- Leave requests can be submitted and approved digitally.
- Employee sickness (including short-term/spontaneous sickness) can be recorded, documented on a period basis, and reflected in planning and reporting.
- Early/late shifts can be scheduled automatically.
- Preferences and external factors (projects, holidays, school schedules) are considered.
- The system runs stably on Linux in a Docker-based deployment.
- Security and data protection requirements are met.

## 11. Deliverables

- Source code (backend, frontend, database migrations)
- Docker Compose or Helm configuration
- Documentation (installation guide, API documentation, user manual)
- Sample dataset (test environment)
- CI/CD pipeline definition
