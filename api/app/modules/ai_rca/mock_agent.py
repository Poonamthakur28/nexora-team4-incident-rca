from app.modules.ai_rca.contracts import (
    CandidateEvidenceLink,
    InvestigationContext,
    RootCauseCandidateDraft,
)


class MockAiRcaAgent:
    """Deterministic local fixture behavior; never promotes candidates to confirmed causes."""

    async def analyze(self, context: InvestigationContext) -> list[RootCauseCandidateDraft]:
        if not context.evidence:
            return [
                RootCauseCandidateDraft(
                    title="Insufficient evidence for a candidate",
                    rationale="The investigation has no linked evidence to assess.",
                    confidence=0,
                    uncertainty=["No evidence was supplied."],
                    missing_information=["Collect investigation evidence."],
                    evidence=[],
                    status="proposed",
                )
            ]
        return [
            RootCauseCandidateDraft(
                title="Example candidate for review",
                rationale="Mock output for interface development; it makes no causal claim about the incident.",
                confidence=0.25,
                uncertainty=["Mock analysis is not based on a live model."],
                missing_information=["Run evidence analysis with an approved implementation."],
                evidence=[
                    CandidateEvidenceLink(
                        evidence_id=item.evidence_id,
                        polarity="context",
                        explanation="Fixture evidence link; interpretation requires review.",
                    )
                    for item in context.evidence
                ],
                status="proposed",
            )
        ]


mock_ai_rca_agent = MockAiRcaAgent()
