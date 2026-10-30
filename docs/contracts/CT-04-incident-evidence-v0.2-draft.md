# CT-04 — Incident & Evidence Contract

| Item | Value |
|---|---|
| Contract | CT-04 — Incident/evidence handoff and approval integration (shared contract Section 5) |
| Version | `0.2.1-draft` |
| Document owner | Team 4 — Incident Management & AI Root Cause Analysis |
| Implementation coordination | Team 5 |
| Dependencies | CT-01 (identity, tenant, authorization — Team 1), CT-06 (audit and platform events), CT-07 (AI Gateway, agents, tool execution) |
| Status | Reconciliation draft. Not an approved implementation baseline. |
| Supersedes as a draft | `docs/contracts/CT-04-incident-evidence-v0.1.md` (unchanged historical draft) |
| Implementation baseline | `api/app/modules/*/contracts.py`, `api/app/shared/*.py`, `docs/erd/team4-erd.md` |

**Revision `0.2.1-draft` is a reconciliation draft. It is not an approved implementation baseline.**

Team 5 feedback is incorporated below as proposed contract text. A Team 5 recommendation or implementation proposal is not an agreement. No decision in this document is Agreed. Nothing proposed here is implemented unless §4 says the repository already does it. The filename remains `docs/contracts/CT-04-incident-evidence-v0.2-draft.md`.

## Change history

| Version | Description |
|---|---|
| `0.1-draft` | Initial contract proposal. Reviewed by Team 5. Preserved unchanged at `docs/contracts/CT-04-incident-evidence-v0.1.md`. |
| `0.2-draft` | Reconciles Team 5's feedback on provenance, validation stages, idempotency, duplicate observations, severity mapping, audit durability, serialization, timestamps, and evidence scope. |
| `0.2-draft` (second Team 5 review) | Reconciles six follow-up comments: observation provenance binding to the authenticated connector registration; mandatory `idempotencyKey` and token-reuse policy; stable source-account identity versus replaceable connector registration; controlled reprocessing and correlation IDs; completion commit boundary and recovery; changed provider content. Adds D-22 to D-26 and fixtures F-15 to F-26. Still not an approved baseline. |
| `0.2.1-draft` | Records Team 5's second reconciliation review. Team 5 accepted all six reconciliation comments at the contract-definition level. F-20 through F-24 were specifically reviewed. All 28 JSON examples passed independent syntax validation. Team 5 submitted implementation proposals for D-11, D-21, D-22, D-23, D-24, D-25, and D-26. No joint decision is marked Agreed because of this review. Executable contract tests were not run. |

## Review checkpoint

| Item | Value |
|---|---|
| Revision | `0.2.1-draft` |
| Review | Team 5 second reconciliation review |
| Review outcome | Six reconciliation comments accepted at the contract-definition level. F-20 through F-24 were specifically reviewed. |
| Implementation status | Pending joint agreement. The Team 5 proposals recorded on D-11, D-21, D-22, D-23, D-24, D-25, and D-26 are not Agreed. |
| JSON validation | 28 examples passed independent syntax validation, as reported by Team 5 for this review. |
| Executable testing | Not performed. |

Acceptance at the contract-definition level does not approve an implementation, select a previously open policy, or change a decision status. D-02 remains dependent on Team 1. D-03 remains dependent on coordinator confirmation.

## Contents

- [Review checkpoint](#review-checkpoint)

1. [Purpose and scope](#1-purpose-and-scope)
2. [Ownership and responsibilities](#2-ownership-and-responsibilities)
3. [Document conventions](#3-document-conventions)
4. [Existing implementation baseline](#4-existing-implementation-baseline)
5. [Identifier categories](#5-identifier-categories)
6. [Proposed canonical Incident](#6-proposed-canonical-incident)
7. [Proposed canonical Evidence](#7-proposed-canonical-evidence)
8. [Proposed Observation Ingestion](#8-proposed-observation-ingestion)
9. [Receipt acknowledgment and processing outcome](#9-receipt-acknowledgment-and-processing-outcome)
10. [Idempotency, duplicates and failures](#10-idempotency-duplicates-and-failures)
11. [Tenant, permissions, approval and audit durability](#11-tenant-permissions-approval-and-audit-durability)
12. [Synthetic acceptance fixtures](#12-synthetic-acceptance-fixtures)
13. [Serialization, timestamps and tests to specify](#13-serialization-timestamps-and-tests-to-specify)
14. [Decision register](#14-decision-register)

---

## 1. Purpose and scope

This document defines Team 4's canonical Incident, Evidence and Observation Ingestion contracts for reconciliation with Team 5. It covers field definitions, validation stages, relationships, receipt and processing semantics, idempotency, JSON serialization, and acceptance fixtures.

In scope:

- The existing Team 4 contract definitions, stated exactly as implemented.
- Proposed canonical Incident, Evidence, and Observation contracts.
- Proposed receipt acknowledgment and processing outcome semantics, including mapping version and processing history.
- Proposed idempotency, duplicate, conflict, and failure behavior.
- Proposed audit-intent durability for domain state changes.
- Integration points with CT-01, CT-06, and CT-07.

Out of scope:

- Application code, database models, migrations, API routes, or services.
- HTTP methods, paths, and status codes (see [D-11](#14-decision-register)).
- Retry counts, backoff intervals, and retention durations (see [D-12](#14-decision-register)).
- Connector, AI Gateway, audit-sink, and identity implementations.
- Storage provider, content URI format, retention, and access control for evidence bytes (see [D-08](#14-decision-register)).

**Current implementation state.** The Team 4 repository implements Pydantic contract types only. The FastAPI application exposes `GET /health`, `GET /api/v1/health`, and `GET /api/v1/health/database`. No incident, evidence, ingestion, review, or remediation routes exist. No SQLAlchemy domain models or Alembic revisions exist (`api/app/db/models.py` imports `Base` only; `api/alembic/versions/` is empty).

---

## 2. Ownership and responsibilities

### 2.1 Responsibility boundaries

| Team | Owns or implements |
|---|---|
| **Team 4** (owner) | Canonical Incident and Evidence schemas. Field validation and domain rules. External-to-canonical severity mapping requirements. Incident lifecycle and status transitions. Observation processing semantics. RCA domain requirements. Human-review and remediation-approval workflow requirements. |
| **Team 5** (implements) | Database and API components once specified. Connector infrastructure. AI Gateway and execution infrastructure. Audit infrastructure and platform event delivery. Authorization and approval enforcement at API and execution boundaries. Database uniqueness, transactions, and the audit outbox dispatcher. |
| **Team 1** (owns) | Authentication. Organization/tenant identity. User identity. RBAC and permission context. |

Team 4 defines *what* is valid and *what* must happen. Team 5 builds the components that store, transport, and enforce those rules. Team 1 is the source of truth for *who* the caller is and *which* organization and permissions apply. Where this draft cannot choose a boundary from v0.1 plus Team 5's feedback, the decision stays open and names who must confirm it.

### 2.2 Contract map

| Contract | Section | Responsibility | Relationship to CT-04 |
|---|---|---|---|
| CT-01 | Section 2 | Identity, organization/tenant context and authorization | CT-04 consumes the trusted organization ID, actor identity, and permission context. |
| CT-04 | Section 5 | Incident/evidence handoff and approval integration | This document. |
| CT-06 | Section 7 | Audit logging and platform events | CT-04 specifies which domain events must be audited and their payload content. CT-06 owns the envelope, transport, and delivery guarantees. |
| CT-07 | Section 8 | AI Gateway, agents and tool execution | CT-04 specifies the RCA input/output domain contracts and the approval preconditions for remediation. CT-07 owns invocation, transport, and execution. |

### 2.3 Confirmation dependencies

| Who | Must confirm |
|---|---|
| Team 1 | Canonical organization/tenant identifiers. User and employee identifiers. Membership and authorization context. Authentication and RBAC integration. |
| Team 5 | Connector and source-account identity, including how a connector registration authorizes a stable source account. Storage references and evidence-content access. API delivery and receipt semantics. Database uniqueness and transaction strategy, including the completion commit boundary. Audit-outbox delivery and replay. Mapping-version representation and governance. Sender-token reuse policy. Provider-event revision handling. Controlled reprocessing transport. Payload size limits and retention limits. Contract/API versioning and compatibility. |
| Coordinator | Service-catalog ownership. Service-to-team and service-to-user mapping ownership. |
| Team 4 | Incident and Evidence semantics. Incident lifecycle. Severity mapping requirements. RCA semantics. Human review and remediation approval decisions. |

---

## 3. Document conventions

### 3.1 Status labels

| Label | Meaning |
|---|---|
| **Existing** | Implemented in the Team 4 repository today, as stated in §4. |
| **Proposed** | Recommended default in this reconciliation draft. Not agreed. |
| **Open** | No default is established, or a numeric policy is deliberately unset. |
| **Needs Team 1 Input** | Blocked on Team 1 identity or authorization definitions. |
| **Needs Team 5 Confirmation** | Team 5 must confirm the implementation contract. |
| **Needs Coordinator Confirmation** | Ownership sits outside Team 4 and Team 5. |
| **Agreed** | Reserved for an explicit joint decision. Unused in this draft. A Team 5 implementation proposal recorded against a decision is not Agreed and does not by itself change that decision's status. |

### 3.2 Field presence terms

| Term | Meaning |
|---|---|
| **Required** | The key must be present. |
| **Optional** | The key may be omitted. |
| **Nullable** | `null` is a valid value. |
| **Non-nullable** | `null` is invalid. |

"Required, nullable" means the key must be present and may hold `null`. "Optional, nullable" means the key may be omitted or sent as `null`.

**Proposed ([D-17](#14-decision-register)).** On output, canonical records include every key, with explicit `null` for empty nullable fields. On input, an omitted optional key and an explicit `null` are equivalent after defaulting, and that equivalence is part of payload equality (§10.4). They are not equivalent to a conflicting pair of aliases.

### 3.3 JSON naming

**Proposed direction from Team 5 feedback ([D-13](#14-decision-register)). Not agreed, and not fully implemented.**

- Canonical JSON uses camelCase.
- Python attributes stay snake_case where a Python model exists.
- Documented input aliases are the snake_case field name and the camelCase alias.
- Output at the API boundary is explicit camelCase.
- Supplying both aliases for one field is rejected, whether or not the values match.
- A JSON object key repeated twice is rejected. Detection must happen before ordinary JSON parsing keeps only the last value.
- `null` versus omission is specified in §3.2 and §10.4.

§4.7 records what the current code actually does. Duplicate-key detection is not implemented. Alias rejection happens today only as a Pydantic `extra="forbid"` side effect, and no test locks that behavior.

Enumeration values are lowercase snake_case (`fix_proposal`, `needs_changes`). Error codes are UPPER_SNAKE_CASE.

### 3.4 Timestamps

Five times are distinct. The same JSON key `receivedAt` appears on two different objects and does not mean the same instant.

| Concept | Where it lives | Set by | In business-payload equality? |
|---|---|---|---|
| Source event time | Observation `occurredAt` | Provider, via the connector | Yes, after UTC normalization |
| Connector receipt from the provider | Observation `receivedAt` | Connector | **Proposed:** no. A retry must not look like new content because the connector clock moved. Needs Team 5 Confirmation ([D-10](#14-decision-register)). |
| Connector submission / send time | Observation `submittedAt` (optional) | Connector, if it supplies one | **Proposed:** no. Same reason. |
| Server receipt time | Transport metadata, not an Observation field | API process, when bytes arrive | No, unless explicitly agreed later |
| Durable ingestion receipt time | Receipt acknowledgment `receivedAt` | Receiving boundary, when the receipt row commits | No |
| Processing start | Processing attempt `processingStartedAt` | Worker | No |
| Processing completion | Processing attempt `processedAt` | Worker | No |

**Proposed ([D-16](#14-decision-register)).** Accepted timestamps are timezone-aware. Canonical processing, storage for comparison, and payload fingerprints use the UTC instant, serialized as RFC 3339 with a `Z` suffix. Where provenance needs the original lexical value (a non-`Z` offset, or a source clock Team 4 must not rewrite), the normalized instant and the supplied lexical form are both retained. The current Pydantic models do **not** normalize offsets to `Z` (§4.7, G-2). This draft does not claim that they do.

Clock skew is §8.8. No numeric tolerance is defined.

---

## 4. Existing implementation baseline

Everything in this section is **Existing**. v0.2-draft does not change these types. The proposals in §5–§13 are not implemented.

### 4.1 `ContractModel` — `api/app/shared/contract.py`

```python
class ContractModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
```

| Behavior | Detail |
|---|---|
| Python attribute names | snake_case (`created_at`). |
| JSON aliases | camelCase via `to_camel` (`createdAt`). |
| Input | Either the field name or the alias (`populate_by_name=True`). |
| Unexpected fields | Rejected (`extra="forbid"`). |
| Output | camelCase only when serialized by alias. The default `model_dump()` is snake_case. |

`ExternalRef` does not inherit `ContractModel`.

### 4.2 Identifiers — `api/app/shared/identifiers.py`

`Team4EntityId` is `NewType("Team4EntityId", str)`. At runtime it is an unvalidated string. `ExternalRef` has `owner` and `id`, is frozen, and rejects unexpected fields. `as_team4_entity_id` and `as_external_ref` do not enforce UUID or non-empty strings. Neither type is a foreign key.

### 4.3 Incident — `api/app/modules/incidents/contracts.py`

`InvestigationId` is a `NewType` over `Team4EntityId`, owned by RCA-001. `as_investigation_id()` wraps a string without validation. The `rca_investigation` entity is not approved.

`IncidentSummary` fields: `id`, `title`, `status` (unconstrained string), `created_at`, `external_refs` (optional, nullable). This is a summary contract, not the canonical Incident.

### 4.4 Evidence — `api/app/modules/evidence_collection/contracts.py`

`EvidenceSubmission` fields: `incident_id`, `investigation_id` (optional), `description`, `source_label`, `captured_at`, `external_source_ref` (optional). This is a submission contract, not the canonical Evidence record. It has no provenance object. The shared `Provenance` shape in §7.3 is **Proposed** and is not implemented.

### 4.5 Ingestion — `api/app/modules/ingestion/contracts.py`

`IncidentIntake` fields: `source` (`manual` or `fixture` only), `external_incident_ref` (optional), `title`, `description`, `occurred_at`. This is initial manual/fixture intake, not a provider observation contract.

### 4.6 AI RCA and related contracts

| Type | File | Existing fields |
|---|---|---|
| `IncidentContext` | `api/app/modules/ai_rca/contracts.py` | `external_incident_ref` optional, `summary`, `occurred_at` |
| `ContextEvidence` | same | `evidence_id`, `description`, `source_ref` optional |
| `InvestigationContext` | same | `investigation_id`, `incident`, `evidence` |
| `CandidateEvidenceLink` | same | `evidence_id`, `polarity` (`supports`, `contradicts`, `context`), `explanation` |
| `RootCauseCandidateDraft` | same | `title`, `rationale`, `confidence` (unbounded float), `uncertainty`, `missing_information`, `evidence`, `status` fixed to `proposed` |
| `AiRcaAgent` | same | `analyze(context) -> list[RootCauseCandidateDraft]` |
| `RootCauseCandidate` | `api/app/modules/root_candidates/contracts.py` | Draft fields plus `id`, `investigation_id`, `status` `proposed`, `review_required` fixed to `true` |
| `FixProposalDraft` | `api/app/modules/fix_agent/contracts.py` | `investigation_id`, `candidate_id`, `summary`, `expected_outcome`, `risks`, `requires_human_review` fixed to `true` |
| `HumanReview` | `api/app/modules/reviews/contracts.py` | `id`, `subject_type` (`candidate`, `fix_proposal`, `resolution`), `subject_id`, `decision` (`pending`, `approved`, `rejected`, `needs_changes`), optional `reviewer_ref`, `decided_at`, `rationale` |

`IncidentContext` and `ContextEvidence` are analysis projections. They do not replace canonical Incident or Evidence records. A deterministic mock implements `AiRcaAgent`. No live model integration exists.

### 4.7 Observed behavior and gaps

Checked with Pydantic 2.14.1. These are facts about current code.

| # | Observed behavior | Gap against this draft |
|---|---|---|
| G-1 | Empty strings are accepted for `str` fields and ids. | Proposed non-empty and length rules. |
| G-2 | Naive datetimes are rejected. Non-UTC offsets are kept (`+05:30` is not rewritten to `Z`). | Proposed UTC normalization ([D-16](#14-decision-register)). Not implemented. |
| G-3 | `status` is any string. | Proposed lifecycle enum (§6.3). |
| G-4 | `external_refs` is optional and nullable. | Proposed required list (§6.1). |
| G-5 | `confidence` is unbounded (`1.7` validates). | Proposed range 0–1 (F-05). |
| G-6 | Both `created_at` and `createdAt` are rejected with `extra_forbidden`, even when the values are identical. This is Pydantic alias handling, not a named rule, and no test asserts it. | [D-13](#14-decision-register) makes rejection the proposed contract rule. |
| G-7 | A repeated JSON key is accepted; the parser keeps the last value. Duplicate-key detection is **not** implemented. | [D-13](#14-decision-register) proposes rejection before ordinary parsing. |
| G-8 | Optional fields serialize as explicit `null` unless `exclude_none=True`. | [D-17](#14-decision-register). |

### 4.8 Relationship between existing and proposed contracts

| Existing | Proposed counterpart | Relationship |
|---|---|---|
| `IncidentSummary` | Incident (§6) | Read projection. Aligning `status` and `externalRefs` is a later, versioned change. |
| `EvidenceSubmission` | Evidence (§7) | Manual input shape. The canonical record adds system fields. |
| `IncidentIntake` | Observation (§8) | Manual/fixture path. Observation is the provider path. |
| `IncidentContext`, `ContextEvidence` | Incident, Evidence | RCA projections only. |

---

## 5. Identifier categories

**Proposed.** These categories are not interchangeable. UUID generation and validation are not implemented and are not agreed ([D-01](#14-decision-register)).

| Category | Examples | Issued by | Purpose |
|---|---|---|---|
| Canonical Team 4 entity IDs | Incident `id`, Evidence `id`, `incidentId`, `evidenceIds` | Persistence layer, at creation | Identity of a Team 4 record. Never caller-supplied on create. |
| Investigation IDs | `investigationId` | Team 4 (RCA-001) | Investigation context. The investigation entity is not approved. |
| Provider/source event IDs | `sourceEventId`, `ExternalRef.id` | Provider | Opaque event identity in the provider. Never a Team 4 primary key. Meaning (occurrence versus mutable alert) is §10.9. |
| Delivery/receipt IDs | `deliveryId`, `observationId` | Receiving boundary | The accepted observation and its receipt. |
| Sender idempotency token | `idempotencyKey` | Sender | Delivery metadata for the sender's retries. Not part of provider-event identity or business-content equality. Reuse policy is [D-22](#14-decision-register). |
| Stable source-account identity | `sourceAccountRef` | Provider (account identity), authorized through connector registration | The provider account the event belongs to. It must identify the same account across reconnects and connector replacements ([D-23](#14-decision-register)). Format Needs Team 5 Confirmation. |
| Connector registration instance | `provenance.collectorRef` (for observations) | Team 5 connector registration | The authenticated, replaceable connection that delivered or collected the data. A reconnect may produce a new instance. Never part of provider-event identity. |
| Correlation | `correlationId` | Connector, sender, or reprocessing requester | Delivery/tracing metadata across receipt, processing, audit, and AI calls. Not an entity id or business content. The three correlation roles are §9.4. |

`deliveryId` is assigned once, when an idempotency identity is first reserved. It is not a second business key.

**Proposed ([D-23](#14-decision-register)).** Three source identities are distinct and are not interchangeable:

| Identity | Stable across reconnect? | Used for |
|---|---|---|
| Stable source-account identity (`sourceAccountRef`) | Yes. Required. | Provider-event identity scope (§10.2), authorization target, and the source-account reference preserved on event Evidence. |
| Connector registration instance (`collectorRef`) | No. May be replaced. | Authentication of the caller, and provenance of which connection collected this data. |
| Provider event identity (`sourceEventId`) | Provider-defined (§10.9) | Event identity inside the source account. |

---

## 6. Proposed canonical Incident

All of §6 is **Proposed**. Not implemented.

### 6.1 Fields

| JSON key | Type | Required | Nullable | Validation | Source of value |
|---|---|---|---|---|---|
| `id` | Canonical ID | Required | No | UUID ([D-01](#14-decision-register)) | Generated. Never caller-supplied. |
| `organizationId` | Tenant ID | Required | No | CT-01 ([D-02](#14-decision-register)) | Trusted context only. A body value does not establish membership. |
| `title` | string | Required | No | Trimmed, 1–255 characters | Caller or observation `title`. |
| `description` | string | Optional | Yes | Empty after trim stored as `null`. Max length [D-15](#14-decision-register). | Caller or observation. |
| `severity` | enum | Required | No | `critical`, `high`, `medium`, `low` | Team 4 mapping, or an authorized user for manual intake. |
| `status` | enum | Required | No | `open`, `investigating`, `resolved`, `closed` | Initial `open`. Changes only through §6.3. |
| `serviceRef` | `ExternalRef` | Required | Yes | Must resolve in trusted service context ([D-03](#14-decision-register)) | **Proposed:** required for observation-derived incidents; may be `null` for manual incidents. |
| `assignedTeamRef` | `ExternalRef` | Optional | Yes | Same organization (CT-01) | Authorized user or routing rule. Team identity is Team 1's. |
| `assignedUserRef` | `ExternalRef` | Optional | Yes | Same organization (CT-01) | Authorized user. User identity is Team 1's. |
| `externalRefs` | `ExternalRef[]` | Required | No | Unique by (`owner`, `id`). May be empty. | Ingestion and authorized users. |
| `createdAt` | timestamp | Required | No | UTC `Z` | System. |
| `updatedAt` | timestamp | Required | No | UTC `Z`, at least `createdAt` | System. |

Callers do not send `id`, `organizationId`, `status` (on create), `createdAt`, or `updatedAt`. **Proposed:** those keys on input are rejected as unexpected.

`ExternalRef` is `{ "owner", "id" }`. **Proposed ([D-04](#14-decision-register)):** both non-empty after trim.

Whether Incident also stores `occurredAt` or `detectedAt` remains [D-18](#14-decision-register).

### 6.2 Example — canonical Incident

```json
{
  "id": "11111111-1111-4111-8111-000000000001",
  "organizationId": "org_synth_0001",
  "title": "Checkout API error rate above threshold",
  "description": "Synthetic monitor reported a 12% HTTP 5xx rate over 5 minutes.",
  "severity": "high",
  "status": "open",
  "serviceRef": { "owner": "service-catalog", "id": "svc_synth_checkout" },
  "assignedTeamRef": { "owner": "team1.team", "id": "team_synth_payments" },
  "assignedUserRef": null,
  "externalRefs": [
    { "owner": "synthetic-monitor", "id": "evt-10001" }
  ],
  "createdAt": "2026-10-01T09:15:04Z",
  "updatedAt": "2026-10-01T09:15:04Z"
}
```

`organizationId` and `serviceRef.owner` are illustrative. Team 1 and the coordinator have not confirmed those formats.

### 6.3 Incident lifecycle

**Proposed ([D-06](#14-decision-register)). Not implemented.**

| Current | Allowed next |
|---|---|
| `open` | `investigating` |
| `investigating` | `resolved` |
| `resolved` | `investigating`, `closed` |
| `closed` | No direct transition |

`resolved → investigating` reopens an incident when the issue recurs or the resolution was ineffective. Any other transition is rejected. A request to set the status the record already has is not a transition. **Proposed:** it is rejected. `open → closed` and reopening a closed incident are [D-06](#14-decision-register) and are not allowed by this table.

Resolving an incident does not approve or execute remediation (§11.3).

### 6.4 Transition record

**Proposed.** Every status change emits one transition and one audit intent (`incident.status_changed`) in the same local transaction (§11.4).

| JSON key | Required | Nullable | Description |
|---|---|---|---|
| `incidentId` | Required | No | Incident in the actor's organization. |
| `fromStatus` | Required | No | Must equal the current status. |
| `toStatus` | Required | No | An allowed next status. |
| `actorRef` | Required | No | Authenticated identity (CT-01), not a body-supplied actor. |
| `reason` | Required | No | Trimmed, non-empty. Max length [D-15](#14-decision-register). |
| `correlationId` | Required | No | Non-empty. |
| `occurredAt` | Required | No | When the change took effect. System-set, UTC `Z`. |

```json
{
  "incidentId": "11111111-1111-4111-8111-000000000001",
  "fromStatus": "open",
  "toStatus": "investigating",
  "actorRef": { "owner": "team1.user", "id": "user_synth_0007" },
  "reason": "On-call engineer started investigation.",
  "correlationId": "corr-synth-0001",
  "occurredAt": "2026-10-01T09:20:00Z"
}
```

---

## 7. Proposed canonical Evidence

All of §7 is **Proposed**. The `Provenance` object is not implemented (§4.4).

### 7.1 Relationships

- Evidence belongs to exactly one Incident (`incidentId`, non-null).
- Evidence may optionally name one investigation of that same incident. The investigation entity is not approved.
- Many-to-many links (`evidence_link` in the ERD) are not approved.
- Deletion and retention are [D-08](#14-decision-register).

### 7.2 Two evidence origins

These are different records. Provenance is not copied from one onto the other.

| Origin | When it is created | Provenance | Trigger reference |
|---|---|---|---|
| Observation event Evidence | With every accepted observation whose mandatory event content is stored successfully | The observation's provenance, unchanged. Same provider and same `sourceEventId`. | None. This evidence *is* the observation's event. |
| Separately collected Evidence | A later or independent collection through a tool, connector, or collector | The collector's actual provider and collector. Never rewritten to the triggering observation's provider. | `triggeredByObservationId`, when this collection was triggered by an observation. That field is a relationship. It is not provenance. |

Phase 1 ingestion creates only the event Evidence (§8.6, [D-19](#14-decision-register)). Separately collected Evidence is a separate operation unless Team 4 and Team 5 jointly agree to include it in initial processing. Absence of that later evidence is not `partial` on the ingestion outcome.

### 7.3 Fields

| JSON key | Type | Required | Nullable | Validation | Source of value |
|---|---|---|---|---|---|
| `id` | Canonical ID | Required | No | [D-01](#14-decision-register) | Generated. |
| `incidentId` | Canonical ID | Required | No | Incident in the same organization | Processing or caller. |
| `investigationId` | Investigation ID | Optional | Yes | Same incident, when set | Caller or investigation flow. |
| `triggeredByObservationId` | Delivery ID | Optional | Yes | An observation in the same organization. Null on event Evidence. | Collection workflow. Not provenance. |
| `evidenceType` | enum | Required | No | `log`, `metric`, `trace`, `event`, `other` ([D-07](#14-decision-register)) | Collector or caller. Event Evidence uses `event`. |
| `description` | string | Required | No | Trimmed, non-empty | Collector or caller. |
| `sourceLabel` | string | Required | No | Trimmed, 1–255 | Collector or caller. |
| `externalSourceRef` | `ExternalRef` | Optional | Yes | [D-04](#14-decision-register) | Collector. |
| `contentRef` | string | Required | Yes | Opaque. Format [D-08](#14-decision-register). See availability rules below. | Storage component (Team 5). |
| `capturedAt` | timestamp | Required | No | UTC `Z` | Source or collector. |
| `collectedAt` | timestamp | Required | No | UTC `Z` | System. |
| `availability` | enum | Required | No | `available`, `partial`, `unavailable` | Collector. |
| `provenance` | `Provenance` | Required | No | §7.4 | The party that actually produced this evidence. |

**Availability ([D-07](#14-decision-register), [D-08](#14-decision-register)).**

| Value | Meaning | `contentRef` |
|---|---|---|
| `available` | The content this record claims is stored. Access rules are [D-08](#14-decision-register) and are not confirmed. | Required, and it must be a valid stored-content reference. A record with no valid `contentRef` must not use `available`. |
| `partial` | A portion of the content was stored (for example a truncated window). `description` states what is missing. | Required for the stored portion. If nothing was stored, the value is `unavailable`, not `partial` and not `available`. |
| `unavailable` | The evidence was identified and no content was stored. | `null`. |

What "valid stored-content reference" means (provider, URI, integrity, access) is Needs Team 5 Confirmation ([D-08](#14-decision-register)). This draft only requires that `available` and `partial` point at stored bytes and that `unavailable` does not pretend those bytes exist.

### 7.4 `Provenance`

**Proposed. Not implemented.**

| JSON key | Required | Nullable | Rule |
|---|---|---|---|
| `originType` | Required | No | `observation`, `manual`, or `tool_execution` |
| `provider` | Required | Yes | Non-null when `originType` is `observation` or `tool_execution`. For event Evidence this is the observation's provider, not a rewritten id. |
| `sourceEventId` | Required | Yes | Non-null when `originType` is `observation`. Opaque. |
| `sourceAccountRef` | Required | Yes | Non-null when `originType` is `observation`, and equal to the observation's top-level `sourceAccountRef`. For `tool_execution`, whether the tool reports the account it read from is Needs Team 5 Confirmation ([D-23](#14-decision-register)); until then it may be `null`. `null` for `manual`. |
| `collectorRef` | Required | Yes | Connector, tool, or user that collected **this** evidence. For `observation`, the authenticated connector registration instance. |

Event Evidence copies the observation `provenance` object unchanged. Separately collected Evidence carries its own `provenance`. If a metric connector collected the bytes, `provider` is that metric source even when an observation triggered the collection.

**Proposed origin-specific rules ([D-07](#14-decision-register), [D-21](#14-decision-register)).**

| `originType` | Produced by | `provider` | `sourceEventId` | `sourceAccountRef` | `collectorRef` |
|---|---|---|---|---|---|
| `observation` | Observation ingestion only | Equals Observation `source` | Equals Observation `sourceEventId` | Equals Observation `sourceAccountRef`, and that account is authorized for the authenticated connector registration | Equals the authenticated connector registration instance |
| `tool_execution` | A separate collection operation (CT-07) | The source the tool actually read | `null` unless the tool returns a provider event id | See the table above | The tool or collector connector that ran |
| `manual` | An authorized user | `null` or a user-declared label ([D-07](#14-decision-register)) | `null` | `null` | The authenticated user (CT-01) |

An Observation must carry `originType` `observation`. Manual and tool-execution provenance are never accepted on the observation path, and observation provenance is never produced by manual or tool collection. A payload value cannot substitute a different collector or source account: the binding is checked against the authenticated registration, not trusted from the body (§8.5).

### 7.5 Example — event Evidence

Provenance matches the observation in §8.7. `triggeredByObservationId` is null.

```json
{
  "id": "22222222-2222-4222-8222-000000000001",
  "incidentId": "11111111-1111-4111-8111-000000000001",
  "investigationId": null,
  "triggeredByObservationId": null,
  "evidenceType": "event",
  "description": "Provider alert: HTTP 5xx rate 12% over 5 minutes on checkout-api-prod.",
  "sourceLabel": "Synthetic Monitor alert",
  "externalSourceRef": { "owner": "synthetic-monitor", "id": "evt-10001" },
  "contentRef": "content_synth_0001",
  "capturedAt": "2026-10-01T09:14:30Z",
  "collectedAt": "2026-10-01T09:15:04Z",
  "availability": "available",
  "provenance": {
    "originType": "observation",
    "provider": "synthetic-monitor",
    "sourceEventId": "evt-10001",
    "sourceAccountRef": { "owner": "synthetic-monitor", "id": "acct_synth_0001" },
    "collectorRef": { "owner": "team5.connector", "id": "conn_synth_monitor_01" }
  }
}
```

`contentRef` is an opaque illustration, not an agreed URI ([D-08](#14-decision-register)).

---

## 8. Proposed Observation Ingestion

All of §8 is **Proposed**. Not implemented. `IncidentIntake` remains the manual/fixture path.

### 8.1 Purpose

An Observation is a normalized provider signal delivered by Team 5's connector. Team 4 decides whether it becomes an Incident and event Evidence. Organization comes from trusted connector context (CT-01), not from the body.

### 8.2 Fields

| JSON key | Type | Required | Nullable | Validation | Purpose |
|---|---|---|---|---|---|
| `source` | string | Required | No | Non-empty | Provider identifier, for example `synthetic-monitor`. |
| `sourceAccountRef` | `ExternalRef` | Required | No | Non-empty owner and id. Must be the stable provider account identity, not a connector registration or connection id ([D-23](#14-decision-register)). Must be authorized for the authenticated connector registration (Stage 1). Format Needs Team 5 Confirmation ([D-09](#14-decision-register)). | Provider account used for idempotency scope and source-account authorization. |
| `sourceEventId` | string | Required | No | Non-empty, opaque. Must be provider-issued (or derived from provider-issued values by a documented deterministic rule); never invented by the sender (§10.9). | Provider event id. Part of provider-event identity. |
| `occurredAt` | timestamp | Required | No | Timezone-aware; normalized to UTC `Z` for processing | Source event time. |
| `occurredAtSupplied` | string | Optional | Yes | Original lexical timestamp when it differs from the normalized form, or whenever the source clock is untrusted (§8.8) | Provenance of the supplied clock. Not used as the equality instant. |
| `receivedAt` | timestamp | Required | No | Timezone-aware | When the **connector** received the event from the provider. Not the durable ingestion receipt time (§3.4). |
| `submittedAt` | timestamp | Optional | Yes | Timezone-aware | When the connector sent this delivery, if it supplies that time. |
| `serviceRef` | `ExternalRef` | Optional | Yes | Provider's service id, not the canonical service ref | Input to service resolution (§8.4). |
| `externalSeverity` | string | Optional | Yes | Non-empty if present | Provider severity. Not canonical severity (§8.3). |
| `title` | string | Required | No | Trimmed, 1–255 | Becomes the incident title. |
| `description` | string | Optional | Yes | Trimmed; empty becomes `null` | Incident and event-evidence description. |
| `provenance` | `Provenance` | Required | No | Schema in §7.4. `originType` must be `observation` (Stage 1). `collectorRef` and `sourceAccountRef` must match the authenticated connector registration (Stage 1). `provider` and `sourceEventId` consistency is Stage 2 (§8.5, §9.3). | Copied unchanged onto event Evidence. |
| `idempotencyKey` | string | Required | No | Non-empty, opaque. Missing, `null`, or empty after trim is a Stage 1 `INVALID_REQUEST`: no receipt. | Sender delivery token. Delivery metadata, not provider-event identity ([D-09](#14-decision-register), [D-22](#14-decision-register)). |
| `correlationId` | string | Required | No | Non-empty | Trace id. |

v0.1 required `source` to be "registered for the organization's connector" in the field table, and also treated an unregistered source as a post-receipt rejection. Those are not the same check. §9.3 splits them. This field table only requires a non-empty `source` at schema level.

### 8.3 Severity mapping

- Provider severity is never stored as canonical severity.
- Team 4 owns the mapping rules from (`source`, `externalSeverity`) to canonical `severity`. The mapping is versioned.
- Each processing attempt that applies a mapping records `severityMappingVersion` and `mappedSeverity` on that attempt (§9.2). History is not overwritten.
- **Proposed:** missing or unmapped severity yields `unresolved` / `SEVERITY_UNMAPPED` and creates no incident. No silent default.
- The version identifier format, where the mapping document lives, and who publishes a version are Needs Team 5 Confirmation ([D-05](#14-decision-register)). Team 4 owns what the mapping means.

Illustrative mapping used only by the fixtures (not an agreed catalog):

| `source` | `externalSeverity` | Version `synthetic-monitor-severity/v1` | Version `synthetic-monitor-severity/v2` |
|---|---|---|---|
| `synthetic-monitor` | `SEV1` | `critical` | `critical` |
| `synthetic-monitor` | `SEV2` | `high` | `critical` |
| `synthetic-monitor` | `SEV3` | `medium` | `medium` |
| `synthetic-monitor` | `SEV4` | `low` | `low` |

`v2` is the corrected mapping used by F-13. The version strings are examples, not a confirmed format.

A controlled reprocessing appends a new attempt. It records the new version and the new `mappedSeverity`. It does not alter the earlier attempt and it does not create another incident.

### 8.4 Service resolution

`serviceRef` on an Observation is the provider's identifier. It is resolved to the incident's canonical `serviceRef` using trusted service ownership for the organization. Catalog ownership is Needs Coordinator Confirmation ([D-03](#14-decision-register)).

**Proposed:** a missing or unresolvable service yields `unresolved` / `SERVICE_UNRESOLVED` and no incident. A service that resolves into another organization is unresolvable, and its existence is not disclosed.

### 8.5 Provenance

- Provider event ids stay opaque. They are not parsed and not reused as Team 4 ids.
- Event Evidence inherits the observation `provenance` unchanged, including `provider`, `sourceEventId`, `sourceAccountRef`, and `collectorRef`. Processing must not replace that provider with a platform, connector-runtime, or Team 4 identity.
- Separately collected Evidence does not inherit this object (§7.2).

**Proposed provenance checks ([D-07](#14-decision-register), [D-21](#14-decision-register)).** Checks split by what they protect. Binding checks protect authorization and the idempotency namespace, so they run before any receipt or identity reservation. Consistency checks compare already-authorized body fields.

| Check | Stage | Failure |
|---|---|---|
| `provenance.originType` is `observation` | 1 (schema) | `INVALID_REQUEST`. No receipt. |
| `provenance.collectorRef` equals the authenticated connector registration instance | 1 (authorization) | Platform denial. No receipt, no reservation. |
| Top-level `sourceAccountRef` is authorized for the authenticated connector registration | 1 (authorization) | Platform denial. No receipt, no reservation. |
| `provenance.sourceAccountRef` equals top-level `sourceAccountRef` | 1 (authorization binding) | Platform denial. No receipt, no reservation. |
| `provenance.provider` equals `source`, and `provenance.sourceEventId` equals top-level `sourceEventId` | 2 (domain consistency) | Receipt kept. `rejected` / `PROVENANCE_MISMATCH`. |

A caller cannot choose another collector or source account through payload fields. Whether the receiving boundary *derives* `collectorRef` from the authenticated registration instead of accepting it from the body (and then rejecting any differing value) is Needs Team 5 Confirmation under [D-21](#14-decision-register). Either way, the stored value must equal the authenticated registration. Whether `provider`/`sourceEventId` consistency should also move to Stage 1 remains [D-21](#14-decision-register). Revision `0.2.1-draft` records Team 5's proposal to derive the authoritative collector identity from the authenticated registration and to validate access to the stable source account ([D-21](#14-decision-register), [D-23](#14-decision-register)). That proposal is not jointly accepted, so those questions stay unresolved.

### 8.6 Processing rules

**Proposed Phase 1 ([D-19](#14-decision-register)).**

1. Stage 1 validation (§9.3). Failure: no durable receipt and no processing outcome.
2. Normalize (§10.4) and compute the idempotency identity and payload fingerprint.
3. Atomically reserve or locate that identity and persist the receipt in the same transaction (§10.4).
4. Stage 2 checks (§9.3): provenance consistency, service resolution, and severity mapping. Existing-identity fingerprint conflicts were already handled during atomic reservation (§10.4).
5. Store the mandatory event content in content storage and obtain its `contentRef` (§9.5.2). Failure follows §8.6.1.
6. On success, in the completion commit unit (§9.5.1), create one Incident in status `open`, exactly one event Evidence whose provenance is the observation's provenance, and the observation-to-Incident binding. Record the mapping version on the attempt.
7. Do not collect further evidence in this operation. Further collection is a separate operation unless a later joint agreement says otherwise.
8. Publish the processing attempt and the audit intents (§11.4).

An ingestion outcome is `completed` when the incident and the event Evidence are stored, including a valid `contentRef` for that event Evidence. It is not `partial` merely because logs, metrics, or traces have not been collected.

`partial` is for an operation that was responsible for collecting a specific item and stored only part of it, or stored an `unavailable` marker for an item in that operation's scope. It is not a statement that optional future collection has not run.

### 8.6.1 Mandatory event Evidence storage failure

**Proposed ([D-07](#14-decision-register), [D-08](#14-decision-register), [D-19](#14-decision-register)).** The event Evidence is mandatory for Phase 1 ingestion. A receipt may already be durable when processing starts, but processing must not report `completed` unless the event content has a valid stored-content reference.

| Failure class | Processing behavior | Incident and Evidence behavior |
|---|---|---|
| Transient event-content storage failure | Keep the receipt. The attempt is `retrying` with `EVENT_EVIDENCE_STORAGE_RETRYING`; it is not `completed` or `partial`. Apply the bounded policy in D-12. | **Proposed:** do not expose a completed Incident or an `available` event Evidence before storage succeeds. Whether provisional, non-canonical rows may exist internally is Needs Team 5 Confirmation. |
| Permanent event-content storage failure | Keep the receipt. **Proposed:** terminal `unresolved` with `EVENT_EVIDENCE_STORAGE_FAILED`, not `completed` and not `partial`. | No canonical `available` event Evidence exists without a valid `contentRef`. This draft proposes no canonical Incident result for this failed ingestion attempt. Whether a durable `unavailable` diagnostic marker is retained, and whether an Incident may be held in a non-completed provisional state, are Needs Team 5 Confirmation. |

This rule applies only to the mandatory event Evidence in ingestion. Missing optional logs, metrics, or traces do not trigger this failure; they are separate collection operations (§7.2 and F-04).

Grouping several provider events into one existing incident is [D-20](#14-decision-register) and is not part of this draft. A new provider-event identity still proposes one new incident. An identical repeat of an existing provider-event identity does not (§10.6).

### 8.7 Example — Observation

```json
{
  "source": "synthetic-monitor",
  "sourceAccountRef": { "owner": "synthetic-monitor", "id": "acct_synth_0001" },
  "sourceEventId": "evt-10001",
  "occurredAt": "2026-10-01T09:14:30Z",
  "occurredAtSupplied": null,
  "receivedAt": "2026-10-01T09:14:58Z",
  "submittedAt": "2026-10-01T09:14:59Z",
  "serviceRef": { "owner": "synthetic-monitor", "id": "checkout-api-prod" },
  "externalSeverity": "SEV2",
  "title": "Checkout API error rate above threshold",
  "description": "Synthetic monitor reported a 12% HTTP 5xx rate over 5 minutes.",
  "provenance": {
    "originType": "observation",
    "provider": "synthetic-monitor",
    "sourceEventId": "evt-10001",
    "sourceAccountRef": { "owner": "synthetic-monitor", "id": "acct_synth_0001" },
    "collectorRef": { "owner": "team5.connector", "id": "conn_synth_monitor_01" }
  },
  "idempotencyKey": "idem_synth_0001",
  "correlationId": "corr-synth-0001"
}
```

`sourceAccountRef` uses `ExternalRef` only as an illustration. Team 5 has not confirmed that shape ([D-09](#14-decision-register), [D-23](#14-decision-register)). In the fixtures, the authenticated connector registration `conn_synth_monitor_01` is authorized for `acct_synth_0001` unless a fixture says otherwise.

### 8.8 Clock skew

**Open ([D-16](#14-decision-register)).** No tolerance in seconds is defined. Team 4 and Team 5 have to set both the tolerance and whether a breach is warning-only or blocking.

| Situation | This draft |
|---|---|
| `occurredAt` is far in the future relative to durable receipt time | Detect and record. Accept, flag, or reject: Open. |
| `occurredAt` is far in the past | Detect and record. Accept, flag, or reject: Open. |
| Source clock missing | Schema requires `occurredAt`, so absence is a Stage 1 rejection. A connector flag that the clock is unreliable is Open. |
| Original lexical timestamp | **Proposed:** retain it in `occurredAtSupplied` when the supplied form is not already canonical UTC `Z`, and on every event the source clock is untrusted. Do not discard it as part of normalization. |
| Equality | Uses the normalized UTC instant of `occurredAt`, not the lexical form. |

Until a tolerance is confirmed, this draft does not treat skew as a processing failure and does not invent a cutoff.

---

## 9. Receipt acknowledgment and processing outcome

**Receipt and processing are separate.** A receipt confirms durable storage of an accepted observation. It does not mean an incident exists. A processing attempt is a later, durable result. All of §9 is **Proposed**. Sync versus async, and how the caller reads the outcome, are Needs Team 5 Confirmation ([D-11](#14-decision-register)). Revision `0.2.1-draft` records Team 5's proposal of an asynchronous durable receipt and a tenant-authorized processing-status query. That proposal is not jointly accepted. HTTP methods, paths, and status codes remain unset.

### 9.1 Receipt acknowledgment

| JSON key | Required | Nullable | Description |
|---|---|---|---|
| `deliveryId` | Required | No | Assigned when the idempotency identity is first reserved. Reused for every identical repeat. |
| `observationId` | Required | No | Stored observation. |
| `receiptStatus` | Required | No | `received` only. |
| `receivedAt` | Required | No | Durable ingestion receipt time. Not Observation `receivedAt`. |
| `correlationId` | Required | No | From the observation. |

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000001",
  "observationId": "33333333-3333-4333-8333-000000000001",
  "receiptStatus": "received",
  "receivedAt": "2026-10-01T09:15:00Z",
  "correlationId": "corr-synth-0001"
}
```

Stage 1 rejection does not return this object and does not create a processing attempt. **Proposed** refusal envelope, matching `api/app/core/errors.py`:

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "The request is invalid.",
    "details": [
      { "path": "body.title", "message": "Field required" }
    ]
  }
}
```

HTTP status codes are [D-11](#14-decision-register).

### 9.2 Processing attempt

Attempts are append-only once they reach a terminal status (`completed`, `rejected`, `unresolved`, `partial`). The current attempt may move `pending` → `retrying` → a terminal status. That progression is the same attempt. A later controlled reprocessing adds a new attempt and does not modify earlier terminal attempts.

| JSON key | Required | Nullable | Rule |
|---|---|---|---|
| `deliveryId` | Required | No | Matches the receipt. |
| `observationId` | Required | No | Matches the receipt. |
| `attempt` | Required | No | Integer, starting at 1. |
| `attemptTrigger` | Required | No | `ingestion` for attempt 1. `controlled_reprocessing` for any later attempt (§9.4). |
| `processingStatus` | Required | No | `pending`, `retrying`, `completed`, `rejected`, `unresolved`, `partial`. |
| `incidentId` | Required | Yes | The Incident bound to this observation (§9.5.1) when this attempt reached its status, or `null` if no binding exists. Non-null for `completed` and `partial`. For `rejected` or `unresolved`, non-null only when an earlier attempt already bound an Incident (failed reprocessing, F-22); this attempt did not create it. Null for `pending` and `retrying` on first ingestion. |
| `evidenceIds` | Required | No | Evidence created by this attempt. Empty until then. |
| `severityMappingVersion` | Required | Yes | The mapping version applied on this attempt. Null when mapping did not run. Immutable once the attempt is terminal. |
| `mappedSeverity` | Required | Yes | Canonical severity that version produced. Null when mapping did not run. |
| `errorCode` | Required | Yes | Null for `pending` and `completed`. Non-null for `rejected`, `unresolved`, and `partial`. For `retrying`, a non-terminal failure code. |
| `errorMessage` | Required | Yes | Safe text. No payload, credentials, or internals. Null when `errorCode` is null. |
| `correlationId` | Required | No | The correlation of the request that started this attempt (§9.4). For `ingestion`, equal to the receipt `correlationId`. For `controlled_reprocessing`, the reprocessing request's correlation, which need not equal the receipt's. |
| `processingStartedAt` | Required | Yes | Null while `pending` before a worker starts. |
| `processedAt` | Required | Yes | Set when the attempt reaches a terminal status. Null while `pending` or `retrying`. |

| Status | Meaning | Incident created | Retry |
|---|---|---|---|
| `pending` | Durably received. Processing has not finished and is not in a retry wait. | No | Not yet. |
| `retrying` | A transient failure occurred. Bounded retries remain. | No | In progress. Counts are [D-12](#14-decision-register). |
| `completed` | This attempt finished the work it was responsible for. For ingestion, that is the incident plus event Evidence. | Yes, unless this attempt is an identical duplicate of work that already completed (§10.6), in which case `incidentId` is the existing incident and `evidenceIds` is empty. | No. |
| `rejected` | Permanent domain failure after receipt. | No | Not retried. A corrected payload is a new delivery only if it is not the same idempotency identity with conflicting content (§10.7). |
| `unresolved` | Valid observation, but required context is missing, or retries were exhausted. | No | Automatic retries stop. Controlled reprocessing is [D-12](#14-decision-register). |
| `partial` | This attempt created the incident (or the collection parent) and at least one evidence item in its scope is `partial` or `unavailable`. | Yes | Follow-up collection is a separate operation ([D-19](#14-decision-register)). |

**Proposed error codes:** `PROVENANCE_MISMATCH`, `SOURCE_NOT_REGISTERED`, `SERVICE_UNRESOLVED`, `SEVERITY_UNMAPPED`, `PROCESSING_RETRY_EXHAUSTED`, `EVENT_EVIDENCE_STORAGE_RETRYING`, `EVENT_EVIDENCE_STORAGE_FAILED`, `EVIDENCE_PARTIAL`, `EVIDENCE_UNAVAILABLE`. `IDEMPOTENCY_CONFLICT` is not a processing-attempt error: it is returned during existing-identity lookup before a second delivery is accepted (§10.7).

`SOURCE_NOT_REGISTERED` is a Stage 2 domain outcome. It is not the Stage 1 connector or source-account authorization failure. See [D-21](#14-decision-register).

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000001",
  "observationId": "33333333-3333-4333-8333-000000000001",
  "attempt": 1,
  "attemptTrigger": "ingestion",
  "processingStatus": "completed",
  "incidentId": "11111111-1111-4111-8111-000000000001",
  "evidenceIds": ["22222222-2222-4222-8222-000000000001"],
  "severityMappingVersion": "synthetic-monitor-severity/v1",
  "mappedSeverity": "high",
  "errorCode": null,
  "errorMessage": null,
  "correlationId": "corr-synth-0001",
  "processingStartedAt": "2026-10-01T09:15:01Z",
  "processedAt": "2026-10-01T09:15:04Z"
}
```

The caller-visible current state is the latest attempt plus the receipt. Older attempts remain stored. Whether an Incident exists is decided by the observation-to-Incident binding (§9.5.1), not by the latest attempt's status: a failed reprocessing attempt after a completed one does not remove the Incident (F-22).

### 9.3 Validation stages

**Proposed ([D-11](#14-decision-register)).** v0.1 was inconsistent: §8.2 treated source registration as input validation, and §9.2 treated an unregistered source as a post-receipt `rejected` outcome. This draft separates authorization and schema checks from domain processing. The line between "source-account authorization" and "domain source registration" is not fully defined by v0.1. That line is [D-21](#14-decision-register) and is Needs Team 5 Confirmation. This draft does not invent the missing field-level rule.

#### Stage 1 — before durable receipt

A failure here does **not** create a receipt, a `deliveryId`, an observation row, or a processing attempt.

| Check | Notes |
|---|---|
| Authentication and identity | CT-01. Team 1. |
| Organization / tenant context | Trusted context present. A body `organizationId` does not establish it and is rejected as unexpected. |
| Tenant membership and authorization | Caller may act in that organization. |
| Connector authorization | This connector registration may submit for this organization. |
| Source-account authorization | The authenticated connector registration is authorized for the stable `sourceAccountRef` ([D-23](#14-decision-register)). The credential or registry check itself is Team 5 / Team 1. Failure happens before identity reservation, so an unauthorized caller cannot reserve or probe identities in another account's scope (F-19). |
| Collector and source-account binding | `provenance.collectorRef` equals the authenticated registration; `provenance.sourceAccountRef` equals top-level `sourceAccountRef` (§8.5, F-15). |
| Request integrity and schema | Required fields, types, non-empty strings in §8.2 (including `idempotencyKey`, F-16), `provenance.originType` `observation`, timezone-aware timestamps, no unknown fields. |
| Duplicate JSON keys | Reject before ordinary parsing discards the earlier value. Not implemented today (G-7). |
| Ambiguous aliases | Reject both snake_case and camelCase for the same field. |

**Proposed** error code for schema, alias, and duplicate-key failures: `INVALID_REQUEST`. Authorization failures use the platform's denial. Neither is a processing status.

#### Stage 2 — after durable receipt

The receipt from Stage 1 stays. The attempt records a terminal status. It must not be `completed` when one of these checks fails.

| Check | Proposed outcome | Why this stage |
|---|---|---|
| Domain source registration, if it is not the same fact as source-account authorization | `rejected` / `SOURCE_NOT_REGISTERED` | v0.1 already had this code on the processing outcome. Whether it collapses into Stage 1 is [D-21](#14-decision-register). |
| Provenance consistency (`provider` and `sourceEventId` match the observation) | `rejected` / `PROVENANCE_MISMATCH` | Domain validity of an already accepted body. Structural absence of `provenance` is Stage 1. |
| Service resolution and ownership | `unresolved` / `SERVICE_UNRESOLVED` | Depends on catalog data ([D-03](#14-decision-register)). |
| Severity mapping | `unresolved` / `SEVERITY_UNMAPPED` | Depends on mapping version ([D-05](#14-decision-register)). |
| Incident grouping | Not in this draft | [D-20](#14-decision-register). |
| Evidence relationship validation | `rejected` when a supplied evidence reference is outside the incident or organization | Applies to collection and RCA, not to the observation body itself. |

### 9.4 Controlled reprocessing

**Proposed ([D-26](#14-decision-register)). Not implemented.** Transport, authorization, and request shape are [D-11](#14-decision-register) and Needs Team 5 Confirmation.

Controlled reprocessing is a deliberate, authorized request to process an already-received observation again. It differs from an identical duplicate delivery, which never starts processing (§10.5, F-10).

Rules:

1. The stored observation is immutable. Reprocessing never edits the observation, its receipt, or its business fingerprint. "Repair" means correcting the context processing depends on (service catalog entry, severity mapping version). Wrong observation content is a provider revision (§10.9), not reprocessing.
2. Each reprocessing request appends one new attempt with `attemptTrigger` `controlled_reprocessing`. Earlier terminal attempts are not modified.
3. If no Incident is bound to the observation, a successful reprocessing attempt creates the first Incident and its mandatory event Evidence and the binding, in the completion commit unit (§9.5.1). This happens at most once per observation.
4. If an Incident is already bound, a successful reprocessing attempt updates that Incident (for example corrected severity, F-13) and does not create another Incident or another event Evidence.
5. A failed reprocessing attempt records its terminal status and leaves the bound Incident, its Evidence, and earlier attempts unchanged (F-22).
6. Concurrent reprocessing requests for one observation must not create two Incidents. The binding is the guard. How concurrent requests are serialized is Needs Team 5 Confirmation.
7. Whether a retried reprocessing *request* (the same request delivered twice) creates one attempt or two is Needs Team 5 Confirmation. Either way, no second Incident results.

Revision `0.2.1-draft` records Team 5's proposal that conflicting work for the same observation be serialized and that a retried reprocessing request be idempotent ([D-26](#14-decision-register)). The proposal is not jointly accepted, so rules 6 and 7 stay unresolved. Transport remains [D-11](#14-decision-register).

**Three correlation IDs.**

| Correlation | Where it lives | Set by | Rule |
|---|---|---|---|
| Original observation correlation | Observation `correlationId` and receipt `correlationId` | Connector, on ingestion | Immutable. Reprocessing never rewrites it. |
| Reprocessing request correlation | The reprocessing request | The authorized requester or the platform | New for each reprocessing request. It need not equal, and normally does not equal, the original observation correlation. |
| Processing attempt correlation | Attempt `correlationId` | Receiving boundary or worker | Attempt 1 (`ingestion`): the original observation correlation. Reprocessing attempts: that request's correlation. Recovery of an interrupted attempt keeps that attempt's correlation (§9.5.1). |

Audit intents for an attempt use that attempt's correlation and carry `deliveryId` and `observationId`, so they join back to the original observation without reusing its correlation id.

### 9.5 Completion commit boundary and recovery

**Proposed ([D-24](#14-decision-register)). Needs Team 5 Confirmation. Not implemented.** This section states required effects. It does not prescribe tables, locks, or a storage product.

#### 9.5.1 Completion commit unit

A processing attempt may report `completed` only after all of the following are durably committed:

| Item | Why it is mandatory |
|---|---|
| Canonical Incident | The result of ingestion. |
| Mandatory event Evidence metadata, including a valid `contentRef` | `completed` requires stored event content (§8.6.1). |
| Observation-to-Incident binding | One observation binds to at most one Incident. Recovery and reprocessing use it to avoid a second Incident. |
| Terminal processing result (`completed`) | The caller-visible outcome. |
| Associated audit intents (`incident.created`, `evidence.recorded`) | §11.4: domain change and audit intent commit together. |

**Proposed default.** All five commit in one local database transaction. If that transaction fails or the process crashes before commit, none of them exists, the attempt is still non-terminal (`pending` or `retrying`), and recovery resumes the same attempt. Revision `0.2.1-draft` records Team 5's Phase 1 proposal to use that single local transaction for the canonical records, the observation binding, the terminal processing result, and the audit intents. The proposal is not jointly accepted. External content storage stays outside the transaction (§9.5.2). The minimum invariant below remains in force until joint acceptance.

**Minimum invariant if Team 5 cannot commit all five together.** The Incident, the event Evidence metadata, the binding, and their audit intents must still commit together. No Incident without a binding. No binding without its Incident. The terminal result may then commit in a later step. If the process crashes in between:

- The attempt is not terminal and must not be reported `completed` until the terminal result commits.
- Recovery resumes the same attempt (same `attempt` number and correlation). It finds the binding, does not create another Incident or Evidence, and records `completed` with the bound `incidentId`.
- Audit intents already committed with the canonical rows are not written again.
- An identical duplicate delivery during that window returns the non-terminal state (§10.5), not `completed`.

Whether the canonical rows are readable by other callers in that window, and how recovery is triggered, are Needs Team 5 Confirmation. F-23 covers this case.

#### 9.5.2 Content storage and `contentRef`

External content storage and the database are **not** assumed to be one atomic transaction. This draft claims no such mechanism unless Team 5 confirms one ([D-24](#14-decision-register)).

| Point | Required behavior |
|---|---|
| Content write | Happens before the completion commit unit. A `contentRef` may be recorded only after storage reports the content durably stored. |
| Crash or failure after content write, before the commit unit | The stored bytes are orphaned. No Evidence references them. Processing resumes or retries without reporting `completed`. Orphans must never be presented as Evidence. Cleanup or reuse of orphaned content is Needs Team 5 Confirmation. |
| Retry after an orphaned write | Must result in exactly one event Evidence referencing exactly one valid `contentRef`. Whether the retry reuses the earlier stored object or writes a new one is Needs Team 5 Confirmation. |
| Commit unit fails after content write | Same as above: nothing canonical exists; the content is orphaned. |
| `contentRef` recorded but content later unreadable | Not a CT-04 ingestion outcome. Integrity and access verification are [D-08](#14-decision-register). |

F-24 covers recovery across this boundary.

---

## 10. Idempotency, duplicates and failures

### 10.1 Three identities

| Identity | Proposed key | Question it answers |
|---|---|---|
| Idempotency / provider-event identity | See §10.2 | "Have we already accepted this event for this tenant, provider, and stable source account?" |
| Sender token | `idempotencyKey` | "Which client retry is this?" |
| Canonical incident identity | `incidentId` | "Which Team 4 incident resulted?" |

One provider event can be retried many times. Several provider events might later group into one incident ([D-20](#14-decision-register)); this draft does not do that. Incident ids are not derived from provider ids.

### 10.2 Idempotency scope

**Proposed ([D-09](#14-decision-register)).** The scope dimensions are:

1. Tenant identity (`organizationId` from trusted context).
2. Provider / source identity (`source`).
3. Stable source-account identity (`sourceAccountRef`, [D-23](#14-decision-register)).
4. Provider event identity (`sourceEventId`).

**Replaceable connector registration is excluded (Proposed, [D-23](#14-decision-register)).** v0.2 previously listed "the connector identity from registration" in dimension 2. That is removed. The connector registration instance (`provenance.collectorRef`) authenticates the caller and records which connection collected the data, but provider-event identity must not depend on it. Reconnecting the same provider account, or replacing its connector registration, must not make an already-accepted event look new and must not create another Incident for it (F-18). Stage 1 still requires the new registration to be authorized for the source account.

The final canonical key structure depends on agreed identifier formats ([D-01](#14-decision-register)) and the source-account contract (Needs Team 5 Confirmation). Until those exist, this draft does not freeze a column list or a hash input beyond the four dimensions.

**Role of `idempotencyKey` ([D-09](#14-decision-register), [D-22](#14-decision-register)).**

- It is **mandatory** (§8.2). Missing, `null`, or empty is a Stage 1 `INVALID_REQUEST`. No receipt, no identity reservation, no attempt (F-16).
- It is **delivery metadata**: it names the sender's delivery and retries. It is not business content, not provider-event identity, and not part of the canonical uniqueness key above.
- **Provider-event identity** is the four dimensions above. It decides whether an event was already accepted.
- Senders should keep the same token when retrying the same delivery. A *changed* token with identical business content and identical provider-event identity is an identical duplicate (§10.5), not a conflict.
- Reuse of one token with **different** provider-event identity or **different** business content is [D-22](#14-decision-register), which remains **Open**. Two candidate policies, neither chosen as the contract rule:

| Candidate | Same token, same provider-event identity, changed content | Same token, different provider-event identity |
|---|---|---|
| A: token is diagnostic metadata only | `IDEMPOTENCY_CONFLICT` from the provider-event fingerprint (§10.7). The token adds nothing. | Treated as a new provider event. The token reuse may be logged. |
| B: token is also a delivery-level conflict key | `IDEMPOTENCY_CONFLICT` (§10.7). | Rejected as a token-reuse conflict before a second receipt. The error code is not defined in this draft. |

Under either candidate, provider-event identity and the business fingerprint still decide event duplicates and conflicts. Token reuse never overwrites a stored observation and never creates a second Incident for an existing provider event. Storage, scope, and retention of the token are Needs Team 5 Confirmation. F-17 shows both cases. Revision `0.2.1-draft` records Team 5's proposal of Candidate B, with the delivery-token binding scoped separately from provider-event deduplication. That proposal is not jointly accepted.

### 10.3 What is compared

**Proposed payload fingerprint ([D-10](#14-decision-register)).**

1. Reject duplicate JSON keys and ambiguous aliases (Stage 1) before comparison.
2. Normalize keys to one canonical camelCase set, so snake_case and camelCase of the same field match.
3. Normalize timestamps that are in the fingerprint to UTC `Z`.
4. Treat an omitted optional field and an explicit `null` as the same after defaults ([D-17](#14-decision-register)).
5. Apply documented defaults before hashing, so a defaulted field does not change the fingerprint.
6. Exclude request and delivery metadata from the business fingerprint: `idempotencyKey`, `correlationId`, server receipt time, durable receipt `receivedAt`, `processingStartedAt`, `processedAt`, **Proposed** Observation `receivedAt` and `submittedAt` (§3.4), and **Proposed** `provenance.collectorRef` ([D-23](#14-decision-register)). Do not put a transport receipt timestamp into business equality unless that exclusion is later reversed by agreement. `collectorRef` is excluded because a reconnect can legitimately change the registration instance for the same event (F-18).
7. Include business fields: `source`, `sourceAccountRef`, `sourceEventId`, normalized `occurredAt`, `serviceRef`, `externalSeverity`, `title`, `description`, and `provenance` without `collectorRef` (`originType`, `provider`, `sourceEventId`, `sourceAccountRef`). `occurredAtSupplied` is excluded so the lexical form cannot fork identity.
8. Serialize that object with object keys sorted lexicographically, array order preserved, UTF-8, and no insignificant whitespace. Hash algorithm: Needs Team 5 Confirmation.

Two payloads are identical for idempotency only when this fingerprint matches. They are conflicting when the idempotency identity matches and the fingerprint does not.

### 10.4 Atomic reservation

**Proposed.** Database uniqueness and transaction shape are Team 5's to design ([D-09](#14-decision-register)). The contract requires the following effects:

1. Normalize and Stage-1-validate the request.
2. Compute the canonical idempotency identity and payload fingerprint.
3. Atomically reserve that identity or locate the existing reservation.
4. If an existing identity has the same fingerprint, return its existing receipt and current attempt state. If it has a different fingerprint, return `IDEMPOTENCY_CONFLICT` before accepting a second delivery.
5. Only for a new identity, persist the durable receipt in the same local transaction as the reservation.
6. Concurrent identical requests must not create two receipts or two observations.

An existing-identity fingerprint conflict is neither a Stage 1 rejection nor a Stage 2 processing failure: it is detected by atomic identity lookup/reservation before a second receipt, observation, attempt, or incident can exist. If the new-identity transaction fails, neither its reservation nor its receipt is committed, and the caller does not receive `receiptStatus: received`.

### 10.5 Identical duplicate, by current state

An identical duplicate is a request whose idempotency identity and payload fingerprint both match an accepted observation. It is not assumed to have completed.

| Existing state | What the duplicate returns | What it must not do |
|---|---|---|
| `pending` | The existing receipt and `processingStatus` `pending` | Must not create a receipt, an incident, or a `completed` outcome. Must not reset the attempt. |
| `retrying` | The existing receipt and `processingStatus` `retrying` | Same. Must not start a second attempt. |
| `unresolved` | The existing receipt and the unresolved attempt, including its `errorCode` | Must not report `completed`. |
| `rejected` | The existing receipt and the rejected attempt | Must not reprocess the same payload. |
| `partial` | The existing receipt and the partial attempt | Must not create another incident. |
| `completed` | The existing receipt and the completed attempt | Must not create another incident or evidence row. |

For every row: do not create another receipt, do not create another incident, do not report `completed` unless the stored attempt is actually `completed`, and do not reset the stored state. Optional audit: `observation.duplicate_delivery` (CT-06).

### 10.6 Same provider event, same fingerprint, already accepted

This is the identical-duplicate row above. v0.1 said a duplicate provider event returns `completed` with the existing `incidentId`. That holds only when the stored attempt is `completed`. If the stored attempt is `pending`, `retrying`, `unresolved`, `rejected`, or `partial`, the duplicate returns that state (F-02b, F-10).

### 10.7 Changed content under the same identity

**Proposed ([D-10](#14-decision-register)).**

- The request is a conflict, not an identical duplicate.
- The original observation, receipt, and attempts stay as stored. Nothing is overwritten.
- No second incident is created.
- It is detected during atomic identity lookup/reservation, before a second delivery is accepted. No receipt, observation, or processing attempt is created for the conflicting request.
- The conflict is visible to the caller and is audited as `observation.idempotency_conflict`.
- **Proposed** caller-visible body (not a receipt and not a `completed` attempt):

```json
{
  "error": {
    "code": "IDEMPOTENCY_CONFLICT",
    "message": "This provider event was already accepted with different content.",
    "details": []
  }
}
```

HTTP status, whether a conflict row is stored, and the replay policy (may the sender retry the original payload, must they use a new provider event id) are Needs Team 5 Confirmation. This draft does not choose them.

### 10.8 Other failures

| Case | Stage | Result |
|---|---|---|
| Schema, alias, or duplicate-key failure, including missing `idempotencyKey` or non-`observation` `originType` | 1 | `INVALID_REQUEST`. No receipt. No attempt. |
| Authorization, connector, source-account, or collector-binding denial | 1 | Platform denial. No receipt. No identity reservation. No attempt. |
| Domain rule after receipt (provenance mismatch, and source registration if [D-21](#14-decision-register) leaves it here) | 2 | Receipt kept. `rejected`. |
| Unresolved service or severity | 2 | Receipt kept. `unresolved`. |
| Event Evidence content stored; no extra evidence collected | 2 | `completed`. Not `partial` ([D-19](#14-decision-register)). |
| Transient mandatory event Evidence storage failure | 2 | Receipt kept. `retrying` / `EVENT_EVIDENCE_STORAGE_RETRYING`. Never `completed` or `partial`. |
| Permanent mandatory event Evidence storage failure | 2 | Receipt kept. Proposed `unresolved` / `EVENT_EVIDENCE_STORAGE_FAILED`. Never `completed`; no `available` event Evidence without a valid `contentRef`. Details need Team 5 confirmation (§8.6.1). |
| A collection operation stores a truncated or missing item in its own scope | Collection | That operation may be `partial`. Ingestion is unchanged. |
| Transient processing failure | 2 | Attempt stays `retrying` until the bounded policy ends, then `unresolved` / `PROCESSING_RETRY_EXHAUSTED`. Counts are [D-12](#14-decision-register). |
| Local transaction failure while committing domain state and audit intent | Persistence | Neither is committed (§11.4, F-12). |
| Crash after canonical persistence, before the terminal result | Persistence | Attempt is not `completed`. Recovery finishes the same attempt from the binding without a second Incident (§9.5.1, F-23). |
| Crash after content write, before the completion commit unit | Persistence | Content is orphaned; no Evidence references it; never `completed` until the commit unit succeeds (§9.5.2, F-24). |
| Failed controlled reprocessing of an observation with a bound Incident | Reprocessing | New terminal attempt records the failure. Bound Incident and Evidence unchanged (§9.4, F-22). |

### 10.9 Provider event identity and changed provider content

**Proposed meaning ([D-25](#14-decision-register)).** Within one tenant, provider, and stable source account, `sourceEventId` identifies one **immutable provider event occurrence**. Its business content is fixed once accepted. Changed content under the same `sourceEventId` is therefore an `IDEMPOTENCY_CONFLICT` (§10.7), not an update.

Some providers expose a **mutable alert** whose id stays the same while severity, title, or state change. Those providers do not fit the occurrence meaning by default. How a revision of a mutable alert is represented is **Open** and Needs Team 5 Confirmation, because it depends on what each provider and connector can supply. Candidate approaches, none chosen:

| Candidate | `sourceEventId` carries | Effect |
|---|---|---|
| Revision-scoped event id | A provider-issued revision or update identifier, or a deterministic combination of provider-issued alert id and provider-issued revision, documented per connector | Each revision is a new provider event. Linking it to the existing Incident requires grouping ([D-20](#14-decision-register)), which is not defined. Without grouping it would create a new Incident, so this candidate cannot be enabled before D-20 is decided. |
| Stable alert id plus a separate revision field | The stable alert id. A new revision field (not defined in this draft) carries the provider revision | A revision becomes an explicit update path for the existing observation's Incident. Fingerprint, conflict, and audit rules for revisions would need to be redefined. |

**Until D-25 is decided** (Proposed interim rule):

- Updated content delivered under an already-accepted `sourceEventId` returns `IDEMPOTENCY_CONFLICT`. It does not overwrite the stored observation, does not update the Incident, and is audited as `observation.idempotency_conflict` (F-25).
- This interim rule can lose provider updates. That is a known limitation. Connectors for providers that emit mutable alerts should not be enabled for automatic ingestion until D-25 is settled. Revision `0.2.1-draft` records Team 5's proposal to enable mutable-alert ingestion only after a provider-specific revision policy is agreed. That proposal is not jointly accepted, and D-25 stays **Open**.

**Prohibited: inventing an event id to bypass a conflict.** A sender must not create a new `sourceEventId` that the provider did not issue (and that is not produced by a connector's documented deterministic rule from provider-issued values), in order to get past an identity or fingerprint conflict. Examples of prohibited values: the original id with a suffix, a random id, or an id derived from delivery time. Such a payload violates the observation contract even if it passes schema validation. Detection depends on what the connector and provider can prove. Whether Team 5 can verify provider-issued ids (and what the outcome code would be) is Needs Team 5 Confirmation under D-25. If it is not detected, the resulting second Incident is a connector conformance defect, not a valid contract outcome (F-26).

---

## 11. Tenant, permissions, approval and audit durability

### 11.1 Trusted organization context

- Organization comes from the authenticated identity or from the organization bound to a registered connector (CT-01).
- A caller-supplied organization id never establishes membership. **Proposed:** `organizationId` on an observation body is an unexpected field and fails Stage 1.
- Reads and writes stay inside the trusted organization. Another organization's resource is reported as not found.
- Organization id format is Needs Team 1 Input ([D-02](#14-decision-register)).

### 11.2 Actor identity and permissions

- `actorRef` and `reviewerRef` come from the authenticated identity. A different body-supplied actor is rejected.
- Permission checks use CT-01. Permission names are Team 1's and are not defined here.
- Team 5 enforces authentication, tenant scope, and permission checks at API and execution boundaries.

### 11.3 Review and remediation approval

Team 4 owns the workflow. Team 5 enforces it at execution boundaries (CT-07).

- AI output stays a proposal. Existing types already fix candidate `status` to `proposed`, `review_required` to `true`, and `requires_human_review` to `true`.
- Remediation must not run only because an agent recommended it. Before execution, the boundary checks: an approved `HumanReview` for that exact `fix_proposal`; the reviewer was permitted (CT-01); the requester may execute for that service; the approval is in the same organization and for that proposal.
- **Proposed:** a human actor is required for approval. How many approvals are required is Open.
- Denied review or execution is audited (CT-06).

### 11.4 Audit durability, outbox and recovery

**Proposed ([D-12](#14-decision-register)).** v0.1 required audit delivery to continue with no bound. This draft uses a bounded retry, then keeps the intent for controlled replay. Counts, intervals, and retention are not specified. They are Needs Team 5 Confirmation.

Local audit-intent persistence and external sink delivery are different:

| | Local audit intent | External sink delivery |
|---|---|---|
| When | Same local database transaction as the domain change | After commit, by an asynchronous dispatcher |
| If it fails | The domain change is not successful and must not be visible as committed | The domain change stays committed. The intent stays stored. Delivery is retried. |
| Owner | Team 4 requires the pairing. Team 5 implements the transaction. | CT-06 / Team 5 |

**Proposed sequence for a domain state change that must be audited:**

1. Prepare the domain change.
2. In one local database transaction, persist the domain change and the durable audit-outbox intent.
3. Commit both together.
4. If that transaction fails, the domain change is not successful. Nothing is left partially committed.
5. A dispatcher delivers the intent to the audit sink.
6. Delivery failures follow a bounded retry policy.
7. When retries are exhausted, the intent remains stored and can be replayed under an explicit controlled replay. Exhaustion does not delete the intent and does not roll back the domain change.

**Crash recovery.**

| Crash point | Required outcome |
|---|---|
| Before the local transaction commits | Neither the domain change nor the audit intent is committed. |
| After commit, before sink delivery | The outbox intent is still there. Recovery delivers it. |
| After the sink accepts the event, before delivery is marked successful | Redelivery uses a stable `eventId` (or an equivalent deduplication key the sink supports) so the sink does not record an uncontrolled duplicate. |

Bounded retry means a finite number of automatic attempts, then stop. Controlled replay means a deliberate later delivery of the same `eventId`. This draft does not set the number, the wait, or how long the intent is kept.

---

## 12. Synthetic acceptance fixtures

Documentation fixtures only. Not executable tests. All values are synthetic. Outcomes are **Proposed**. CT-06 and CT-07 rows are dependencies, not CT-04 implementation.

Organization `org_synth_0001` is trusted connector context and is not a body field. `sourceAccountRef` is `{ "owner": "synthetic-monitor", "id": "acct_synth_0001" }` unless a fixture says otherwise. Mapping version strings are illustrative ([D-05](#14-decision-register)).

### F-01 — Successful observation import and acknowledgment

**Scenario.** Valid observation, service resolves, `SEV2` maps under `synthetic-monitor-severity/v1`.

**Input.** §8.7.

**Preconditions.** Connector and source account are authorized. Service `checkout-api-prod` resolves to `service-catalog` / `svc_synth_checkout`. No prior event `evt-10001`.

**Expected receipt.** §9.1 example (`deliveryId` `44444444-4444-4444-8444-000000000001`).

**Expected processing.** §9.2 example: attempt 1, `completed`, `mappedSeverity` `high`, `severityMappingVersion` `synthetic-monitor-severity/v1`.

**Expected records.** Incident §6.2. Event Evidence §7.5 with the observation's provenance unchanged. No log, metric, or trace evidence.

**Expected audit (CT-06).** `incident.created` and `evidence.recorded`, correlation `corr-synth-0001`, written as outbox intents in the same transaction as those rows.

**Decisions.** D-05, D-07, D-09, D-12, D-19.

### F-02 — Duplicate delivery of a completed observation

**Scenario.** §8.7 is retried with the same identity and the same fingerprint after F-01 has `completed`.

**Preconditions.** F-01 attempt 1 is `completed`.

**Expected receipt.** The F-01 receipt, including the original `receivedAt`. No second `deliveryId`.

**Expected processing.** The F-01 attempt unchanged. Not a new attempt.

**Expected records.** Still one incident and one event Evidence.

**Expected audit (CT-06).** Optional `observation.duplicate_delivery`. No second `incident.created`.

**Decisions.** D-09, D-10.

### F-02b — Identical duplicate at each processing state

**Scenario.** For each row, a second request matches the accepted identity and fingerprint while attempt 1 is in that state. The completed row is F-02.

**Preconditions.** One accepted observation. No second provider event.

| Existing state | Receipt | Processing returned | Incident |
|---|---|---|---|
| `pending` | Existing | `pending`, `incidentId` null, `processedAt` null | None |
| `retrying` | Existing | `retrying`, same non-terminal `errorCode` | None |
| `unresolved` | Existing | `unresolved`, original `errorCode` (see F-10) | None |
| `rejected` | Existing | `rejected`, original `errorCode` | None |
| `partial` | Existing | `partial`, original `evidenceIds` | The original one only |
| `completed` | Existing | `completed` (F-02) | The original one only |

**Expected persistence.** No new receipt, observation, incident, evidence, or attempt. State is not reset. `completed` is returned only in the last row.

**Decisions.** D-10, D-12, D-20.

### F-03 — Invalid payload or unresolved service mapping

**F-03a — Stage 1 schema failure.** `title` is absent and `organizationId` is present. `sourceAccountRef` is the synthetic account above; other fields match §8.7 except `sourceEventId` `evt-10003`, `idempotencyKey` `idem_synth_0003`, `correlationId` `corr-synth-0003`, `externalSeverity` `SEV3`, and `description` `Latency p95 above 2s.`

**Expected receipt.** None.

**Expected processing.** None. `org_synth_9999` is not used for scope.

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "The request is invalid.",
    "details": [
      { "path": "body.title", "message": "Field required" },
      { "path": "body.organizationId", "message": "Extra inputs are not permitted" }
    ]
  }
}
```

**F-03b — Stage 2 unresolved service.** Body as §8.7 but `sourceEventId` `evt-10004`, `idempotencyKey` `idem_synth_0004`, `correlationId` `corr-synth-0004`, `externalSeverity` `SEV3`, `title` `Unknown service health check failing`, `description` null, and `serviceRef.id` `unknown-service-xyz`. Provenance `sourceEventId` is `evt-10004`.

**Expected receipt.** A new receipt (`deliveryId` `44444444-4444-4444-8444-000000000004`). Stage 1 passed.

**Expected processing.**

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000004",
  "observationId": "33333333-3333-4333-8333-000000000004",
  "attempt": 1,
  "attemptTrigger": "ingestion",
  "processingStatus": "unresolved",
  "incidentId": null,
  "evidenceIds": [],
  "severityMappingVersion": null,
  "mappedSeverity": null,
  "errorCode": "SERVICE_UNRESOLVED",
  "errorMessage": "The affected service could not be resolved for this organization.",
  "correlationId": "corr-synth-0004",
  "processingStartedAt": "2026-10-01T10:05:14Z",
  "processedAt": "2026-10-01T10:05:15Z"
}
```

Mapping does not run if service resolution fails first. **Proposed** order is service, then severity. If Team 5 needs the reverse, that is [D-11](#14-decision-register) and is not fixed here.

**Expected records.** None. **Audit.** `observation.unresolved`.

**Decisions.** D-03, D-11, D-21.

### F-04 — Ingestion completes without optional evidence; later collection keeps its own provenance

**Scenario.** Two operations. Ingestion does not collect logs or metrics. A later collection does, and that collection's provenance is the collector, not the monitor.

**F-04a — ingestion.** Input as §8.7 with `sourceEventId` `evt-10005`, `idempotencyKey` `idem_synth_0005`, `correlationId` `corr-synth-0005`, `externalSeverity` `SEV1`, `title` `Checkout API unavailable`, `description` `All synthetic checks failing for 3 minutes.`, provenance `sourceEventId` `evt-10005`, `occurredAt` `2026-10-01T11:00:00Z`.

**Preconditions.** Service resolves. `SEV1` maps to `critical` under `synthetic-monitor-severity/v1`. No separate collection has been requested.

**Expected receipt.** New receipt `44444444-4444-4444-8444-000000000005`.

**Expected processing.** `completed`, not `partial`. `incidentId` `11111111-1111-4111-8111-000000000005`. `evidenceIds` contains only `22222222-2222-4222-8222-000000000051`. `mappedSeverity` `critical`. `severityMappingVersion` `synthetic-monitor-severity/v1`. `errorCode` null.

**Expected event Evidence.** `evidenceType` `event`, `availability` `available`, `contentRef` `content_synth_0051`, `triggeredByObservationId` null, provenance:

```json
{
  "originType": "observation",
  "provider": "synthetic-monitor",
  "sourceEventId": "evt-10005",
  "sourceAccountRef": { "owner": "synthetic-monitor", "id": "acct_synth_0001" },
  "collectorRef": { "owner": "team5.connector", "id": "conn_synth_monitor_01" }
}
```

**F-04b — separate collection.** Not part of F-04a. A collector stores a truncated log and fails to store metrics. `triggeredByObservationId` is `33333333-3333-4333-8333-000000000005`.

**Expected collection outcome.** `partial` / `EVIDENCE_PARTIAL` for the collection operation only. F-04a's attempt stays `completed`.

**Expected log evidence** `22222222-2222-4222-8222-000000000052`:

```json
{
  "id": "22222222-2222-4222-8222-000000000052",
  "incidentId": "11111111-1111-4111-8111-000000000005",
  "investigationId": null,
  "triggeredByObservationId": "33333333-3333-4333-8333-000000000005",
  "evidenceType": "log",
  "description": "Log window 10:50Z–11:00Z was truncated at 10:57Z.",
  "sourceLabel": "Synthetic log store",
  "externalSourceRef": null,
  "contentRef": "content_synth_0052",
  "capturedAt": "2026-10-01T11:00:00Z",
  "collectedAt": "2026-10-01T11:02:00Z",
  "availability": "partial",
  "provenance": {
    "originType": "tool_execution",
    "provider": "synthetic-logs",
    "sourceEventId": null,
    "sourceAccountRef": null,
    "collectorRef": { "owner": "team5.connector", "id": "conn_synth_logs_01" }
  }
}
```

**Expected metric evidence** `22222222-2222-4222-8222-000000000053`: `evidenceType` `metric`, `availability` `unavailable`, `contentRef` null, `provider` `synthetic-metrics`, `collectorRef` `conn_synth_metrics_01`, same `triggeredByObservationId`. It must not use `available`.

**CT-07 dependency.** If a tool collects the bytes, the tool result must say whether content is complete, truncated, or missing. CT-04 maps that onto `availability`. The tool's provider stays on the evidence record.

**Decisions.** D-07, D-08, D-19.

### F-05 — Valid structured RCA response and invalid-output handling

**Expected receipt and processing outcome.** Not applicable. This is not observation ingestion.

**Input context (existing `InvestigationContext`).**

```json
{
  "investigationId": "55555555-5555-4555-8555-000000000001",
  "incident": {
    "externalIncidentRef": { "owner": "synthetic-monitor", "id": "evt-10001" },
    "summary": "Checkout API error rate above threshold",
    "occurredAt": "2026-10-01T09:14:30Z"
  },
  "evidence": [
    {
      "evidenceId": "22222222-2222-4222-8222-000000000001",
      "description": "Provider alert: HTTP 5xx rate 12% over 5 minutes on checkout-api-prod.",
      "sourceRef": { "owner": "synthetic-monitor", "id": "evt-10001" }
    }
  ]
}
```

**F-05a — valid output.** One `RootCauseCandidateDraft` with `status` `proposed`, `confidence` `0.4`, and one `supports` link to evidence `...0001`. **Expected:** one `RootCauseCandidate` with `reviewRequired` true, and a pending `HumanReview` for `subjectType` `candidate` (**Proposed**). Incident status does not change by itself.

**F-05b — invalid output.** `status` `confirmed`, extra field `autoRemediate`, `confidence` `1.7`, and an `evidenceId` not in the investigation.

| Defect | Rejected by existing code? | Proposed rule |
|---|---|---|
| `status` `confirmed` | Yes | AI output cannot confirm a cause. |
| `autoRemediate` | Yes (`extra="forbid"`) | AI output cannot carry execution instructions. |
| `confidence` `1.7` | No (G-5) | Reject values outside 0–1. |
| Evidence outside the investigation | No | Reject. |

**Proposed:** if any draft is invalid, the whole response is rejected and nothing is stored. Per-draft acceptance is Open. **Audit:** `rca.output_rejected`. **CT-07** owns transport and model selection.

### F-06 — Unauthorized review or remediation request

**Expected receipt and processing outcome.** Not applicable.

**F-06a.** Authenticated user `team1.user` / `user_synth_0042` has no approval permission. Body is a `HumanReview` with `decision` `approved`, `subjectType` `fix_proposal`, `subjectId` `88888888-8888-4888-8888-000000000001`, and `reviewerRef` `team1.user` / `user_synth_0001`.

**Expected.** Team 5 denies the call. The reviewer does not match the authenticated user. No `HumanReview` is stored.

**F-06b.** Fix proposal `...0001` has `requiresHumanReview` true and no approved review. An agent requests execution. **Expected.** Denied at the execution boundary. Nothing runs.

**Audit (CT-06).** `review.authorization_denied` and `remediation.execution_denied`.

### F-07 — Audit sink delivery fails after a durable local commit

**Scenario.** An authorized user moves incident `...0001` from `investigating` to `resolved`. The local transaction commits the status and the outbox intent. The sink then rejects delivery.

**Input facts.** `fromStatus` `investigating`, `toStatus` `resolved`, `actorRef` `team1.user` / `user_synth_0007`, `reason` `Connection pool limit restored; error rate back to baseline.`, `correlationId` `corr-synth-0007`, `occurredAt` `2026-10-01T13:00:00Z`.

**Expected audit intent (CT-04 payload; CT-06 owns the envelope).**

```json
{
  "eventId": "99999999-9999-4999-8999-000000000007",
  "eventType": "incident.status_changed",
  "organizationId": "org_synth_0001",
  "actorRef": { "owner": "team1.user", "id": "user_synth_0007" },
  "resourceType": "incident",
  "resourceId": "11111111-1111-4111-8111-000000000001",
  "occurredAt": "2026-10-01T13:00:00Z",
  "correlationId": "corr-synth-0007",
  "data": {
    "fromStatus": "investigating",
    "toStatus": "resolved",
    "reason": "Connection pool limit restored; error rate back to baseline."
  }
}
```

**Expected.** The incident status stays `resolved`. The outbox row stays. Automatic delivery uses a bounded retry policy and the same `eventId`. This draft does not require delivery to continue until success. After the bound, the row remains for controlled replay. Sink failure does not delete the intent and does not roll back the status.

**Decisions.** D-12.

### F-08 — Concurrent identical submissions

**Scenario.** Two or more requests for the same tenant, provider/source, stable source account, and provider event arrive concurrently. Their normalized business fingerprints match. Their `idempotencyKey`, `correlationId`, connector `receivedAt`, or `submittedAt` may differ; those are delivery metadata and do not make the business payload conflict. Body content otherwise matches §8.7.

**Preconditions.** No existing observation for that identity.

**Expected receipt.** One receipt. Every caller receives that same `deliveryId`, `observationId`, and `receivedAt`.

**Expected processing.** One observation. One attempt. Every caller sees that attempt's current state (`pending` if the race finishes at reservation). No caller sees `completed` unless the attempt has completed.

**Expected persistence.** One observation row. No second incident.

**Expected audit.** At most one `incident.created`, and only if processing later completes.

**Decisions.** D-09, D-10.

### F-09 — Conflicting payload under the same provider event

**Scenario.** F-01 is accepted. A later request uses the same tenant, provider/source, `sourceAccountRef`, and `sourceEventId` `evt-10001`, but `title` is `Checkout API latency above threshold`. The business fingerprint differs. `idempotencyKey` and `correlationId` may be the same or different; neither causes the conflict.

**Preconditions.** F-01 receipt and attempt exist.

**Expected receipt.** No new receipt. The F-01 receipt is unchanged. Atomic identity lookup detects the different business fingerprint before accepting the second delivery.

**Expected processing.** No new attempt. F-01 stays `completed` with `mappedSeverity` `high`. Caller receives `IDEMPOTENCY_CONFLICT` (§10.7), rather than a Stage 2 processing outcome. HTTP status is not specified.

**Expected persistence.** Original observation bytes unchanged. No second incident.

**Expected audit.** `observation.idempotency_conflict` with `correlationId` of the conflicting request and the original `observationId`.

**Decisions.** D-10, D-12.

### F-10 — Duplicate of unresolved work

**Scenario.** F-03b has finished as `unresolved` / `SERVICE_UNRESOLVED`. The same payload is submitted again.

**Preconditions.** Attempt 1 terminal and `unresolved`. Service mapping is still absent.

**Expected receipt.** The F-03b receipt. Not a new one.

**Expected processing.** The same unresolved attempt. `processingStatus` is not `completed`. `incidentId` is null.

**Expected persistence.** No incident. The unresolved attempt is not reset and not replaced.

**Expected audit.** Optional `observation.duplicate_delivery`. No `incident.created`.

**Decisions.** D-10, D-12, D-20.

### F-11 — Crash after commit and before sink delivery

**Scenario.** The F-07 transaction has committed. The worker crashes before the sink call.

**Preconditions.** Incident status is `resolved`. Outbox row `eventId` `99999999-9999-4999-8999-000000000007` is not marked delivered.

**Expected.** Status stays `resolved`. The intent is still stored. Recovery delivers that same `eventId`. The audit event is not lost. A later crash after the sink accepted the event but before the delivered mark still uses `eventId` so the sink can drop the duplicate.

**Decisions.** D-12.

### F-12 — Audit-record persistence failure

**Scenario.** The same transition as F-07 is attempted. The local transaction that would write the status and the outbox intent fails.

**Preconditions.** Incident is `investigating`. No outbox row for `corr-synth-0007`.

**Expected.** The caller is told the operation failed. Status stays `investigating`. No outbox row. No sink delivery. No partial commit of status without intent, or of intent without status.

**Decisions.** D-12.

### F-13 — Reprocessing after a severity mapping correction

**Scenario.** F-01 completed under `synthetic-monitor-severity/v1` with `mappedSeverity` `high` for `SEV2`. The mapping is corrected so `SEV2` is `critical` (§8.3, version `v2`). An authorized controlled reprocessing of observation `33333333-3333-4333-8333-000000000001` runs. The reprocessing request has its own correlation `corr-synth-0013`.

**Preconditions.** Attempt 1 is immutable and `completed`. An Incident is already bound to the observation (§9.5.1). The caller is allowed to reprocess. This is not an identical-duplicate retry.

**Expected receipt.** Unchanged, including its original `correlationId` `corr-synth-0001`. The reprocessing request's `corr-synth-0013` is **not** required to equal it, and the receipt is not rewritten (§9.4).

**Expected processing.** Attempt 1 remains `mappedSeverity` `high`, version `synthetic-monitor-severity/v1`, and `correlationId` `corr-synth-0001`. Attempt 2 is appended with the reprocessing request's correlation:

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000001",
  "observationId": "33333333-3333-4333-8333-000000000001",
  "attempt": 2,
  "attemptTrigger": "controlled_reprocessing",
  "processingStatus": "completed",
  "incidentId": "11111111-1111-4111-8111-000000000001",
  "evidenceIds": [],
  "severityMappingVersion": "synthetic-monitor-severity/v2",
  "mappedSeverity": "critical",
  "errorCode": null,
  "errorMessage": null,
  "correlationId": "corr-synth-0013",
  "processingStartedAt": "2026-10-02T09:00:00Z",
  "processedAt": "2026-10-02T09:00:02Z"
}
```

**Expected persistence.** The incident's current `severity` becomes `critical` and `updatedAt` changes. **Proposed.** No second incident. Attempt 1 is still readable. How severity history on the incident itself is stored beyond the attempts is Open ([D-05](#14-decision-register)).

**Expected audit.** `incident.severity_corrected` (**Proposed** event type) with both versions, both severities, `attempt` 2, `deliveryId`, `observationId`, and correlation `corr-synth-0013`. CT-06 owns delivery.

First-time Incident creation after repair is a different case and is F-20.

**Decisions.** D-05, D-11, D-12, D-26.

### F-14 — Mandatory event Evidence storage failure

**Scenario.** A valid new observation passes Stage 1, is durably received, and starts ingestion. The mandatory event Evidence content cannot be stored.

**Preconditions.** The input is otherwise valid and has a new provider-event identity. Connector and source account are authorized. Service resolution and severity mapping succeed. No Incident or canonical Evidence exists for this observation. The event content store first returns a transient error; a later variant returns a permanent error.

**Expected receipt behavior.** One durable receipt is returned before processing. It is retained for both failure variants:

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000014",
  "observationId": "33333333-3333-4333-8333-000000000014",
  "receiptStatus": "received",
  "receivedAt": "2026-10-03T09:15:00Z",
  "correlationId": "corr-synth-0014"
}
```

**Transient storage failure — expected processing.** Attempt 1 is `retrying` with `EVENT_EVIDENCE_STORAGE_RETRYING`. It is not `completed` and not `partial`. Bounded retry parameters are D-12 and are not specified. An identical duplicate returns this same receipt and retrying state.

**Permanent storage failure — expected processing.** After the storage failure is classified permanent, or after the bounded retry policy exhausts according to the eventual Team 5 storage contract, the proposed terminal result is:

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000014",
  "observationId": "33333333-3333-4333-8333-000000000014",
  "attempt": 1,
  "attemptTrigger": "ingestion",
  "processingStatus": "unresolved",
  "incidentId": null,
  "evidenceIds": [],
  "severityMappingVersion": "synthetic-monitor-severity/v1",
  "mappedSeverity": "high",
  "errorCode": "EVENT_EVIDENCE_STORAGE_FAILED",
  "errorMessage": "Mandatory event evidence content could not be stored.",
  "correlationId": "corr-synth-0014",
  "processingStartedAt": "2026-10-03T09:15:01Z",
  "processedAt": "2026-10-03T09:16:00Z"
}
```

**Expected Incident persistence.** No completed canonical Incident result is exposed for this ingestion attempt. Whether Team 5 keeps a provisional, non-canonical Incident row inside the processing implementation is Needs Team 5 Confirmation; it must not be presented as a completed Incident and it must not make retries create another Incident.

**Expected Evidence persistence and availability.** No Evidence may claim `availability: "available"` without a valid `contentRef`. This draft proposes no canonical event Evidence row for the permanent-failure result. Whether an `unavailable` diagnostic marker is retained for recovery is Needs Team 5 Confirmation; if retained, it is not the mandatory event Evidence required for `completed`.

**Expected audit.** CT-06 audit intent records `observation.event_evidence_storage_failed` with `deliveryId`, `observationId`, `correlationId`, failure classification, and the stable processing attempt identity. Its local intent follows §11.4. No `incident.created` or `evidence.recorded` audit event is emitted unless their corresponding canonical records committed.

**Decisions.** D-07, D-08, D-11, D-12, D-19.

### F-15 — Observation provenance: valid, invalid, and unauthorized collector binding

**Common preconditions.** The authenticated connector registration is `team5.connector` / `conn_synth_monitor_01`. It is authorized for source account `synthetic-monitor` / `acct_synth_0001` only. Each sub-case uses §8.7 with the stated changes and its own `sourceEventId`, `idempotencyKey`, and `correlationId` so no sub-case collides with another.

**F-15a — valid provenance.** §8.7 unchanged (F-01). `originType` `observation`; `collectorRef` equals the authenticated registration; `provenance.sourceAccountRef` equals top-level `sourceAccountRef`; `provider` equals `source`; `provenance.sourceEventId` equals `sourceEventId`. **Expected.** Receipt and processing as F-01.

**F-15b — wrong origin type.** `sourceEventId` and `provenance.sourceEventId` `evt-10151`, `idempotencyKey` `idem_synth_0151`, `correlationId` `corr-synth-0151`, `provenance.originType` `manual`. **Expected.** Stage 1. No receipt, no reservation, no attempt.

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "The request is invalid.",
    "details": [
      { "path": "body.provenance.originType", "message": "Input should be 'observation'" }
    ]
  }
}
```

**F-15c — substituted collector.** `evt-10152`, `idem_synth_0152`, `corr-synth-0152`, `provenance.collectorRef` `team5.connector` / `conn_synth_monitor_99`, which is not the authenticated registration. **Expected.** Stage 1 platform denial (CT-01; body not defined here). No receipt, no reservation. The stored record can never name a collector other than the authenticated one.

**F-15d — substituted source account inside provenance.** `evt-10153`, `idem_synth_0153`, `corr-synth-0153`. Top-level `sourceAccountRef` is `acct_synth_0001`, but `provenance.sourceAccountRef` is `synthetic-monitor` / `acct_synth_0002`. **Expected.** Stage 1 platform denial. No receipt, no reservation.

**F-15e — provider inconsistency (domain check).** `evt-10154`, `idem_synth_0154`, `corr-synth-0154`, `provenance.provider` `other-monitor`. Collector and source-account bindings are valid. **Expected receipt.** New receipt `44444444-4444-4444-8444-000000000154`. **Expected processing.**

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000154",
  "observationId": "33333333-3333-4333-8333-000000000154",
  "attempt": 1,
  "attemptTrigger": "ingestion",
  "processingStatus": "rejected",
  "incidentId": null,
  "evidenceIds": [],
  "severityMappingVersion": null,
  "mappedSeverity": null,
  "errorCode": "PROVENANCE_MISMATCH",
  "errorMessage": "Observation provenance does not match the observation source.",
  "correlationId": "corr-synth-0154",
  "processingStartedAt": "2026-10-04T09:00:01Z",
  "processedAt": "2026-10-04T09:00:01Z"
}
```

Whether F-15e should move to Stage 1 is [D-21](#14-decision-register).

**Expected audit.** F-15c and F-15d: authorization denial audit per CT-06 (event name not defined here). F-15e: `observation.rejected`. No `incident.created` in any invalid sub-case.

**Decisions.** D-07, D-21, D-23.

### F-16 — Missing idempotency key

**Scenario.** §8.7 without the `idempotencyKey` key, with `sourceEventId` and `provenance.sourceEventId` `evt-10016` and `correlationId` `corr-synth-0016`. Variant: `idempotencyKey` present as `""`.

**Preconditions.** No prior event `evt-10016`.

**Expected receipt.** None. No `deliveryId`, no observation row, no identity reservation, no attempt.

**Expected response.**

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "The request is invalid.",
    "details": [
      { "path": "body.idempotencyKey", "message": "Field required" }
    ]
  }
}
```

For the empty-string variant, the detail path is the same and the message states the value must be non-empty. Exact message text is not part of the contract.

**Follow-up.** A corrected submission of `evt-10016` with a token is a first delivery, because the failed request reserved nothing.

**Decisions.** D-09, D-22.

### F-17 — Idempotency token reuse with changed content

**Preconditions.** F-01 is `completed`. Its delivery used `idempotencyKey` `idem_synth_0001`.

**F-17a — same token, same provider event, changed content.** `sourceEventId` `evt-10001`, `idempotencyKey` `idem_synth_0001`, `correlationId` `corr-synth-0171`, `title` `Checkout API latency above threshold`. **Expected under both D-22 candidates.** `IDEMPOTENCY_CONFLICT` from the provider-event fingerprint (§10.7), exactly as F-09. No receipt, no attempt, no overwrite, no second Incident.

**F-17b — same token, different provider event.** `sourceEventId` and `provenance.sourceEventId` `evt-10017`, `idempotencyKey` `idem_synth_0001`, `correlationId` `corr-synth-0172`, `title` `Checkout API latency above threshold`, `externalSeverity` `SEV3`.

| D-22 candidate | Expected |
|---|---|
| A: diagnostic only | New provider event. New receipt `44444444-4444-4444-8444-000000000017`. Processed normally. Token reuse may be logged. |
| B: delivery-level conflict key | Token-reuse conflict before any receipt. Error code not defined in this draft. No receipt, no attempt. |

**Invariant in both.** F-01's observation, receipt, attempt, and Incident are unchanged. D-22 stays **Open**. Revision `0.2.1-draft` records Team 5's proposal of Candidate B; it is not jointly accepted, so F-17b still has two possible outcomes.

**Decisions.** D-09, D-10, D-22.

### F-18 — Connector reconnection with a stable source account

**Scenario.** F-01 is `completed`. The provider account `acct_synth_0001` is reconnected. Registration `conn_synth_monitor_01` is revoked and replaced by `conn_synth_monitor_02`, which is authorized for the same stable account. The new connection backfills recent events, including `evt-10001`.

**Input (redelivery through the new registration).**

```json
{
  "source": "synthetic-monitor",
  "sourceAccountRef": { "owner": "synthetic-monitor", "id": "acct_synth_0001" },
  "sourceEventId": "evt-10001",
  "occurredAt": "2026-10-01T09:14:30Z",
  "occurredAtSupplied": null,
  "receivedAt": "2026-10-05T08:00:00Z",
  "submittedAt": "2026-10-05T08:00:01Z",
  "serviceRef": { "owner": "synthetic-monitor", "id": "checkout-api-prod" },
  "externalSeverity": "SEV2",
  "title": "Checkout API error rate above threshold",
  "description": "Synthetic monitor reported a 12% HTTP 5xx rate over 5 minutes.",
  "provenance": {
    "originType": "observation",
    "provider": "synthetic-monitor",
    "sourceEventId": "evt-10001",
    "sourceAccountRef": { "owner": "synthetic-monitor", "id": "acct_synth_0001" },
    "collectorRef": { "owner": "team5.connector", "id": "conn_synth_monitor_02" }
  },
  "idempotencyKey": "idem_synth_0018",
  "correlationId": "corr-synth-0018"
}
```

**Expected Stage 1.** Passes: `conn_synth_monitor_02` is the authenticated registration and is authorized for `acct_synth_0001`.

**Expected identity and fingerprint.** Provider-event identity matches F-01 (tenant, `synthetic-monitor`, `acct_synth_0001`, `evt-10001`). The fingerprint matches because `collectorRef`, `idempotencyKey`, `correlationId`, `receivedAt`, and `submittedAt` are excluded (§10.3).

**Expected result.** Identical duplicate (§10.5): the F-01 receipt and completed attempt. No new receipt, Incident, or Evidence. The stored event Evidence keeps `collectorRef` `conn_synth_monitor_01` and `sourceAccountRef` `acct_synth_0001`; provenance is not rewritten. Whether the new registration is recorded as a diagnostic is Needs Team 5 Confirmation.

**Variants.** A new event `evt-10018` through `conn_synth_monitor_02` is a first delivery; its event Evidence carries `collectorRef` `conn_synth_monitor_02` and `sourceAccountRef` `acct_synth_0001`. A submission through revoked `conn_synth_monitor_01` is a Stage 1 denial with no receipt.

**Decisions.** D-04, D-09, D-10, D-20, D-23.

### F-19 — Unauthorized source-account submission

**Scenario.** Authenticated registration `conn_synth_monitor_01` submits §8.7 with `sourceAccountRef` and `provenance.sourceAccountRef` both `synthetic-monitor` / `acct_synth_0099`, `sourceEventId` and `provenance.sourceEventId` `evt-10019`, `idempotencyKey` `idem_synth_0019`, `correlationId` `corr-synth-0019`. The body is internally consistent. `conn_synth_monitor_01` is not authorized for `acct_synth_0099`.

**Expected.** Stage 1 platform denial. No receipt, no identity reservation, no attempt, no Incident. The denial does not disclose whether `acct_synth_0099` exists or which organization owns it.

**Follow-up.** If the connector actually authorized for `acct_synth_0099` later submits `evt-10019`, it is a first delivery, not a duplicate and not a conflict, because the denied request reserved nothing.

**Expected audit.** Authorization denial per CT-06 (event name not defined here).

**Decisions.** D-09, D-21, D-23.

### F-20 — Repaired unresolved observation creates its first Incident

**Step 1 — accepted but unresolved.** F-03b: receipt `44444444-4444-4444-8444-000000000004` with `correlationId` `corr-synth-0004`. Attempt 1 is `unresolved` / `SERVICE_UNRESOLVED`. No Incident is bound.

**Step 2 — missing information corrected.** The service catalog gains an entry resolving `unknown-service-xyz` to `service-catalog` / `svc_synth_inventory` for `org_synth_0001` (catalog ownership is D-03). The stored observation is not edited.

**Step 3 — controlled reprocessing.** An authorized operator requests reprocessing of observation `33333333-3333-4333-8333-000000000004`. The request correlation is `corr-synth-0020`. It is not required to equal `corr-synth-0004`.

**Step 4 — first canonical Incident.** Attempt 2 resolves the service, maps `SEV3` to `medium` under `synthetic-monitor-severity/v1`, stores the event content, and commits the completion unit (§9.5.1): Incident `11111111-1111-4111-8111-000000000020`, event Evidence `22222222-2222-4222-8222-000000000201`, binding, terminal result, and audit intents.

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000004",
  "observationId": "33333333-3333-4333-8333-000000000004",
  "attempt": 2,
  "attemptTrigger": "controlled_reprocessing",
  "processingStatus": "completed",
  "incidentId": "11111111-1111-4111-8111-000000000020",
  "evidenceIds": ["22222222-2222-4222-8222-000000000201"],
  "severityMappingVersion": "synthetic-monitor-severity/v1",
  "mappedSeverity": "medium",
  "errorCode": null,
  "errorMessage": null,
  "correlationId": "corr-synth-0020",
  "processingStartedAt": "2026-10-06T09:00:00Z",
  "processedAt": "2026-10-06T09:00:03Z"
}
```

**Expected persistence.** Receipt unchanged (still `corr-synth-0004`). Attempt 1 unchanged. Exactly one Incident. Event Evidence provenance equals the observation's provenance.

**Expected audit.** `incident.created` and `evidence.recorded`, correlation `corr-synth-0020`, with `deliveryId` and `observationId`.

Steps 5 and 6 (repeat and failed reprocessing) are F-21 and F-22.

**Decisions.** D-03, D-05, D-11, D-12, D-24, D-26.

### F-21 — Repeated reprocessing does not create another Incident

**Preconditions.** F-20 is complete. Incident `...0020` is bound to observation `...0004`.

**Scenario.** A second reprocessing request with correlation `corr-synth-0021` runs against the same observation. Context is unchanged.

**Expected processing.** Attempt 3 is appended:

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000004",
  "observationId": "33333333-3333-4333-8333-000000000004",
  "attempt": 3,
  "attemptTrigger": "controlled_reprocessing",
  "processingStatus": "completed",
  "incidentId": "11111111-1111-4111-8111-000000000020",
  "evidenceIds": [],
  "severityMappingVersion": "synthetic-monitor-severity/v1",
  "mappedSeverity": "medium",
  "errorCode": null,
  "errorMessage": null,
  "correlationId": "corr-synth-0021",
  "processingStartedAt": "2026-10-06T10:00:00Z",
  "processedAt": "2026-10-06T10:00:01Z"
}
```

**Expected persistence.** Still one Incident and one event Evidence. No `incident.created` audit.

**Concurrent variant.** Two reprocessing requests run concurrently while no Incident is bound (F-20 before step 4). Exactly one Incident is created and bound. The other attempt ends `completed` with the same `incidentId` and `evidenceIds` `[]`, or is serialized behind the first; the mechanism is Needs Team 5 Confirmation (§9.4 rule 6).

**Decisions.** D-11, D-12, D-26.

### F-22 — Failed reprocessing preserves committed Incident and Evidence

**Preconditions.** F-21 is complete. The catalog entry for `unknown-service-xyz` has since been removed in error.

**Scenario.** A reprocessing request with correlation `corr-synth-0022` runs.

**Expected processing.** Attempt 4 is appended:

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000004",
  "observationId": "33333333-3333-4333-8333-000000000004",
  "attempt": 4,
  "attemptTrigger": "controlled_reprocessing",
  "processingStatus": "unresolved",
  "incidentId": "11111111-1111-4111-8111-000000000020",
  "evidenceIds": [],
  "severityMappingVersion": null,
  "mappedSeverity": null,
  "errorCode": "SERVICE_UNRESOLVED",
  "errorMessage": "The affected service could not be resolved for this organization.",
  "correlationId": "corr-synth-0022",
  "processingStartedAt": "2026-10-07T09:00:00Z",
  "processedAt": "2026-10-07T09:00:01Z"
}
```

`incidentId` is the already-bound Incident. Attempt 4 did not create it (§9.2).

**Expected persistence.** Incident `...0020` keeps its status, severity, `serviceRef`, and `updatedAt`. Event Evidence `...0201` is unchanged. Attempts 1–3 are unchanged. Nothing is deleted or rolled back.

**Expected audit.** `observation.unresolved` with correlation `corr-synth-0022`. No Incident change event.

**Decisions.** D-03, D-12, D-26.

### F-23 — Crash after canonical persistence, before completion is recorded

**Scenario.** New observation: §8.7 with `sourceEventId` and `provenance.sourceEventId` `evt-10023`, `idempotencyKey` `idem_synth_0023`, `correlationId` `corr-synth-0023`. Receipt `44444444-4444-4444-8444-000000000023`, observation `33333333-3333-4333-8333-000000000023`. Service and severity resolve. Event content is stored as `content_synth_0231`. The process crashes during completion.

**F-23a — Proposed default (single completion transaction).** The crash happens before commit. Nothing canonical exists: no Incident, Evidence, binding, terminal result, or audit intent. Attempt 1 stays non-terminal. Recovery resumes attempt 1 and completes it once. `content_synth_0231` may be reused or orphaned (F-24).

**F-23b — only if Team 5 splits the terminal result from the canonical commit (§9.5.1 minimum invariant).** Incident `11111111-1111-4111-8111-000000000023`, event Evidence `22222222-2222-4222-8222-000000000231`, the binding, and `incident.created` / `evidence.recorded` intents are committed. The crash happens before the terminal result commits.

State visible to an identical duplicate during the window:

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000023",
  "observationId": "33333333-3333-4333-8333-000000000023",
  "attempt": 1,
  "attemptTrigger": "ingestion",
  "processingStatus": "pending",
  "incidentId": null,
  "evidenceIds": [],
  "severityMappingVersion": null,
  "mappedSeverity": null,
  "errorCode": null,
  "errorMessage": null,
  "correlationId": "corr-synth-0023",
  "processingStartedAt": "2026-10-08T09:00:01Z",
  "processedAt": null
}
```

After recovery resumes the same attempt and finds the binding:

```json
{
  "deliveryId": "44444444-4444-4444-8444-000000000023",
  "observationId": "33333333-3333-4333-8333-000000000023",
  "attempt": 1,
  "attemptTrigger": "ingestion",
  "processingStatus": "completed",
  "incidentId": "11111111-1111-4111-8111-000000000023",
  "evidenceIds": ["22222222-2222-4222-8222-000000000231"],
  "severityMappingVersion": "synthetic-monitor-severity/v1",
  "mappedSeverity": "high",
  "errorCode": null,
  "errorMessage": null,
  "correlationId": "corr-synth-0023",
  "processingStartedAt": "2026-10-08T09:00:01Z",
  "processedAt": "2026-10-08T09:02:00Z"
}
```

**Expected in both variants.** `completed` is never reported before all §9.5.1 items are committed. Exactly one Incident and one event Evidence. Recovery is the same attempt, not attempt 2, and keeps `corr-synth-0023`. Audit intents are not duplicated. Whether the Incident is readable by other callers during the F-23b window is Needs Team 5 Confirmation.

**Decisions.** D-08, D-12, D-24.

### F-24 — External content-storage recovery

**Scenario.** New observation `evt-10024` (`idem_synth_0024`, `corr-synth-0024`; receipt `44444444-4444-4444-8444-000000000024`). Content storage reports `content_synth_0241` durably stored. Before the completion commit unit, the database commit fails (or the process crashes).

**Expected immediately after the failure.** No Evidence references `content_synth_0241`. No Incident, binding, or audit intent exists. Attempt 1 is `pending` or `retrying`, never `completed` or `partial`.

**Expected recovery.** Attempt 1 resumes. It ends with exactly one event Evidence `22222222-2222-4222-8222-000000000241` referencing exactly one valid `contentRef`. That is either `content_synth_0241` (reused) or a newly written reference; which one is Needs Team 5 Confirmation. Any unreferenced stored object is an orphan, is never shown as Evidence, and its cleanup is Needs Team 5 Confirmation.

**Variant — commit keeps failing.** This is a transient processing failure, not an event-content storage failure: bounded retries, then `unresolved` / `PROCESSING_RETRY_EXHAUSTED` (§10.8). No `available` Evidence exists.

**Not claimed.** This fixture does not assume that content storage and the database share one atomic transaction.

**Decisions.** D-08, D-12, D-24.

### F-25 — Provider event content revision

**Scenario.** F-01 is `completed` (Incident `...0001`, `severity` `high`). The provider updates the same alert: `sourceEventId` `evt-10001` now has `externalSeverity` `SEV1` and `title` `Checkout API unavailable`. The connector delivers it with `idempotencyKey` `idem_synth_0025` and `correlationId` `corr-synth-0025`. Same tenant, provider, and source account.

**Expected under the interim rule (§10.9).** The fingerprint differs under an accepted identity: `IDEMPOTENCY_CONFLICT`. No receipt, no attempt. The stored observation is not overwritten. Incident `...0001` keeps `severity` `high` and its title.

```json
{
  "error": {
    "code": "IDEMPOTENCY_CONFLICT",
    "message": "This provider event was already accepted with different content.",
    "details": []
  }
}
```

**Expected audit.** `observation.idempotency_conflict` with `corr-synth-0025` and the original `observationId`.

**Open.** Applying the revision to the Incident needs a revision policy ([D-25](#14-decision-register)). This fixture records the interim behavior only and the known loss of the update.

**Decisions.** D-10, D-20, D-25.

### F-26 — Attempt to bypass a conflict with an invented source event ID

**Scenario.** After F-25's conflict, the sender resubmits the changed content with a `sourceEventId` the provider never issued.

```json
{
  "source": "synthetic-monitor",
  "sourceAccountRef": { "owner": "synthetic-monitor", "id": "acct_synth_0001" },
  "sourceEventId": "evt-10001-r2",
  "occurredAt": "2026-10-01T09:14:30Z",
  "occurredAtSupplied": null,
  "receivedAt": "2026-10-09T08:00:00Z",
  "submittedAt": "2026-10-09T08:00:01Z",
  "serviceRef": { "owner": "synthetic-monitor", "id": "checkout-api-prod" },
  "externalSeverity": "SEV1",
  "title": "Checkout API unavailable",
  "description": "Synthetic monitor reported a 12% HTTP 5xx rate over 5 minutes.",
  "provenance": {
    "originType": "observation",
    "provider": "synthetic-monitor",
    "sourceEventId": "evt-10001-r2",
    "sourceAccountRef": { "owner": "synthetic-monitor", "id": "acct_synth_0001" },
    "collectorRef": { "owner": "team5.connector", "id": "conn_synth_monitor_01" }
  },
  "idempotencyKey": "idem_synth_0026",
  "correlationId": "corr-synth-0026"
}
```

**Contract requirement.** The connector must not send this payload (§10.9). `evt-10001-r2` is not provider-issued and is not produced by a documented deterministic rule.

**Expected outcome.** No second Incident for the provider occurrence already bound to Incident `...0001`. Incident `...0001` and F-01's records are unchanged.

**Enforcement.** Schema validation alone cannot detect the fabrication. Whether Team 5 can verify provider-issued ids, at which stage, and with which code is Needs Team 5 Confirmation ([D-25](#14-decision-register)). If it is not detected and a second Incident results, that is a connector conformance defect, not a valid outcome of this contract.

**Decisions.** D-10, D-20, D-25.

---

## 13. Serialization, timestamps and tests to specify

**Proposed direction from Team 5 feedback. Not agreed. Not an instruction to change code in this task.**

### 13.1 Serialization contract

| Rule | Contract | Existing code |
|---|---|---|
| Canonical output | camelCase at the API boundary | True only when the caller serializes by alias. Default `model_dump()` is snake_case (G-8's neighbor in §4.1). |
| Python names | snake_case | Existing, where models exist. |
| Accepted input | snake_case or camelCase, not both | Both forms work alone. Both together are rejected today only as `extra_forbidden` (G-6). |
| Repeated JSON keys | Reject before ordinary parsing drops the first value | Not implemented. Last value wins (G-7). |
| `null` vs omission | Equivalent on input after defaults. Output writes explicit `null`. | Output `null` is existing if `exclude_none` is not used. Input equivalence is not specified in code. |

### 13.2 UTC and original values

- Fingerprints and canonical comparisons use UTC instants.
- Records returned by the API serialize those instants with `Z`.
- `occurredAtSupplied` keeps the lexical original when provenance needs it (§3.4, §8.8).
- Do not read G-2 as if normalization already happened.

### 13.3 Tests to specify later

Not implemented in this task.

| ID | Test | Expected once the contract is implemented | Today |
|---|---|---|---|
| ST-01 | Serialize by alias | camelCase keys | Holds for current models. One test covers `InvestigationContext` only. |
| ST-02 | Default dump | Documents snake_case default so boundaries must opt into aliases | Holds; easy to misuse. |
| ST-03 | snake_case input | Accepted | Holds; thin coverage. |
| ST-04 | camelCase input | Accepted | Holds; thin coverage. |
| ST-05 | Unknown field | Rejected | Holds for `ContractModel`. |
| ST-06 | Both aliases, different values | Rejected as ambiguous | Rejected today as a side effect (G-6). |
| ST-07 | Both aliases, same value | Rejected | Rejected today (G-6). |
| ST-08 | Repeated JSON key | Rejected before last-wins parsing | Accepted today (G-7). |
| ST-09 | Naive datetime | Rejected | Holds. |
| ST-10 | Offset timestamp | Stored and compared as UTC `Z`, with lexical form retained when required | Not normalized (G-2). |
| ST-11 | `ExternalRef` extra field, and mutation | Rejected | Holds; untested. |
| ST-12 | camelCase round trip | Stable for normalized values | Untested. |
| ST-13 | Omitted optional field vs `null` | Same fingerprint | Not specified in code. |
| ST-14 | Two `occurredAt` values that are the same instant with different offsets | Same fingerprint; originals distinguishable if `occurredAtSupplied` is set | Not implemented. |

No precedence rule makes one alias win. Ambiguous duplicates are rejected.

---

## 14. Decision register

No row is Agreed. "Proposed" means this draft recommends it. Team 5's review is the reason the text changed; it is not acceptance.

| ID | Topic | Proposed default | Responsible | Status |
|---|---|---|---|---|
| D-01 | Identifier format and generation | Server-generated UUIDs for canonical, investigation, delivery, and observation ids. Opaque provider ids and `idempotencyKey`. Formats still unset. | Team 4 (rules), Team 5 (generation) | Proposed |
| D-02 | Tenant and actor identifiers | Opaque organization id from trusted context only. User, employee, and system-actor forms unset. | Team 1 | Needs Team 1 Input |
| D-03 | Service catalog and service mapping | Canonical `serviceRef` is an `ExternalRef` resolved in trusted context. Catalog owner, and service-to-team and service-to-user mapping owners, are unset. | Coordinator | Needs Coordinator Confirmation |
| D-04 | External reference namespace | Non-empty `owner` and `id`. Registry of owner strings unset. For `sourceAccountRef`, `owner` names the provider namespace and `id` the stable provider account, not a connector connection ([D-23](#14-decision-register)). | Team 4 with Team 5 | Proposed |
| D-05 | Severity mapping version | Canonical severities `critical`, `high`, `medium`, `low`. Each attempt records `severityMappingVersion` and `mappedSeverity`. Terminal attempts are immutable. Reprocessing appends an attempt and does not create an incident when one is already bound; first-time creation after repair follows [D-26](#14-decision-register). Unmapped severity is `unresolved` / `SEVERITY_UNMAPPED`. Version token format, storage, and governance unset. Incident-level severity history beyond attempts is Open. | Team 4 (meaning), Team 5 (version representation) | Proposed |
| D-06 | Incident lifecycle | `open` → `investigating` → `resolved` → `closed`, plus `resolved` → `investigating`. `closed` has no direct transition. `open` → `closed` and reopening `closed` unset. | Team 4 | Proposed |
| D-07 | Evidence types, availability, provenance | Types `log`, `metric`, `trace`, `event`, `other`. `available` requires a valid `contentRef`; `unavailable` has `contentRef` null and cannot be labeled `available`. Event Evidence copies observation provenance unchanged, including `sourceAccountRef`. Observation provenance must use `originType` `observation`, with `collectorRef` and `sourceAccountRef` bound to the authenticated connector registration (§8.5); manual and tool-execution provenance stay separate origins (§7.4). Separately collected Evidence keeps collector provenance. `triggeredByObservationId` is a relationship, not provenance. Mandatory event Evidence storage failure cannot yield `completed`. The `Provenance` schema is not implemented. | Team 4 with Team 5 | Proposed |
| D-08 | Evidence storage and Phase 1 scope | Phase 1 ingestion stores the observation and its mandatory event Evidence only; `completed` requires a valid event-Evidence `contentRef`. Extra collection is separate unless jointly agreed. For permanent mandatory-storage failure, this draft proposes `unresolved` with no completed canonical Incident or `available` Evidence; provisional rows and diagnostic markers need confirmation. Storage provider, URI, encryption, access, retention, deletion, and permanent/transient classification are unset. The boundary between content storage and the stored `contentRef` is [D-24](#14-decision-register). | Team 5 with Team 4 | Needs Team 5 Confirmation |
| D-09 | Idempotency scope | Identity scope is tenant, provider/source, stable source account, and provider event id. The replaceable connector registration instance is not part of it ([D-23](#14-decision-register)). `sourceAccountRef` shape is unset. `idempotencyKey` is mandatory; missing or empty is a Stage 1 `INVALID_REQUEST` with no receipt. It is sender delivery metadata, not business content and not an additional canonical key. Token reuse policy is [D-22](#14-decision-register). Uniqueness and transaction design are Team 5's, subject to §10.4. Retention is unset. | Team 4 (semantics), Team 5 (source-account contract and database) | Proposed |
| D-10 | Equality and duplicate semantics | Fingerprint rules in §10.3 exclude `idempotencyKey`, `correlationId`, delivery/transport timestamps, and `provenance.collectorRef`. Changed provider content under an accepted `sourceEventId` is a conflict until [D-25](#14-decision-register) defines revisions; inventing a new `sourceEventId` to bypass a conflict is prohibited. Identical business content returns the current state (§10.5) and never invents `completed`. Changed business content under the same provider-event identity is detected during atomic lookup and returns `IDEMPOTENCY_CONFLICT`; it creates no second receipt, observation, attempt, or incident and overwrites nothing. HTTP status and replay policy are unset. | Team 4 with Team 5 | Proposed |
| D-11 | Validation stages and acknowledgment API | Stage 1 failures create no receipt and no attempt. Ordinary Stage 2 domain failures keep the receipt and record `rejected`, `unresolved`, or `partial`, never a false `completed`. An existing-identity fingerprint conflict is pre-acceptance atomic lookup, not Stage 2. Mapping version is on the attempt (§9.2). HTTP methods, paths, status codes, sync vs async, and service-versus-severity check order are unset. Transport, authorization, and request shape for controlled reprocessing (§9.4) are also unset. Team 5 proposal recorded in `0.2.1-draft`, not jointly accepted: asynchronous durable receipt, plus a tenant-authorized query for processing status. Methods, paths, and status codes remain unset. | Team 5 with Team 4 | Proposed |
| D-12 | Audit persistence and recovery | Domain change and outbox intent commit together or not at all. Sink failure does not delete the intent. Bounded automatic retry, then the row remains for controlled replay. Stable `eventId` covers redelivery. The same bounded-retry concept applies to transient mandatory event-Evidence storage failure. Recovery of an interrupted attempt resumes the same attempt and its correlation (§9.5.1). Retry count, backoff, retention, permanent/transient classification, and reprocessing of `unresolved` are unset. | Team 5 (CT-06) with Team 4 | Proposed |
| D-13 | Serialization | Explicit camelCase output. Accept either alias, reject both at once, reject repeated keys before last-wins parsing. Not implemented for repeated keys (G-7). | Team 4 | Proposed |
| D-14 | Contract and API versioning | This document revision is `0.2.1-draft` and is not a baseline. Wire version and compatibility unset. Existing API prefix is `/api/v1` for health only. | Team 4 with Team 5 | Needs Team 5 Confirmation |
| D-15 | Text field limits | Title and `sourceLabel` 1–255 after trim. Other maxima and payload size unset. | Team 4; size limits Team 5 | Proposed |
| D-16 | UTC, original timestamps, clock skew | Normalize accepted instants to UTC for processing and equality. Keep the supplied lexical form when provenance needs it. Serialization `Z`. Current code does not normalize (G-2). Skew tolerance and warning-vs-blocking unset. No numeric tolerance in this draft. | Team 4 with Team 5 | Proposed |
| D-17 | Null and omitted fields | Output writes explicit `null`. Input treats omission and `null` as equal after defaults, including in fingerprints. | Team 4 with Team 5 | Proposed |
| D-18 | Incident event time | Whether Incident stores `occurredAt` or `detectedAt` as well as `createdAt`. | Team 4 | Open |
| D-19 | Evidence collection scope and provenance | Default: ingestion does not collect optional evidence and must not return `partial` for that reason. It must store mandatory event Evidence with a valid `contentRef` before `completed`. Separate collection keeps actual collector provenance and may set `triggeredByObservationId`. Including collection inside ingestion requires a later joint agreement. Not implemented. | Team 4 with Team 5 (CT-07) | Proposed |
| D-20 | Grouping and duplicate events | Identical provider-event repeats follow §10.5 and do not assume `completed`. They do not create another incident. Reconnection through a new registration for the same stable source account is an identical repeat (F-18). Grouping distinct provider events into one incident is not defined, which also blocks revision-scoped event ids under [D-25](#14-decision-register). | Team 4 | Open |
| D-21 | Authorization vs domain validation (source registration and provenance binding) | v0.1 mixed "source is registered" (field rule) with post-receipt `SOURCE_NOT_REGISTERED`. Stage 1 owns connector and source-account authorization, and (Proposed) the binding of `provenance.collectorRef` and `provenance.sourceAccountRef` to the authenticated registration (§8.5). Stage 2 owns domain registration and `provider`/`sourceEventId` consistency only where that is not the same check. Open: whether `collectorRef` is derived from the authenticated registration rather than accepted from the body; whether provider consistency moves to Stage 1; the field-level registration boundary. Topic name clarified in the second Team 5 review to match the §8.5 use of D-21; the decision is unchanged in scope. Team 5 proposal recorded in `0.2.1-draft`, not jointly accepted: derive the authoritative collector identity from the authenticated registration, and validate access to the stable source account. The other open points in this row are unchanged. | Team 5 with Team 4 | Needs Team 5 Confirmation |
| D-22 | Sender idempotency token reuse | `idempotencyKey` is mandatory delivery metadata (D-09). A changed token with identical content is an identical duplicate. Same token with changed content for the same provider event is already a fingerprint conflict. Same token for a different provider event: candidate A (diagnostic only) or candidate B (delivery-level conflict), §10.2. Team 5 proposal recorded in `0.2.1-draft`, not jointly accepted: Candidate B, with the delivery-token binding scoped separately from provider-event deduplication. Neither candidate is the contract rule until joint acceptance. | Team 5 with Team 4 | Open |
| D-23 | Stable source identity vs connector registration | Three identities: stable source account (`sourceAccountRef`), replaceable connector registration instance (`collectorRef`), provider event (`sourceEventId`). Provider-event identity uses the stable source account, not the registration instance. The authenticated registration must be authorized for the source account. Event Evidence preserves `sourceAccountRef`. Reconnecting must not create a new incident for an accepted event. Account id format, how registrations map to accounts, and tool-execution account reporting are unset. No storage design is implied. Team 5 proposal recorded in `0.2.1-draft`, not jointly accepted: derive the authoritative collector identity from the authenticated registration, and validate access to the stable source account. | Team 5 with Team 4 | Needs Team 5 Confirmation |
| D-24 | Completion commit boundary and content-storage recovery | `completed` requires Incident, event Evidence metadata with valid `contentRef`, observation-to-Incident binding, terminal result, and audit intents to be committed (§9.5.1). Default: one local transaction. Minimum invariant if split: Incident, Evidence, binding, and audit intents together; recovery resumes the same attempt from the binding. Content storage is not assumed atomic with the database; orphaned content is never Evidence (§9.5.2). Visibility during a split window, recovery trigger, orphan cleanup, and content reuse are unset. Team 5 proposal recorded in `0.2.1-draft`, not jointly accepted: for Phase 1, one local transaction covering the canonical records, the observation binding, the terminal processing result, and the audit intents. External content storage is not part of that transaction. The split minimum invariant remains until joint acceptance. | Team 5 with Team 4 | Needs Team 5 Confirmation |
| D-25 | Provider event mutability and revisions | Proposed meaning: `sourceEventId` is an immutable occurrence within tenant, provider, and source account. Interim: changed content under an accepted id is `IDEMPOTENCY_CONFLICT` (known update loss). Inventing a `sourceEventId` to bypass a conflict is prohibited. Mutable-alert revision handling (revision-scoped id vs stable id plus revision field), provider-id verification, and outcome codes are not chosen. Team 5 proposal recorded in `0.2.1-draft`, not jointly accepted: enable mutable provider alerts only after a provider-specific revision policy is agreed. | Team 4 (meaning) with Team 5 (connector capability) | Open |
| D-26 | Controlled reprocessing and correlation | Reprocessing never edits the stored observation. Each request appends an attempt with `attemptTrigger` `controlled_reprocessing`. It creates the first Incident at most once (binding guard), updates a bound Incident without creating another, and on failure leaves committed records unchanged. Three correlations: original observation, reprocessing request, attempt; a reprocessing request's correlation is not required to equal the receipt's. Concurrency serialization and retried reprocessing requests were unset. Team 5 proposal recorded in `0.2.1-draft`, not jointly accepted: serialize conflicting work for the same observation, and make a retried reprocessing request idempotent. Transport remains D-11. | Team 4 (semantics), Team 5 (execution) | Proposed |

### 14.1 What this draft asks each party to confirm

**Team 1.** D-02, and the membership and RBAC inputs to Stage 1. CT-04 will not define user or organization id formats.

**Team 5.** Proposals recorded in `0.2.1-draft` and still requiring joint acceptance, not confirmation that they are Agreed: D-11 (asynchronous durable receipt and a tenant-authorized processing-status query), D-21 and D-23 (derive collector identity; validate stable source-account access), D-22 (Candidate B, delivery-token binding separate from provider-event deduplication), D-24 (Phase 1 single local completion transaction), D-25 (enable mutable alerts only after a provider-specific revision policy), and D-26 (idempotent retried reprocessing and serialized conflicting work). Still awaiting a Team 5 proposal or confirmation: D-08, D-09 (source-account shape and uniqueness), D-10 (HTTP status, replay, and fingerprint exclusions including `collectorRef`), D-12 (retry numbers and outbox), D-14, the remaining open points inside D-21 and D-23, plus mapping-version syntax in D-05 and payload limits in D-15.

**Coordinator.** D-03. F-20 and F-22 depend on service-catalog data whose ownership is unconfirmed.

**Team 4.** D-05 meaning, D-06, D-07, D-18, D-19, D-20, D-25 meaning, D-26 semantics, RCA rules, and approval rules in §11.3. Team 4 does not treat this draft as approval of those proposals.

**Team 1.** Unchanged: D-02 and CT-01 membership and RBAC inputs remain Needs Team 1 Input. The connector-registration authorization in D-21 and D-23 depends on CT-01 for tenant binding.
