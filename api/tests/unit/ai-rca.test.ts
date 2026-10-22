import { describe, expect, it } from 'vitest';
import { mockAiRcaAgent } from '../../src/modules/ai-rca/mock-ai-rca.agent.js';
import {
  asInvestigationId,
  type InvestigationId,
} from '../../src/modules/incidents/incidents.types.js';
import type { RootCauseCandidate } from '../../src/modules/root-candidates/root-candidates.types.js';
import {
  asTeam4EntityId,
  type ExternalRef,
  type Team4EntityId,
} from '../../src/shared/identifiers.js';

type Expect<T extends true> = T;
type NotAssignable<A, B> = [A] extends [B] ? false : true;

describe('mock AI RCA agent', () => {
  it('returns an explicitly proposed candidate with traceable evidence', async () => {
    const results = await mockAiRcaAgent.analyze({
      investigationId: asInvestigationId('inv-1'),
      incident: { summary: 'Synthetic fixture', occurredAt: '2026-01-01T00:00:00Z' },
      evidence: [{ evidenceId: asTeam4EntityId('ev-1'), description: 'Synthetic event' }],
    });
    const draft = results[0];
    expect(draft?.status).toBe('proposed');
    expect(draft?.evidence[0]?.evidenceId).toBe('ev-1');
    expect(draft?.confidence).toBeLessThan(1);
    expect(draft?.rationale.length).toBeGreaterThan(0);
    expect(draft?.uncertainty.length).toBeGreaterThan(0);
    expect(draft?.missingInformation.length).toBeGreaterThan(0);

    const stored: RootCauseCandidate = {
      id: asTeam4EntityId('candidate-1'),
      investigationId: asInvestigationId('inv-1'),
      title: draft?.title ?? '',
      rationale: draft?.rationale ?? '',
      confidence: draft?.confidence ?? 0,
      uncertainty: draft?.uncertainty ?? [],
      missingInformation: draft?.missingInformation ?? [],
      evidence: draft?.evidence ?? [],
      status: 'proposed',
      reviewRequired: true,
    };
    expect(stored.status).toBe('proposed');
    expect(stored.missingInformation).toEqual(draft?.missingInformation);
    expect(stored.reviewRequired).toBe(true);
  });

  it('keeps an empty-evidence draft proposed and lists the missing information', async () => {
    const results = await mockAiRcaAgent.analyze({
      investigationId: asInvestigationId('inv-empty'),
      incident: { summary: 'Synthetic fixture', occurredAt: '2026-01-01T00:00:00Z' },
      evidence: [],
    });
    expect(results[0]?.status).toBe('proposed');
    expect(results[0]?.confidence).toBe(0);
    expect(results[0]?.missingInformation).toContain('Collect investigation evidence.');
    expect(results[0]?.evidence).toEqual([]);
  });

  it('keeps Team 4 ids distinct from external references and investigation ids', () => {
    const externalIsNotTeam4: Expect<NotAssignable<ExternalRef, Team4EntityId>> = true;
    const team4IdIsNotInvestigation: Expect<NotAssignable<Team4EntityId, InvestigationId>> = true;
    const investigationIsTeam4: Expect<InvestigationId extends Team4EntityId ? true : false> = true;
    expect([externalIsNotTeam4, team4IdIsNotInvestigation, investigationIsTeam4]).toEqual([
      true,
      true,
      true,
    ]);
  });
});
