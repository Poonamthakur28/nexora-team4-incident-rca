import type { InvestigationId } from '../incidents/incidents.types.js';
import type { Team4EntityId } from '../../shared/identifiers.js';

export interface FixProposalDraft {
  investigationId: InvestigationId;
  candidateId: Team4EntityId;
  summary: string;
  expectedOutcome: string;
  risks: string[];
  requiresHumanReview: true;
}
