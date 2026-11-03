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
digest, the canonical bytes, and later an optional Stage 2 assessment.
`accept` does not write an assessment. The same identity and digest is a
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
M6 (D-26). Check order versus Team 5 remains unset (D-11). Completion is
M5 (D-24).

Single-flight uses the repository lock plus a per-identity condition on
that lock. The first caller evaluates outside the lock. Duplicates wait.
`in_flight` is internal and is not a processing status. Different
identities do not wait on each other's resolver or mapper work.

`assess` does not create an Incident, Evidence, receipt, delivery id, or
attempt.

## Not in this milestone

No database, migration, HTTP route, durable receipt, processing attempt, audit
outbox, or content storage. No live provider authentication, polling, or
webhook. No Incident creation, Evidence write, grouping, token reuse, or
reprocessing. CT-04 decisions are not treated as Agreed.
