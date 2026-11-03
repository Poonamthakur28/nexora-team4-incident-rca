# RCA-002 Incident Ingestion

M1 added Observation shape and Stage 1 checks. It does not create receipts,
store attempts, or call a live connector. M3 later added process-local
identity reservation (`accepted`, `duplicate`, or conflict). That store is
not a durable receipt.

`IncidentIntake` is unchanged. It remains the manual and local-fixture intake
shape. `Observation` is the proposed provider-event shape from CT-04 §8.2.

## Mock connector boundary

`AuthenticatedConnectorContext` is an injected stand-in for the trusted
organization and the authenticated connector registration. It does not
authenticate anything and is not a production security boundary. Team 1 still
owns identity and membership (D-02, Needs Team 1 Input). Team 5 still owns
connector registration (D-21 and D-23, Needs Team 5 Confirmation).

`InMemorySourceAccountAuthorizer` is a deterministic allow-list copied into the
instance. It has no global state and does not query Team 1 or Team 5. A denial
uses one generic message, so a caller cannot learn whether a source account
exists or which organization it belongs to.

`sourceAccountRef` reuses `ExternalRef` only because that is the existing Team 4
reference type. CT-04 presents that shape as an illustration. Team 5 has not
confirmed it (D-09, D-23).

## What Stage 1 checks

1. `provenance.originType` is `observation`. Any other origin is an invalid
   request. Constructing `Observation` already rejects it; the Stage 1 function
   checks it again.
2. `provenance.collectorRef` equals the injected registration.
3. `provenance.sourceAccountRef` equals the top-level `sourceAccountRef`.
   A mismatch is denied before the authorizer is called.
4. The top-level `sourceAccountRef` is authorized for that registration in the
   trusted organization.

Missing, null, or blank `idempotencyKey` fails while building `Observation`,
before Stage 1 runs. Opaque identifiers are rejected when blank and otherwise
kept exactly; they are not trimmed.

Stage 1 does not check that `provenance.provider` equals `source`, or that
`provenance.sourceEventId` equals `sourceEventId`. Those remain Stage 2
(D-21). No numeric clock-skew tolerance is defined (D-16).

## Normalization and fingerprinting

M2 builds two in-memory values from a constructed Observation and a trusted
organization id. It does not look up prior rows or reserve an identity.

`IdempotencyIdentity` is the four Proposed D-09 dimensions: trusted
organization id, `source`, stored `sourceAccountRef`, and opaque
`sourceEventId`. The organization id is taken from the caller, not from the
body. The identity is not hashed. `collectorRef` and `idempotencyKey` are not
part of it.

`PayloadFingerprint` is a digest of the Proposed D-10 business object:
`source`, `sourceAccountRef`, `sourceEventId`, UTC `Z` `occurredAt`,
`serviceRef`, `externalSeverity`, `title`, `description`, and `provenance`
without `collectorRef`. Delivery fields (`idempotencyKey`, `correlationId`,
`receivedAt`, `submittedAt`, `occurredAtSupplied`) are omitted. Omitted
optional values and explicit `null` serialize the same way.

Canonical JSON uses camelCase keys, lexicographic key order, UTF-8, and no
insignificant whitespace. The hasher is injected. No production algorithm is
chosen (D-10 Needs Team 5 Confirmation). `sourceAccountRef` as `ExternalRef`
remains provisional (D-09, D-23).

## In-memory reservation

M3 reserves a provider-event identity in the process that constructed it.
`ObservationIngestionService.accept` runs Stage 1, fingerprints the payload,
then calls `InMemoryObservationRepository.reserve`.

A new identity is `accepted` and receives one `observation_id` from an injected
factory. The store keeps a deep copy of the Observation, the fingerprint
digest, the canonical bytes, later an optional Stage 2 assessment, and
later an optional process-local binding. `accept` does not write an
assessment or a binding. The same identity and digest is a
`duplicate`: the original reservation is returned and nothing is overwritten.
The same identity with a different digest raises `ObservationIdempotencyConflict`
with a generic message. The existing row is left unchanged.

`get(observation_id, organization_id)` returns a copy, or `None` when the id
is missing or belongs to another organization. There is no list-all.

The instance lock serializes reserve and get inside one process. It is not a
database transaction and does not provide cross-process uniqueness (D-09,
D-24). The hash algorithm remains unset (D-10). `idempotencyKey` is not a
store key (D-22 is Open). `sourceAccountRef` as `ExternalRef` is still
provisional (D-09, D-23).

`reserve` trusts that `observation` and `normalized` came from the same
Stage 1-validated input. `ObservationIngestionService.accept` is the
supported path and always builds both together. Direct `reserve` callers
must do the same. The repository does not re-run M1 or M2 validation.

This store is not a durable receipt. It does not assign a delivery id, record
`receiptStatus`, or create a processing attempt.

## Stage 2 assessment

`ObservationIngestionService.accept` still only reserves. `assess` is the
additive path: Stage 1, fingerprint, reserve, then single-flight Stage 2.

Order: provenance consistency, then mock service resolution, then mock
severity mapping. A domain miss stores `PROVENANCE_MISMATCH`,
`SERVICE_UNRESOLVED`, or `SEVERITY_UNMAPPED` on the reservation and keeps
the reservation. Ready assessments carry a canonical service ref, a
canonical Incident severity, and an opaque fixture version string.

Values are compared as stored. Top-level `sourceEventId` is opaque and is
not trimmed; RCA-004 trims `provenance.sourceEventId`. Those strings can
differ after construction (D-04 / D-09). Stage 2 does not rewrite them.

`ServiceResolver` and `SeverityMapper` are injected. The in-memory resolver
is an allow-list, not a coordinator catalog (D-03). The in-memory mapper
uses the illustrative synthetic-monitor SEV1–SEV4 table from CT-04 §8.3 as
a **test fixture only**. It is not an approved production mapping (D-05).
Unknown, missing, ambiguous, and cross-organization services all resolve
as unresolved, with no disclosure. Missing or unknown severity is unmapped;
there is no default. `SOURCE_NOT_REGISTERED` is not implemented (D-21).

A stored domain assessment is stable. An identical later `assess` returns
it and does not call the resolver or mapper. A resolver or mapper exception
is `IngestionConfigurationError`, stores no assessment, and a later
independent call may retry. Waiters of a failed in-flight wave get the
same generic configuration error, even if a later retry starts before they
wake. `complete` and `abort` accept only the claiming generation, so a
stale finally cleanup cannot release a newer retry. Reprocessing a stored
domain failure is
M6 (D-26). Check order versus Team 5 remains unset (D-11). Incident and
Evidence creation stay later (D-24). M5.1 only stores a process-local
binding.

Single-flight uses the repository lock plus a per-identity condition on
that lock. The first caller evaluates outside the lock. Duplicates wait.
`in_flight` is internal and is not a processing status. Different
identities do not wait on each other's resolver or mapper work.

`assess` does not create an Incident, Evidence, receipt, delivery id, or
attempt.

## Process-local completion binding

M5.1 stores an optional `ObservationBinding` on the reservation:
`incident_id`, and `evidence_id` when Evidence also exists. A full local
bind is `ObservationCompletion` (both ids). Neither value is
`processingStatus` or CT-04 `completed`. D-24 remains Needs Team 5
Confirmation.

The bind is keyed by the existing `IdempotencyIdentity`, including
organization. `get` and reserve duplicates return copies. Incident-only
state is allowed so a later retry can reuse that Incident id. Evidence
cannot be stored without an Incident id. Ids are non-empty strings; there
is no UUID rule.

Completion ownership is a separate generation from Stage 2. One owner
evaluates at a time. Concurrent callers wait and receive the stored full
bind, or `failed` if that wave aborted or failed to publish. `abort`
releases only the caller's generation. A stale abort cannot release a
newer completion retry. Failed-wave waiters are not absorbed into a later
retry. Different identities do not wait on each other.

`accept` and `assess` do not claim or write a binding.

## Process-local completion coordinator

`ObservationIngestionService.complete` is additive. `accept` and `assess` are
unchanged. Completion claims the M5.1 generation, not the Stage 2 generation.

`complete` reuses the reservation and requires a stored Stage 2 assessment
with kind `ready`. A missing assessment or a domain Stage 2 failure raises
`ObservationNotReadyForCompletion` and creates neither Incident nor Evidence.
Fingerprint conflict still raises before any completion claim.

Trusted organization always comes from `AuthenticatedConnectorContext`.
`ConnectorRegistrationActorFactory` builds `IncidentRequestContext` from that
organization, the observation `correlation_id`, and a stand-in actor: an
injected test `ExternalRef` or the connector `registration_ref`. The
registration is not treated as a Team 1 employee identity. A custom factory
that returns another organization is rejected by the ingestion service.

If no Incident id is bound, `complete` calls `IncidentService.create_incident`
with the stored Observation title and description, the Stage 2 mapped
severity, and the Stage 2 resolved `service_ref`. It then remembers that
Incident id on the completion slot and `bind_incident` before any Evidence
write. Remembering the id is not a shared transaction with Incident storage.
A later retry with that Incident id does not create a second Incident.

If no Evidence id is bound, `complete` calls
`record_observation_event_evidence` using the stored Observation provenance as
the source input. It does not reconstruct provenance from top-level
`sourceEventId`. Evidence `description` is Observation.description, or
Observation.title when description is absent. `source_label` is
Observation.source. `captured_at` is Observation.occurred_at (the stored
event time, not `receivedAt` or `submittedAt`). `content_ref` comes from an
injected mock factory and is checked by the existing verifier (D-08). After a
successful Evidence write, `complete` calls `complete_binding`.

This is **not** CT-04 `completed`. D-24 remains Needs Team 5 Confirmation.
There is no shared transaction across Incident, Evidence, and ingestion
stores. RCA-001 still does not emit `incident.created`. RCA-004 still stores
an undelivered `evidence.recorded` intent. There is no outbox or CT-06
delivery. Bindings do not survive process restart.

Partial failure and retry:

- Incident create fails before a recoverable id exists: the identity is marked
  so another create is blocked. The coordinator does not assume the Incident
  store is empty. `IncidentService.create_incident` raises
  `UncertainIncidentCreate` when `add` succeeded and the following reload
  failed; that exception carries the generated id. The coordinator remembers
  it and a later owner reuses that Incident. If the id cannot be recovered or
  remembered, completion raises `Incident was created but could not be bound`.
- Incident create succeeds and bind fails: the created id is stored on the
  completion slot before the reservation copy, and again by
  `remember_created_incident`. The owned generation is released. Retry reuses
  that Incident. If the id cannot be persisted safely, completion raises
  `Incident was created but could not be bound` and a later owner will not
  silently create another Incident.
- Evidence fails after Incident create: incident-only binding is kept. Only
  the owned generation is released. Retry reuses that Incident and writes
  Evidence only.
- Full binding: later `complete` returns the same ids and does not write
  again.
- Evidence is append-only and has no idempotency key. The coordinator never
  blindly records Evidence after an uncertain write. If observation-origin
  event Evidence already exists on the bound Incident (same stored
  provenance provider, sourceEventId, and source account), that id is reused
  and bound. `collector_ref` is not part of that match. M2
  `IdempotencyIdentity` is organization, source, source account, and
  sourceEventId; it also excludes `collectorRef`. Including collector would
  treat the same provider event as new Evidence after a collector change and
  could append a second row. Unrelated manual or tool-execution Evidence is
  still not reused. If more than one matching row exists, or Incident/Evidence
  lookup fails, completion raises instead of writing another row.
- Waiters of a failed generation receive a generic configuration error.
  `abort` releases only the caller's generation. Incidents and Evidence are
  never deleted.

Remaining process-local limits: bindings do not survive restart. There is no
observation-to-Incident lookup key and no unique create constraint. Recovery
uses only the id generated before `add`, carried on `UncertainIncidentCreate`
or returned by a successful create. A wrapper that persists an Incident and
raises a generic error without that id cannot be recovered; another create is
blocked. A crash after `add` and before the exception is raised leaves the
same gap as a crash before remember. If ownership is lost before the id is
stored and another owner is already in flight, that other owner may still
create; this process then refuses further creates and raises the unbound
reconciliation error. There is still no shared transaction or exactly-once
create.

## Not in this milestone

No database, migration, HTTP route, durable receipt, processing attempt, audit
outbox, or live content storage. No live provider authentication, polling, or
webhook. No grouping, token reuse, reprocessing, or severity correction.
CT-04 decisions are not treated as Agreed. D-24 and D-08 remain unresolved.
