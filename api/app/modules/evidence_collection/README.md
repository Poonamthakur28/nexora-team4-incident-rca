# RCA-004 Evidence Collection Core

This module records append-only Evidence metadata in memory. Manual recording
and observation-origin event recording (F-04a) are supported. It has no
database models, migrations, routes, content storage, connector, Observation
ingestion coordinator, Investigation entity, or audit delivery.

## Tenant-aware verifier boundary

`contentRef` is opaque. A non-null reference requires an injected verifier,
which stands in for the future Team 5-owned storage boundary; this module does
not upload, parse, encrypt, retain, delete, or read content. `verify` takes an
`organization_id` from the caller's trusted `IncidentRequestContext` — never
from the Evidence command, which has no organization field — so a verifier
implementation can scope a lookup to the authenticated tenant. This module does
not itself implement storage scoping or URI parsing; it only passes the trusted
organization id through the port.

## Opaque contentRef handling

A non-null `contentRef` is preserved exactly, including any internal or
surrounding whitespace: this module never trims it. A `contentRef` that is
empty or whitespace-only is rejected outright at validation time; it is never
silently converted to `null`. `unavailable` Evidence still requires `contentRef`
to be exactly `null`, and `available`/`partial` still require a verified,
non-blank reference.

## Manual provider-label behavior

CT-04 v0.2 allows manual provenance `provider` to be `null` or a user-declared
label (D-07, Proposed). The canonical `Provenance` validation allows both. The
manual-evidence service path still defaults `provider` to `null`: `EvidenceService`
builds manual provenance only from the trusted request context, and
`RecordManualEvidence` exposes no field through which a caller can set
`provider`, `sourceEventId`, `sourceAccountRef`, or `collectorRef`. A
user-declared label is reachable only through direct `Provenance` construction,
not through this module's manual-recording command.

## Audit actor consistency

For manual Evidence, the repository rejects an `evidence.recorded` audit intent
whose `actorRef` does not match `Evidence.provenance.collectorRef`. This is a
repository-level consistency check; `EvidenceService.record_manual_evidence`
cannot violate it in normal use because it sets both fields from the same
trusted `context.actor_ref`.

`correlation_id` stays optional on `EvidenceRecordedAuditIntent`, unlike
RCA-001's `IncidentAuditIntent.correlation_id`, which is required. RCA-001's own
`IncidentRequestContext.correlation_id` is optional; `IncidentService` enforces
it as a business rule only for `change_status`. Neither CT-04 nor this
milestone defines an equivalent requirement for `evidence.recorded`, so this
module keeps `correlation_id` consistent with the trusted context's own shape
instead of inventing a new requirement.

Manual commands reject non-null Investigation and Observation-trigger
relationships because those records and workflows are not implemented.

## Observation-origin event Evidence

`EvidenceService.record_observation_event_evidence` records F-04a event
Evidence. `evidence_type` is `event`, `availability` is `available`, and
`triggered_by_observation_id` is always null. Provenance is copied from the
command's Observation provenance (`provider`, `sourceEventId`,
`sourceAccountRef`, `collectorRef`) and re-validated by the existing
`Provenance` rules, including RCA-004 trimming of `provider` and
`sourceEventId`. This module does not read the Observation top-level
`sourceEventId`, so the M1/M4 opaque/trim asymmetry is unchanged.

Organization and actor come only from trusted `IncidentRequestContext`. The
command has no organization, actor, Evidence id, collection time,
`evidence_type`, `availability`, or `triggeredByObservationId` fields.
`content_ref` is a required opaque mock reference checked by the existing
verifier (D-08). There is no live content store.

The repository's collector/actor match check stays limited to manual
Evidence. Observation-origin `collectorRef` is the connector; the audit
actor is the trusted context actor and may differ.

`record_manual_evidence` is unchanged.

Each successful write stores an undelivered `evidence.recorded` intent with the
Evidence record. The intent's `data` payload is provisional: CT-04 requires the
event but CT-04 and CT-06 do not define its payload or delivery envelope. This
review did not change that payload shape and does not claim CT-06 approval.

## Remaining provisional decisions

CT-04 decisions D-01, D-02, D-04, D-07, D-08, D-12, D-13, D-14, D-15, D-16,
D-17, D-19, D-21, D-23, and D-24 remain Proposed, Open, or pending external
confirmation as stated in the contract. This module does not treat them as
Agreed. In particular, D-04 (empty `ExternalRef` owner/id parts) is unchanged
by this review: `source_account_ref` and `collector_ref` keep their existing
`ExternalRef` behavior.
