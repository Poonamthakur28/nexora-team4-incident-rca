# Team 4 ERD foundation

## Source and status

No Team 4 ERD or requirements source was present in the inspected workspace. Therefore the list below is a proposed entity inventory from the setup brief, **not an approved schema**. No product models or migrations have been generated. Confirm the ERD with Team 4 before assigning permanent foreign keys, uniqueness rules, required fields, or lifecycle constraints.

## Proposed Team 4 entities

| Entity | Intended role | Status |
|---|---|---|
| `incident` | Team 4 incident record | Proposed |
| `incident_event` | Timestamped incident event | Proposed |
| `incident_timeline` | Timeline projection or ordered view | Clarify whether entity or derived view |
| `evidence` | Captured evidence record | Proposed |
| `evidence_source` | Provenance/source metadata | Proposed |
| `evidence_link` | Evidence relation to an incident, finding, or candidate | Relationship targets need confirmation |
| `rca_investigation` | Investigation session/context | Proposed |
| `root_cause_candidate` | AI or human candidate explanation | Proposed |
| `analysis_finding` | Evidence-engine finding | Proposed |
| `finding_evidence` | Finding/evidence association | Proposed join; cardinality needs confirmation |
| `fix_proposal` | Proposed remediation | Proposed |
| `proposed_code_change` | Proposed change metadata | Ownership and storage policy need confirmation |
| `remediation_task` | Team 4 remediation tracking record | Clarify if task is Team 4-owned or external reference |
| `test_plan` | Plan for validating a proposal | Proposed |
| `test_case` | Individual test case | Proposed |
| `test_execution` | Recorded test run result | Proposed |
| `review_decision` | Human decision on candidate/proposal/resolution | Subject reference modeling needs confirmation |
| `approval_history` | Append-only approval events | Clarify overlap with review decision/history |
| `incident_fix_link` | Incident and fix/resolution association | Clarify whether an explicit join is needed |
| `resolution` | Recorded resolution and outcome | Proposed |
| `investigation_history` | Append-only investigation audit events | Proposed |

## Relationships to confirm

The likely workflow suggests incident → event/timeline/evidence/investigation; investigation → candidates/findings; finding → evidence; candidate → fix proposal; proposal → code change/test plan; test plan → cases → executions; and investigation → review decisions/resolution/history. These are discussion hypotheses only. Validate cardinalities, ownership, deletion behavior, and whether timeline is materialized before creating foreign keys or migrations.

## Identifier and timestamp conventions

- Prefer UUID primary keys for Team 4 records, subject to the confirmed ERD.
- Use UTC timestamps; serialize as RFC 3339/ISO 8601 with `Z`.
- External IDs must include an owner namespace and stay opaque; never create foreign keys to another team's database.
- Keep AI confidence bounded and preserve rationale, evidence polarity, uncertainty, and missing information separately.

## Lifecycle, validation, indexes, and isolation

- **Unconfirmed:** incident, investigation, candidate, proposal, review, test, and resolution state names and valid transitions.
- Validate UUID syntax, non-empty summaries, timestamp ordering, confidence range (0 to 1), evidence references, and required decision rationale once contracts are agreed.
- Plan indexes around incident status/updated time, incident-to-event chronological lookup, incident/investigation relationships, evidence provenance, candidate/review status, and proposal/test status. Confirm query patterns first.
- Tenant isolation is a requirement to resolve before production data: establish the tenant key source, enforcement strategy, and claim boundary with the owning platform team. This repository does not implement tenant or authentication infrastructure.
- Never store credentials in model records, fixtures, or checked-in configuration.

## Local development

Use `database/fixtures/` for clearly synthetic, Team 4-only data. Do not use fixtures to imply cross-team integration. Once relationships are approved, add SQLAlchemy models under `api/app/` (imported from `api/app/db/models.py`) and the matching Alembic revisions in `api/alembic/versions/`.
