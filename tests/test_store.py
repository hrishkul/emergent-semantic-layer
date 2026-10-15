import pytest

from esl.store import DirectoryStore, S3Store


def test_directory_store_roundtrip(tmp_path) -> None:
    store = DirectoryStore(tmp_path)
    uri = store.put("debate_spec/sales-ontology/abc", b"{}")
    assert uri == "dir://debate_spec/sales-ontology/abc"
    assert store.get(uri) == b"{}"
    store.put("debate_spec/sales-ontology/abc", b"ignored")
    assert store.get(uri) == b"{}"


def test_s3_store_roundtrip() -> None:
    moto = pytest.importorskip("moto.server")
    server = moto.ThreadedMotoServer(port=19090)
    server.start()
    try:
        store = S3Store(
            bucket="esl-artifacts",
            region="us-east-1",
            endpoint_url="http://127.0.0.1:19090",
            access_key="testing",
            secret_key="testing",
        )
        store.ensure_bucket()
        uri = store.put("debate_spec/sales-ontology/abc", b"claim")
        assert uri == "s3://esl-artifacts/debate_spec/sales-ontology/abc"
        assert store.get(uri) == b"claim"
    finally:
        server.stop()
