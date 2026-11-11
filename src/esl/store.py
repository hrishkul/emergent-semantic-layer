from pathlib import Path
from typing import Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class ArtifactStore(Protocol):
    def put(self, key: str, data: bytes) -> str: ...

    def get(self, uri: str) -> bytes: ...


class DirectoryStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, key: str, data: bytes) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        return f"dir://{key}"

    def get(self, uri: str) -> bytes:
        key = _dir_key(uri)
        return (self.root / key).read_bytes()


class S3Store:
    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None,
        access_key: str,
        secret_key: str,
    ) -> None:
        # Checksums only when an operation requires them: the Cloud Storage XML
        # endpoint rejects the default CRC trailers that newer botocore sends.
        config = Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
        kwargs: dict[str, object] = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
            config = config.merge(Config(s3={"addressing_style": "path"}))
        kwargs["config"] = config
        if access_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        self._client = boto3.client("s3", **kwargs)
        self._bucket = bucket

    def ensure_bucket(self, *, create: bool) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
        if not create:
            raise RuntimeError(f"artifact bucket does not exist: {self._bucket}")
        self._client.create_bucket(Bucket=self._bucket)

    def put(self, key: str, data: bytes) -> str:
        if not self._exists(key):
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return f"s3://{self._bucket}/{key}"

    def _exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def get(self, uri: str) -> bytes:
        bucket, key = _s3_parts(uri)
        obj = self._client.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()


def _dir_key(uri: str) -> str:
    prefix = "dir://"
    if not uri.startswith(prefix):
        raise ValueError(f"not a directory artifact uri: {uri}")
    return uri[len(prefix) :]


def _s3_parts(uri: str) -> tuple[str, str]:
    prefix = "s3://"
    if not uri.startswith(prefix):
        raise ValueError(f"not an s3 artifact uri: {uri}")
    rest = uri[len(prefix) :]
    bucket, sep, key = rest.partition("/")
    if not sep or not bucket or not key:
        raise ValueError(f"not an s3 artifact uri: {uri}")
    return bucket, key
