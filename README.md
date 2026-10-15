# Emergent Semantic Layer

Agents propose an ontology, a KPI registry, and a Cube manifest. Deterministic pipelines compile those into a warehouse. A person approves every proposal until there is calibration data.

Phase 0 is the control plane: a versioned artifact store, a review queue, tracing, and the debate specification. No debate is executed. No cloud account is required.

## Decisions

- The first pipeline is sales, plus shared foundation. The ontology debate seats every vertical on that run.
- Data is the public Levantia ERP extract. An Epicor adapter comes later.
- BI is Apache Superset in Phase 2. The SQL API stays something Power BI can also connect to.
- The debate framework is locked in [plan/DEBATE_FRAMEWORK.md](plan/DEBATE_FRAMEWORK.md), from the taxonomy in [arXiv:2607.26212](https://arxiv.org/html/2607.26212v1). The document is [specs/ontology_debate.json](specs/ontology_debate.json).
- The model vendor is still open. One open-weight model behind an OpenAI-compatible API, chosen in Phase 1.
- The cloud vendor is confirmed after Phase 0. The service map is [plan/CLOUD.md](plan/CLOUD.md).

The project license is the MIT license in the GitHub repository `hrishkul/emergent-semantic-layer`. That repository currently holds the license only.

## Run locally

Postgres 16, then:

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

## API

`POST /artifacts` stores a version. `kind` is `source_extract`, `ontology`, `kpi_registry`, `cube_manifest`, `debate_transcript`, or `debate_spec`. A `debate_spec` must match the locked framework.

`POST /proposals` opens a review. The only policy is `human_required`.

`POST /proposals/{id}/decision` records `approved` or `rejected` with an actor and a reason. A second decision is refused.
