import type { CandidateEvidenceLink, RootCauseCandidateDraft } from '../ai-rca/ai-rca.types.js';
import type { InvestigationId } from '../incidents/incidents.types.js';
import type { Team4EntityId } from '../../shared/identifiers.js';

export interface RootCauseCandidate {
  id: Team4EntityId;
  investigationId: InvestigationId;
  title: string;
  rationale: string;
  confidence: number;
  uncertainty: string[];
  missingInformation: string[];
  evidence: CandidateEvidenceLink[];
  status: RootCauseCandidateDraft['status'];
  reviewRequired: true;
}
