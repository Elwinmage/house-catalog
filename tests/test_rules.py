"""Rules of the catalog: what an entry must follow beyond its schema."""

from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest
from conftest import REPO

import house_catalog_rules as rules
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
    assert sorted(validators) == ["object", "path", "pond_fish", "tree"]
    assert where_of("pond_fish", "koi") == "pond_fish/items/koi"
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
    report = check(
        "pond_fish", fish, validators, {"pond_fish.json": 900, "image.webp": 1}
    )
    assert (report.errors, report.warnings) == ([], [])


def test_fish_rules(fish, validators):
    fish["length"] = {"default": 0.5, "min": 0.6, "max": 3}
    fish["varieties"][1]["id"] = "red-white"
    fish["varieties"][0]["patches"][0]["amount"] = 0.95
    fish["varieties"][1]["patches"][0]["color"] = "#ffaa00"
    ctx = Context(fish={"other": {}, "carp": {"latin": "carassius AURATUS"}})
    report = check("pond_fish", fish, validators, {"pond_fish.json": 1}, ctx)
    assert report.errors == [
        "pond_fish/items/draft: length needs min <= default <= max, got {'default': 0.5, 'min': 0.6, 'max': 3}",
        "pond_fish/items/draft: a fish of 3 m is larger than 2 m",
        "pond_fish/items/draft: latin 'Carassius auratus' already used by 'carp'",
        "pond_fish/items/draft variety red-white: the patches cover 1.05 of the back, more than all of it",
        "pond_fish/items/draft variety red-white: id used twice",
    ]
    assert report.warnings == [
        "pond_fish/items/draft: missing translations: fr, de, es, it, pl, pt",
        "pond_fish/items/draft variety red-white: missing translations: fr, de, es, it, pl, pt",
        "pond_fish/items/draft variety red-white: missing translations: fr, de, es, it, pl, pt",
        "pond_fish/items/draft variety red-white: a patch has the colour of the body: it does not show",
        "pond_fish/items/draft: no picture, only the icon will be shown",
    ]
    del fish["latin"]
    assert not any(
        "latin" in e for e in check("pond_fish", fish, validators, ctx=ctx).errors
    )


def test_fish_schema(fish, validators):
    fish["varieties"][0]["patches"].append(
        {"color": "#123456", "amount": 0.1, "size": "huge"}
    )
    errors = check("pond_fish", fish, validators).errors
    assert len(errors) == 1 and "huge" in errors[0]


def test_varieties_colour_what_the_seasons_show(tree, validators):
    tree["varieties"] = [
        {"id": "red", "name": {"en": "Red"}, "fruits": "#aa0000"},
        {"id": "pink", "name": {"en": "Pink"}, "flowers": "#f9d3e0"},
    ]
    assert check("tree", tree, validators).errors == []
    tree["varieties"] += [
        {"id": "red", "name": {"en": "Again"}, "fruits": "#bb0000"},
        {"id": "plain", "name": {"en": "Plain"}},
    ]
    assert check("tree", tree, validators).errors == [
        "trees/items/draft: variety 'red' is listed twice",
        "trees/items/draft: variety 'plain' changes no colour",
    ]


def test_varieties_cannot_colour_what_no_season_shows(tree, validators):
    for look in tree["seasons"].values():
        look.pop("fruits", None)
    tree["varieties"] = [{"id": "red", "name": {"en": "Red"}, "fruits": "#aa0000"}]
    assert check("tree", tree, validators).errors == [
        "trees/items/draft: varieties colour the fruits, but no season shows any"
    ]


# -- paths ------------------------------------------------------------------------


def report_path(data, validators, files=None, ctx=None):
    return rules.validate_draft(
        "path",
        "gravel",
        data,
        files if files is not None else {"path.json": 500, "image.webp": 900},
        ctx or rules.Context(),
        validators,
    )


def test_a_complete_path_passes(path, validators):
    path["name"] |= {lang: "x" for lang in rules.KNOWN_LANGS}
    report = report_path(path, validators)
    assert (report.errors, report.warnings) == ([], [])


def test_a_path_width_needs_its_bounds_in_order(path, validators):
    path["width"] = {"default": 20, "min": 0.5, "max": 12}
    assert report_path(path, validators).errors == [
        "paths/items/gravel: width needs min <= default <= max, "
        "got {'default': 20, 'min': 0.5, 'max': 12}"
    ]


def test_grains_cannot_cover_more_than_the_strip(path, validators):
    path["surface"]["speckles"] = [
        {"color": "#a99d86", "amount": 0.7, "size": 0.02},
        {"color": "#d2c8b3", "amount": 0.6, "size": 0.02},
    ]
    assert report_path(path, validators).errors == [
        "paths/items/gravel: the grains cover 1.30 of the strip, more than all of it"
    ]


def test_a_grain_covering_nothing_is_pointless(path, validators):
    path["surface"]["speckles"] = [{"color": "#a99d86", "amount": 0, "size": 0.02}]
    assert (
        "paths/items/gravel: a grain of #a99d86 covers nothing"
        in report_path(path, validators).warnings
    )


def test_joints_of_the_colour_of_the_units_do_not_show(path, validators):
    path["surface"]["joints"] = {"color": path["surface"]["color"], "cell": [0.2, 0.1]}
    assert (
        "paths/items/gravel: the joints have the colour of the units: they do not show"
        in report_path(path, validators).warnings
    )


def test_wheel_tracks_must_have_a_width_and_keep_apart(path, validators):
    path["surface"]["wheels"] = {
        "color": "#8d7150",
        "bands": [[0.4, 0.4], [0.3, 0.8]],
        "speckles": [{"color": "#76593b", "amount": 0, "size": 0.02}],
    }
    report = report_path(path, validators)
    assert report.errors == [
        "paths/items/gravel: wheel track [0.4, 0.4] has no width",
        "paths/items/gravel: wheel tracks [0.4, 0.4] and [0.3, 0.8] overlap",
    ]
    assert (
        "paths/items/gravel wheels: a grain of #76593b covers nothing"
        in report.warnings
    )


MODULE = {
    "name": {"en": "Stepping stones"},
    "kind": "module",
    "draft": "#b5b0a6",
    "width": {"default": 0.5, "min": 0.3, "max": 1.2},
    "module": {
        "shapes": ["round", "half-moon"],
        "size": [0.45, 0.45],
        "thickness": 0.05,
        "gap": 0.25,
        "colors": ["#8d8a84", "#a39a8c"],
    },
}


def test_a_complete_module_path_passes(validators):
    data = copy.deepcopy(MODULE)
    data["name"] |= {lang: "x" for lang in rules.KNOWN_LANGS}
    report = report_path(data, validators)
    assert (report.errors, report.warnings) == ([], [])


def test_an_element_taller_than_it_is_wide_is_a_post(validators):
    data = copy.deepcopy(MODULE)
    data["module"]["thickness"] = 0.3
    data["module"]["size"] = [0.2, 0.25]
    assert (
        "paths/items/gravel: an element 0.3 m thick and 0.2 m wide "
        "is a post, not a step" in report_path(data, validators).warnings
    )


def test_a_colour_listed_twice_and_an_element_too_wide(validators):
    data = copy.deepcopy(MODULE)
    data["module"]["colors"] = ["#8d8a84", "#8d8a84"]
    data["module"]["size"] = [0.45, 1.6]
    assert report_path(data, validators).errors == [
        "paths/items/gravel: colour #8d8a84 is listed twice",
        "paths/items/gravel: an element 1.6 m across never fits a path "
        "of at most 1.2 m",
    ]


def test_a_path_without_a_picture_is_a_warning(path, validators):
    assert (
        "paths/items/gravel: no picture, only the icon will be shown"
        in report_path(path, validators, files={"path.json": 500}).warnings
    )
