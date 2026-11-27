"""Pictures drawn from the descriptors."""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
import pytest
from conftest import COPING, FENCE, FISH, OBJECT, TERRACE, TREE, WALL, dump
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
        dict.fromkeys(rp.PICTURES, draw),
    )
    return calls


def test_only_missing_pictures_are_drawn(root: Path, quick):
    (root / "objects/items/stool/image.png").write_bytes(b"a photo")
    (root / "trees/items/empty").mkdir()
    (root / "pond_fish/items/goldfish/image.webp").write_bytes(b"drawn")
    (root / "paths/items/gravel/thumb.webp").write_bytes(b"drawn")
    for folder in (
        "terraces/items/wood-decking",
        "walls/items/rubble-stone",
        "copings/items/brick",
    ):
        (root / folder / "image.webp").write_bytes(b"drawn")
    (root / "fences/items/mesh/thumb.webp").write_bytes(b"drawn")
    assert rp.write_pictures(root) == ["trees/oak"]
    assert quick == ["Oak"]
    with Image.open(root / "trees/items/oak/image.webp") as image:
        assert image.format == "WEBP" and image.size == (8, 8)
    assert (root / "trees/items/oak/thumb.webp").is_file()
    assert not (root / "objects/items/stool/image.webp").exists()

    assert rp.write_pictures(root) == []
    assert rp.write_pictures(root, only=["stool"]) == ["objects/stool"]
    assert rp.write_pictures(root, force=True) == EVERY_ENTRY


#: The entries of the catalog of the tests, in the order of the sections
EVERY_ENTRY = [
    "trees/oak",
    "objects/stool",
    "pond_fish/goldfish",
    "paths/gravel",
    "terraces/wood-decking",
    "walls/rubble-stone",
    "copings/brick",
    "fences/mesh",
]


def test_command(root: Path, quick, capsys):
    args = ["--root", str(root)]
    assert rp.main(args) == 0
    assert (
        "".join(f"drawn: {name}\n" for name in EVERY_ENTRY) + "8 entries drawn"
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
        "terrace": lambda data: rp.terrace_pictures(data, 32, 16),
        "wall": lambda data: rp.wall_pictures(data, 32, 16),
        "coping": lambda data: rp.coping_pictures(data, 32, 16),
        "fence": lambda data: rp.fence_pictures(data, 32, 16),
    }
    assert set(small) == set(rp.PICTURES)
    monkeypatch.setattr(rp, "PICTURES", small)
    dump(root / "trees/items/oak/tree.json", TREE)
    assert rp.write_pictures(root) == EVERY_ENTRY
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


# -- terraces, walls, fences ------------------------------------------------------


def test_uneven_units_fill_their_row_and_no_more():
    surface = {
        "color": "#a89a80",
        "grain": 0,
        "joints": {
            "color": "#000000",
            "cell": [0.5, 0.25],
            "width": 0.02,
            "stagger": 0.5,
            "shade": 0,
            "vary": 0.5,
        },
    }
    layer = rp.surface_layer(surface, 200, 100, 100, random.Random(11))
    stones = np.abs(np.array(layer)[:, :, :3].astype(int) - (168, 154, 128)).sum(axis=2)
    row = stones[25] < 10  # through the middle of the first row
    # the joints between the stones of a row: uneven lengths, the row filled to its end
    cuts = [x for x in range(1, 200) if row[x] and not row[x - 1]]
    lengths = np.diff(cuts)
    assert len(cuts) >= 6 and lengths.max() > 1.3 * lengths.min()
    assert row[-12:].any()
    # the same numbers without `vary`: every stone as long as the next
    even = rp.surface_layer(
        surface | {"joints": surface["joints"] | {"vary": 0}},
        200,
        100,
        100,
        random.Random(11),
    )
    plain = np.abs(np.array(even)[:, :, :3].astype(int) - (168, 154, 128)).sum(axis=2)
    starts = [x for x in range(1, 200) if plain[25, x] < 10 and plain[25, x - 1] >= 10]
    assert set(np.diff(starts)) == {25}


class Dice:
    """A source of chance that always gives the same share of its range."""

    def __init__(self, share: float) -> None:
        self.share = share

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self.share

    def random(self) -> float:
        return self.share


def area(polygon) -> float:
    return abs(
        sum(
            a[0] * b[1] - b[0] * a[1]
            for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True)
        )
        / 2
    )


def test_the_middles_of_irregular_stones_are_set_off_and_moved_about():
    # nothing moved, nothing left out: one to a square, every other row half a square on
    even = rp.stone_sites(4, 2, 0, Dice(0.5))
    assert even[:4] == [(0.125, 0.25), (0.375, 0.25), (0.625, 0.25), (0.875, 0.25)]
    assert even[4:] == [(0.25, 0.75), (0.5, 0.75), (0.75, 0.75), (0.0, 0.75)]
    moved = rp.stone_sites(4, 2, 0.8, Dice(0.999))
    assert moved[0] == pytest.approx((0.125 + 0.4 * 0.998 / 4, 0.25 + 0.4 * 0.998 / 2))
    # the last one of the second row is pushed over the edge and comes back on the left
    assert 0 < moved[-1][0] < 0.125
    # the more uneven, the more stones are left out: their neighbours grow
    rng = random.Random(4)
    assert len(rp.stone_sites(20, 20, 0.8, rng)) < 360
    assert len(rp.stone_sites(20, 20, 0, rng)) == 400
    # never an empty wall
    assert rp.stone_sites(3, 2, 0.8, Dice(0)) == [(0.5, 0.5)]


def test_a_polygon_is_cut_along_a_line():
    square = [(0, 0), (4, 0), (4, 4), (0, 4)]
    assert rp.clip_polygon(square, 1, 0, 1) == [(0, 0), (1.0, 0.0), (1.0, 4.0), (0, 4)]
    assert rp.clip_polygon(square, 1, 0, 9) == square
    assert rp.clip_polygon(square, 1, 0, -1) == []
    # a line through two corners keeps them, and adds none
    assert rp.clip_polygon(square, 1, -1, 0) == [(0, 0), (4, 4), (0, 4)]


def test_irregular_stones_fill_the_surface_less_their_joints():
    sites = rp.stone_sites(5, 4, 0.8, random.Random(7))
    cells = rp.stone_cells(sites, 100, 80, 0)
    assert len(cells) == len(sites)
    # without joints the stones share the whole surface, each around its middle
    assert sum(area(corners) for _, corners in cells) == pytest.approx(8000)
    sizes = sorted(area(corners) for _, corners in cells)
    assert sizes[-1] > 2 * sizes[0]  # small stones wedged between large blocks
    for (mx, my), corners in cells:
        assert min(x for x, _ in corners) < mx < max(x for x, _ in corners)
        assert min(y for _, y in corners) < my < max(y for _, y in corners)
    # with joints each stone is that much smaller, and a joint too wide leaves none
    jointed = rp.stone_cells(sites, 100, 80, 4)
    assert len(jointed) == len(sites)
    assert sum(area(corners) for _, corners in jointed) < 0.9 * 8000
    assert rp.stone_cells(sites, 100, 80, 500) == []
    # a single stone is cut by itself, a whole surface away on every side
    ((middle, alone),) = rp.stone_cells([(0.5, 0.5)], 100, 80, 0)
    assert middle == (50, 40)
    assert area(alone) == pytest.approx(8000)
    assert min(alone) == pytest.approx((0, 0)) and max(alone) == pytest.approx(
        (100, 80)
    )


def test_the_outline_of_a_stone_is_pulled_in_and_rounded():
    square = [(0, 0), (40, 0), (40, 40), (0, 40)]
    sharp = rp.stone_outline(square, (20, 20), 0, random.Random(1))
    assert len(sharp) == 4 * (rp.STONE_CORNER_STEPS + 1)
    # each corner is cut off: the outline leaves a side and joins the next one a little way along
    cut = 40 * rp.STONE_CORNER
    assert sharp[0] == pytest.approx((0, cut))
    assert sharp[rp.STONE_CORNER_STEPS] == pytest.approx((cut, 0))
    assert 0.9 * 1600 < area(sharp) < 1600
    # the more uneven, the more each corner is pulled towards the middle
    rough = rp.stone_outline(square, (20, 20), 0.8, Dice(1))
    assert area(rough) < 0.85 * area(sharp)
    for x, y in rough:
        assert 0 < x < 40 and 0 < y < 40


def test_a_side_too_short_to_show_is_dropped():
    corners = 4 * (rp.STONE_CORNER_STEPS + 1)
    # two corners almost at the same place, in the middle of the outline, then at its ends
    nicked = [(0, 0), (40, 0), (40, 1), (40, 40), (0, 40)]
    assert len(rp.stone_outline(nicked, (20, 20), 0, random.Random(1))) == corners
    closing = [(0, 1), (40, 0), (40, 40), (0, 40), (0, 0)]
    assert len(rp.stone_outline(closing, (20, 20), 0, random.Random(1))) == corners
    # but a stone keeps three sides
    sliver = [(0, 0), (40, 0), (20, 30), (0, 1)]
    assert len(rp.stone_outline(sliver, (20, 10), 0, random.Random(1))) == 3 * (
        rp.STONE_CORNER_STEPS + 1
    )


def test_the_face_of_a_stone_sits_up_and_left_in_its_rim():
    square = [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)]
    face = rp.stone_face(square, (20, 20), 1)
    assert area(face) == pytest.approx(1600 * (1 - rp.RELIEF_RIM) ** 2)
    left, top = face[0]
    right, bottom = face[2]
    # the rim left in shade is wider below and on the right
    assert 0 < left < 40 - right and 0 < top < 40 - bottom
    # as arrays: approx() takes no list of points
    flat = np.array(rp.stone_face(square, (20, 20), 0))
    assert flat == pytest.approx(np.array(square))
    # a stone without any room around its middle keeps its face on it
    assert rp.stone_face([(5.0, 5.0), (5.0, 5.0)], (5, 5), 1) == [(5.0, 5.0)] * 2


def test_a_unit_takes_a_tint_for_its_share_of_the_units():
    tints = [{"color": "#ff0000", "amount": 0.25}, {"color": "#0000ff", "amount": 0.25}]
    base = (10, 20, 30)
    assert rp._unit_colour(base, tints, Dice(0.1)) == (255, 0, 0)
    assert rp._unit_colour(base, tints, Dice(0.4)) == (0, 0, 255)
    assert rp._unit_colour(base, tints, Dice(0.6)) == base
    assert rp._unit_colour(base, [], None) == base  # no dice thrown without tints


IRREGULAR = {
    "color": "#b7b0a1",
    "grain": 0,
    "joints": {
        "pattern": "irregular",
        "color": "#000000",
        "cell": [0.2, 0.3],
        "width": 0.02,
        "shade": 0,
        "vary": 0.8,
    },
}


def test_irregular_stones_are_fitted_into_one_another_without_rows():
    layer = rp.surface_layer(IRREGULAR, 240, 160, 100, random.Random(5))
    stone = np.abs(np.array(layer)[:, :, :3].astype(int) - (183, 176, 161)).sum(axis=2)
    stones = stone < 10
    # mostly stone, with joints all around
    assert 0.7 < stones.mean() < 0.95
    assert pixels(layer, "#000000", tolerance=10) > 2000
    # no joint runs across the whole wall, as the bed of a course would
    assert not (~stones).all(axis=1).any()
    assert not (~stones).all(axis=0).any()
    # the wall joins up with itself: what leaves on one side comes back on the other
    assert (stones[:, 0] == stones[:, -1]).mean() > 0.85
    assert (stones[0] == stones[-1]).mean() > 0.85
    # the same numbers in rows: beds from side to side
    rows = rp.surface_layer(
        IRREGULAR | {"joints": IRREGULAR["joints"] | {"pattern": "rows"}},
        240,
        160,
        100,
        random.Random(5),
    )
    assert pixels(rows, "#000000", tolerance=10) > 0
    assert (np.array(rows)[:, :, :3].sum(axis=2) == 0).all(axis=1).any()


def test_stones_that_bulge_have_a_rim_in_shade_and_some_take_a_tint():
    joints = IRREGULAR["joints"] | {
        "relief": 1,
        "tints": [{"color": "#c08040", "amount": 0.3}],
    }
    layer = rp.surface_layer(
        IRREGULAR | {"joints": joints}, 240, 160, 100, random.Random(5)
    )
    lit = pixels(layer, "#b7b0a1", tolerance=10)
    dark = tuple(int(c * (1 - rp.RELIEF_SHADE)) for c in rp.rgb("#b7b0a1"))
    rim = pixels(layer, "#{:02x}{:02x}{:02x}".format(*dark), tolerance=10)
    assert lit > 4000 and rim > 2000
    assert pixels(layer, "#c08040", tolerance=10) > 1000
    # in rows too, some units take the tint
    rows = rp.surface_layer(
        IRREGULAR | {"joints": joints | {"pattern": "rows", "vary": 0}},
        240,
        160,
        100,
        random.Random(5),
    )
    assert pixels(rows, "#c08040", tolerance=10) > 1000
    uneven = rp.surface_layer(
        IRREGULAR | {"joints": joints | {"pattern": "rows"}},
        240,
        160,
        100,
        random.Random(5),
    )
    assert pixels(uneven, "#c08040", tolerance=10) > 1000


def test_terrace_pictures_show_a_square_of_it():
    image, thumb = rp.terrace_pictures(TERRACE, 64, 24)
    assert (image.size, thumb.size) == ((64, 64), (24, 24))
    alpha = np.array(image)[:, :, 3]
    assert alpha[0, 0] == 0 and alpha[32, 32] == 255
    assert pixels(image, "#a07b4f", tolerance=90) > 1500  # the boards
    # a thicker terrace throws a longer shadow, under and to the right of it
    thin = np.array(rp.terrace_picture(TERRACE | {"thickness": 0.02}, 64))[:, :, 3]
    thick = np.array(rp.terrace_picture(TERRACE | {"thickness": 0.6}, 64))[:, :, 3]
    assert (thick > 0).sum() > (thin > 0).sum()
    # no thickness given: the usual one
    plain = {key: value for key, value in TERRACE.items() if key != "thickness"}
    assert rp.terrace_picture(plain, 32).size == (32, 32)


def test_wall_pictures_show_its_face_and_its_coping():
    image, thumb = rp.wall_pictures(WALL, 96, 24)
    assert (image.size, thumb.size) == ((96, 96), (24, 24))
    data = np.array(image)
    assert data[0, 0, 3] == 0 and data[48, 48, 3] == 255
    covered = np.nonzero(data[:, 48, 3] == 255)[0]
    capped_top = covered.min()
    bare = np.array(
        rp.wall_picture({k: v for k, v in WALL.items() if k != "coping"}, 96)
    )
    bare_top = np.nonzero(bare[:, 48, 3] == 255)[0].min()
    assert capped_top < bare_top  # the coping stands on the wall
    assert pixels(image, "#b9ad96", tolerance=50) > pixels(
        Image.fromarray(bare), "#b9ad96", tolerance=50
    )
    # a coping given by its colour alone takes the usual height and overhang
    short = rp.wall_picture(WALL | {"coping": {"color": "#ff0000"}}, 96)
    assert pixels(short, "#ff0000", tolerance=60) > 20


def test_coping_pictures_show_its_top_its_edge_and_the_wall_under_it():
    image, thumb = rp.coping_pictures(COPING, 96, 24)
    assert (image.size, thumb.size) == ((96, 96), (24, 24))
    data = np.array(image)
    assert data[0, 0, 3] == 0 and data[48, 48, 3] == 255
    covered = np.nonzero(data[:, 48, 3] == 255)[0]
    # from the top: the bricks, then the wall under them, in its own colour
    assert pixels(image, COPING["surface"]["color"], tolerance=70) > 200
    assert pixels(image, rp.COPING_WALL, tolerance=12) > 1500
    wall = np.array(rp.rgb(rp.COPING_WALL))
    wall_rows = [
        y for y in covered if np.abs(data[y, 48, :3].astype(int) - wall).sum() < 12
    ]
    assert covered.min() < min(wall_rows)
    # the wall is narrower than what caps it, by what the coping juts out
    wide = np.array(rp.coping_picture(COPING | {"overhang": 0.15}, 96))
    top_row, wall_row = covered.min() + 1, max(wall_rows) - 1
    assert (wide[top_row, :, 3] == 255).sum() > (wide[wall_row, :, 3] == 255).sum()
    # edges that come down over the faces make it taller, a coping given by its surface
    # alone takes the usual sizes
    plain = {"name": COPING["name"], "surface": {"color": "#4f5459"}}
    flat = np.array(rp.coping_picture(plain, 96))
    folded = np.array(rp.coping_picture(plain | {"drop": 0.15}, 96))
    greys = [
        pixels(Image.fromarray(picture), "#4f5459", tolerance=40)
        for picture in (flat, folded)
    ]
    assert greys[1] > greys[0] > 0


def test_wires_and_bars_of_a_see_through_fence():
    mesh = rp.open_lines({"pattern": "mesh", "pitch": 0.1, "fill": 0.4}, 100, 50, 100)
    assert len(mesh) % 2 == 0 and {round(w, 6) for _, w in mesh} == {2.0}
    # two sets of wires leaning opposite ways
    (ax0, ay0, ax1, ay1), _ = mesh[0]
    (bx0, by0, bx1, by1), _ = mesh[1]
    assert (ay0, ay1, by0, by1) == (0.0, 50, 0.0, 50)
    assert (ax1 - ax0) == -(bx1 - bx0) == 50

    grid = rp.open_lines({"pattern": "grid", "pitch": 0.1, "fill": 0.4}, 100, 50, 100)
    upright = [box for box, _ in grid if box[0] == box[2]]
    level = [box for box, _ in grid if box[1] == box[3]]
    assert len(upright) == 11 and len(level) == 2  # one level wire every four
    assert level[0][1] == 50  # the lowest one is on the ground

    bars = rp.open_lines({"pattern": "bars"}, 100, 50, 100)  # usual pitch and fill
    rails = [(box, w) for box, w in bars if box[1] == box[3]]
    assert len(bars) - len(rails) == 10 and len(rails) == 2
    assert [box[1] for box, _ in rails] == pytest.approx([7, 43])
    assert {round(w, 6) for _, w in bars} == {3.5}


@pytest.mark.parametrize("pattern", ["mesh", "grid", "bars"])
def test_a_see_through_fence_shows_what_is_behind(pattern):
    data = FENCE | {"open": {"pattern": pattern, "pitch": 0.2, "fill": 0.3}}
    panel = rp.fence_panel(data, 120, 60, 60, random.Random(12))
    alpha = np.array(panel)[:, :, 3]
    assert 0.05 < (alpha > 0).mean() < 0.7
    assert pixels(panel, "#5f7d5c", tolerance=30) > 100  # wires of the surface colour


def test_a_solid_fence_is_painted_and_a_hedge_has_an_uneven_top():
    solid = {key: value for key, value in FENCE.items() if key != "open"}
    solid["surface"] = {"color": "#3f6b35", "grain": 0}
    panel = np.array(rp.fence_panel(solid, 90, 60, 60, random.Random(13)))
    assert (panel[:, :, 3] == 255).all()
    hedge = np.array(
        rp.fence_panel(solid | {"foliage": True}, 90, 60, 60, random.Random(13))
    )
    top = [np.nonzero(hedge[:, x, 3] > 128)[0].min() for x in range(5, 85)]
    assert len(set(top)) > 3 and max(top) <= rp.HEDGE_BUMP * 60 + 1
    assert (hedge[-1, 5:85, 3] == 255).all()  # full down to the ground


def test_fence_pictures_stand_on_the_ground_with_their_posts():
    image, thumb = rp.fence_pictures(FENCE, 96, 24)
    assert (image.size, thumb.size) == ((96, 96), (24, 24))
    assert np.array(image)[0, 0, 3] == 0
    assert pixels(image, "#3d4a3c", tolerance=60) > 30  # the posts
    bare = rp.fence_picture({k: v for k, v in FENCE.items() if k != "posts"}, 96)
    assert pixels(bare, "#3d4a3c", tolerance=60) < pixels(
        image, "#3d4a3c", tolerance=60
    )
    # posts given by their colour alone: the usual size and spacing
    plain = rp.fence_picture(FENCE | {"posts": {"color": "#ff0000"}}, 96)
    assert pixels(plain, "#ff0000", tolerance=90) > 10
    # a low fence leaves the top of the picture empty, a tall one is cut to what fits
    low = np.array(rp.fence_picture(FENCE | {"height": {"default": 0.5}}, 96))
    tall = np.array(rp.fence_picture(FENCE | {"height": {"default": 6}}, 96))

    def first(picture) -> int:
        """Topmost row of the picture that is not empty."""
        return int(np.nonzero(picture[:, :, 3].max(axis=1) > 0)[0].min())

    assert first(low) > first(tall) >= 0
    # a thick fence throws a wider shadow on the ground
    thick = np.array(rp.fence_picture(FENCE | {"thickness": 0.3}, 96))[:, :, 3]
    assert (thick > 0).sum() > (np.array(image)[:, :, 3] > 0).sum()
