import type { ExternalRef, Team4EntityId } from '../../shared/identifiers.js';

export type ReviewDecision = 'pending' | 'approved' | 'rejected' | 'needs_changes';

export interface HumanReview {
  id: Team4EntityId;
  subjectType: 'candidate' | 'fix_proposal' | 'resolution';
  subjectId: Team4EntityId;
  decision: ReviewDecision;
  reviewerRef?: ExternalRef;
  decidedAt?: string;
  rationale?: string;
}
