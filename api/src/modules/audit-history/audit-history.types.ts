import type { InvestigationId } from '../incidents/incidents.types.js';
import type { ExternalRef, Team4EntityId } from '../../shared/identifiers.js';

export interface InvestigationHistoryEntry {
  id: Team4EntityId;
  investigationId: InvestigationId;
  eventType: string;
  actorRef?: ExternalRef;
  occurredAt: string;
  details: Record<string, unknown>;
}
