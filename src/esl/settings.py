import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    artifact_backend: str = "dir"
    artifact_dir: Path = Path("/tmp/esl-artifacts")
    s3_endpoint: str | None = None
    s3_bucket: str = "esl-artifacts"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"

    @classmethod
    def from_env(cls) -> "Settings":
        endpoint = os.environ.get("S3_ENDPOINT") or None
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/esl-artifacts")
        return cls(
            database_url=os.environ.get(
                "DATABASE_URL",
                "postgresql://esl:esl@127.0.0.1:5432/esl",
            ),
            artifact_backend=os.environ.get("ARTIFACT_BACKEND", "dir"),
            artifact_dir=Path(artifact_dir),
            s3_endpoint=endpoint,
            s3_bucket=os.environ.get("S3_BUCKET", "esl-artifacts"),
            s3_access_key=os.environ.get("S3_ACCESS_KEY", ""),
            s3_secret_key=os.environ.get("S3_SECRET_KEY", ""),
            s3_region=os.environ.get("S3_REGION", "us-east-1"),
        )
