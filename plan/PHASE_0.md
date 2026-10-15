# Phase 0 — foundations

Scope, from the design walkthrough: schemas, a versioned artifact store, a review queue, tracing, and CI. No agents. No dbt. No Cube. No Superset.

The cloud vendor is confirmed after this phase. Tasks P0-2 through P0-6 run against local Postgres. Task P0-7 is the only one that needs the account from `plan/CLOUD.md`.

## Done when

A person can submit a proposal, see it waiting, and approve or reject it. The decision stores who did it and why. The artifact bytes are content-addressed and versioned. A trace is exported for the write. The sales debate spec can be submitted and approved, and a majority-vote spec is refused. CI is green. Pointing the artifact store at an S3 endpoint instead of a local directory does not change the API.

Nothing in that path calls a model, and nothing is approved without a person.

## Stack

Python 3.12 and FastAPI for the control plane. dbt, DuckDB, and the later debate orchestration are Python, so the control plane matches them. Cube and Superset stay separate containers in later phases.

Postgres 16 for the queue and metadata. MinIO for the S3-compatible store in Compose. An OpenTelemetry collector for traces.

## Schema

Migrations are plain SQL in `src/esl/migrations`. Four tables are enough.

`artifacts`
: One row per immutable version. Columns: id, kind (`source_extract`, `ontology`, `kpi_registry`, `cube_manifest`, `debate_transcript`, `debate_spec`), logical name, monotonic version, content URI, sha256, created at, created by. `debate_spec` is validated against the locked framework before it is stored.

`proposals`
: A request to accept an artifact version. Columns: id, artifact id, parent artifact id, status (`pending`, `approved`, `rejected`, `superseded`), policy, summary, submitted at, submitted by. The only policy value the API will write is `human_required`.

`approvals`
: One decision row. Columns: id, proposal id, decision (`approved` or `rejected`), actor, reason, decided at. Actor is required. There is no system actor.

`runs`
: One row per pipeline attempt, so later phases can attach traces. Columns: id, kind, status, started at, finished at, trace id.

The source extract is an artifact of kind `source_extract` whose metadata names the adapter: `levantia_erp` now, `epicor` later. The warehouse schema does not import ERP table names directly.

## Build order

| Task | What lands | Account |
| --- | --- | --- |
| P0-1 | This plan, the locked decisions, and the service contract. | No |
| P0-2 | Repository skeleton: `pyproject.toml`, FastAPI app, SQL migrations, Compose file with Postgres, MinIO, and the OTel collector. Health check only. | No |
| P0-3 | Artifact store interface. Directory driver and S3 driver. Tests against MinIO. | No |
| P0-4 | Review API. Submit, list pending, approve, reject. Reject a missing actor, a second decision, and any policy other than `human_required`. | No |
| P0-5 | OpenTelemetry on those writes. A test asserts a span is exported. | No |
| P0-6 | GitHub Actions: ruff, the migration applied to a Postgres service container, pytest. | No |
| P0-7 | Point the S3 driver at the real bucket (AWS, or Cloud Storage HMAC). Azure Blob driver only if that is the account. Secret stays empty until Phase 1. | Yes |

Each task is one commit. P0-2 is the next one.

## Explicitly later

| Item | Phase |
| --- | --- |
| Debate client, response cache, model vendor | 1 |
| Levantia extract, planted exceptions, profiler, document index | 1 |
| dbt on DuckDB, ontology tests, KPI reconciliation | 1 |
| Cube manifest and the SQL API that refuses a bad aggregation | 1 |
| Grafana lineage view | 1 |
| Superset | 2 |
| Pipelines for finance, inventory, procurement, and production | 2 |
| Terraform, Epicor adapter, row-level security | 3 |
