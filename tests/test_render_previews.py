"""Pictures drawn from the descriptors."""

from __future__ import annotations

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

    monkeypatch.setattr(rp, "PICTURES", {"tree": draw, "object": draw, "pond_fish": draw})
    return calls


def test_only_missing_pictures_are_drawn(root: Path, quick):
    (root / "objects/items/stool/image.png").write_bytes(b"a photo")
    (root / "trees/items/empty").mkdir()
    (root / "pond_fish/items/goldfish/image.webp").write_bytes(b"drawn")
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
    ]


def test_command(root: Path, quick, capsys):
    args = ["--root", str(root)]
    assert rp.main(args) == 0
    assert (
        "drawn: trees/oak\ndrawn: objects/stool\ndrawn: pond_fish/goldfish\n3 entries drawn"
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
    }
    monkeypatch.setattr(rp, "PICTURES", small)
    dump(root / "trees/items/oak/tree.json", TREE)
    assert rp.write_pictures(root) == ["trees/oak", "objects/stool", "pond_fish/goldfish"]
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
