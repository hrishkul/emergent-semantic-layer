# Cloud services

The cloud vendor is confirmed after Phase 0. Until then the control plane is local Postgres, a directory or S3-compatible artifact store, and an OpenTelemetry collector. The account, when chosen, is for three things: durable object storage, a secret for the model API, and a machine to publish the demo.

Checked against the provider pages on 15 October 2026. Confirm the numbers on the signup page. Offers change.

## Which account to open

Open **Google Cloud**, and put the project in `us-central1` (or `us-east1` / `us-west1`).

- New accounts get **$300** of welcome credit for **90 days**, and are not billed during the trial.
- After the trial, an `e2-micro` (1 GB RAM), **5 GB** of regional Cloud Storage, and Secret Manager (6 active versions, 10,000 reads a month) stay inside the always-free monthly limits. That is the only one of the three that still has a free VM when the credits end.
- The warehouse stays DuckDB. BigQuery is not part of this design, so choosing Google does not pull the project onto a different database.

**Azure** is the better signup if a managed Postgres for a year matters more than the leftover free VM. New accounts get **$200 for 30 days**, then, for 12 months: Flexible Server burstable B1MS for 750 hours a month (32 GB storage), 5 GB of hot LRS blob, and 750 hours each of the B1s, B2pts v2, and B2ats v2 VMs. Upgrade to pay-as-you-go before day 30, or the account is disabled and those 12-month allowances stop. Set a budget alert at the same time. The free VM sizes are **1 GB RAM**.

**AWS** is the signup if a resume line you are matching names AWS. New accounts get **$100** at signup and can earn up to **$100** more, over at most **6 months**. Choose the **Paid** plan and a budget alarm around $5. The Free plan closes the account at six months or when the credits run out, whichever comes first. After the credits, almost none of this stack is free.

## Services this project uses

One interface in code, one driver per cloud. The S3 API covers AWS S3, MinIO locally, and Google Cloud Storage via its XML interoperability endpoint and an HMAC key. Azure Blob needs its own driver, and that driver is written only if the account is Azure.

| Capability | AWS | Azure | Google Cloud | When |
| --- | --- | --- | --- | --- |
| Versioned artifact store | S3, bucket versioning on | Blob Storage, hot LRS | Cloud Storage, regional, in a free-tier US region | Driver in Phase 0. Pointed at the account only after signup (task P0-7). |
| Review queue and metadata | Postgres on the box. RDS `db.t4g.micro` or `db.t3.micro` only while credits last | Database for PostgreSQL Flexible Server, B1MS, 750 hours/month for 12 months | Postgres on the box. Cloud SQL has a 30-day trial instance, then it bills | Schema is local Postgres in Phase 0 on every cloud. A managed instance is optional. |
| Always-on compute | EC2, paid from credits | B1s, B2pts v2, or B2ats v2, each 1 GB, 750 hours/month for 12 months | `e2-micro`, 1 GB, always free in `us-central1`, `us-east1`, `us-west1`, plus 30 GB-month of disk | Optional. Compose is the development target. |
| Demo compute | A larger EC2 instance, stopped when idle | A larger VM. The free sizes are 1 GB, so this one is paid | `e2-medium` (4 GB) on the welcome credit, stopped when idle | Phase 1–2, only while showing Cube, Superset, and Grafana. |
| Secrets | SSM Parameter Store (standard parameters). Secrets Manager bills per secret | Key Vault | Secret Manager | Phase 1, when the model API key exists. |
| Traces | OpenTelemetry collector in Compose | Same | Same | Phase 0. CloudWatch, Application Insights, and Cloud Trace stay off. |
| Container images | ECR | Container Registry, one Standard registry with 100 GB is always free | Artifact Registry, 0.5 GB free | First deploy, not Phase 0. |
| CI | GitHub Actions | GitHub Actions | GitHub Actions | Phase 0. |

## Leave these off

Turning them on spends the credit and forks the design.

| Service | Why it stays off |
| --- | --- |
| Redshift, Synapse, BigQuery | The warehouse is a DuckDB file. The debate compiles dbt, it does not target a cloud warehouse. |
| Bedrock, Azure OpenAI, Vertex AI | The debate model is an external OpenAI-compatible API, chosen for price. The cloud only stores the key. |
| QuickSight, a Power BI tenant, Looker | Superset in Phase 2. Power BI, if used at all, connects to the same SQL API. |
| NAT Gateway | About $32 a month on AWS before any data. Use a public subnet with a tight firewall, or stay on Compose. |
| Cognito, Entra ID, Identity Platform | One named approver. An identity provider arrives when a second person approves. |
| SQS, Service Bus, Pub/Sub | One approver. The review queue is rows in Postgres (`SKIP LOCKED` if a worker is added). |
| Lambda, Cloud Functions, Azure Functions | dbt, Cube, and the debate are long-running processes, not request handlers. |

## Signup checklist

### Google Cloud (recommended)

1. Create the account and accept the $300 / 90-day trial. You are not billed during the trial.
2. Create one project. Set the default region to `us-central1`.
3. Add a budget alert at 50% of the credit and another near the end.
4. Enable Cloud Storage and Secret Manager when task P0-7 starts. Do not enable them now.
5. Do not create a Cloud SQL instance, a BigQuery dataset, a Vertex endpoint, or a Cloud NAT.

### Azure (if you want the 12-month Postgres)

1. Create the free account ($200 / 30 days).
2. Before day 30, upgrade to pay-as-you-go and set a budget alert at a few dollars. Skipping the upgrade disables the account.
3. Create Blob and the Postgres Flexible Server from the Free services page, so the SKU is the free one (B1MS, 32 GB). A randomly chosen SKU spends the $200.
4. The free VMs have 1 GB of RAM. Do not put Superset on them.

### AWS (if the resume line says AWS)

1. Choose the Paid plan, not the Free plan. The Free plan closes the account.
2. Create a budget alarm at $5 and turn on billing anomaly detection.
3. One region. S3 versioning on. No NAT Gateway, no Redshift, no Bedrock.
4. RDS only if you accept that it stops being free when the credits end. Default is Postgres on the box.

## What fits in the free RAM

Every always-free VM above has 1 GB of RAM. Postgres and the review API fit. Superset, Cube, Grafana, and the debate worker do not, not together.

Development stays in Docker Compose. A larger machine is started for a public demo and stopped afterward. A 4 GB machine left on all month consumes a large share of a trial credit.

## How this shapes development

- The artifact store is an interface. Tests run against MinIO, which speaks the S3 API. AWS and Google Cloud Storage then work without an application change. Azure waits on a second driver.
- The review queue is Postgres SQL. It does not become DynamoDB, Cosmos DB, or Firestore.
- Traces are OTLP. The vendor APM is not in the dependency list.
- Terraform is Phase 3 in the walkthrough. Phase 0 does not grow a cloud module before an account exists.
- The model client is Phase 1. Its only cloud dependency is the secret.
