# Milestone 1 — bronze extract

Completed 20 November 2026. Design is in `plan/PHASE_1.md`. This file records what that milestone required and what this session finished.

## Done when

The `bronze_erp_mtdd` dataset answers queries, and the extract and the profile are approved artifacts.

## Result

The pinned Kaggle ERP seed, version 11 of `moutasmtamimi/dataset-erp-system-modules-tables-dependency`, is in Cloud Storage and queryable in BigQuery. This is the whole extract, 199 tables and 14,686 rows, not a sales-only slice. Sales is the first modeled slice in a later milestone. Bronze keeps the source values as they are.

| Check | Result |
| --- | --- |
| Parquet in the bucket | `gs://esl-bucket-01-enterprise/bronze/erp_mtdd/44b5f43d09d1b186/` — 2 raw workbooks, 199 table files, 6 documentation sheets, 1 manifest |
| `source_extract` approved | `erp-mtdd` version 1. Proposal `a724d23e-1ab4-4036-89ef-bdafb0901d53`, approved by Hrishikesh |
| `source_profile` approved | `erp-mtdd` version 1. Proposal `1242e16e-be09-44bf-bc4c-94001c4588b9`, approved by Hrishikesh. 199/199 primary keys ok, 748 relationships ok |
| BigQuery answers a query | Dataset `bronze_erp_mtdd` in `us-central1`, project `project-9a3d61d7-226e-4e0b-bad`. 199 external tables. `accounting_periods` returns 19 rows |

## What this session did

- Fast-forwarded local `main` to the remote, which already contained the bronze pipeline, the BigQuery warehouse decision, and the Cloud Storage driver.
- Installed the Google Cloud CLI and signed in. Application default credentials use project `project-9a3d61d7-226e-4e0b-bad`.
- Put the bucket and BigQuery settings in a local `.env`. That file is gitignored. The HMAC key is not in the repository.
- Ran `bronze_erp_mtdd`. The first run wrote the extract to the bucket and stopped because the review API was not running.
- Started Postgres 16 and the API on `127.0.0.1:8091`, pointed at the Google bucket, and submitted the source-extract proposal. It was approved.
- Signed in with `gcloud auth login --update-adc`, enabled BigQuery, and reran the job. The extract bytes were unchanged, so no second extract version was opened. The rerun created the external tables and the profile. The profile was approved.
- Stopped the API. Postgres was left running for the review queue.

## Still later

Milestone 2 is the ontology and KPI registry schemas, and the document index over the schema workbook. Silver and gold models for the sales slice are Milestone 5. The other verticals stay in bronze until their own modeled pipelines.
