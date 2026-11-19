"""Check the catalog before it is merged or released.

Errors make the command fail; warnings (missing translations, missing
pictures, missing seasons) are printed only, unless --strict is given.

    python scripts/validate.py [--root .] [--strict]

The rules themselves live in client/house_catalog_rules.py, shared with the
tools that edit the catalog; this script reads the repository and applies them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

from catalog import SECTIONS, collect, entry_id, read_json
from house_catalog_rules import (
    DESCRIPTORS,
    Context,
    Report,
    check_files,
    load_validators,
    validate_entry,
    where_of,
)


def validate(root: Path) -> Report:
    report = Report()
    validators = load_validators(root / "schema")
    ctx = Context()
    for section in SECTIONS:
        if not (root / section).is_dir():
            report.error(section, "section folder missing")
        for entry in collect(root, section):
            descriptor = DESCRIPTORS[entry.kind]
            where = where_of(entry.kind, entry_id(entry))
            sizes = {name: path.stat().st_size for name, path in entry.files.items()}
            check_files(report, where, sizes, descriptor)
            if descriptor not in entry.files:
                continue
            try:
                data = read_json(entry.files[descriptor])
            except (OSError, json.JSONDecodeError) as err:
                report.error(where, f"unreadable JSON ({err})")
                continue
            validate_entry(
                report, entry.kind, entry_id(entry), data, sizes, ctx, validators
            )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    parser.add_argument(
        "--strict", action="store_true", help="treat warnings as errors"
    )
    args = parser.parse_args(argv)

    report = validate(args.root)
    for line in report.warnings:
        print(f"warning: {line}")
    for line in report.errors:
        print(f"error: {line}")
    failed = report.errors or (args.strict and report.warnings)
    print(f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
