CREATE TABLE artifacts (
    id uuid PRIMARY KEY,
    kind text NOT NULL CHECK (
        kind IN (
            'source_extract',
            'ontology',
            'kpi_registry',
            'cube_manifest',
            'debate_transcript',
            'debate_spec'
        )
    ),
    logical_name text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    content_uri text NOT NULL,
    content_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL CHECK (length(btrim(created_by)) > 0),
    UNIQUE (kind, logical_name, version)
);

CREATE TABLE proposals (
    id uuid PRIMARY KEY,
    artifact_id uuid NOT NULL REFERENCES artifacts (id),
    parent_artifact_id uuid REFERENCES artifacts (id),
    status text NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'superseded')),
    policy text NOT NULL CHECK (policy = 'human_required'),
    summary text NOT NULL CHECK (length(btrim(summary)) > 0),
    submitted_at timestamptz NOT NULL DEFAULT now(),
    submitted_by text NOT NULL CHECK (length(btrim(submitted_by)) > 0)
);

CREATE INDEX proposals_status_idx ON proposals (status);

CREATE TABLE approvals (
    id uuid PRIMARY KEY,
    proposal_id uuid NOT NULL UNIQUE REFERENCES proposals (id),
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    decided_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE runs (
    id uuid PRIMARY KEY,
    kind text NOT NULL,
    status text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    trace_id text
);
