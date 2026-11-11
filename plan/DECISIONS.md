# Decisions

Locked on 15 October 2026, before Phase 0 code. These override the recommendations in the design walkthrough where they differ.

| Topic | Decision | Consequence for the build |
| --- | --- | --- |
| First slice | Sales, plus the shared foundation entities that slice needs. | Phase 1 builds the sales pipeline. The ontology debate still seats every vertical. |
| Source data | Public Levantia ERP extract (Kaggle ERP-MTDD). Epicor is a later adapter. | The extract is a source adapter, not a schema baked into the warehouse. Licence is CC BY-NC-SA 4.0: fine for a portfolio demo, not a commercial product. |
| Approval | A person approves every proposal until calibration data exists. | The only enabled policy is `human_required`. There is no auto-approve path to turn on by accident. |
| BI | Apache Superset in Phase 2. Open source. | Phase 1 still exposes a SQL API. Power BI can connect to that same API later. No Power BI tenant, no Looker, no QuickSight. |
| Debate framework | Cross-vertical. The taxonomy in arXiv:2607.26212, instantiated as `specs/ontology_debate.json`. One stance each for sales, finance, inventory, procurement, and production. A judge keeps dissent. A person promotes. | Phase 1 materializes sales. It does not shrink the panel to sales. See `plan/DEBATE_FRAMEWORK.md`. |
| Debate model | Not chosen. An OpenAI-compatible API in front of one open-weight model. | Provider and model id stay empty on the spec until Phase 1. Candidates then: DeepSeek, Qwen, SiliconFlow. One debate under 15 minutes and under $8. |
| Cloud | Not chosen. Confirm the account after Phase 0. | Portable contracts. DuckDB stays the warehouse. See `plan/CLOUD.md`. |

## Added on 11 November 2026

From a review of a graph-database design (documents into a graph ontology, a functional agent panel, Cube compiled from the graph, conversational BI). The parts that fit are kept. The parts that conflict with the decisions above are not adopted.

| Topic | Decision | Consequence for the build |
| --- | --- | --- |
| Ontology store | The `ontology` artifact is the system of record: nodes, edges, and links to physical tables and source documents, versioned and content-addressed. No graph database. | A graph store may be added later as a read-only projection of an approved version, for lineage queries. It never accepts writes. |
| Agent panel | The vertical panel stays. No ingestion, modeling, or governance agents. | Grain, normalization, and star versus wide tables follow from the approved ontology in deterministic dbt models and tests. The judge does not reach consensus or approve. |
| Cube manifest | Compiled, not written by an agent. A plain function from an approved `ontology` version and an approved `kpi_registry` version to a `cube_manifest`. | The output is a new artifact version and goes through the review queue like any other. |
| Drift | Compiling from the ontology removes drift between Cube and the ontology only. Drift between Cube and the warehouse is a CI check. | dbt tests plus a check of the compiled manifest against DuckDB run in CI from Phase 1. |
| Conversational BI | A question layer over the Cube API, after Superset. Phase 2b. | It only reaches approved measures. Every answer shows the resolved query (measures, dimensions, filters, time window) and the ontology version. |

## Still open, and when it gets closed

| Topic | Closes in |
| --- | --- |
| Which model vendor and which model id | Phase 1, before the first debate. The framework spec already has an empty slot |
| Which cloud account was opened | After Phase 0, when you confirm the vendor. Task P0-7 points the artifact store at that bucket |
| Whether the demo VM is Google Compute Engine, an Azure VM, or EC2 | First time the demo is published. Local Compose is the development target until then |
