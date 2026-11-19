"""Copy the rules of the catalog into the tools that edit it.

Run from the folder holding the checkouts side by side, or give it with --base:

    python house-catalog/scripts/sync_client.py [--base ..] [--check]

For each tool found it writes, in custom_components/<domain>/, a copy of
client/house_catalog_rules.py with a "do not edit" header: the rules an entry
must follow, shared with validate.py, so that a draft is accepted by the tool
exactly when the CI of the catalog accepts it.

--check changes nothing and fails when a copy is out of date.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLIENT_FILES = ("house_catalog_rules.py",)
HEADER = "# Generated from house-catalog/client/{name} by scripts/sync_client.py: do not edit this copy.\n"

#: checkout folder -> domain of the tool
TARGETS: dict[str, str] = {
    "catalog-editor": "catalog_editor",
}


def sync(base: Path, check: bool = False, root: Path = REPO) -> list[str]:
    """Sync every tool found under `base`; return what is (or was) out of date."""
    stale: list[str] = []
    for folder, domain in TARGETS.items():
        component = base / folder / "custom_components" / domain
        if not component.is_dir():
            print(f"skip {folder}: no custom_components/{domain}")
            continue
        for name in CLIENT_FILES:
            fresh = HEADER.format(name=name) + (root / "client" / name).read_text(
                encoding="utf-8"
            )
            target = component / name
            if target.is_file() and target.read_text(encoding="utf-8") == fresh:
                continue
            stale.append(f"{folder}/{name}")
            if not check:
                target.write_text(fresh, encoding="utf-8")
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--base", type=Path, default=Path.cwd(), help="folder holding the checkouts"
    )
    parser.add_argument(
        "--check", action="store_true", help="only report what is out of date"
    )
    args = parser.parse_args(argv)
    stale = sync(args.base, args.check)
    for line in stale:
        print(("out of date: " if args.check else "updated: ") + line)
    if not stale:
        print("everything up to date")
    return 1 if args.check and stale else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
