"""The result of the CI as one answer (the "CI passed" job).

Reads the `needs` context of GitHub Actions (JSON, in the NEEDS environment variable) and fails
unless every job succeeded: a skipped or cancelled job is not a success.
"""

import json
import os
import sys


def main() -> int:
    needs = json.loads(os.environ["NEEDS"])
    for name, job in needs.items():
        print(f"{name}: {job['result']}")
    bad = {name: job["result"] for name, job in needs.items() if job["result"] != "success"}
    if bad:
        print(f"Not green: {bad}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
