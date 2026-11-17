"""Dagster job ``bronze_erp_mtdd``: download, land, warehouse, profile.

Configuration comes from the environment, the same variables the API reads:
the artifact store (``ARTIFACT_BACKEND``, ``S3_*``), BigQuery (``BQ_PROJECT``,
``BQ_DATASET``, ``BQ_LOCATION``), the control plane (``ESL_API_URL``,
``ESL_ACTOR``), and ``ERP_MTDD_DIR`` to use local files instead of Kaggle.
"""

import os
from pathlib import Path

import dagster as dg

from esl.bronze import canonical_json, land_extract, sha256
from esl.control_plane import ControlPlane
from esl.profile import profile_extract
from esl.settings import Settings
from esl.sources import erp_mtdd
from esl.store import build_store
from esl.warehouse.bigquery import BigQueryTarget, apply_bronze

GROUP = "bronze_erp_mtdd"


class PipelineEnv(dg.ConfigurableResource):
    source_dir: str = ""
    bq_project: str = ""
    bq_dataset: str = "bronze_erp_mtdd"
    bq_location: str = "us-central1"
    api_url: str = ""
    actor: str = ""

    @classmethod
    def from_env(cls) -> "PipelineEnv":
        return cls(
            source_dir=os.environ.get("ERP_MTDD_DIR", ""),
            bq_project=os.environ.get("BQ_PROJECT", ""),
            bq_dataset=os.environ.get("BQ_DATASET", "bronze_erp_mtdd"),
            bq_location=os.environ.get("BQ_LOCATION", "us-central1"),
            api_url=os.environ.get("ESL_API_URL", ""),
            actor=os.environ.get("ESL_ACTOR", ""),
        )

    def store(self):
        return build_store(Settings.from_env())

    def control_plane(self) -> ControlPlane | None:
        if not self.api_url:
            return None
        if not self.actor:
            raise ValueError("ESL_ACTOR must name who submits proposals when ESL_API_URL is set")
        return ControlPlane(self.api_url, self.actor)


@dg.asset(group_name=GROUP, description="The pinned Kaggle version, or local copies of it.")
def erp_mtdd_source(context: dg.AssetExecutionContext, env: PipelineEnv) -> dict:
    if env.source_dir:
        files = erp_mtdd.SourceFiles.in_directory(Path(env.source_dir))
        origin = "local"
    else:
        files = erp_mtdd.download()
        origin = "kaggle"
    context.log.info(f"source files from {origin}: {files.seed.parent}")
    return {"seed": str(files.seed), "schema": str(files.schema), "origin": origin}


@dg.asset(group_name=GROUP, description="Raw files, Parquet tables and docs, and the manifest.")
def bronze_manifest(
    context: dg.AssetExecutionContext, env: PipelineEnv, erp_mtdd_source: dict
) -> dict:
    seed, schema = Path(erp_mtdd_source["seed"]), Path(erp_mtdd_source["schema"])
    manifest = land_extract(
        env.store(),
        adapter=erp_mtdd.ADAPTER,
        source={"dataset": erp_mtdd.DATASET, "version": erp_mtdd.VERSION,
                "origin": erp_mtdd_source["origin"]},
        raw_files=[seed, schema],
        tables=erp_mtdd.read_tables(seed),
        docs=erp_mtdd.read_docs(schema),
    )
    context.add_output_metadata(
        {"extract_id": manifest["extract_id"], "tables": manifest["totals"]["tables"],
         "rows": manifest["totals"]["rows"], "manifest": manifest["uri"]}
    )
    plane = env.control_plane()
    if plane:
        submitted = plane.propose(
            kind="source_extract", name="erp-mtdd", content=manifest,
            summary=(f"erp_mtdd extract {manifest['extract_id']}: "
                     f"{manifest['totals']['tables']} tables, {manifest['totals']['rows']} rows"),
        )
        _log_submission(context, "source_extract", submitted)
    return manifest


@dg.asset(group_name=GROUP, description="External tables in BigQuery over the Parquet files.")
def bronze_bigquery(
    context: dg.AssetExecutionContext, env: PipelineEnv, bronze_manifest: dict
) -> list[str]:
    if not env.bq_project:
        context.log.warning("BQ_PROJECT is not set; skipping BigQuery")
        return []
    target = BigQueryTarget(env.bq_project, env.bq_dataset, env.bq_location)
    created = apply_bronze(target, bronze_manifest)
    context.add_output_metadata({"tables": len(created), "dataset": env.bq_dataset})
    return created


@dg.asset(group_name=GROUP, description="Keys, relationships, and columns checked against docs.")
def source_profile(
    context: dg.AssetExecutionContext, env: PipelineEnv,
    erp_mtdd_source: dict, bronze_manifest: dict,
) -> dict:
    profile = profile_extract(
        erp_mtdd.read_tables(Path(erp_mtdd_source["seed"])),
        erp_mtdd.read_docs(Path(erp_mtdd_source["schema"])),
    )
    profile = {"extract_id": bronze_manifest["extract_id"],
               "manifest": bronze_manifest["uri"], **profile}
    body = canonical_json(profile)
    key = f"bronze/{erp_mtdd.ADAPTER}/{bronze_manifest['extract_id']}/profile/{sha256(body)}.json"
    uri = env.store().put(key, body)
    summary = profile["summary"]
    context.add_output_metadata(
        {"profile": uri, "primary_keys_ok": summary["primary_keys_ok"],
         "relationship_status": dg.MetadataValue.json(summary["relationship_status"])}
    )
    plane = env.control_plane()
    if plane:
        submitted = plane.propose(
            kind="source_profile", name="erp-mtdd", content=profile,
            summary=(f"Profile of erp_mtdd extract {bronze_manifest['extract_id']}: "
                     f"{summary['primary_keys_ok']}/{summary['tables']} keys ok, "
                     f"relationships {summary['relationship_status']}"),
        )
        _log_submission(context, "source_profile", submitted)
    return {**profile, "uri": uri}


def _log_submission(context: dg.AssetExecutionContext, kind: str, submitted: dict) -> None:
    artifact = submitted["artifact"]
    if submitted["proposal"] is None:
        context.log.info(f"{kind} unchanged: version {artifact['version']} already holds it")
    else:
        context.log.info(
            f"{kind} version {artifact['version']}: proposal {submitted['proposal']['id']}"
        )


bronze_job = dg.define_asset_job(GROUP, selection=dg.AssetSelection.groups(GROUP))

defs = dg.Definitions(
    assets=[erp_mtdd_source, bronze_manifest, bronze_bigquery, source_profile],
    jobs=[bronze_job],
    resources={"env": PipelineEnv.from_env()},
)
