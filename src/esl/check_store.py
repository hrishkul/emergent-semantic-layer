"""Write, read back, and report one probe object in the configured artifact store.

Run after pointing the S3 settings at a real bucket:
    python -m esl.check_store
"""

import hashlib
import sys
from datetime import UTC, datetime

from esl.app import build_store
from esl.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    store = build_store(settings)
    data = f"esl store check {datetime.now(UTC).isoformat()}".encode()
    key = f"store_check/{hashlib.sha256(data).hexdigest()}"
    uri = store.put(key, data)
    if store.get(uri) != data:
        raise RuntimeError(f"read back different bytes from {uri}")
    print(f"ok: {settings.artifact_backend} store wrote and read {uri}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"store check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
