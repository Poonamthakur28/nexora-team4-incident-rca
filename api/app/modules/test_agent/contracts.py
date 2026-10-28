from app.shared.contract import ContractModel
from app.shared.identifiers import Team4EntityId


class TestCaseDraft(ContractModel):
    __test__ = False

    title: str
    steps: list[str]
    expected_result: str


class TestPlanDraft(ContractModel):
    __test__ = False

    proposal_id: Team4EntityId
    objective: str
    cases: list[TestCaseDraft]
