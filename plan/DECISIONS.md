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

## Closed on 16 November 2026

| Topic | Decision | Consequence for the build |
| --- | --- | --- |
| Cloud | Google Cloud, `us-central1`. | Artifacts live in `esl-bucket-01-enterprise` (regional, versioning on, public access prevented) through the S3 driver and the Cloud Storage XML endpoint. The `agent-bucket-access` service account holds Storage Object User on that bucket only, with an HMAC key kept outside the repository. Secret Manager stays off until the model key exists in Phase 1. |

## Revised on 17 November 2026

The build now mirrors a production data platform on Google Cloud. This section supersedes the rows above where they differ: **Source data**, **Cloud** ("DuckDB stays the warehouse"), and the DuckDB check under **Drift**, which now runs against BigQuery.

| Topic | Decision | Consequence for the build |
| --- | --- | --- |
| Source data | Kaggle `moutasmtamimi/dataset-erp-system-modules-tables-dependency`, pinned to version 11. A fictional manufacturer and trading company (Zad Industrial & Trading Co., JOD, January 2025 to July 2026): 199 seed tables, 14,779 rows, plus a schema workbook with a column dictionary, 748 documented relationships, and a load order. Replaces the "Levantia ERP-MTDD" working name. | Adapter name `erp_mtdd`. The schema workbook is the first document corpus for retrieval. Licence to be confirmed on the dataset page before the repository is public. |
| Warehouse | **BigQuery**, `us-central1`. Bronze is external tables over Parquet in the bucket. Silver and gold are native BigQuery datasets. DuckDB is dropped. | Free tier covers this volume (10 GB storage, 1 TB queries a month). A per-query bytes cap is set. |
| Transformation | **dbt Core** with `dbt-bigquery`. Bronze, silver, gold models, with tests and silver-versus-gold KPI reconciliation. | dbt models are compiled from the approved ontology, not written by an agent. |
| Orchestration | **Dagster**, open source, run in Docker. Not Airflow, not Cloud Composer. | Composer's idle cost would spend the trial credit in under a month. |
| Spark | Not used. | The volume does not justify a cluster. |
| Agent runtime | **LangGraph** for the debate graph, with ReAct tools that query the profile and the warehouse and search documents. One open-weight model behind an OpenAI-compatible API. | The panel, judge, and `human_required` promotion are unchanged. |
| Retrieval | Hybrid: **pgvector** plus BM25 in the control-plane Postgres. | No separate vector database. |
| Evaluation and tracing | **Langfuse** for debate traces and evals, **OpenTelemetry** for the control plane. Gates in GitHub Actions: exception recall at least 0.70, stability at least 0.75 across 3 runs, 100% refusal on the adversarial question set (reported with its size and the false-refusal rate). | A gate is a target until a CI run passes it. |
| Serving | **Cube** SQL API to Superset, plus a guardrailed **MCP server** that rejects invalid aggregations and anything outside approved measures. | Replaces the Phase 2b question layer with an MCP server. |
| Infrastructure | **Terraform**: BigQuery, Compute Engine for the Dockerized FastAPI and Postgres control plane, Cloud Storage, Secret Manager, Artifact Registry. CI/CD in GitHub Actions. | Terraform arrives with milestone 8, not Phase 3. Vertex AI and Composer stay off. |

## Still open, and when it gets closed

| Topic | Closes in |
| --- | --- |
| Which model vendor and which model id | Phase 1, before the first debate. The framework spec already has an empty slot |
| Compute Engine machine size for the demo | Milestone 8. Local Compose is the development target until then |
