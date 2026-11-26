"""Pictures drawn from the descriptors."""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
import pytest
from conftest import FISH, OBJECT, TREE, dump
from PIL import Image

import render_previews as rp
from house_catalog_rules import object_bounds

BOX = ((-1, 0, -1), (1, 2, 1))


def extent(triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    points = triangles.reshape(-1, 3)
    return points.min(axis=0), points.max(axis=0)


def pixels(picture: Image.Image, color: str, tolerance: int = 70) -> int:
    """Opaque pixels close to a colour."""
    data = np.array(picture).astype(int)
    near = np.abs(data[:, :, :3] - np.array(rp.rgb(color))).sum(axis=2) < tolerance
    return int((near & (data[:, :, 3] > 200)).sum())


# -- meshes ---------------------------------------------------------------------


def test_colors():
    assert rp.rgb("#ff8000") == (255, 128, 0)


def test_frustum_between_two_points():
    upright = rp.frustum((0, 0, 0), (0, 2, 0), 1, 0.5, 8)
    assert upright.shape == (32, 3, 3)
    low, high = extent(upright)
    assert low == pytest.approx((-1, 0, -1)) and high == pytest.approx((1, 2, 1))
    lying = rp.frustum((0, 1, 0), (3, 1, 0), 0.5, 0.5)  # along x: another helper axis
    low, high = extent(lying)
    assert low == pytest.approx((0, 0.5, -0.5)) and high == pytest.approx((3, 1.5, 0.5))


def test_blobs():
    assert rp.blob((0, 0, 0), (1, 1, 1), level=0).shape == (20, 3, 3)
    ball = rp.blob((1, 2, 3), (2, 1, 0.5))
    assert ball.shape == (80, 3, 3)
    low, high = extent(ball)
    assert np.all(low >= (-1, 1, 2.5)) and np.all(high <= (3, 3, 3.5))
    radius = np.linalg.norm(
        rp.blob((0, 0, 0), (1, 1, 1), level=2).reshape(-1, 3), axis=1
    )
    assert radius == pytest.approx(np.ones(320 * 3))
    bumpy = rp.blob((0, 0, 0), (1, 1, 1), random.Random(1))
    radius = np.linalg.norm(bumpy.reshape(-1, 3), axis=1)
    assert radius.min() >= 0.85 and radius.max() <= 1.15 and radius.std() > 0.01


@pytest.mark.parametrize("shape", ["box", "cylinder", "sphere", "cone"])
def test_a_part_is_where_the_descriptor_puts_it(shape):
    part = {
        "shape": shape,
        "width": 0.4,
        "height": 1,
        "depth": 0.6,
        "x": 1,
        "z": -2,
        "elevation": 0.5,
        "color": "#808080",
    }
    low, high = extent(rp.part_triangles(part))
    expected_low, expected_high = object_bounds([part])
    assert low == pytest.approx(expected_low, abs=0.02)
    assert high == pytest.approx(expected_high, abs=0.02)
    # turned a quarter about the vertical axis, width and depth swap
    low, high = extent(rp.part_triangles(dict(part, yaw=90)))
    assert (high - low) == pytest.approx((0.6, 1, 0.4), abs=0.03)


def test_cone_points_up():
    cone = rp.part_triangles(
        {"shape": "cone", "width": 1, "height": 2, "depth": 1, "color": "#000000"}
    ).reshape(-1, 3)
    top = cone[cone[:, 1] > 1.99]
    assert np.abs(top[:, [0, 2]]).max() < 1e-9


def test_object_mesh_has_outward_normals():
    triangles, normals, colors, shades = rp.object_mesh(OBJECT).arrays()
    assert len(triangles) == len(normals) == len(colors) == len(shades) == 64 + 12
    assert np.linalg.norm(normals, axis=1) == pytest.approx(np.ones(len(normals)))
    box = slice(64, 76)  # second part: a box standing on the ground at the origin
    outward = triangles[box].mean(axis=1) - np.array([0, 0.205, 0])
    assert np.all(np.sum(normals[box] * outward, axis=1) > 0)
    assert tuple(colors[70]) == rp.rgb("#8a6a45")


def test_tree_mesh_follows_the_season():
    count = {
        season: len(rp.tree_mesh(TREE, season).arrays()[0]) for season in rp.SEASONS
    }
    assert (
        count["winter"] < count["summer"] < count["spring"]
    )  # bare / fruits / blossom
    low, high = extent(rp.tree_mesh(TREE, "summer").arrays()[0])
    reach = TREE["crown_radius"] * 1.2
    assert np.all(low >= (-reach, 0, -reach))
    assert np.all(high <= (reach, TREE["height"]["default"] * 1.08, reach))
    assert high[1] > TREE["height"]["default"] * 0.85

    only_summer = TREE | {"seasons": {"summer": TREE["seasons"]["summer"]}}
    assert len(rp.tree_mesh(only_summer, "winter").arrays()[0]) == count["summer"]


def test_blossom_on_bare_branches():
    bare = {
        "foliage": "#000000",
        "density": 0,
        "flowers": {"color": "#ffffff", "amount": 1},
    }
    blossom = TREE | {"seasons": {"summer": TREE["seasons"]["summer"], "spring": bare}}
    plain = TREE | {"seasons": {"summer": {"foliage": "#000000", "density": 0}}}
    with_flowers = len(rp.tree_mesh(blossom, "spring").arrays()[0])
    assert with_flowers == len(rp.tree_mesh(plain, "spring").arrays()[0]) + 170 * 20


def test_conical_tree():
    fir = TREE | {
        "shape": "conical",
        "latin": "Abies",
        "seasons": {
            "summer": {
                "foliage": "#205030",
                "fruits": {"color": "#aa0000", "amount": 0.2},
            },
            "winter": {"foliage": "#205030", "density": 0},
        },
    }
    triangles = rp.tree_mesh(fir, "summer").arrays()[0]
    low, high = extent(triangles)
    assert low[1] == pytest.approx(0, abs=0.01)
    assert high[1] == pytest.approx(fir["height"]["default"], rel=0.02)
    assert high[0] == pytest.approx(fir["crown_radius"], rel=0.05)
    # no leaf, no cone to hang on: a conifer without needles is a bare trunk
    assert len(rp.tree_mesh(fir, "winter").arrays()[0]) < 60


# -- drawing --------------------------------------------------------------------


def test_render_draws_what_faces_the_camera():
    mesh = rp.Mesh()
    mesh.add(rp._UNIT_BOX * 0.5 + np.array([0, 1, 0]), rp.rgb("#c80000"))
    front = rp.render(mesh, 40, (0.0, 0.0), BOX, supersample=2)
    assert front.size == (40, 40) and front.mode == "RGBA"
    data = np.array(front)
    assert tuple(data[0, 0]) == (0, 0, 0, 0)  # transparent around
    assert data[20, 20, 3] == 255 and data[20, 20, 0] > data[20, 20, 1]
    # from above, the lit top is brighter than the front seen from the side
    above = np.array(rp.render(mesh, 40, (0.0, 89.0), BOX, supersample=2))
    assert above[20, 20, 0] > data[20, 20, 0]


def test_render_hides_what_is_behind():
    mesh = rp.Mesh()
    mesh.add(rp._UNIT_BOX * 0.6 + np.array([0, 1, -1]), rp.rgb("#0000c8"))  # far
    mesh.add(rp._UNIT_BOX * 0.3 + np.array([0, 1, 1]), rp.rgb("#c80000"))  # near
    data = np.array(rp.render(mesh, 60, (0.0, 0.0), ((-1, 0, -2), (1, 2, 2)), 1))
    assert data[30, 30, 0] > data[30, 30, 2]  # the near red box in the middle
    assert data[30, 14, 2] > data[30, 14, 0]  # the far blue one around it


def test_render_skips_what_is_outside_or_flat():
    mesh = rp.Mesh()
    mesh.add(rp._UNIT_BOX + np.array([50, 1, 0]), rp.rgb("#c80000"))  # out of the frame
    flat = np.array([[[0, 1, 0], [0, 1, 0], [0, 1, 0]]], dtype=float)
    mesh.add(flat, rp.rgb("#00c800"))  # a triangle without area
    data = np.array(rp.render(mesh, 20, (0.0, 0.0), BOX, 1))
    assert data[:, :, 3].max() == 0


def test_shadow_under_the_picture():
    empty = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    assert np.array(rp._on_ground(empty))[:, :, 3].max() == 0
    tree = empty.copy()
    tree.paste((0, 150, 0, 255), (5, 5, 35, 15))  # a wide crown
    tree.paste((90, 60, 30, 255), (18, 15, 22, 30))  # on a thin trunk
    grounded = np.array(rp._on_ground(tree))
    assert tuple(grounded[10, 20]) == (0, 150, 0, 255)  # the picture stays on top
    assert tuple(grounded[28, 20]) == (90, 60, 30, 255)
    assert 0 < grounded[28, 10, 3] < 255  # a soft shadow around the foot
    assert grounded[20, 10, 3] == 0  # and nowhere else


def test_tree_pictures_show_the_seasons():
    sheet, thumb = rp.tree_pictures(TREE, size=96, thumb=32)
    assert sheet.size == (96, 96) and thumb.size == (32, 32)
    tiles = {
        season: sheet.crop(
            ((i % 2) * 48, (i // 2) * 48, (i % 2) * 48 + 48, (i // 2) * 48 + 48)
        )
        for i, season in enumerate(rp.SEASONS)
    }
    assert pixels(tiles["summer"], "#3f7f35") > 150
    assert pixels(tiles["autumn"], "#c98a2e") > 60
    assert pixels(tiles["winter"], "#3f7f35") == pixels(tiles["winter"], "#c98a2e") == 0
    assert pixels(tiles["spring"], "#ffffff") > 10  # blossom, kept bright
    assert pixels(thumb, "#3f7f35") > 40


def test_object_pictures():
    image, thumb = rp.object_pictures(OBJECT, size=64, thumb=24)
    assert image.size == (64, 64) and thumb.size == (24, 24)
    assert pixels(image, "#b8915f", 90) > 100  # the seat, seen from above
    assert np.array(image)[0, 0, 3] == 0


# -- files ----------------------------------------------------------------------


@pytest.fixture
def quick(monkeypatch):
    """Tiny pictures: the files matter here, not what is on them."""
    tiny = Image.new("RGBA", (8, 8), (10, 200, 10, 255))
    calls: list[str] = []

    def draw(data, *args):
        calls.append(data["name"]["en"])
        return tiny, tiny

    monkeypatch.setattr(
        rp,
        "PICTURES",
        {"tree": draw, "object": draw, "pond_fish": draw, "path": draw},
    )
    return calls


def test_only_missing_pictures_are_drawn(root: Path, quick):
    (root / "objects/items/stool/image.png").write_bytes(b"a photo")
    (root / "trees/items/empty").mkdir()
    (root / "pond_fish/items/goldfish/image.webp").write_bytes(b"drawn")
    (root / "paths/items/gravel/thumb.webp").write_bytes(b"drawn")
    assert rp.write_pictures(root) == ["trees/oak"]
    assert quick == ["Oak"]
    with Image.open(root / "trees/items/oak/image.webp") as image:
        assert image.format == "WEBP" and image.size == (8, 8)
    assert (root / "trees/items/oak/thumb.webp").is_file()
    assert not (root / "objects/items/stool/image.webp").exists()

    assert rp.write_pictures(root) == []
    assert rp.write_pictures(root, only=["stool"]) == ["objects/stool"]
    assert rp.write_pictures(root, force=True) == [
        "trees/oak",
        "objects/stool",
        "pond_fish/goldfish",
        "paths/gravel",
    ]


def test_command(root: Path, quick, capsys):
    args = ["--root", str(root)]
    assert rp.main(args) == 0
    assert (
        "drawn: trees/oak\ndrawn: objects/stool\n"
        "drawn: pond_fish/goldfish\ndrawn: paths/gravel\n4 entries drawn"
        in capsys.readouterr().out
    )
    assert rp.main([*args, "oak"]) == 0
    assert "1 entry drawn" in capsys.readouterr().out
    assert rp.main(args) == 0
    assert "0 entries drawn" in capsys.readouterr().out


def test_real_drawing_ends_in_a_file(root: Path, monkeypatch):
    monkeypatch.setattr(rp, "IMAGE_SIZE", 32)
    small = {
        "tree": lambda data: rp.tree_pictures(data, 32, 16),
        "object": lambda data: rp.object_pictures(data, 32, 16),
        "pond_fish": lambda data: rp.fish_pictures(data, 32, 16),
        "path": lambda data: rp.path_pictures(data, 32, 16),
    }
    monkeypatch.setattr(rp, "PICTURES", small)
    dump(root / "trees/items/oak/tree.json", TREE)
    assert rp.write_pictures(root) == [
        "trees/oak",
        "objects/stool",
        "pond_fish/goldfish",
        "paths/gravel",
    ]
    with Image.open(root / "objects/items/stool/thumb.webp") as thumb:
        assert thumb.size == (16, 16) and thumb.mode == "RGBA"


# -- fish -----------------------------------------------------------------------


def test_body_is_narrow_at_the_tail_and_round_at_the_head():
    assert rp.body_halfwidth(0) == pytest.approx(0.28)
    assert rp.body_halfwidth(0.62) == pytest.approx(1)
    assert rp.body_halfwidth(1) == pytest.approx(0, abs=1e-6)
    assert rp.body_halfwidth(-1) == rp.body_halfwidth(0)
    assert rp.body_halfwidth(2) == rp.body_halfwidth(1)


def test_patches_of_a_fish():
    red_white, gold = FISH["varieties"]
    body = FISH["body"]
    patches = rp.fish_patches(red_white, body, 1)
    assert len(patches) == rp.PATCH_COUNT["large"] + rp.PATCH_COUNT["small"]
    assert patches == rp.fish_patches(red_white, body, 1)  # same seed, same robe
    assert patches != rp.fish_patches(red_white, body, 2)
    for color, x, _, rx, ry in patches:
        assert color in ("#dd2200", "#000000") and -0.25 < x < 0.5 and rx > ry
    # a head spot: one round patch on the middle line, near the snout
    [(color, x, y, rx, ry)] = rp.fish_patches(gold, body, 3)
    assert (color, y, rx) == ("#cc0000", 0, ry) and x > 0.3
    assert rp.fish_patches({"base": "#000000"}, body, 1) == []


def test_fish_pictures():
    sheet, thumb = rp.fish_pictures(FISH, size=96, thumb=48)
    assert sheet.size == (96, 96) and thumb.size == (48, 48)
    left, right = sheet.crop((0, 0, 48, 48)), sheet.crop((48, 0, 96, 48))
    assert pixels(left, "#ffffff") > 20 and pixels(left, "#dd2200") > 5
    assert pixels(right, "#ffaa00", 120) > 20  # the gold one, made shinier
    assert pixels(right, "#ffaa00", 60) > 3 * pixels(left, "#ffaa00", 60)
    assert np.array(sheet)[0, 0, 3] == 0
    assert pixels(thumb, "#dd2200") > 5
    short = FISH | {"body": FISH["body"] | {"fins": "short"}}
    wide = np.array(rp.fish_picture(FISH, FISH["varieties"][0], 64))[:, :, 3] > 100
    narrow = np.array(rp.fish_picture(short, FISH["varieties"][0], 64))[:, :, 3] > 100
    assert wide.any(axis=1).sum() > narrow.any(axis=1).sum()  # long fins reach out


def test_columnar_tree_is_a_column_down_to_the_ground():
    yew = TREE | {
        "shape": "columnar",
        "latin": "Taxus baccata",
        "evergreen": True,
        "height": {"default": 6, "min": 1.5, "max": 15},
        "crown_radius": 0.9,
        "trunk": {"height": 0.4, "radius": 0.25, "color": "#6e4a3a"},
        "seasons": {"summer": {"foliage": "#1f4a2c"}},
    }
    solids = rp._crown(yew, 1)
    assert len(solids) == len(rp._COLUMN_TIERS)
    assert {kind for kind, *_ in solids} == {
        "blob"
    }  # a column of foliage, not a stack of cones
    width = [sizes[0] for _, _, sizes in solids]
    assert max(width) == pytest.approx(yew["crown_radius"])
    assert width[0] > 0.8 * max(width)  # as wide at the foot as in the middle
    assert width[-1] < 0.4 * max(width)  # narrowing only at the top
    # the foliage comes down under the top of the trunk, which hardly shows
    assert (
        min(centre[1] - sizes[1] for _, centre, sizes in solids)
        < yew["trunk"]["height"]
    )

    low, high = extent(rp.tree_mesh(yew, "summer").arrays()[0])
    assert low[1] == pytest.approx(0, abs=0.01)
    assert high[1] == pytest.approx(yew["height"]["default"], rel=0.05)
    assert high[0] == pytest.approx(yew["crown_radius"], rel=0.1)


def test_weeping_tree_hangs_curtains_to_the_trunk():
    willow = TREE | {
        "shape": "weeping",
        "latin": "Salix",
        "trunk": {"height": 1.5, "radius": 0.2, "color": "#5a4b3a"},
        "seasons": {
            "summer": {"foliage": "#6aa14a"},
            "winter": {"foliage": "#6aa14a", "density": 0},
        },
    }
    low, high = extent(rp.tree_mesh(willow, "summer").arrays()[0])
    assert high[1] == pytest.approx(willow["height"]["default"], rel=0.03)
    assert low[1] < willow["trunk"]["height"] + 0.5  # the curtains reach the bottom
    assert high[0] == pytest.approx(willow["crown_radius"], rel=0.25)
    assert len(rp._weeping(9, 3.8, 1.5, 1)) == 5 + rp._CURTAINS
    # bare in winter: branches only, and the blossom of a bare weeping tree sits on them
    assert len(rp.tree_mesh(willow, "winter").arrays()[0]) < 400


def test_palm_has_a_bare_trunk_and_a_tuft_of_turned_fronds():
    palm = TREE | {
        "shape": "palm",
        "latin": "Phoenix",
        "height": {"default": 12, "min": 4, "max": 25},
        "crown_radius": 4,
        "trunk": {"height": 10, "radius": 0.3, "color": "#8a6f4f"},
        "seasons": {"summer": {"foliage": "#5b8c34"}},
    }
    solids = rp._palm(12, 4, 10, 1)
    assert len(solids) == 1 + rp._FRONDS * 3
    assert all(len(solid) == 4 for solid in solids)  # kind, centre, sizes, yaw
    low, high = extent(rp.tree_mesh(palm, "summer").arrays()[0])
    assert low[1] == pytest.approx(0, abs=0.01)
    assert high[1] == pytest.approx(12, rel=0.05)
    assert high[0] > 2  # the fronds spread well beyond the trunk
    # a turned blob keeps its size: a frond along x, turned a quarter turn, lies along z
    flat = rp.blob((0, 0, 0), (3, 0.2, 0.5), level=1)
    turned = rp.blob((0, 0, 0), (3, 0.2, 0.5), level=1, yaw=math.pi / 2)
    assert extent(flat)[1][0] == pytest.approx(3, rel=0.01)
    assert extent(turned)[1][2] == pytest.approx(3, rel=0.01)


# -- paths ----------------------------------------------------------------------

SURFACE = {
    "name": {"en": "Pavers"},
    "kind": "surface",
    "draft": "#c99a7b",
    "width": {"default": 2, "min": 0.6, "max": 8},
    "surface": {
        "color": "#a3816b",
        "grain": 0.2,
        "speckles": [
            {"color": "#ffffff", "amount": 0.2, "size": 0.05},
            {"color": "#000000", "amount": 0.1, "size": 0.05, "stretch": 3},
        ],
        "joints": {
            "color": "#5e4a3d",
            "cell": [0.4, 0.3],
            "width": 0.02,
            "stagger": 0.5,
            "shade": 0.2,
        },
    },
}

MODULE = {
    "name": {"en": "Stepping stones"},
    "kind": "module",
    "draft": "#b5b0a6",
    "width": {"default": 0.6, "min": 0.3, "max": 1.2},
    "module": {
        "shapes": ["round"],
        "size": [0.45, 0.45],
        "thickness": 0.05,
        "gap": 0.3,
        "colors": ["#808080"],
        "vary": {"size": 0, "angle": 0, "side": 0, "shade": 0},
    },
}


def test_a_colour_is_lightened_and_clamped():
    assert rp._shade((100.0, 200.0, 50.0), 1.5) == (150, 255, 75, 255)
    assert rp._shade((100.0, 200.0, 50.0), -1) == (0, 0, 0, 255)


def test_grains_are_scattered_round_or_stretched():
    rng = random.Random(1)
    layer = Image.new("RGBA", (120, 120), (0, 0, 0, 255))
    rp._speckle(layer, [{"color": "#ffffff", "amount": 0.3, "size": 1.0}], 10, rng)
    round_cover = pixels(layer, "#ffffff")
    assert 0.1 * 120 * 120 < round_cover < 0.6 * 120 * 120
    chips = Image.new("RGBA", (120, 120), (0, 0, 0, 255))
    rp._speckle(
        chips,
        [{"color": "#ffffff", "amount": 0.3, "size": 1.0, "stretch": 4}],
        10,
        random.Random(1),
    )
    # the same share of the strip, as flakes instead of pebbles
    assert pixels(chips, "#ffffff") == pytest.approx(round_cover, rel=0.5)
    assert np.array(chips)[:, :, :3].any()


def test_a_grain_is_never_smaller_than_a_pixel():
    rng = random.Random(2)
    layer = Image.new("RGBA", (40, 40), (0, 0, 0, 255))
    rp._speckle(layer, [{"color": "#ffffff", "amount": 0.05, "size": 1e-6}], 1, rng)
    assert pixels(layer, "#ffffff") > 0


def test_units_are_laid_over_their_joints():
    layer = rp.surface_layer(SURFACE["surface"], 100, 100, 100, random.Random(3))
    assert layer.size == (100, 100)
    # the joints show between the units, the units keep the base colour
    assert pixels(layer, "#5e4a3d", tolerance=40) > 300
    assert pixels(layer, "#a3816b", tolerance=60) > 2000


def test_a_flat_surface_keeps_its_colour():
    flat = {"color": "#102030", "grain": 0}
    layer = rp.surface_layer(flat, 20, 20, 50, random.Random(4))
    assert layer.getpixel((5, 5)) == (16, 32, 48, 255)


def test_wheels_wear_two_tracks_and_skip_an_empty_one():
    surface = {
        "color": "#6f8f4a",
        "grain": 0,
        "wheels": {
            "color": "#8d7150",
            "bands": [[0.1, 0.3], [0.5, 0.5]],
            "speckles": [{"color": "#ffffff", "amount": 0.2, "size": 0.02}],
        },
    }
    layer = rp.surface_layer(surface, 100, 60, 100, random.Random(5))
    assert layer.getpixel((20, 30))[:3] == (141, 113, 80)  # inside the first track
    assert layer.getpixel((80, 30))[:3] == (111, 143, 74)  # grass beside it
    assert pixels(layer, "#ffffff", tolerance=40) > 0  # grains, inside the track only
    assert pixels(layer, "#ffffff", tolerance=40) < 20 * 60


@pytest.mark.parametrize("shape", ["round", "oval", "half-moon", "slab", "stone"])
def test_an_element_stays_inside_its_size(shape):
    points = rp.element_outline(shape, 0.4, 0.6, random.Random(6))
    assert len(points) >= 10
    along = [x for x, _ in points]
    across = [y for _, y in points]
    if shape == "stone":
        # a broken paving stone is cut where it broke, give or take a tenth
        assert max(across) - min(across) == pytest.approx(0.6, rel=0.15)
        assert max(along) - min(along) == pytest.approx(0.4, rel=0.15)
        return
    assert max(across) - min(across) == pytest.approx(0.6, abs=1e-6)
    if shape == "half-moon":
        # a disc of the width of the path cut in two: half as deep as it is wide
        assert max(along) - min(along) == pytest.approx(0.3, abs=1e-6)
        assert min(along) == pytest.approx(-0.15, abs=1e-6)
    else:
        assert max(along) - min(along) <= 0.4 + 1e-6


def test_a_stone_is_not_a_perfect_ellipse():
    reach = {
        round(math.hypot(x / 0.2, y / 0.3), 3)
        for x, y in rp.element_outline("stone", 0.4, 0.6, random.Random(7))
    }
    assert len(reach) > 10
    assert all(0.7 < value < 1.15 for value in reach)


def test_elements_follow_one_another_down_the_path():
    elements = rp.module_elements(MODULE["module"], 60, 300, 100, random.Random(8))
    middles = [sum(y for _, y in points) / len(points) for points, _ in elements]
    assert len(elements) == 4
    # one every size + gap, all of the same colour, all on the centre line
    assert middles == pytest.approx([22.5, 97.5, 172.5, 247.5], abs=1.0)
    assert {color for _, color in elements} == {(128, 128, 128, 255)}
    for points, _ in elements:
        assert sum(x for x, _ in points) / len(points) == pytest.approx(30, abs=1.0)


def test_an_element_is_never_wider_than_the_path():
    module = MODULE["module"] | {"size": [0.45, 4.0]}
    elements = rp.module_elements(module, 60, 100, 100, random.Random(9))
    for points, _ in elements:
        assert max(x for x, _ in points) - min(x for x, _ in points) <= 60 + 1e-6


def test_elements_are_drawn_over_their_shadow():
    layer = rp.module_layer(MODULE["module"], 60, 200, 100, random.Random(10))
    assert pixels(layer, "#808080", tolerance=30) > 2000
    shaded = np.array(layer)
    assert (shaded[:, :, 3] > 0).sum() > pixels(layer, "#808080", tolerance=30)


@pytest.mark.parametrize("data", [SURFACE, MODULE])
def test_path_pictures_show_a_piece_of_path(data):
    image, thumb = rp.path_pictures(data, 48, 16)
    assert (image.size, thumb.size) == ((48, 48), (16, 16))
    for picture in (image, thumb):
        alpha = np.array(picture)[:, :, 3]
        assert alpha[:, 0].max() == 0  # the ground on both sides
        assert alpha[:, -1].max() == 0
        assert alpha[:, picture.width // 2].max() > 200  # the path down the middle


def test_a_path_without_a_width_takes_the_usual_one():
    narrow = rp.path_picture(SURFACE, 64)
    wide = rp.path_picture({k: v for k, v in SURFACE.items() if k != "width"}, 64)
    # fewer, so larger, units across the same strip
    assert pixels(wide, "#5e4a3d", tolerance=40) < pixels(
        narrow, "#5e4a3d", tolerance=40
    )
