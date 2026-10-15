import sys

from esl.db import apply_migrations
from esl.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    applied = apply_migrations(settings.database_url)
    if applied:
        print("applied:", ", ".join(applied))
    else:
        print("migrations already applied")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
