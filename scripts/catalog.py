"""Catalog layout shared by the scripts.

A folder is the entry id: descriptors carry no id, so an entry can never
disagree with its location.

    trees/items/<tree_id>/tree.json       [+ image.webp, thumb.webp]
    objects/items/<object_id>/object.json [+ image.webp, thumb.webp]
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

# Bumped only on breaking changes: consumers skip releases they cannot read.
SCHEMA_VERSION = 1

#: section -> ((folder, kind), ...)
LAYOUT: dict[str, tuple[tuple[str, str], ...]] = {
    "trees": (("items", "tree"),),
    "objects": (("items", "object"),),
}
SECTIONS = tuple(LAYOUT)


@dataclass
class Entry:
    """One release unit: a set of files archived together."""

    name: str  # release entry name, e.g. "tree.oak"
    kind: str  # tree | object
    files: dict[str, Path] = field(default_factory=dict)  # archive name -> path

    def content_hash(self) -> str:
        """Hash of the archived content, independent of zip encoding."""
        digest = hashlib.sha256()
        for arcname in sorted(self.files):
            digest.update(arcname.encode() + b"\0")
            digest.update(self.files[arcname].read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def folders(base: Path) -> list[Path]:
    """The entry folders of a kind, by id."""
    if not base.is_dir():
        return []
    return [
        folder
        for folder in sorted(base.iterdir())
        if folder.is_dir() and not folder.name.startswith(".")
    ]


def collect(root: Path, section: str) -> list[Entry]:
    """List the release entries of a section (descriptors are not parsed here)."""
    if section not in LAYOUT:
        raise ValueError(f"unknown section {section!r}")
    entries: list[Entry] = []
    for folder_name, kind in LAYOUT[section]:
        for folder in folders(root / section / folder_name):
            entry = Entry(f"{kind}.{folder.name}", kind)
            for path in sorted(folder.iterdir()):
                if path.is_file() and not path.name.startswith("."):
                    entry.files[path.name] = path
            entries.append(entry)
    return entries


def entry_id(entry: Entry) -> str:
    return entry.name.split(".", 1)[1]
