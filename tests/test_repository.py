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
    "paths": {"gravel", "pavers", "stepping-stones"},
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


#: The sections of what the house is surrounded with: every entry is complete
SURROUNDINGS = ("terraces", "walls", "copings", "fences")


def test_terraces_walls_copings_and_fences_are_complete():
    for section in SURROUNDINGS:
        for entry in collect(REPO, section):
            name = f"{section}/{entry_id(entry)}"
            data = read_json(entry.files[DESCRIPTORS[entry.kind]])
            assert set(data["name"]) >= set(KNOWN_LANGS), name
            assert data["icon"], name
            for file, side in (("image.webp", 512), ("thumb.webp", 128)):
                with Image.open(entry.files[file]) as picture:
                    assert picture.format == "WEBP", name
                    assert picture.size == (side, side), name
                    corner = picture.convert("RGBA").getpixel((0, 0))
                    assert isinstance(corner, tuple) and corner[3] == 0, name


def test_the_card_finds_its_own_fences_in_the_catalog():
    """The kinds of fence the card knew before the catalog keep their ids."""
    fences = {entry_id(entry) for entry in collect(REPO, "fences")}
    assert {"mesh", "wood", "wall", "hedge", "hedge_laurel", "iron", "gabion"} <= fences


def test_the_card_finds_its_own_sprinklers_in_the_catalog():
    """The models of sprinkler the card knew before the catalog keep their ids."""
    heads = {entry_id(entry) for entry in collect(REPO, "sprinklers")}
    assert {
        "hunter-psu-04-8a",
        "hunter-psu-04-10a",
        "hunter-psu-04-12a",
        "hunter-psu-04-15a",
        "hunter-psu-04-17a",
        "hunter-srm-04",
        "hunter-pgj-04",
        "hunter-pgp-ultra",
        "hunter-mp1000",
        "hunter-mp2000",
        "hunter-mp3000",
    } <= heads


def test_painted_surfaces_join_up_from_one_tile_to_the_next():
    """A whole number of rows in a tile (even when staggered), and of even units."""
    for section in SURROUNDINGS:
        for entry in collect(REPO, section):
            data = read_json(entry.files[DESCRIPTORS[entry.kind]])
            surface = data["surface"]
            joints = surface.get("joints")
            if joints is None or joints.get("pattern") == "irregular":
                continue  # irregular stones are fitted to the tile, whatever its size
            name = f"{section}/{entry_id(entry)}"
            tile = surface.get("tile", 2)
            depth, length = joints["cell"]
            rows = tile / depth
            assert abs(rows - round(rows)) < 1e-6, name
            if joints.get("stagger"):
                assert round(rows) % 2 == 0, name
            if not joints.get("vary"):
                units = tile / length
                assert abs(units - round(units)) < 1e-6, name
