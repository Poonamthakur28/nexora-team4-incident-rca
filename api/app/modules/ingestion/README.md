# RCA-002 Incident Ingestion

M1 records Observation shape and Stage 1 checks in memory. It does not create
receipts, reserve identities, store attempts, or call a live connector.

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
`provenance.sourceEventId` equals `sourceEventId`. Those are Stage 2 (D-21).
Service resolution, severity mapping, and clock-skew cutoffs are also out of
scope. No numeric skew tolerance is defined (D-16).

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

## Not in this milestone

No database, migration, HTTP route, durable receipt, idempotency store,
processing attempt, audit outbox, or content storage. No live provider
authentication, polling, or webhook. No duplicate detection, conflict outcome,
Stage 2 check, service resolution, or severity mapping. CT-04 decisions are
not treated as Agreed.
