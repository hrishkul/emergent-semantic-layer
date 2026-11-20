"""Run the bronze job once, in process: ``python -m esl.pipeline``."""

import sys

from esl.pipeline.definitions import GROUP, defs


def main() -> int:
    result = defs.resolve_job_def(GROUP).execute_in_process()
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
