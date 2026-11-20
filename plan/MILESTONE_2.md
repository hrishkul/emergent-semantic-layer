# Milestone 2 — ontology, KPI registry, document index

Completed 20 November 2026. Design is in `plan/PHASE_1.md`. This file records what that milestone required and what this session finished.

## Done when

A hand-written ontology validates, and search returns schema-workbook passages.

## Result

The sales ontology and the KPI registry validate and are stored as version 1 of `erp-mtdd`. Both proposals are approved. The schema workbook is indexed in Postgres: 4,066 passages, pgvector embeddings from local `BAAI/bge-small-en-v1.5`, and BM25 over the same text. The debate model chosen for milestone 3 is `google/gemma-4-26b-a4b-it-maas`.

| Check | Result |
| --- | --- |
| Ontology validates | `specs/ontology_erp_mtdd.json`. 9 nodes, 16 edges. Shared foundation: customer, item, legal entity, order, invoice, stock. Invoice records `customer_invoices` as authoritative and sales `invoices` as a duplicate |
| KPI registry validates | `specs/kpi_registry_erp_mtdd.json`. Booked value, invoiced revenue, quoted value. Each measure sits on a table of its node |
| Links cite the workbook | Every document locator in those two files is a passage built from the schema workbook |
| Search returns a passage | `GET /search?q=final+order+value` returns `Column Dictionary` / `Sales Orders.Total_Amount`: "Final order value" |
| Corpus | `erp_mtdd_schema`, 4,066 passages, in the control-plane Postgres |

## What this session did

- Added validation for `ontology` and `kpi_registry` on `POST /artifacts`, and `GET /search`.
- Switched Compose and CI to `pgvector/pgvector:pg16`. The milestone 1 approvals were dumped and restored onto that database. They are still approved.
- Indexed the six schema-workbook sheets from the pinned Kaggle version.
- Submitted the ontology and the KPI registry to the bucket. Ontology proposal `2e33022b-c46d-4a5c-b276-7714c26799dd`, approved by Hrishikesh. KPI proposal `78bde4e0-aedb-46bb-aaa8-29ae8bc176de`, approved by Hrishikesh.

## Still later

Milestone 3 is the LangGraph debate on `google/gemma-4-26b-a4b-it-maas`. The debate reads this index and writes an ontology that has to pass the same schema. Silver and gold models stay in milestone 5.
