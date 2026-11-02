# RCA-002 — Incident Ingestion Scope Clarification

**Document version:** 0.1-draft
**Status:** Team 4 working-scope clarification
**Module:** RCA-002 — Incident Ingestion
**Date:** 2026-11-02

## 1. Purpose

This document clarifies the intended Team 4 development scope for RCA-002 — Incident Ingestion.

It records the decision to include observation ingestion using local fixtures and mock connector ports, in addition to manual and local fixture incident intake.

This is a Team 4 scope clarification. It does not represent approval of unresolved CT-04 decisions or acceptance by other teams.

## 2. Scope

RCA-002 will cover the following:

1. Manual incident intake.
2. Local fixture-based incident intake.
3. Observation ingestion using synthetic/local fixtures.
4. Observation contract definitions and validation.
5. Stage 1 and Stage 2 observation-processing semantics.
6. Payload normalization and fingerprinting through an injected hashing function.
7. In-memory receipt, reservation, attempt, and idempotency behavior.
8. Mock service resolution and severity mapping.
9. Integration with RCA-001 for Incident creation.
10. Integration with RCA-004 for event Evidence creation, subject to the required service capabilities and contracts becoming available.

## 3. Connector Boundary

RCA-002 may use mock connector contexts and injected ports to exercise observation-ingestion behavior.

The following are explicitly out of scope:

- Live external provider integrations.
- Real connector registration and authentication.
- Provider-specific polling, webhooks, or synchronization.
- Production connector infrastructure.
- Claims of real external-source authorization.

Team 5 retains ownership of connector infrastructure and real provider integrations.

## 4. Module Responsibilities

| Component | Responsibility |
|---|---|
| RCA-001 | Canonical Incident records and lifecycle operations |
| RCA-002 | Incident intake and observation-ingestion orchestration |
| RCA-004 | Evidence records and Evidence collection semantics |
| Team 1 | Organization, identity, authentication, and RBAC |
| Team 5 | Connector infrastructure and real provider integrations |

RCA-002 must use the appropriate RCA-001 and RCA-004 service interfaces rather than bypassing their domain validation through direct repository writes.

## 5. Implementation Constraints

Initial development will remain transport-free and mock-based.

- Use in-memory implementations where required.
- Inject clocks, ID factories, hashing functions, and external dependencies.
- Do not introduce database migrations or production persistence.
- Do not introduce HTTP/API routes as part of the initial milestones.
- Do not claim database transactions, durable receipts, or concurrent uniqueness guarantees.
- Keep mock implementations clearly distinguishable from production integrations.
- Preserve the existing IncidentIntake contract unless a separately reviewed change is required.

## 6. Milestones

| Milestone | Scope |
|---|---|
| M0 | Record this scope clarification |
| M1 | Observation contracts and Stage 1 validation |
| M2 | Payload normalization and fingerprinting |
| M3 | In-memory observation store and idempotency |
| M4 | Stage 2 validation, mock service resolution, and severity mapping |
| M5 | Completion workflow integrating RCA-001 and RCA-004 |
| M6 | Controlled reprocessing after relevant decisions are clarified |

Each milestone must be reviewed against its applicable requirements and unresolved dependencies before proceeding.

## 7. Dependencies and Open Decisions

The following existing CT-04 statuses remain unchanged:

- D-02 — Needs Team 1 Input.
- D-03 — Needs Coordinator Confirmation.
- D-08, D-14, D-21, D-23, D-24 — Needs Team 5 Confirmation.
- D-18, D-20, D-22, D-25 — Open.

Other Proposed decisions remain Proposed.

This document does not approve, resolve, or reclassify any CT-04 decision.

M5 remains dependent on the required RCA-001 audit-intent capability, the RCA-004 observation Evidence service path, and an agreed interim completion-commit position.

## 8. Explicit Non-Goals

This scope clarification does not authorize:

- Live external connector implementation.
- Production database or schema changes.
- Changes to Team 1 identity or authorization ownership.
- Changes to Team 2 project or task ownership.
- Bypassing RCA-001 or RCA-004 domain services.
- Treating mock behavior as production guarantees.
- Marking unresolved CT-04 decisions as agreed.

## 9. Change Control

Any change to this scope must be documented and reviewed by Team 4.

Cross-team dependencies and CT-04 decision statuses must continue to be tracked through their existing ownership and review process.
