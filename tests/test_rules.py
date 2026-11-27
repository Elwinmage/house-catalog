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
    assert sorted(validators) == [
        "coping",
        "fence",
        "object",
        "path",
        "pond_fish",
        "terrace",
        "tree",
        "wall",
    ]
    assert where_of("terrace", "painted") == "terraces/items/painted"
    assert where_of("wall", "brick") == "walls/items/brick"
    assert where_of("coping", "brick") == "copings/items/brick"
    assert where_of("fence", "mesh") == "fences/items/mesh"
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


# -- terraces, walls, fences --------------------------------------------------------


def report_of(kind, data, validators, files=None, ctx=None):
    return rules.validate_draft(
        kind,
        "draft",
        data,
        files if files is not None else {f"{kind}.json": 500, "image.webp": 900},
        ctx or rules.Context(),
        validators,
    )


@pytest.mark.parametrize("kind", ["terrace", "wall", "coping", "fence"])
def test_a_complete_entry_of_the_new_kinds_passes(kind, request, validators):
    data = request.getfixturevalue(kind)
    data["name"] |= {lang: "x" for lang in rules.KNOWN_LANGS}
    report = report_of(kind, data, validators)
    assert (report.errors, report.warnings) == ([], [])
    bare = report_of(kind, data, validators, files={f"{kind}.json": 500})
    assert bare.warnings == [
        f"{kind}s/items/draft: no picture, only the icon will be shown"
    ]


def test_the_surface_of_a_terrace_is_checked_like_the_one_of_a_path(
    terrace, validators
):
    terrace["surface"]["speckles"] = [
        {"color": "#8d6b43", "amount": 0.8, "size": 0.01},
        {"color": "#5c3c29", "amount": 0.5, "size": 0.01},
    ]
    terrace["surface"]["joints"]["color"] = terrace["surface"]["color"]
    report = report_of("terrace", terrace, validators)
    assert report.errors == [
        "terraces/items/draft: the grains cover 1.30 of the strip, more than all of it"
    ]
    assert (
        "terraces/items/draft: the joints have the colour of the units: "
        "they do not show" in report.warnings
    )
    # the ruts of a grass track are a thing of the paths
    terrace["surface"]["wheels"] = {"color": "#8d7150", "bands": [[0.1, 0.3]]}
    assert any(
        "wheels" in line for line in report_of("terrace", terrace, validators).errors
    )


def test_a_wall_is_laid_in_courses_under_a_coping_that_shows(wall, validators):
    wall["surface"]["joints"]["cell"] = [0.6, 0.2]
    wall["coping"]["color"] = wall["surface"]["color"]
    assert report_of("wall", wall, validators).warnings[1:] == [
        "walls/items/draft: units 0.6 m high and 0.2 m long stand on end: "
        "the height of a course comes first, then the length of a unit",
        "walls/items/draft: the coping has the colour of the faces: it does not show",
    ]
    # a rendered wall has neither joints nor coping
    plain = {key: value for key, value in wall.items() if key != "coping"}
    plain["surface"] = {"color": "#e3d9c6", "grain": 0.1}
    assert report_of("wall", plain, validators).errors == []


def test_a_coping_is_one_unit_wide_and_stands_clear_of_the_faces(coping, validators):
    # rows 20 cm deep on a coping 42 cm wide: joints would run along the wall
    coping["surface"]["joints"]["cell"] = [0.2, 0.075]
    assert report_of("coping", coping, validators).warnings[1:] == [
        "copings/items/draft: rows 0.2 m deep on a coping 0.42 m wide: "
        "a joint runs along the wall, in the middle of the coping",
    ]
    # stones without rows, or no joints at all, have none to tell
    coping["surface"]["joints"]["pattern"] = "irregular"
    assert report_of("coping", coping, validators).warnings[1:] == []
    # a folded sheet: its edges come down over the faces, which they must stand clear of
    sheet = {
        "name": coping["name"],
        "surface": {"color": "#4f5459", "roughness": 0.35},
        "height": 0.015,
        "overhang": 0,
        "drop": 0.05,
    }
    assert report_of("coping", sheet, validators).warnings[1:] == [
        "copings/items/draft: edges that come down over the faces need an overhang: "
        "without one they lie in the faces of the wall",
    ]
    del sheet["overhang"]  # the usual one: 3 cm
    report = report_of("coping", sheet, validators)
    assert (report.errors, report.warnings[1:]) == ([], [])
    # a coping is checked by its schema too
    sheet["drop"] = 0.5
    assert any("drop" in line for line in report_of("coping", sheet, validators).errors)


def test_irregular_stones_are_checked(wall, validators):
    joints = wall["surface"]["joints"]
    joints |= {
        "pattern": "irregular",
        "relief": 0.6,
        "tints": [
            {"color": "#c7a36c", "amount": 0.15},
            {"color": "#8f8b82", "amount": 0.2},
        ],
    }
    del joints["stagger"]
    report = report_of("wall", wall, validators)
    assert (report.errors, report.warnings[1:]) == ([], [])
    # what an irregular surface does not read, and a tile too small for its stones
    joints["stagger"] = 0.5
    wall["surface"]["tile"] = 0.5
    assert report_of("wall", wall, validators).warnings[1:] == [
        "walls/items/draft: irregular stones are not laid in rows: `stagger` is not read",
        "walls/items/draft: a tile of 0.5 m holds less than two stones of 0.3 m: "
        "the same ones repeat side by side",
    ]
    # without a tile of its own, the surface is laid in tiles of two metres
    del wall["surface"]["tile"]
    joints["cell"] = [0.9, 1.2]
    assert report_of("wall", wall, validators).warnings[1:] == [
        "walls/items/draft: irregular stones are not laid in rows: `stagger` is not read",
        "walls/items/draft: a tile of 2 m holds less than two stones of 1.2 m: "
        "the same ones repeat side by side",
    ]
    # a newer way of laying is refused by the schema
    joints["pattern"] = "herringbone"
    assert any(
        "herringbone" in line for line in report_of("wall", wall, validators).errors
    )


def test_tints_are_other_colours_for_a_share_of_the_units(wall, validators):
    joints = wall["surface"]["joints"]
    joints["tints"] = [
        {"color": "#c7a36c", "amount": 0.7},
        {"color": wall["surface"]["color"], "amount": 0.2},
        {"color": "#c7a36c", "amount": 0.3},
    ]
    assert report_of("wall", wall, validators).errors == [
        "walls/items/draft: tint #a89a80 is the base colour or is listed twice",
        "walls/items/draft: tint #c7a36c is the base colour or is listed twice",
        "walls/items/draft: the tints cover 1.2 of the units: more than all of them",
    ]
    # stones that bulge are irregular ones: in rows the relief is not drawn
    joints["tints"] = [{"color": "#c7a36c", "amount": 1}]
    joints["relief"] = 0.5
    report = report_of("wall", wall, validators)
    assert report.errors == []
    assert report.warnings[1:] == [
        "walls/items/draft: `relief` is only drawn on irregular stones"
    ]
    # a tint that no unit takes says nothing
    joints["tints"] = [{"color": "#c7a36c", "amount": 0}]
    assert any("amount" in line for line in report_of("wall", wall, validators).errors)


def test_a_fence_height_needs_its_bounds_in_order(fence, validators):
    fence["height"] = {"default": 5, "min": 0.5, "max": 3}
    assert report_of("fence", fence, validators).errors == [
        "fences/items/draft: height needs min <= default <= max, "
        "got {'default': 5, 'min': 0.5, 'max': 3}"
    ]


def test_fences_are_told_apart_by_their_draft_colour(fence, validators):
    other = copy.deepcopy(fence) | {"draft": "#00ff00"}
    ctx = rules.Context(fences={"panel": other, "mesh": copy.deepcopy(fence)})
    assert report_of("fence", fence, validators, ctx=ctx).errors == [
        "fences/items/draft: draft colour #ff2bd6 already used by 'mesh'"
    ]
    assert list(ctx.fences) == ["panel", "mesh"]  # the context is left as given
    fence["draft"] = "#123456"
    assert report_of("fence", fence, validators, ctx=ctx).errors == []


def test_a_see_through_fence_is_neither_a_hedge_nor_textured(fence, validators):
    fence["foliage"] = True
    fence["surface"]["speckles"] = [{"color": "#2f4f2d", "amount": 0.2, "size": 0.03}]
    report = report_of("fence", fence, validators)
    assert report.errors == [
        "fences/items/draft: a hedge is not see-through: open and foliage together"
    ]
    assert (
        "fences/items/draft: a see-through fence only shows the colour of its "
        "surface: joints and grains are not drawn" in report.warnings
    )
    fence["surface"] = {
        "color": "#8a6a48",
        "joints": {"color": "#5a4330", "cell": [2.8, 0.14]},
    }
    assert any(
        "joints and grains" in line
        for line in report_of("fence", fence, validators).warnings
    )
    # a hedge that is not see-through, with its leaves: nothing to say
    del fence["open"]
    fence["surface"] = {
        "color": "#3f6b35",
        "speckles": [{"color": "#2f4f2d", "amount": 0.2, "size": 0.03}],
    }
    report = report_of("fence", fence, validators)
    assert report.errors == [] and len(report.warnings) == 1  # the translations


def test_a_coping_is_laid_on_a_wall_only(fence, validators):
    fence["coping"] = True  # on the wire mesh of the fixture
    assert report_of("fence", fence, validators).errors == [
        "fences/items/draft: a coping is laid on a wall: not with open, not with foliage"
    ]
    del fence["open"]
    fence["foliage"] = True
    assert report_of("fence", fence, validators).errors == [
        "fences/items/draft: a coping is laid on a wall: not with open, not with foliage"
    ]
    # a sheet, or boards: too thin to carry one
    del fence["foliage"]
    assert report_of("fence", fence, validators).errors == [
        "fences/items/draft: a coping needs a wall at least 0.1 m thick, got 0"
    ]
    fence["thickness"] = 0.04
    assert report_of("fence", fence, validators).errors == [
        "fences/items/draft: a coping needs a wall at least 0.1 m thick, got 0.04"
    ]
    fence["thickness"] = 0.2
    assert report_of("fence", fence, validators).errors == []
    # and a fence that says it carries none is whatever it wants to be
    fence |= {"coping": False, "thickness": 0}
    assert report_of("fence", fence, validators).errors == []
