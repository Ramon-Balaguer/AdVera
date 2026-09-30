"""Validate AdVera documentation invariants.

Checks:
- every ADR file is indexed in docs/adr/README.md and the Status column reproduces the
  ADR's `## Status` text (trailing period ignored);
- every feature record is indexed in docs/features/README.md, the index row matches the
  record header, and the declared record count is correct;
- every feature record starts with `Status:` (one of five values) and `Last updated:`
  (ISO date) directly under its title;
- relative links in Markdown resolve (links into code that the rebuild has not produced
  yet are reported as warnings unless --strict-code-links is passed);
- no Markdown file under docs/ or .github/agents/ is empty.

Exit code 0 when no errors are found.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ADR_DIR = DOCS / "adr"
FEATURES_DIR = DOCS / "features"
AGENTS_DIR = ROOT / ".github" / "agents"

FEATURE_STATUSES = {"planned", "in progress", "partial", "complete", "blocked"}
FENCE = re.compile(r"^(```|~~~)")
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
TABLE_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def strip_fences(text: str) -> list[str]:
    """Return lines with fenced code blocks blanked out, preserving line numbers."""
    lines, inside = [], False
    for line in text.splitlines():
        if FENCE.match(line.strip()):
            inside = not inside
            lines.append("")
            continue
        lines.append("" if inside else line)
    return lines


def table_rows(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped) <= {"|", "-", " ", ":"}:
            continue
        rows.append([cell.strip() for cell in stripped.strip("|").split("|")])
    return rows


def check_adr_index(errors: list[str]) -> None:
    readme = ADR_DIR / "README.md"
    rows = table_rows(strip_fences(readme.read_text(encoding="utf-8")))
    indexed: dict[str, str] = {}
    for row in rows:
        match = TABLE_LINK.search(row[0])
        if match and len(row) >= 3:
            indexed[match.group(1)] = row[2]

    for adr in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")):
        if adr.name not in indexed:
            errors.append(f"{rel(readme)}: ADR {adr.name} is not indexed")
            continue
        heading_status = adr_status(adr)
        if heading_status is None:
            errors.append(f"{rel(adr)}: missing '## Status' section")
        elif heading_status.rstrip(".") != indexed[adr.name].rstrip("."):
            errors.append(
                f"{rel(readme)}: Status for {adr.name} is {indexed[adr.name]!r}, "
                f"ADR says {heading_status!r}"
            )
    for name in indexed:
        if not (ADR_DIR / name).is_file():
            errors.append(f"{rel(readme)}: indexed ADR {name} does not exist")


def adr_status(path: Path) -> str | None:
    lines = strip_fences(path.read_text(encoding="utf-8"))
    for index, line in enumerate(lines):
        if line.strip().lower() == "## status":
            for following in lines[index + 1 :]:
                if following.strip():
                    return following.strip()
    return None


def feature_header(path: Path) -> tuple[str | None, str | None]:
    lines = path.read_text(encoding="utf-8").splitlines()
    status = lines[1].strip() if len(lines) > 1 else ""
    updated = lines[2].strip() if len(lines) > 2 else ""
    status_value = status.removeprefix("Status:").strip() if status.startswith("Status:") else None
    updated_value = (
        updated.removeprefix("Last updated:").strip()
        if updated.startswith("Last updated:")
        else None
    )
    return status_value, updated_value


def check_features(errors: list[str]) -> None:
    readme = FEATURES_DIR / "README.md"
    lines = strip_fences(readme.read_text(encoding="utf-8"))
    indexed: dict[str, tuple[str, str]] = {}
    for row in table_rows(lines):
        match = TABLE_LINK.search(row[0])
        if match and len(row) >= 3:
            indexed[match.group(1)] = (row[1], row[2])

    records = sorted(p for p in FEATURES_DIR.glob("*.md") if p.name != "README.md")
    count_match = re.search(r"^(\d+) feature records", "\n".join(lines), re.MULTILINE)
    if not count_match:
        errors.append(f"{rel(readme)}: missing '<N> feature records' count line")
    elif int(count_match.group(1)) != len(records):
        errors.append(
            f"{rel(readme)}: declares {count_match.group(1)} records, found {len(records)}"
        )

    for record in records:
        first = record.read_text(encoding="utf-8").splitlines()[:1]
        if not first or not first[0].startswith("# "):
            errors.append(f"{rel(record)}: first line must be a '# ' title")
        status, updated = feature_header(record)
        if status is None:
            errors.append(f"{rel(record)}: line 2 must be 'Status: <value>'")
        elif status not in FEATURE_STATUSES:
            errors.append(f"{rel(record)}: invalid Status {status!r}")
        if updated is None:
            errors.append(f"{rel(record)}: line 3 must be 'Last updated: YYYY-MM-DD'")
        else:
            try:
                dt.date.fromisoformat(updated)
            except ValueError:
                errors.append(f"{rel(record)}: invalid Last updated {updated!r}")
        if record.name not in indexed:
            errors.append(f"{rel(readme)}: record {record.name} is not indexed")
        elif (
            status is not None
            and updated is not None
            and indexed[record.name]
            != (
                status,
                updated,
            )
        ):
            errors.append(
                f"{rel(readme)}: row for {record.name} is {indexed[record.name]}, "
                f"record header is {(status, updated)}"
            )
    for name in indexed:
        if not (FEATURES_DIR / name).is_file():
            errors.append(f"{rel(readme)}: indexed record {name} does not exist")


def markdown_files() -> list[Path]:
    files = list(DOCS.rglob("*.md"))
    if AGENTS_DIR.is_dir():
        files += list(AGENTS_DIR.glob("*.md"))
    readme = ROOT / "README.md"
    if readme.is_file():
        files.append(readme)
    return sorted(files)


def check_links_and_empty(errors: list[str], warnings: list[str], strict_code: bool) -> None:
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            errors.append(f"{rel(path)}: file is empty")
            continue
        for number, line in enumerate(strip_fences(text), start=1):
            for target in LINK.findall(line):
                if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                    continue
                resolved = (path.parent / target.split("#", 1)[0]).resolve()
                if resolved.exists():
                    continue
                message = f"{rel(path)}:{number}: broken link {target}"
                is_doc = resolved.suffix == ".md" or DOCS in resolved.parents
                if is_doc or strict_code:
                    errors.append(message)
                else:
                    warnings.append(message + " (code not built yet)")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--strict-code-links",
        action="store_true",
        help="treat links to missing source files as errors",
    )
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    check_adr_index(errors)
    check_features(errors)
    check_links_and_empty(errors, warnings, args.strict_code_links)

    for warning in warnings:
        print(f"WARNING {warning}")
    for error in errors:
        print(f"ERROR {error}")
    print(f"check_docs: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
