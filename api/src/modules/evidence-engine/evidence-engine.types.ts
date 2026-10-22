import type { Team4EntityId } from '../../shared/identifiers.js';

export interface EvidenceAssessment {
  evidenceId: Team4EntityId;
  summary: string;
  relevance: number;
  limitations: string[];
  processedAt: string;
}
