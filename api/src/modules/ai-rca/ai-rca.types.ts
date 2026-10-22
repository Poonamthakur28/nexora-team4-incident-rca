import type { InvestigationId } from '../incidents/incidents.types.js';
import type { ExternalRef, Team4EntityId } from '../../shared/identifiers.js';

export type EvidencePolarity = 'supports' | 'contradicts' | 'context';

export interface InvestigationContext {
  investigationId: InvestigationId;
  incident: { externalIncidentRef?: ExternalRef; summary: string; occurredAt: string };
  evidence: Array<{ evidenceId: Team4EntityId; description: string; sourceRef?: ExternalRef }>;
}

export interface CandidateEvidenceLink {
  evidenceId: Team4EntityId;
  polarity: EvidencePolarity;
  explanation: string;
}

export interface RootCauseCandidateDraft {
  title: string;
  rationale: string;
  confidence: number;
  uncertainty: string[];
  missingInformation: string[];
  evidence: CandidateEvidenceLink[];
  status: 'proposed';
}

export interface AiRcaAgent {
  analyze(context: InvestigationContext): Promise<RootCauseCandidateDraft[]>;
}
