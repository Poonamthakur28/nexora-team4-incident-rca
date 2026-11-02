"""RCA-004 domain failures, independent of FastAPI and transport."""


class EvidenceDomainError(Exception):
    """Base type for Evidence Collection domain failures."""


class EvidenceNotFound(EvidenceDomainError):
    """The Evidence is absent from the caller's organization."""

    def __init__(self, evidence_id: str) -> None:
        self.evidence_id = evidence_id
        super().__init__(f"Evidence {evidence_id} was not found.")


class InvalidEvidenceInput(EvidenceDomainError):
    """An Evidence command or repository operation violates domain rules."""


class UnverifiedContentReference(InvalidEvidenceInput):
    """A supplied opaque content reference was not confirmed by the injected verifier."""


class EvidenceServiceConfigurationError(EvidenceDomainError):
    """An injected id factory, clock, or content verifier is unavailable or invalid."""


class UnsupportedEvidenceRelationship(InvalidEvidenceInput):
    """A relationship requires an entity or workflow not implemented in RCA-004."""


class InconsistentEvidenceRecord(EvidenceDomainError):
    """Evidence and its locally stored audit intent do not describe the same record."""
