-- A profile of a source extract is its own reviewable artifact.
ALTER TABLE artifacts DROP CONSTRAINT artifacts_kind_check;
ALTER TABLE artifacts ADD CONSTRAINT artifacts_kind_check CHECK (
    kind IN (
        'source_extract',
        'source_profile',
        'ontology',
        'kpi_registry',
        'cube_manifest',
        'debate_transcript',
        'debate_spec'
    )
);
