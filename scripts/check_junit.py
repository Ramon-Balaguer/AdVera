"""Fail when a pytest run skipped tests or ran none (CI).

Integration tests are skipped when PostgreSQL or Redis are not reachable, so a green run can
hide that they never ran. Usage: python scripts/check_junit.py pytest.xml
"""

import sys
import xml.etree.ElementTree as ET


def main(path: str) -> int:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    tests = sum(int(s.get("tests", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    print(f"{path}: {tests} tests, {skipped} skipped")
    if tests == 0:
        print("No test ran.", file=sys.stderr)
        return 1
    if skipped:
        print(f"{skipped} tests were skipped: every test must run in CI.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
