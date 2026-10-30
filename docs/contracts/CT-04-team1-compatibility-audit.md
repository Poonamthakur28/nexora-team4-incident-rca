# CT-04 Team 1 / Team 4 Compatibility Audit

| Item | Value |
|---|---|
| Audit scope | Team 1 identity, organization, authorization, ownership, lifecycle, and integration compatibility with CT-04 |
| Team 1 source | `docs/contracts/team4_incident_management_integration_contract.md`, version 1.0.0 |
| Team 4 source | `docs/contracts/CT-04-incident-evidence-v0.2-draft.md`, version `0.2-draft` |
| Audit status | Documentation assessment only; not an implementation or cross-team approval |
| Date | 2026-10-30 |

## 1. Executive summary

Team 1's supplied contract establishes concrete identity and organization facts that CT-04 v0.2 deliberately leaves open: Team 1's canonical organization, department, team, employee, and user identifiers are immutable RFC 4122 UUIDs; `user_id` is an authentication principal; and `employee_id` is the organization-scoped personnel record. [T1 §1.1, §2.1, §2.2] CT-04 instead currently treats organization identity as an opaque trusted-context value and represents Team 1 references as unvalidated `ExternalRef` objects. [CT-04 §5, §6.1, §11.1, D-01, D-02, D-04]

The contracts are directionally compatible on authority boundaries: Team 1 owns authentication, organization identity, user identity, and RBAC; Team 4 owns incident semantics and lifecycle. [T1 §11; CT-04 §2.1–§2.3] They are not yet wire-compatible. CT-04 has no implemented incident API, no finalized Team 1 UUID rules, no established owner-string registry for `ExternalRef`, no finalized Team 1 request adapter, and no agreed service-to-service authentication model. [CT-04 §4, §5, §13, D-01, D-02, D-04, D-14]

No Team 1 recommendation or proposed SQL in the source document is treated by this audit as an approved Team 4 schema. In particular, Team 1's proposed `incident` and `incident_service` tables are useful compatibility input, not an implementation baseline. [T1 §3.2, §9; CT-04 §1, §3.1, §4]

**Readiness conclusion: not implementation-ready for Team 1-integrated incident APIs.** CT-04 may continue to define Team 4 domain behavior, but Team 1 identifier serialization, tenant validation, principal-to-employee resolution, authorization claims, service authentication, and the reference representation must be agreed before implementation. This conclusion is an **OPEN_DECISION**, not a rejection of either contract. [T1 §5, §8, §12.3; CT-04 §2.3, §11, D-02, D-14, D-21]

### Classification legend

| Classification | Meaning in this audit |
|---|---|
| `COMPATIBLE` | Both documents state compatible behavior without requiring a CT-04 schema or validation change. |
| `SCHEMA_ALIGNMENT_REQUIRED` | The persisted or canonical contract representation needs agreement or change before Team 1 values can be represented safely. |
| `VALIDATION_REQUIRED` | The representation can remain, but Team 1-derived format, activity, organization, or permission validation is required. |
| `INTEGRATION_REQUIRED` | A Team 1 API, token flow, adapter, or cross-service behavior is needed. |
| `OPEN_DECISION` | The source documents leave a material policy, owner, or API behavior unresolved. |

## 2. Team 1 contract facts

The following are confirmed facts stated as such by Team 1's authoritative integration contract. They are not Team 4 implementation decisions.

1. **Canonical identifier types — `COMPATIBLE`.** `organization_id`, `department_id`, `team_id`, `employee_id`, and `user_id` are immutable RFC 4122 UUID primary keys. Mutable business codes, including organization `code` and employee `employee_code`, must not be used as primary foreign keys. [T1 Executive Summary, item 1; §1.1; §2.1]
2. **Principal and personnel are distinct — `COMPATIBLE`.** `user_id` identifies an authentication account. `employee_id` identifies a corporate personnel record with organization, department, team, manager, and employment-status context. A valid user may have no employee record. [T1 Executive Summary, item 2; §2.1.4–§2.2]
3. **Organization membership is resolved, not stored directly on every user — `VALIDATION_REQUIRED`.** Team 1 says a `user` does not carry an `organization_id`; organization context is derived from active employment, organization registration, and role assignments. [T1 §1.3]
4. **Tenant validation is mandatory — `VALIDATION_REQUIRED`.** A client-supplied `organization_id` is untrusted. Team 1 prescribes validating the caller through `/api/v1/auth/me` and an employee lookup, or through an organization read that returns `403` for a non-member. [T1 §1.4]
5. **Team 1 APIs use UUID path and payload values — `SCHEMA_ALIGNMENT_REQUIRED`.** The documented `GET /auth/me`, organization, department, team, employee, and reporting-history APIs expose UUID strings in snake_case payload keys such as `user_id`, `organization_id`, `team_id`, and `employee_id`. [T1 §5.1–§5.4]
6. **Employee departure is non-destructive — `COMPATIBLE`.** Deletion is a soft deactivation (`status = inactive`, `is_active = false`); records remain so historical employee references remain valid. [T1 Executive Summary, item 5; §7; §12.1]
7. **Current organization assignment is mutable — `SCHEMA_ALIGNMENT_REQUIRED`.** Team 1 does not retain historical team or department assignments when employees transfer, and explicitly recommends Team 4 snapshot assignment context on the incident. Manager history is retained separately. [T1 §7; §12.2]
8. **No Team 1 service catalog exists — `OPEN_DECISION`.** Team 1 owns neither services nor service-to-team/user mappings. Its suggested Team 4 service-table SQL is explicitly a recommendation only. [T1 Executive Summary, item 3; §3.1–§3.2; §12.2]
9. **Projects belong to Team 2 — `INTEGRATION_REQUIRED`.** Team 1 cannot validate `project_id` or project scopes. [T1 §1.5; §11]
10. **Team 1 currently supports bearer user JWTs, not machine authentication — `INTEGRATION_REQUIRED`.** JWTs use HS256 and Team 1 says no mTLS, client-credentials OAuth, API key, or internal service-to-service mechanism exists. Its service-user and future internal-token suggestions are recommendations, not an agreed protocol. [T1 §8.1–§8.2; §12.2–§12.3]
11. **Authorization information is currently exposed through `/auth/me` — `INTEGRATION_REQUIRED`.** The endpoint returns `user_id`, `employee_id`/`employee_ids`, active status, and a list of role codes. Team 1 documents `MANAGER` and `ORG_ADMIN` as roles Team 4 can use for critical closure/RCA approval checks. [T1 §5.1; §6; §12.1]

## 3. Existing Team 4 behavior

The following is the existing Team 4 baseline, distinguished from CT-04's proposed future behavior.

1. **Existing reference representation — `SCHEMA_ALIGNMENT_REQUIRED`.** `ExternalRef` is a frozen `{owner, id}` object; both values are currently unvalidated strings, and `Team4EntityId` is an unvalidated runtime string. These are not foreign keys and do not require UUIDs today. [CT-04 §4.2]
2. **Existing contract serialization — `SCHEMA_ALIGNMENT_REQUIRED`.** `ContractModel` accepts snake_case and camelCase input and rejects extras, but normal `model_dump()` emits snake_case unless aliases are requested. `ExternalRef` does not inherit that model. [CT-04 §4.1–§4.2, §4.7]
3. **Existing review record — `SCHEMA_ALIGNMENT_REQUIRED`.** `HumanReview` has optional `reviewer_ref`, but does not encode a Team 1 user or employee UUID type, an approver role, organization scope, or approval eligibility. [CT-04 §4.6]
4. **Existing application surface — `INTEGRATION_REQUIRED`.** There are no incident, evidence, ingestion, review, remediation, or Team 1 integration routes; the repository currently exposes health endpoints only. [CT-04 §1, §4]
5. **Proposed CT-04 incident references — `SCHEMA_ALIGNMENT_REQUIRED`.** The draft proposes a trusted-context `organizationId`, optional `assignedTeamRef`, optional `assignedUserRef`, and an `actorRef` sourced from the authenticated identity. It does not define reporter, employee, department, approver, or project fields. [CT-04 §6.1, §6.4, §11.1–§11.3, D-02]
6. **Proposed Team 4 policy is intentionally incomplete — `OPEN_DECISION`.** CT-04 explicitly requests Team 1 input on tenant and actor identifiers, membership, authorization context, authentication, and RBAC integration. No decision is marked Agreed. [CT-04 §2.3, §3.1, D-02, §14.1]

## 4. Field-by-field compatibility matrix

This matrix records actual contract comparisons, not a prescriptive Team 4 schema. “Missing from CT-04” means the v0.2 draft does not define that canonical field; it does not authorize adding one.

| Area / field | Team 1 fact | CT-04 v0.2 state | Finding | Required disposition |
|---|---|---|---|---|
| `organization_id` / `organizationId` | Immutable RFC 4122 UUID. Caller-provided value must be membership-validated. [T1 Executive Summary; §1.4; §2.1.1] | Required, trusted-context tenant ID; format explicitly Needs Team 1 Input. Examples use non-UUID synthetic values. [CT-04 §6.1–§6.2; §11.1; D-02] | `SCHEMA_ALIGNMENT_REQUIRED` | Agree UUID representation and validation at the CT-01/CT-04 boundary; preserve the rule that request-body organization values do not establish scope. |
| Department reference | `department_id` is UUID, belongs to an organization; Team 1 exposes department reads. [T1 §2.1.2; §5.3] | No canonical department field. [CT-04 §6.1; §7–§11] | `OPEN_DECISION` | Decide whether an incident needs an ownership snapshot/reference, or whether the assigned team/service is sufficient. Do not adopt Team 1's recommended SQL automatically. |
| Team reference / `assigned_team_id` | `team_id` is UUID and maps to a department; API provides team and lead. [T1 §2.1.3; §5.3; §6] | Optional `assignedTeamRef`; owner/id formats only proposed and unvalidated. [CT-04 §4.2; §6.1–§6.2; D-02, D-04] | `SCHEMA_ALIGNMENT_REQUIRED` | Define `team1.team` namespace and UUID `id` semantics, or replace the generic reference with a typed Team 1 UUID at the integration boundary. |
| User reference / `assigned_user_id` | `user_id` is UUID authentication identity and may lack an employee. [T1 §2.1.5; §2.2] | Optional `assignedUserRef`; proposed to be same organization, but no UUID rule or employee eligibility rule. [CT-04 §6.1; §11.2; D-02] | `VALIDATION_REQUIRED` | Validate a user UUID and organization membership; do not infer that it is a valid responder absent its employee relationship and active status. |
| Employee assignee / `assigned_employee_id` | UUID personnel record; Team 1 recommends it for incident assignment and requires active, in-organization employees. [T1 §2.1.4; §2.3; §6] | No employee-assignee field; only `assignedUserRef`. [CT-04 §6.1; §11.2] | `SCHEMA_ALIGNMENT_REQUIRED` | Decide whether Team 4 assignment is to a user, an employee, or both. If operational assignment needs team/manager/status data, model or resolve an employee reference explicitly. |
| Reporter / `reported_by_user_id` | Team 1 recommends a user UUID for the authenticated reporter, optionally with an employee UUID. [T1 §2.3; §9] | No reporter field. Actor identity is only specified for transitions and reviews. [CT-04 §6.1; §6.4; §11.2] | `SCHEMA_ALIGNMENT_REQUIRED` | Decide whether reports must retain the authenticated user principal, including system users without employees, and distinguish it from creator/transition actor. |
| Reviewer / approver | Team 1 recommends a reviewer/approver identity and requires `MANAGER` or `ORG_ADMIN` for critical closure/RCA approval; its prose ambiguously labels `reviewed_by_user_id` while allowing employee or user targets. [T1 §2.3; §6; §9] | `HumanReview.reviewerRef` is optional; an authenticated reviewer is proposed and permission names are intentionally undefined. [CT-04 §4.6; §11.2–§11.3; D-02] | `SCHEMA_ALIGNMENT_REQUIRED` | Resolve user-versus-employee review identity and make reviewer identity/non-null requirements explicit. Map approval permissions only after Team 1 confirms the required claim/role semantics. |
| UUID validation and serialization | UUIDs are canonical externally; Team 1 HTTP payloads use snake_case. [T1 Executive Summary; §5.1–§5.4] | Canonical Team 4 IDs are proposed UUIDs, but validation is not implemented. API JSON direction is camelCase, while existing types serialize snake_case by default. [CT-04 §4.1–§4.2; §5; §13; D-01, D-13] | `SCHEMA_ALIGNMENT_REQUIRED` | Define adapter/wire rules: Team 1 UUID strings remain UUID strings, Team 1 payloads may be snake_case, and CT-04 API outputs are camelCase only when a future boundary explicitly serializes by alias. |
| Organization/tenant context | Team 1 resolves context via employment, registration, and roles; validates through bearer token and `/auth/me` and/or organization endpoint. [T1 §1.3–§1.4; §8.3] | CT-04 requires trusted context, denies body `organizationId`, and delegates membership to CT-01. [CT-04 §9.3; §11.1; D-02] | `COMPATIBLE` | Implement the same trusted-context rule after agreeing the Team 1 adapter and failure behavior. |
| Authentication / RBAC | Bearer JWT; `/auth/me` returns status and role codes. [T1 §5.1; §8.1] | CT-04 delegates authentication/authorization to CT-01/Team 1; Team 5 enforces at API/execution boundaries. [CT-04 §2.1–§2.3; §9.3; §11.2] | `INTEGRATION_REQUIRED` | Agree token forwarding/validation ownership, required claims, calls to Team 1, caching, and authorization failure mapping. |
| Employee deactivation | Employee is soft-deactivated and retained; open work must be reassigned. [T1 §7; §12.1] | No assignee lifecycle or reassignment rule. [CT-04 §6; §11; D-06] | `VALIDATION_REQUIRED` | On assignment and escalation, validate active status; define a future Team 4 workflow for open incidents assigned to a newly inactive employee. Historical references should remain immutable. |
| Team/department snapshots | Team 1 overwrites team/department on transfer and has no historical audit; it recommends Team 4 snapshot the incident context. [T1 §7; §12.2–§12.3] | No department field or historical ownership snapshot is specified. `assignedTeamRef` is an optional current reference. [CT-04 §6.1; D-18, D-20] | `SCHEMA_ALIGNMENT_REQUIRED` | Decide whether creation/assignment stores immutable UUID snapshots, display snapshots, or both; distinguish historical incident ownership from a later current assignee. |
| Service ownership | No Team 1 service catalog or mapping; Team 1's Team 4 table is a recommendation. [T1 §3.1–§3.2; §11] | `serviceRef` is required/nullable; catalog ownership and service-to-team/user mappings are Needs Coordinator Confirmation. [CT-04 §6.1; §8.4; D-03] | `OPEN_DECISION` | Obtain coordinator ownership decision. Team 1 UUIDs may be referenced by a future catalog, but Team 1 cannot resolve services. |
| Project reference | Team 2 owns projects and Team 1 cannot validate project scope. [T1 §1.5; §11] | No project field or Team 2 contract in CT-04. [CT-04 §6–§11; §2.3] | `INTEGRATION_REQUIRED` | Obtain a Team 2 contract before defining or validating project context. This audit defines no Team 2 API. |
| Service-to-service access | No current M2M mechanism. Team 1 offers two recommendations only. [T1 §8.2; §12.2–§12.3] | CT-04 has connector/worker processing but does not define Team 1 M2M access. [CT-04 §2.3; §8; §9.3; D-21] | `OPEN_DECISION` | Teams 1, 4, and 5 must select and document a supported service-auth model before background workers call Team 1. |
| Team 1 API request/response shape | Documented routes are snake_case JSON and use `id` for entity IDs except `/auth/me`, which uses `user_id` and `employee_id`. Errors are documented as `{error, detail}`. [T1 §5.1–§5.5] | CT-04 proposes camelCase at its own API boundary and a nested `{error:{code,message,details}}` refusal envelope, but no integration endpoint. [CT-04 §3.3; §9.1; §13; D-11, D-13, D-14] | `INTEGRATION_REQUIRED` | Add a future adapter/translation contract; do not require either service to expose the other's payload or error envelope natively. |

## 5. Confirmed compatible fields and behaviors

The following compatibility findings are confirmed by the two documents. They do not establish a new schema.

1. **Trusted tenant context — `COMPATIBLE`.** Both documents reject client-controlled tenant scope: Team 1 requires membership validation for supplied organization values, and CT-04 says the organization comes from authenticated identity or a registered connector rather than the request body. [T1 §1.4, §8.3; CT-04 §9.3, §11.1]
2. **Authentication principal is distinct from operational personnel — `COMPATIBLE`.** Team 1's distinction between a `user_id` principal and an optional `employee_id` aligns with CT-04's rule that transition actors and reviewers originate from the authenticated identity rather than a body-supplied actor. [T1 §2.2; CT-04 §6.4, §11.2]
3. **Service catalog is not a Team 1 responsibility — `COMPATIBLE`.** Team 1 declares that it does not own services; CT-04 leaves service-catalog ownership with the coordinator rather than asserting Team 1 ownership. [T1 §3.1, §11; CT-04 §2.3, §8.4, D-03]
4. **Project validation is outside Team 1 — `COMPATIBLE`.** Team 1 assigns project ownership to Team 2, while CT-04 does not claim a project schema or API. [T1 §1.5, §11; CT-04 §2.3, §6–§11]
5. **Historical references must not be destroyed on personnel departure — `COMPATIBLE`.** Team 1 retains inactive employees; CT-04's append-only processing and audit orientation does not conflict with retaining historic identity links. CT-04 still needs a specific assignment lifecycle rule. [T1 §7; CT-04 §9.2, §11.4]

## 6. Fields requiring schema changes or schema alignment

These are proposed future CT-04 changes for discussion, not instructions to alter code or models.

1. **Organization identifier representation — `SCHEMA_ALIGNMENT_REQUIRED`.** CT-04 D-02 must reconcile its currently opaque `organizationId` with Team 1's canonical UUID. The synthetic non-UUID examples in CT-04 must not be treated as a production identifier format. [T1 Executive Summary; §2.1.1; CT-04 §6.2, §11.1, D-02]
2. **Team and assignee references — `SCHEMA_ALIGNMENT_REQUIRED`.** `assignedTeamRef` and `assignedUserRef` need an agreed mapping to Team 1 UUIDs. The currently proposed owner strings (`team1.team`, `team1.user`) are illustrative, not a registered namespace. [T1 §2.1.3, §2.1.5; CT-04 §6.1–§6.2, D-04]
3. **Employee assignment — `SCHEMA_ALIGNMENT_REQUIRED`.** CT-04 lacks Team 1's recommended `assigned_employee_id`. A generic user reference is insufficient to express Team 1's personnel eligibility, team membership, manager escalation, and active-employment rule. Whether CT-04 stores employee, user, or both remains a design decision. [T1 §2.2–§2.3, §6; CT-04 §6.1, §11.2]
4. **Reporter and reviewer/approver references — `SCHEMA_ALIGNMENT_REQUIRED`.** CT-04 lacks a reporter field and makes `reviewerRef` optional. A future contract must distinguish authenticated user identity from optional employee context and resolve Team 1's internally inconsistent reviewer naming/type guidance. [T1 §2.3, §9; CT-04 §4.6, §11.2–§11.3]
5. **Department/team ownership history — `SCHEMA_ALIGNMENT_REQUIRED`.** Team 1's mutable assignments require a Team 4 decision on immutable incident ownership snapshots. The audit does not assume the Team 1 proposed `department_id` column is approved. [T1 §7, §9, §12.3; CT-04 §6.1, D-18]
6. **Serialization adapter — `SCHEMA_ALIGNMENT_REQUIRED`.** CT-04's camelCase future API contract and Team 1's snake_case payloads can coexist, but the boundary mapping must be specified. Existing Team 4 Python behavior does not provide it automatically. [T1 §5.1–§5.4; CT-04 §4.1, §13.1, D-13]

## 7. Fields requiring only validation or integration changes

1. **Tenant membership and cross-organization access — `VALIDATION_REQUIRED`.** Preserve CT-04 trusted context and use Team 1-confirmed membership information. The exact choice between `/auth/me` plus employee lookup and organization-read authorization is an integration decision; client input is never sufficient. [T1 §1.4, §8.3; CT-04 §9.3, §11.1]
2. **Assignment eligibility — `VALIDATION_REQUIRED`.** Before operational assignment, verify that the selected employee is active and belongs to the incident organization. Team 1 also provides a team-employee candidate endpoint. [T1 §5.4, §6; CT-04 §6.1]
3. **Approval authorization — `VALIDATION_REQUIRED`.** CT-04 already requires a permitted reviewer and same-organization proposal. Team 1 documents roles it believes suitable for high-severity approval, but the mapping from Team 1 role codes to CT-04 approval permissions is not yet a joint decision. [T1 §6; CT-04 §11.2–§11.3, D-02]
4. **Historical employee references — `VALIDATION_REQUIRED`.** Active status should gate new assignments, not erase historical links. Team 4 needs a rule to reassign open incidents when an employee becomes inactive. [T1 §7; CT-04 §6, D-06]
5. **Authentication and Team 1 API invocation — `INTEGRATION_REQUIRED`.** CT-04 needs a confirmed token-forwarding/validation and API-calling model for user-initiated requests. Team 1's endpoints and documented `401`, `403`, `404`, and `422` cases must be translated only in an explicit integration layer. [T1 §5, §8.1; CT-04 §2.3, §9.3, D-11]
6. **Background worker access — `INTEGRATION_REQUIRED`.** CT-04 connector, ingestion, and worker paths cannot rely on an unspecified Team 1 service principal. The Team 1 recommendations require explicit acceptance and security design. [T1 §8.2, §12.3; CT-04 §8–§9, D-21]

## 8. Unresolved questions for Team 1

Each question remains unresolved until Team 1 answers it. None is a request to change Team 1's schema.

1. **`OPEN_DECISION`:** Does Team 1 confirm that CT-04 should accept and store Team 1 UUID values as canonical string UUIDs for organization, department, team, employee, and user references, while retaining Team 4-generated IDs separately? [T1 Executive Summary; §2.1; CT-04 §5, D-01, D-02]
2. **`OPEN_DECISION`:** What is the supported, stable way for Team 4 to derive the organization(s) for a user with no `employee_id`, including prospective organization administrators and external/service users? [T1 §1.3, §2.2; CT-04 §11.1–§11.2]
3. **`OPEN_DECISION`:** Are `employee_ids` in `/api/v1/auth/me` always limited to one employee today, and what should CT-04 do if the list contains multiple values or conflicts with `employee_id`? [T1 §5.1; CT-04 §11.1–§11.2]
4. **`OPEN_DECISION`:** Which Team 1 API is the supported authorization source for a user-initiated incident request: token claims, `/auth/me`, an organization read, an employee read, or a combination? What caching/revocation behavior is allowed? [T1 §1.4, §5.1–§5.2, §8.1; CT-04 §9.3, §11.2]
5. **`OPEN_DECISION`:** Is Team 1's intended post-mortem approval reference a user UUID, an employee UUID, or a pair? The `reviewed_by_user_id` label and “employee or user” target in §2.3 conflict with `reviewed_by_employee_id` in the proposed Team 1 schema. [T1 §2.3, §9; CT-04 §4.6, §11.3]
6. **`OPEN_DECISION`:** Are `MANAGER` and `ORG_ADMIN` the authoritative role-code requirements for CT-04 critical-incident closure and RCA/fix approval, or only examples? If authoritative, what organization scoping and active-user checks accompany them? [T1 §6, §8.3; CT-04 §11.2–§11.3]
7. **`OPEN_DECISION`:** What supported event, polling, or SLA mechanism tells Team 4 that an employee became inactive or transferred teams/departments so it can reassign open incidents and retain correct historical snapshots? The documented API only establishes reads; it does not define a change-notification contract. [T1 §5, §7, §12.2; CT-04 §6, §11]
8. **`OPEN_DECISION`:** Will Team 1 approve a specific service-to-service authentication solution for Team 4 workers? The options in Team 1 §8.2 are recommendations, not a committed protocol. [T1 §8.2, §12.3; CT-04 §2.3, D-21]

## 9. Team 2 and Team 5 dependencies

### Team 2 dependency

- **Project references — `INTEGRATION_REQUIRED`.** Team 1 assigns project ownership, project membership, and project validation to Team 2. CT-04 v0.2 has no `projectId` field or Team 2 API contract. No project field, validation algorithm, path, payload, or authorization model can be inferred from this audit. [T1 §1.5, §11; CT-04 §2.3, §6–§11]

### Team 5 dependencies

- **Identity integration enforcement — `INTEGRATION_REQUIRED`.** Team 5 is responsible for enforcing authentication, tenant scope, and permission checks at API/execution boundaries after Team 1 facts are made consumable. [CT-04 §2.1, §9.3, §11.2]
- **Reference validation and persistence — `INTEGRATION_REQUIRED`.** Any future UUID checks, Team 1 lookup adapter, caching strategy, and persistence transaction design require Team 5 implementation confirmation; CT-04 has no current incident storage. [CT-04 §4, §5, §6, D-01, D-02]
- **Service-to-service identity — `OPEN_DECISION`.** Team 5 cannot implement a Team 1 worker integration until the joint M2M model is selected. [T1 §8.2; CT-04 §2.3, D-21]
- **Service catalog routing — `OPEN_DECISION`.** Team 5 must not implement a Team 1 service lookup because Team 1 has none. A coordinator decision must identify the catalog and its service-to-team/user mapping authority. [T1 §3.1; CT-04 §2.3, §8.4, D-03]
- **Wire/API compatibility — `INTEGRATION_REQUIRED`.** Team 5 needs a future versioned integration adapter for Team 1 snake_case payloads and errors versus CT-04’s proposed camelCase boundary. CT-04’s transport and versioning are still unresolved. [T1 §5.1–§5.5; CT-04 §3.3, §9.1, §13, D-11, D-14]

## 10. Recommended changes for a future CT-04 v0.3

These are recommendations for a future draft only. They are not approved and do not modify CT-04 v0.2.

1. **`SCHEMA_ALIGNMENT_REQUIRED` — Add a Team 1 identifier appendix.** Define the UUID representation for `organizationId`, Team 1 user, employee, team, and department references; distinguish Team 1 IDs from Team 4-generated UUIDs and opaque provider IDs. [T1 Executive Summary; §2.1–§2.2; CT-04 §5, D-01, D-02]
2. **`SCHEMA_ALIGNMENT_REQUIRED` — Resolve person-reference semantics.** Define separate optional/relevant fields or reference roles for reporter (user), actor (user), assignee (employee and/or user), reviewer (user and/or employee), and approver. Require Team 1 to resolve its reviewer identity ambiguity before choosing the canonical form. [T1 §2.3, §6, §9; CT-04 §4.6, §6.1, §6.4, §11.2–§11.3]
3. **`VALIDATION_REQUIRED` — Specify validation rules, not direct database foreign keys.** Since Team 1 is a separate service, define Team 1 UUID validation, active-status checks, organization membership, employee-team relation, and authorization checks through an integration contract. Do not imply cross-database foreign-key enforcement. [T1 §1.4, §5–§6; CT-04 §4.2, §9.3, §11]
4. **`SCHEMA_ALIGNMENT_REQUIRED` — Specify ownership history.** Define whether Team 4 snapshots team and department UUIDs, names/codes, and effective times at incident creation/assignment; define how snapshots coexist with current assignment. [T1 §7, §12.2–§12.3; CT-04 §6.1]
5. **`OPEN_DECISION` — Retain service ownership outside Team 1.** Once the coordinator identifies a catalog owner, define the canonical `serviceRef` namespace and the relationship to Team 1 organization/team/employee UUIDs. [T1 §3.1–§3.2; CT-04 §8.4, D-03]
6. **`INTEGRATION_REQUIRED` — Add a Team 1 integration profile.** Specify endpoint usage, token forwarding or validation, error translation, caching/revocation expectations, and user-without-employee behavior. Preserve Team 1's rule that client-provided organization identifiers do not prove membership. [T1 §1.3–§1.4, §5, §8.1; CT-04 §9.3, §11.1–§11.2]
7. **`OPEN_DECISION` — Add a service authentication decision.** Record only an explicitly agreed M2M approach and its credential lifecycle. Do not elevate either Team 1 recommendation in §8.2 to an approved protocol. [T1 §8.2, §12.3; CT-04 §2.3, D-21]
8. **`INTEGRATION_REQUIRED` — Add a Team 2 project-reference dependency section only after Team 2 supplies its contract.** It should state the authority, UUID/value format, membership validation, and lifecycle behavior without inventing endpoints or payloads now. [T1 §1.5, §11; CT-04 §2.3]
9. **`SCHEMA_ALIGNMENT_REQUIRED` — State API naming and error-boundary compatibility.** CT-04 should declare an adapter boundary between Team 1 snake_case API responses/errors and CT-04’s proposed camelCase API representation. It must not claim common envelopes where none are agreed. [T1 §5.1–§5.5; CT-04 §3.3, §9.1, §13, D-13, D-14]

## 11. Implementation readiness assessment

### Ready to preserve as design constraints

- **`COMPATIBLE`:** Team 1 remains authoritative for identity, organization context, personnel, and RBAC; Team 4 remains authoritative for incident semantics and lifecycle. [T1 §11; CT-04 §2.1]
- **`COMPATIBLE`:** Organization scope must be derived from authenticated/registered context rather than trusted from a request body. [T1 §1.4; CT-04 §11.1]
- **`COMPATIBLE`:** Team 1 must not be used as a service catalog or project authority. [T1 §1.5, §3.1; CT-04 §2.3, §8.4]
- **`COMPATIBLE`:** Historical personnel records can remain referentially meaningful after deactivation. [T1 §7; CT-04 §11.4]

### Not ready to implement

- **`SCHEMA_ALIGNMENT_REQUIRED`:** CT-04's generic, unvalidated `ExternalRef` cannot yet be treated as a canonical Team 1 UUID reference for organization, team, user, employee, department, reporter, or reviewer/approver use. [T1 §2.1–§2.3; CT-04 §4.2, §6.1, D-02, D-04]
- **`INTEGRATION_REQUIRED`:** No Team 4 incident endpoint or Team 1 adapter currently exists, and no cross-service payload/error or version negotiation contract has been agreed. [T1 §5; CT-04 §1, §4, D-11, D-14]
- **`INTEGRATION_REQUIRED`:** User-JWT authentication is documented, but service-to-service authentication for Team 4 workers is explicitly absent. [T1 §8; CT-04 §8–§9]
- **`OPEN_DECISION`:** Ownership history, reviewer identity, approval-role semantics, service catalog authority, and Team 2 project behavior are unresolved. [T1 §2.3, §3, §7, §12.3; CT-04 §2.3, §11.3, D-02, D-03]

### Gate for implementation readiness

CT-04 becomes ready to implement Team 1-backed identity and organization integrations only after:

1. Team 1 confirms the identifier and principal/employee semantics in §8 of this audit.
2. Teams 1, 4, and 5 agree a supported user-request and worker/service authentication model.
3. CT-04 v0.3 (or an explicitly versioned companion contract) defines Team 1 UUID/reference representation, validation rules, ownership snapshots, reviewer/approver semantics, and wire adaptation.
4. The coordinator resolves service-catalog ownership, and Team 2 supplies a project contract before project references are introduced.

These gates are **OPEN_DECISION** items. They do not assert that any team has approved the recommended changes.

## 12. Source-section index

For traceability, all findings above cite these complete-source sections:

- **Team 1:** Executive Summary; §1 Organization and Project References; §2 User, Employee, Department and Team Identifiers; §3 Service Ownership; §5 API Contracts; §6 Incident Assignment and Escalation; §7 Lifecycle; §8 Authentication and Organization Context; §9 Proposed Incident Reference Schema; §11 Ownership Boundaries; §12 Confirmed Facts, Unsupported Features and Open Questions.
- **CT-04 v0.2:** §2 Ownership; §3 Conventions; §4 Existing Implementation; §5 Identifier Categories; §6 Incident; §8 Observation Ingestion; §9 Receipt/Validation; §11 Tenant, Permissions and Approval; §13 Serialization; and decisions D-01, D-02, D-03, D-04, D-11, D-13, D-14, D-21.

This audit makes no claim beyond those documents and records absent contracts as gaps rather than inferred behavior.
