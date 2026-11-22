"""The catalog of this repository.

Only what a contribution must not break: `validate.py` accepts an entry with
warnings (a missing translation, no picture), and the lists of the README are
refreshed after the merge, so neither is asserted for every entry here.
"""

from __future__ import annotations

from conftest import REPO
from PIL import Image

import validate
from catalog import SECTIONS, collect, entry_id, read_json
from house_catalog_rules import DESCRIPTORS, KNOWN_LANGS, SEASONS

#: The entries the catalog started with: complete, they are the examples to copy
FIRST = {
    "trees": {"oak", "pine", "yew", "cherry-tree", "apricot-tree"},
    "objects": {"chair"},
}


def test_catalog_is_valid():
    assert validate.validate(REPO).errors == []


def test_first_entries_are_complete():
    for section, ids in FIRST.items():
        entries = {entry_id(entry): entry for entry in collect(REPO, section)}
        assert ids <= set(entries)
        for name in ids:
            entry = entries[name]
            data = read_json(entry.files[DESCRIPTORS[entry.kind]])
            # every known language, and possibly others (Dutch, which the rules do not ask for yet)
            assert set(data["name"]) >= set(KNOWN_LANGS), name
            assert data["keywords"] and data["icon"], name
            for file, side in (("image.webp", 512), ("thumb.webp", 128)):
                with Image.open(entry.files[file]) as picture:
                    assert picture.format == "WEBP" and picture.size == (side, side)
                    corner = picture.convert("RGBA").getpixel((0, 0))
                    assert isinstance(corner, tuple) and corner[3] == 0, name


def test_first_trees_show_their_four_seasons():
    for entry in collect(REPO, "trees"):
        if entry_id(entry) in FIRST["trees"]:
            assert tuple(read_json(entry.files["tree.json"])["seasons"]) == SEASONS


def test_every_section_has_entries():
    assert all(collect(REPO, section) for section in SECTIONS)
