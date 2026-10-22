# Incident investigation lifecycle

This is the intended Team 4 workflow and remains subject to product and ERD review.

1. **Ingest** a manual incident report or local fixture; retain external source IDs only as references.
2. **Manage incident** details and record a chronology of events.
3. **Collect evidence** with capture time, source label, and provenance; connect it to the relevant incident/investigation.
4. **Assess evidence** through the Evidence Engine and preserve limitations and traceability.
5. **Investigate** with the AI RCA contract, returning candidate drafts, rationale, uncertainty, missing information, and evidence polarity links.
6. **Review candidates** with a person. AI confidence is advisory; only an explicit human decision can advance a candidate.
7. **Propose a fix** and prepare a test plan; validate outcomes and record blockers.
8. **Approve and resolve** through human review, then retain resolution and investigation history.

Lifecycle states, transitions, authorization rules, and whether a single incident may have concurrent investigations still need product confirmation. The above is a planning flow, not an implemented state machine.
