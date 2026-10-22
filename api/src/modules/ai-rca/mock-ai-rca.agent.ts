import type { AiRcaAgent, InvestigationContext } from './ai-rca.types.js';

/** Deterministic local fixture behavior; never promotes candidates to confirmed causes. */
export const mockAiRcaAgent: AiRcaAgent = {
  async analyze(context: InvestigationContext) {
    if (context.evidence.length === 0) return [{
      title: 'Insufficient evidence for a candidate', rationale: 'The investigation has no linked evidence to assess.', confidence: 0,
      uncertainty: ['No evidence was supplied.'], missingInformation: ['Collect investigation evidence.'], evidence: [], status: 'proposed',
    }];
    return [{
      title: 'Example candidate for review', rationale: 'Mock output for interface development; it makes no causal claim about the incident.', confidence: 0.25,
      uncertainty: ['Mock analysis is not based on a live model.'], missingInformation: ['Run evidence analysis with an approved implementation.'],
      evidence: context.evidence.map((item) => ({ evidenceId: item.evidenceId, polarity: 'context' as const, explanation: 'Fixture evidence link; interpretation requires review.' })), status: 'proposed',
    }];
  },
};
