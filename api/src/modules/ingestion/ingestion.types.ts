import type { ExternalRef } from '../../shared/identifiers.js';

export interface IncidentIntake {
  source: 'manual' | 'fixture';
  externalIncidentRef?: ExternalRef;
  title: string;
  description: string;
  occurredAt: string;
}
