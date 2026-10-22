import type { InvestigationId } from '../incidents/incidents.types.js';
import type { ExternalRef, Team4EntityId } from '../../shared/identifiers.js';

export interface EvidenceSubmission {
  incidentId: Team4EntityId;
  investigationId?: InvestigationId;
  description: string;
  sourceLabel: string;
  capturedAt: string;
  externalSourceRef?: ExternalRef;
}
