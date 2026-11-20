# Phase 1 and after: milestones

Stack and reasons are in `plan/DECISIONS.md` (revised 17 November 2026). Estimates are focused build time.

| # | Milestone | Estimate | Done when |
| --- | --- | --- | --- |
| 1 | Bronze: Kaggle extract to Parquet in the bucket, BigQuery external tables, profiler, Dagster job | 1 week | The `bronze_erp_mtdd` dataset answers queries, and the extract and profile are approved artifacts |
| 2 | Ontology and KPI registry schemas, document index (pgvector plus BM25) | 1 week | A hand-written ontology validates, and search returns schema-workbook passages |
| 3 | LangGraph debate: five verticals, ReAct tools, judge, model vendor | 2 weeks | One full debate runs under 15 minutes and $8 and produces a transcript and a proposal |
| 4 | Evals: planted exceptions, stability over 3 runs, Langfuse, CI gates | 1 week | Gates run in CI and report recall and stability |
| 5 | Compiler from the approved ontology to dbt bronze, silver, gold on BigQuery, KPI reconciliation | 1.5 to 2 weeks | `dbt build` passes and silver and gold KPIs reconcile |
| 6 | Cube manifest compiler, Cube SQL API, Superset | 1 week | Superset charts a sales KPI through Cube |
| 7 | Guardrailed MCP server, adversarial question set | 1 week | The adversarial set is refused and the false-refusal rate is reported |
| 8 | Terraform, Compute Engine, Secret Manager, Artifact Registry, CI/CD | 1 week | `terraform apply` from a clean project reproduces the deployment |

## Milestone 1 design

The Dagster job `bronze_erp_mtdd` has four steps.

1. **Download** the pinned Kaggle version with `kagglehub`. No Kaggle login is needed for this public dataset.
2. **Land** in the artifact store under `bronze/erp_mtdd/<extract id>/`: the two original workbooks in `raw/`, one Parquet file per seed table in `tables/`, the schema-workbook sheets in `docs/`, and `manifest.json`. The extract id is derived from the source file hashes, so a rerun of the same version writes nothing new.
3. **Warehouse**: `CREATE OR REPLACE EXTERNAL TABLE` in BigQuery dataset `bronze_erp_mtdd`, one per seed table, over the Parquet URIs. Skipped when no BigQuery project is configured.
4. **Profile**: row counts, column null and distinct counts, documented primary keys checked for uniqueness, every documented relationship checked for orphans, and columns compared with the column dictionary. Stored as `profile.json` next to the manifest.

When a control-plane URL is configured, the manifest is submitted as a `source_extract` artifact and the profile as a `source_profile` artifact, each with a `human_required` proposal.

Bronze keeps values as the source holds them. Dates stay text. Silver casts with the column dictionary types.

## Milestone 2 design

The ontology and the KPI registry are JSON artifacts. The API rejects a document that does not match, the same way it rejects a debate spec. There is no graph database. The hand-written sales ontology is `specs/ontology_erp_mtdd.json`. The KPI registry is `specs/kpi_registry_erp_mtdd.json`.

An ontology has nodes and edges. Every node has one authoritative bronze table and at least one link into the schema workbook. A second table may be marked `duplicate`. An edge is a foreign key: `source` holds `column`, and `target` is the referenced node. The sales slice keeps the shared foundation nodes `customer`, `item`, `legal_entity`, `order`, `invoice`, and `stock`. The invoice node records what the column dictionary says: `customer_invoices` is the authoritative accounts-receivable document, and the sales `invoices` table duplicates it.

A KPI names one node, one aggregation (`sum`, `count`, or `count_distinct`), and one measure column on a table of that node. The compiler that turns the measure into SQL is milestone 5.

The document index is one passage per schema-workbook row, stored in the control-plane Postgres. The embedding is 384-dimensional, from the local model `BAAI/bge-small-en-v1.5`. BM25 ranks the same text. `GET /search` fuses the two rankings. The debate model is not called here.

Passage locators are stable, so an ontology can cite them:

| Sheet | Locator |
| --- | --- |
| Table Index, Dependency Register | table name |
| Column Dictionary | `Table.Column` |
| Relationships | `Child Table.Child Column -> Parent Table.Parent Key` |
| Load Order | table name |
| Complexity Rules | complexity label |

`python -m esl.corpus index` reads the schema workbook and replaces the `erp_mtdd_schema` corpus. `python -m esl.corpus search "<query>"` prints the top passages.
