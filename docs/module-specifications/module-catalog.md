# Team 4 module catalog

All modules below belong to Team 4 and run inside one modular monolith. IDs are stable product references; module folders use the listed short names. These are ownership and contract foundations, not completed features.

| Module ID | Module | Priority | Responsibility and initial boundary |
|---|---|---|---|
| RCA-001 | Incident Management | P0 | Own incident records and lifecycle; external IDs remain opaque references. |
| RCA-002 | Incident Ingestion | P0 | Accept manual and local fixture incident intake; no external connectors. |
| RCA-003 | Incident Timeline | P0 | Represent ordered incident events and timeline entries. |
| RCA-004 | Evidence Collection | P0 | Record evidence submissions and source provenance. |
| RCA-005 | Evidence Engine | P0 | Assess, normalize, and summarize evidence for investigation use. |
| RCA-006 | AI RCA Agent | P0 | Produce structured, traceable candidate drafts; never confirm a cause. |
| RCA-007 | Root Cause Candidates | P0 | Store and present candidate explanations with supporting and contradicting evidence. |
| RCA-008 | Fix Agent | P1 | Draft remediation proposals linked to candidates; human review required. |
| RCA-009 | Test Agent | P1 | Draft test plans and cases for proposed fixes. |
| RCA-010 | Validation Workflow | P1 | Track proposal validation outcomes and blockers. |
| RCA-011 | Human Review & Approval | P0 | Record human decisions, rationale, and reviewer references. |
| RCA-012 | RCA History & Audit | P1 | Preserve investigation event history and audit records. |

## Dependency direction

Modules communicate through typed service contracts. The initial foundation has types only; no module imports another module's persistence implementation. Shared code is limited to generic identifiers and utilities. Avoid cyclic dependencies; promote a contract to `api/src/shared` only when it is genuinely cross-module and Team 4-owned.

`ExternalRef` in `api/src/shared/identifiers.ts` is the only external-reference shape. `Team4EntityId` in the same file is the Team 4 record id and is not interchangeable with an external reference. `InvestigationId` is owned by RCA-001 in `api/src/modules/incidents/incidents.types.ts`; evidence, the AI RCA agent, candidates, fix proposals, and audit history import that type. The proposed `rca_investigation` entity is still unconfirmed, so this id is not a table.
