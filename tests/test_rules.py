"""Rules of the catalog: what an entry must follow beyond its schema."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from conftest import REPO

from house_catalog_rules import (
    ASSET_FILES,
    DESCRIPTOR_MAX,
    Context,
    Report,
    check_files,
    load_validators,
    object_bounds,
    object_size,
    part_center,
    part_extent,
    rotation,
    validate_draft,
    validate_entry,
    where_of,
)

FILES = {"tree.json": 900, "image.webp": 20_000, "thumb.webp": 2_000}
ALL_LANGS = {lang: "x" for lang in ("en", "fr", "de", "es", "it", "pl", "pt")}


@pytest.fixture(scope="module")
def validators():
    return load_validators(REPO / "schema")


def check(kind, data, validators, files=None, ctx=None) -> Report:
    files = files if files is not None else {f"{kind}.json": 900, "image.webp": 1}
    return validate_draft(kind, "draft", data, files, ctx or Context(), validators)


def test_validators_cover_the_kinds_only(validators):
    assert sorted(validators) == ["fish", "object", "tree"]
    assert where_of("fish", "koi") == "fish/items/koi"
    assert where_of("tree", "oak") == "trees/items/oak"
    assert where_of("object", "chair") == "objects/items/chair"


def test_a_complete_entry_passes_without_a_remark(tree, thing, validators):
    tree["name"] = thing["name"] = ALL_LANGS
    assert check("tree", tree, validators, FILES).errors == []
    assert check("tree", tree, validators, FILES).warnings == []
    report = check("object", thing, validators)
    assert (report.errors, report.warnings) == ([], [])


def test_schema_errors_are_located(tree, validators):
    tree["shape"] = "cube"
    tree["trunk"]["color"] = "brown"
    tree["seasons"]["spring"]["flowers"]["amount"] = 0
    del tree["name"]
    errors = check("tree", tree, validators).errors
    assert any("shape: 'cube' is not one of" in e for e in errors)
    assert any("trunk/color: 'brown' does not match" in e for e in errors)
    assert any("seasons/spring/flowers/amount" in e for e in errors)
    assert any("(root): 'name' is a required property" in e for e in errors)


def test_a_part_index_and_a_key_sort_together(thing, validators):
    # error paths mix list indexes and keys: they must still be ordered
    thing["parts"][1]["shape"] = "pyramid"
    thing["category"] = "toy"
    errors = check("object", thing, validators).errors
    assert len(errors) == 2 and "parts/1/shape" in " ".join(errors)


def test_files_of_an_entry():
    report = Report()
    check_files(report, "w", {"tree.json": DESCRIPTOR_MAX + 1}, "tree.json")
    check_files(report, "w", {"image.webp": ASSET_FILES["image.webp"] + 1}, "tree.json")
    check_files(report, "w", {"tree.json": 1, "model.glb": 5}, "tree.json")
    check_files(
        report, "w", {"tree.json": 1, "image.webp": 1, "image.png": 1}, "tree.json"
    )
    assert report.errors == [
        f"w: tree.json is {DESCRIPTOR_MAX + 1} bytes, limit {DESCRIPTOR_MAX}",
        "w: missing tree.json",
        "w: image.webp is 300001 bytes, limit 300000",
        "w: unexpected file 'model.glb' (allowed: tree.json, image.webp, image.png, thumb.webp)",
        "w: image.webp and image.png both present, keep one",
    ]


def test_tree_sizes_must_agree(tree, validators):
    tree["height"] = {"default": 2, "min": 4, "max": 25}
    tree["trunk"]["height"] = 2
    tree["trunk"]["radius"] = 2.5
    tree["crown_radius"] = 2.5
    errors = check("tree", tree, validators).errors
    assert len(errors) == 4
    assert "height needs min <= default <= max" in errors[0]
    assert "trunk height 2 must be below the tree height 2" in errors[1]
    assert "trunk radius 2.5 must be below the crown radius 2.5" in errors[2]
    assert "crown radius 2.5 is implausible for a tree of 2 m" in errors[3]


def test_latin_name_is_unique_whatever_the_case(tree, validators):
    ctx = Context(trees={"old-oak": {"latin": "QUERCUS ROBUR"}, "nameless": {}})
    assert check("tree", tree, validators, ctx=ctx).errors == [
        "trees/items/draft: latin 'Quercus robur' already used by 'old-oak'"
    ]
    del tree["latin"]
    assert check("tree", tree, validators, ctx=ctx).errors == []


def test_tree_warnings(tree, validators):
    del tree["seasons"]["spring"], tree["seasons"]["winter"]
    warnings = check("tree", tree, validators, {"tree.json": 1}).warnings
    assert warnings == [
        "trees/items/draft: missing translations: fr, de, es, it, pl, pt",
        "trees/items/draft: deciduous tree without spring, winter: drawn like summer then",
        "trees/items/draft: no picture, only the icon will be shown",
    ]
    tree["evergreen"] = True  # summer alone is enough for an evergreen
    assert len(check("tree", tree, validators, FILES).warnings) == 1


def test_object_must_stand_centred_on_the_ground(thing, validators):
    thing["name"] = ALL_LANGS
    thing["parts"][0]["x"] = 0.2
    thing["parts"][1]["z"] = -0.3
    errors = check("object", thing, validators).errors
    assert errors == [
        "objects/items/draft: footprint off centre along x: shift every part by -0.165 m",
        "objects/items/draft: footprint off centre along z: shift every part by +0.085 m",
    ]


def test_object_under_or_above_the_ground_or_too_large(thing, validators):
    thing["name"] = ALL_LANGS
    slab = {
        "shape": "box",
        "width": 2,
        "height": 0.04,
        "depth": 0.04,
        "color": "#aaaaaa",
    }
    lying = dict(thing, parts=[dict(slab, roll=90)])  # stood up about its centre
    report = check("object", lying, validators, {"object.json": 1})
    assert report.errors == [
        "objects/items/draft: a part reaches 0.980 m under the ground"
    ]
    assert report.warnings == [
        "objects/items/draft: no picture, only the icon will be shown"
    ]

    floating = dict(thing["parts"][1], elevation=0.5)
    report = check("object", dict(thing, parts=[floating]), validators)
    assert report.warnings == ["objects/items/draft: floats 0.500 m above the ground"]

    wall = {
        "shape": "box",
        "width": 20,
        "height": 2,
        "depth": 20,
        "yaw": 45,
        "color": "#aaaaaa",
    }
    report = check("object", dict(thing, parts=[wall]), validators)
    assert report.errors == [
        "objects/items/draft: 28.28 x 2.00 x 28.28 m is larger than 20 m"
    ]


def test_rotation_senses():
    def turned(yaw, pitch, roll, vector):
        matrix = rotation(yaw, pitch, roll)
        return [round(sum(row[k] * vector[k] for k in range(3)), 6) for row in matrix]

    assert turned(0, 0, 0, (1, 2, 3)) == [1, 2, 3]
    assert turned(90, 0, 0, (0, 0, 1)) == [1, 0, 0]  # yaw: the front turns toward +x
    assert turned(0, 90, 0, (0, 1, 0)) == [0, 0, 1]  # pitch: the top leans to the front
    assert turned(0, 0, 90, (0, 1, 0)) == [-1, 0, 0]  # roll: the top leans toward -x
    # yaw is applied last: a part pitched forward then turned leans toward +x
    assert turned(90, 90, 0, (0, 1, 0)) == [1, 0, 0]


def test_extent_of_a_turned_part():
    box = {"shape": "box", "width": 2, "height": 4, "depth": 6, "color": "#000000"}
    assert part_center(dict(box, x=1, z=-1, elevation=3)) == (1, 5, -1)
    assert part_extent(box) == (1, 2, 3)
    assert part_extent(dict(box, yaw=90)) == pytest.approx((3, 2, 1))
    assert part_extent(dict(box, roll=90)) == pytest.approx((2, 1, 3))
    diagonal = part_extent(dict(box, width=2, depth=2, yaw=45))
    assert diagonal == pytest.approx((math.sqrt(2), 2, math.sqrt(2)))
    ball = dict(box, shape="sphere", width=2, height=2, depth=2)
    assert part_extent(dict(ball, yaw=33, pitch=71, roll=12)) == pytest.approx(
        (1, 1, 1)
    )
    egg = dict(box, shape="sphere", pitch=90)  # the long axis stands up
    assert part_extent(egg) == pytest.approx((1, 3, 2))


def test_size_of_an_object(thing):
    low, high = object_bounds(thing["parts"])
    assert low == pytest.approx((-0.15, 0, -0.15))
    assert high == pytest.approx((0.15, 0.45, 0.15))
    assert object_size(thing["parts"]) == pytest.approx((0.3, 0.45, 0.3))


def test_an_accepted_entry_joins_the_context_a_draft_does_not(tree, validators):
    ctx, report = Context(), Report()
    assert validate_entry(report, "tree", "oak", tree, FILES, ctx, validators)
    assert list(ctx.trees) == ["oak"]
    assert not validate_entry(
        report, "tree", "bad", {"name": 1}, FILES, ctx, validators
    )
    assert list(ctx.trees) == ["oak"]

    twin = dict(tree)
    assert "already used by 'oak'" in check("tree", twin, validators, ctx=ctx).errors[0]
    assert list(ctx.trees) == ["oak"] and ctx.objects == {}


def test_schemas_are_read_from_any_folder(tmp_path: Path, tree):
    for path in (REPO / "schema").glob("*.json"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    assert check("tree", tree, load_validators(tmp_path)).errors == []


def test_a_complete_fish_passes(fish, validators):
    fish["name"] = ALL_LANGS
    for variety in fish["varieties"]:
        variety["name"] = ALL_LANGS
    report = check("fish", fish, validators, {"fish.json": 900, "image.webp": 1})
    assert (report.errors, report.warnings) == ([], [])


def test_fish_rules(fish, validators):
    fish["length"] = {"default": 0.5, "min": 0.6, "max": 3}
    fish["varieties"][1]["id"] = "red-white"
    fish["varieties"][0]["patches"][0]["amount"] = 0.95
    fish["varieties"][1]["patches"][0]["color"] = "#ffaa00"
    ctx = Context(fish={"other": {}, "carp": {"latin": "carassius AURATUS"}})
    report = check("fish", fish, validators, {"fish.json": 1}, ctx)
    assert report.errors == [
        "fish/items/draft: length needs min <= default <= max, got {'default': 0.5, 'min': 0.6, 'max': 3}",
        "fish/items/draft: a fish of 3 m is larger than 2 m",
        "fish/items/draft: latin 'Carassius auratus' already used by 'carp'",
        "fish/items/draft variety red-white: the patches cover 1.05 of the back, more than all of it",
        "fish/items/draft variety red-white: id used twice",
    ]
    assert report.warnings == [
        "fish/items/draft: missing translations: fr, de, es, it, pl, pt",
        "fish/items/draft variety red-white: missing translations: fr, de, es, it, pl, pt",
        "fish/items/draft variety red-white: missing translations: fr, de, es, it, pl, pt",
        "fish/items/draft variety red-white: a patch has the colour of the body: it does not show",
        "fish/items/draft: no picture, only the icon will be shown",
    ]
    del fish["latin"]
    assert not any(
        "latin" in e for e in check("fish", fish, validators, ctx=ctx).errors
    )


def test_fish_schema(fish, validators):
    fish["varieties"][0]["patches"].append(
        {"color": "#123456", "amount": 0.1, "size": "huge"}
    )
    errors = check("fish", fish, validators).errors
    assert len(errors) == 1 and "huge" in errors[0]
