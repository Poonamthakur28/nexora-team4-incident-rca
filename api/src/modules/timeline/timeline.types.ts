import type { Team4EntityId } from '../../shared/identifiers.js';

export interface TimelineEntry {
  id: Team4EntityId;
  incidentId: Team4EntityId;
  occurredAt: string;
  recordedAt: string;
  label: string;
  detail?: string;
}
