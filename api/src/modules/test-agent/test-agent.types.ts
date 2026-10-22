import type { Team4EntityId } from '../../shared/identifiers.js';

export interface TestPlanDraft {
  proposalId: Team4EntityId;
  objective: string;
  cases: Array<{ title: string; steps: string[]; expectedResult: string }>;
}
