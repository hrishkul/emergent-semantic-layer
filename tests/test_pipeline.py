import json

from esl.pipeline.definitions import GROUP, PipelineEnv, defs
from tests.erp_fixture import write_workbooks


def test_bronze_job_runs_without_cloud(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    write_workbooks(source, defects=True)
    monkeypatch.setenv("ARTIFACT_BACKEND", "dir")
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("DAGSTER_HOME", str(tmp_path / "dagster"))
    (tmp_path / "dagster").mkdir()

    job = defs.resolve_job_def(GROUP)
    result = job.execute_in_process(resources={"env": PipelineEnv(source_dir=str(source))})

    assert result.success
    manifest = result.output_for_node("bronze_manifest")
    assert manifest["totals"] == {"tables": 2, "rows": 7}
    assert result.output_for_node("bronze_bigquery") == []
    profile = result.output_for_node("source_profile")
    assert profile["summary"]["relationship_status"] == {"orphans": 1}
    stored = tmp_path / "store" / profile["uri"][len("dir://"):]
    assert json.loads(stored.read_text())["extract_id"] == manifest["extract_id"]
