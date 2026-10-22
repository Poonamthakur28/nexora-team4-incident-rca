import type { Team4EntityId } from '../../shared/identifiers.js';

export type ValidationState = 'not_started' | 'pending' | 'passed' | 'failed' | 'blocked';

export interface ValidationSummary {
  proposalId: Team4EntityId;
  state: ValidationState;
  completedAt?: string;
  notes: string[];
}
