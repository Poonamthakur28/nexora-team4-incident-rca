import { asTeam4EntityId, type ExternalRef, type Team4EntityId } from '../../shared/identifiers.js';

declare const investigationIdBrand: unique symbol;

/**
 * Canonical investigation id.
 * Owner: RCA-001 Incident Management.
 * Unresolved: `docs/erd/team4-erd.md` proposes `rca_investigation`, but no
 * entity, foreign key, or lifecycle is approved. This alias adds no module
 * and no database model.
 */
export type InvestigationId = Team4EntityId & { readonly [investigationIdBrand]: 'investigation' };

export function asInvestigationId(id: string): InvestigationId {
  return asTeam4EntityId(id) as InvestigationId;
}

export interface IncidentSummary {
  id: Team4EntityId;
  title: string;
  status: string;
  createdAt: string;
  externalRefs?: ExternalRef[];
}
