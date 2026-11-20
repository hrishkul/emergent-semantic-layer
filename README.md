# Emergent Semantic Layer

Agents propose an ontology, a KPI registry, and a Cube manifest. Deterministic pipelines compile those into a warehouse. A person approves every proposal until there is calibration data.

Phase 0 built the control plane: a versioned artifact store, a review queue, tracing, and the debate specification. Phase 1 milestones are in [plan/PHASE_1.md](plan/PHASE_1.md).

## Decisions

- The first pipeline is sales, plus shared foundation. The ontology debate seats every vertical on that run.
- Data is the Kaggle ERP seed dataset (adapter `erp_mtdd`). An Epicor adapter comes later.
- The platform is Google Cloud: BigQuery, dbt, Dagster, Cube, Superset, an MCP server, LangGraph agents, Langfuse, and Terraform. See [plan/DECISIONS.md](plan/DECISIONS.md).
- BI is Apache Superset in Phase 2. The SQL API stays something Power BI can also connect to.
- The debate framework is locked in [plan/DEBATE_FRAMEWORK.md](plan/DEBATE_FRAMEWORK.md), from the taxonomy in [arXiv:2607.26212](https://arxiv.org/html/2607.26212v1). The document is [specs/ontology_debate.json](specs/ontology_debate.json).
- The debate model is Gemma 4 26B A4B IT on Vertex AI MaaS, `google/gemma-4-26b-a4b-it-maas`, one model for every role. See [plan/DECISIONS.md](plan/DECISIONS.md).
- The service map and console steps are in [plan/CLOUD.md](plan/CLOUD.md).

The project license is the MIT license in the GitHub repository `hrishkul/emergent-semantic-layer`. That repository currently holds the license only.

## Run locally

Postgres 16 with the pgvector extension (`pgvector/pgvector:pg16` in Compose), then:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
export DATABASE_URL=postgresql://esl:esl@127.0.0.1:5432/esl
.venv/bin/python -m esl.migrate
.venv/bin/uvicorn esl.app:app --host 127.0.0.1 --port 8091
```

`GET /health` returns `{"status": "ok"}`.

Compose (`compose.yaml`) adds MinIO and an OpenTelemetry collector for a later machine. The API defaults to a directory artifact store so it runs without either.

```bash
.venv/bin/ruff check src tests
.venv/bin/pytest
```

## Milestone 1: bronze pipeline

The Dagster job `bronze_erp_mtdd` downloads the pinned Kaggle dataset, lands it under `bronze/erp_mtdd/<extract id>/` in the artifact store (raw workbooks, one Parquet file per table, documentation sheets, manifest), creates BigQuery external tables over the Parquet files, and profiles the extract against its documentation. Design: [plan/PHASE_1.md](plan/PHASE_1.md).

```bash
.venv/bin/pip install -e ".[dev,pipeline]"
.venv/bin/python -m esl.pipeline
```

Without settings it writes to a local directory and skips BigQuery. Against Google Cloud, set the bucket variables from `plan/CLOUD.md`, plus `BQ_PROJECT`, after `gcloud auth application-default login`. With `ESL_API_URL` and `ESL_ACTOR`, the manifest and profile are submitted as `source_extract` and `source_profile` proposals. A rerun with the same data writes nothing and proposes nothing.

`dagster dev -m esl.pipeline.definitions` opens the Dagster UI. Compose runs the same UI on port 3000.

## Milestone 2: ontology, KPI registry, document index

`POST /artifacts` validates `ontology` and `kpi_registry` before storing them. The hand-written sales ontology and KPI registry are `specs/ontology_erp_mtdd.json` and `specs/kpi_registry_erp_mtdd.json`. Design: [plan/PHASE_1.md](plan/PHASE_1.md).

The schema workbook is indexed in Postgres (pgvector plus BM25). Embeddings are local (`BAAI/bge-small-en-v1.5` via the `index` extra). The debate model is separate: `google/gemma-4-26b-a4b-it-maas`.

```bash
.venv/bin/pip install -e ".[index]"
ERP_MTDD_DIR=/path/to/the/kaggle/version .venv/bin/python -m esl.corpus index
.venv/bin/python -m esl.corpus search "final order value"
```

`GET /search?q=final+order+value` returns the same passages.

## API

`POST /artifacts` stores a version, or returns the latest version with `existing: true` and status 200 when the bytes are unchanged. `kind` is `source_extract`, `source_profile`, `ontology`, `kpi_registry`, `cube_manifest`, `debate_transcript`, or `debate_spec`. A `debate_spec` must match the locked framework. An `ontology` must be the sales slice plus the shared foundation nodes, and a `kpi_registry` must name one measure per KPI. `GET /search` returns schema-workbook passages for a query.

`POST /proposals` opens a review. The only policy is `human_required`.

`POST /proposals/{id}/decision` records `approved` or `rejected` with an actor and a reason. A second decision is refused.
