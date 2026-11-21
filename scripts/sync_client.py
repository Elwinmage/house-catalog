"""Copy what the tools need from this catalog: its rules, and a built-in snapshot.

Run from the folder holding the checkouts side by side, or give it with --base:

    python house-catalog/scripts/sync_client.py [--base ..] [--check]

For each tool found it writes, in custom_components/<domain>/:
  house_catalog_sections.py   the repository and the sections of the catalog,
                              which the tool declares to the catalog client
                              (`register_section`), with a "do not edit" header
  house_catalog_rules.py      (editors of the catalog) the rules an entry must
                              follow, shared with validate.py: a draft is
                              accepted by the editor exactly when the CI of the
                              catalog accepts it
  catalog_builtin/            (integrations reading the catalog) the entries of
  catalog_builtin_<section>/  its sections, used before the first download and
                              offline; the first section has the plain name, as
                              the catalog client expects (`CatalogSpec.by_section`)

The catalog client itself (catalog_pack.py, catalog_runtime.py) comes from
reeftech-catalog, with its own sync_client.py.

--check changes nothing and fails when a copy or a snapshot is out of date.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from catalog import collect, entry_id

REPO = Path(__file__).resolve().parent.parent
SECTIONS_FILE = "house_catalog_sections.py"
RULES_FILE = "house_catalog_rules.py"
HEADER = "# Generated from house-catalog/client/{name} by scripts/sync_client.py: do not edit this copy.\n"


@dataclass(frozen=True)
class Target:
    """What a tool takes from the catalog."""

    domain: str
    #: gets the rules too (it edits the catalog); every tool gets the sections
    rules: bool = False
    #: sections it reads: a built-in snapshot of each
    reads: tuple[str, ...] = ()


#: checkout folder -> what the tool takes
TARGETS: dict[str, Target] = {
    "catalog-editor": Target("catalog_editor", rules=True),
    "ha-house-view-component": Target(
        "house_view", reads=("trees", "objects", "pond_fish")
    ),
}


def snapshot_name(reads: tuple[str, ...], section: str) -> str:
    """Folder of the built-in snapshot of a section, next to the modules."""
    return "catalog_builtin" + ("" if section == reads[0] else f"_{section}")


def write_snapshot(root: Path, section: str, dest: Path) -> None:
    """Write the built-in snapshot of a section into `dest` (replaced)."""
    shutil.rmtree(dest, ignore_errors=True)
    for entry in collect(root, section):
        folder = dest / "items" / entry_id(entry)
        folder.mkdir(parents=True, exist_ok=True)
        for name, path in entry.files.items():
            shutil.copyfile(path, folder / name)


def _same_tree(left: Path, right: Path) -> bool:
    """Two folders hold the same files with the same content."""
    if not right.is_dir():
        return False
    compared = filecmp.dircmp(left, right)
    if compared.left_only or compared.right_only or compared.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(
        left, right, compared.common_files, shallow=False
    )
    return (
        not mismatch
        and not errors
        and all(_same_tree(left / name, right / name) for name in compared.common_dirs)
    )


def sync(base: Path, check: bool = False, root: Path = REPO) -> list[str]:
    """Sync every tool found under `base`; return what is (or was) out of date."""
    stale: list[str] = []
    for folder, target in TARGETS.items():
        component = base / folder / "custom_components" / target.domain
        if not component.is_dir():
            print(f"skip {folder}: no custom_components/{target.domain}")
            continue
        for name in (SECTIONS_FILE, *((RULES_FILE,) if target.rules else ())):
            fresh = HEADER.format(name=name) + (root / "client" / name).read_text(
                encoding="utf-8"
            )
            copy = component / name
            if not copy.is_file() or copy.read_text(encoding="utf-8") != fresh:
                stale.append(f"{folder}/{name}")
                if not check:
                    copy.write_text(fresh, encoding="utf-8")
        for section in target.reads:
            name = snapshot_name(target.reads, section)
            with tempfile.TemporaryDirectory() as tmp:
                fresh_dir = Path(tmp) / name
                write_snapshot(root, section, fresh_dir)
                fresh_dir.mkdir(exist_ok=True)  # a section without an entry yet
                if _same_tree(fresh_dir, component / name):
                    continue
                stale.append(f"{folder}/{name}")
                if not check:
                    shutil.rmtree(component / name, ignore_errors=True)
                    shutil.copytree(fresh_dir, component / name)
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
