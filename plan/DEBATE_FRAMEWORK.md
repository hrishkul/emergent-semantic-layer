# Debate framework

Locked from Motger, Oriol, Marco, and Franch, *Multi-Agent Debate Strategies: Survey, Taxonomy, and Challenges* (arXiv:2607.26212v1). The paper is a taxonomy of 141 studies, not a system to install.

The checked-in document is `specs/ontology_debate.json`. `esl.debate` refuses a sales-only panel, and it refuses a majority vote.

## Sales is the slice, not the panel

Phase 1 materializes sales, plus the shared foundation entities that slice needs. That is a pipeline decision: which models get built first.

The debate is how the ontology is produced. Shared concepts (customer, item, legal entity, order, invoice, stock) are contested by more than one vertical. A panel of sales roles would write a sales schema and call it the model. The panel is therefore every vertical, on this run and on later ones.

Working names for the five, until the module list from the design notes replaces them:

| Vertical | What it defends |
| --- | --- |
| Sales | Booked commitment to a customer, including before invoice |
| Finance | External invoiced revenue, tax, credit, receivables, entity boundaries |
| Inventory | Stock and consignment, which move on shipment and receipt |
| Procurement | The buying entity, and the purchase that matches an intercompany sale |
| Production | Availability when work is completed, not when it is promised |

Phase 2 is when finance, inventory, procurement, and production get their own silver, gold, and metrics. They do not wait until Phase 2 to sit in the debate.

## What we took from the paper

The task is an open-ended settlement, not a question with one answer. The paper's split fits: qualitative disagreement uses distinct stances and a judge who evaluates arguments. Each vertical is a stance. Humans are not debaters. A person promotes the proposal after the judge writes it.

| Taxonomy axis | Locked value | Why |
| --- | --- | --- |
| Personas | One manual stance per vertical | Stance is the control the survey finds usable. The disagreement is between verticals. |
| Base model | One open-weight model, OpenAI-compatible API. Provider and model id empty | Homogeneous models keep a miss attributable to the protocol. The vendor is a Phase 1 choice. |
| Topology | Static and sparse | Round 1 verticals do not read each other. Round 2 they all critique the same verbatim claim list. |
| Protocol | Hybrid, two rounds | Simultaneous claims, then a simultaneous critique. No single vertical speaks first. |
| Content | Verbatim claims, summarized digest | The digest is for the reviewer. The judge and the verticals still see the claims. |
| Memory | Short-term, plus retrieval | A claim needs a table or a document from that vertical's part of the extract. No memory across runs, so the three-run stability gate stays meaningful. |
| Agreement | Judge, argument evaluation, dissent kept | A cited claim another vertical did not answer stays in the proposal. |
| Promotion | Human, `human_required` | The judge does not approve. |
| Materialization | Phase 1 slice is sales, with shared foundation | This field is not the panel. |

## Budgets and gates

- One debate under 15 minutes and under $8. The cap is for the full panel, not a smaller sales rehearsal.
- Exception recall at least 0.70.
- Stability at least 0.75 across 3 runs.

## What stays out

A sales-only panel. Personality-trait roles standing in for a vertical. Automatic persona generation, dynamic graphs, embedding messages, long-term memory, confidence-weighted votes, and a second model inside the same debate. A change to the panel goes through the review queue as a new version of this spec.
