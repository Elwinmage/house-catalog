"""Draw the pictures of the entries from their descriptors.

    python scripts/render_previews.py [--root .] [--force] [id ...]

Writes `image.webp` (512 px) and `thumb.webp` (128 px) next to each descriptor
that has no picture yet (`--force`: every entry, or the given ids). A tree gets
its four seasons on the picture (spring, summer / autumn, winter) and its summer
on the thumbnail; an object is seen from three quarters; a fish is seen from
above, one fish per variety on the picture and the first variety on the
thumbnail.

The pictures are drawn exactly from what the descriptor says (see
doc/format.md), with a small software renderer (flat shading, depth buffer):
this script is also the reference reading of the format. Needs `numpy` and
`pillow`.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

from catalog import SECTIONS, collect, entry_id, read_json
from house_catalog_rules import DESCRIPTORS, SEASONS, object_bounds, rotation

IMAGE_SIZE = 512
THUMB_SIZE = 128
#: Pixels drawn per pixel kept (smooth edges)
SUPERSAMPLE = 3
#: Where the light comes from (x, y, z), and how dark a face turned away gets:
#: solids, and the small dots (flowers, fruits, fallen leaves) that must stay bright
LIGHT = (-0.45, 0.8, 0.4)
SHADE = 0.58
DOT_SHADE = 0.86
#: Camera: turned about the vertical axis, then tilted down, in degrees
TREE_VIEW = (30.0, 14.0)
OBJECT_VIEW = (35.0, 28.0)

Color = tuple[float, float, float]


def rgb(color: str) -> Color:
    """`#rrggbb` as three numbers between 0 and 255."""
    return (
        float(int(color[1:3], 16)),
        float(int(color[3:5], 16)),
        float(int(color[5:7], 16)),
    )


# -- meshes ---------------------------------------------------------------------


@dataclass
class Mesh:
    """Flat coloured triangles."""

    triangles: list[np.ndarray] = field(default_factory=list)  # (n, 3, 3) each
    normals: list[np.ndarray] = field(default_factory=list)  # (n, 3) each, outward
    colors: list[np.ndarray] = field(default_factory=list)  # (n, 3) each
    shades: list[np.ndarray] = field(default_factory=list)  # (n,) each

    def add(self, triangles: np.ndarray, color: Color, shade: float = SHADE) -> None:
        """Add a convex solid: its normals are turned away from its centre.

        `shade` is how dark its faces turned away from the light get (1: no shading).
        """
        centre = triangles.reshape(-1, 3).mean(axis=0)
        normal = np.cross(
            triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
        )
        length = np.linalg.norm(normal, axis=1, keepdims=True)
        normal = normal / np.where(length == 0, 1, length)
        outward = triangles.mean(axis=1) - centre
        normal[np.sum(normal * outward, axis=1) < 0] *= -1
        self.triangles.append(triangles)
        self.normals.append(normal)
        self.colors.append(np.tile(np.array(color), (len(triangles), 1)))
        self.shades.append(np.full(len(triangles), shade))

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        return (
            np.concatenate(self.triangles),
            np.concatenate(self.normals),
            np.concatenate(self.colors),
            np.concatenate(self.shades),
        )


def _fan(ring: np.ndarray, point: np.ndarray) -> np.ndarray:
    """Triangles joining each edge of a closed ring to a point."""
    return np.stack(
        [ring, np.roll(ring, -1, axis=0), np.broadcast_to(point, ring.shape)], axis=1
    )


def frustum(
    start: Sequence[float],
    end: Sequence[float],
    radius_start: float,
    radius_end: float,
    sides: int = 8,
) -> np.ndarray:
    """A cone trunk between two points (a cylinder, or a cone when a radius is 0)."""
    p0, p1 = np.array(start, dtype=float), np.array(end, dtype=float)
    axis = (p1 - p0) / np.linalg.norm(p1 - p0)
    helper = np.array([1.0, 0, 0]) if abs(axis[0]) < 0.9 else np.array([0, 0, 1.0])
    u = np.cross(axis, helper)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    angles = np.arange(sides) * (2 * math.pi / sides)
    circle = np.outer(np.cos(angles), u) + np.outer(np.sin(angles), v)
    low, high = p0 + circle * radius_start, p1 + circle * radius_end
    low_next, high_next = np.roll(low, -1, axis=0), np.roll(high, -1, axis=0)
    return np.concatenate(
        [
            np.stack([low, low_next, high], axis=1),
            np.stack([low_next, high_next, high], axis=1),
            _fan(low, p0),
            _fan(high, p1),
        ]
    )


@cache
def _icosphere(level: int) -> tuple[np.ndarray, np.ndarray]:
    """Vertices (on the unit sphere) and faces of a subdivided icosahedron."""
    t = (1 + math.sqrt(5)) / 2
    vertices = [
        (-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t),
        (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1),
    ]  # fmt: skip
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9),
        (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2),
        (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
        (8, 6, 7), (9, 8, 1),
    ]  # fmt: skip
    points = [np.array(v, dtype=float) / math.sqrt(1 + t * t) for v in vertices]
    for _ in range(level):
        middles: dict[tuple[int, int], int] = {}

        def middle(a: int, b: int, middles=middles) -> int:
            key = (min(a, b), max(a, b))
            if key not in middles:
                point = points[a] + points[b]
                points.append(point / np.linalg.norm(point))
                middles[key] = len(points) - 1
            return middles[key]

        split = []
        for a, b, c in faces:
            ab, bc, ca = middle(a, b), middle(b, c), middle(c, a)
            split += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = split
    return np.array(points), np.array(faces)


def blob(
    centre: Sequence[float],
    radii: Sequence[float],
    rng: random.Random | None = None,
    level: int = 1,
    yaw: float = 0.0,
) -> np.ndarray:
    """An ellipsoid of triangles; with `rng`, bumpy like a clump of leaves.

    `yaw` turns it about the vertical axis (the fronds of a palm), in radians.
    """
    vertices, faces = _icosphere(level)
    if rng is not None:
        bumps = np.array([1 + (rng.random() - 0.5) * 0.3 for _ in vertices])
        vertices = vertices * bumps[:, None]
    vertices = vertices * np.array(radii)
    if yaw:
        cos, sin = math.cos(yaw), math.sin(yaw)
        vertices = vertices @ np.array([[cos, 0, -sin], [0, 1, 0], [sin, 0, cos]])
    return (vertices + np.array(centre))[faces]


_UNIT_BOX = np.array(
    [
        [(x, y, z) for x, y, z in face]
        for face in [
            [(-1, -1, -1), (1, -1, -1), (1, 1, -1)], [(-1, -1, -1), (1, 1, -1), (-1, 1, -1)],
            [(-1, -1, 1), (1, -1, 1), (1, 1, 1)], [(-1, -1, 1), (1, 1, 1), (-1, 1, 1)],
            [(-1, -1, -1), (-1, -1, 1), (-1, 1, 1)], [(-1, -1, -1), (-1, 1, 1), (-1, 1, -1)],
            [(1, -1, -1), (1, -1, 1), (1, 1, 1)], [(1, -1, -1), (1, 1, 1), (1, 1, -1)],
            [(-1, -1, -1), (1, -1, -1), (1, -1, 1)], [(-1, -1, -1), (1, -1, 1), (-1, -1, 1)],
            [(-1, 1, -1), (1, 1, -1), (1, 1, 1)], [(-1, 1, -1), (1, 1, 1), (-1, 1, 1)],
        ]
    ],
    dtype=float,
)  # fmt: skip


def part_triangles(part: dict[str, Any]) -> np.ndarray:
    """The triangles of a part of an object, where the descriptor puts it."""
    shape = part["shape"]
    if shape == "box":
        unit = _UNIT_BOX
    elif shape == "sphere":
        unit = blob((0, 0, 0), (1, 1, 1), level=2)
    else:
        unit = frustum((0, -1, 0), (0, 1, 0), 1, 1 if shape == "cylinder" else 0, 16)
    half = np.array([part["width"], part["height"], part["depth"]]) / 2
    matrix = np.array(
        rotation(part.get("yaw", 0), part.get("pitch", 0), part.get("roll", 0))
    )
    centre = np.array(
        [part.get("x", 0), part.get("elevation", 0) + half[1], part.get("z", 0)]
    )
    return (unit * half) @ matrix.T + centre


def object_mesh(data: dict[str, Any]) -> Mesh:
    """An object: its parts, one colour each."""
    mesh = Mesh()
    for part in data["parts"]:
        mesh.add(part_triangles(part), rgb(part["color"]))
    return mesh


#: Clumps of a round crown, in a box from -1 to 1: centre (x, y, z) and radius
_CLUMPS = (
    (0.0, -0.15, 0.0, 0.8),
    (0.5, 0.1, 0.25, 0.5),
    (-0.5, 0.05, -0.3, 0.5),
    (0.1, 0.5, -0.35, 0.5),
    (-0.2, 0.45, 0.45, 0.5),
    (0.05, -0.45, 0.5, 0.45),
    (-0.1, -0.4, -0.5, 0.45),
)
#: Tiers of a conical crown
_TIERS = 4


#: Curtains of branches hanging from a weeping crown
_CURTAINS = 10

#: Fronds of a palm, around the trunk
_FRONDS = 9


def _palm(
    top: float, radius: float, bottom: float, thin: float
) -> list[tuple[str, tuple, tuple, float]]:
    """A tuft at the top of the trunk and fronds that leave it, rise a little and
    droop at their tip: three flat blobs along each frond, turned about the
    vertical axis (the fourth value of a solid, in radians).
    """
    reach = min(max(0.5, top - bottom), radius * 0.8)
    solids: list[tuple[str, tuple, tuple, float]] = [
        (
            "blob",
            (0.0, top - 0.25 * reach, 0.0),
            (0.28 * radius * thin, 0.3 * reach * thin, 0.28 * radius * thin),
            0.0,
        )
    ]
    for index in range(_FRONDS):
        angle = index / _FRONDS * 2 * math.pi + (index % 2) * 0.18
        lift = 0.05 if index % 2 else 0.2  # two ranks: the upper fronds rise
        for along, drop, length, thick, width in (
            (0.28, 0.1, 0.32, 0.08, 0.15),
            (0.62, 0.5, 0.34, 0.07, 0.14),
            (0.98, 1.2, 0.26, 0.06, 0.10),
        ):
            solids.append(
                (
                    "blob",
                    (
                        along * radius * math.cos(angle),
                        top - (drop - lift) * reach,
                        along * radius * math.sin(angle),
                    ),
                    (
                        length * radius * thin,
                        thick * reach * thin,
                        width * radius * thin,
                    ),
                    -angle,
                )
            )
    return solids


def _weeping(
    top: float, radius: float, bottom: float, thin: float
) -> list[tuple[str, tuple, tuple]]:
    """A low dome and curtains of branches hanging from its rim down to the trunk.

    The crown fills the same box as the others: the dome is in its upper part,
    the curtains hang from the rim (0.85 of the radius), some longer than others.
    """
    span = top - bottom
    solids: list[tuple[str, tuple, tuple]] = [
        (
            "blob",
            (0.0, bottom + 0.78 * span, 0.0),
            (0.7 * radius * thin, 0.22 * span * thin, 0.7 * radius * thin),
        )
    ]
    for index in range(4):
        angle = math.radians(index * 90 + 45)
        solids.append(
            (
                "blob",
                (
                    0.55 * radius * math.cos(angle),
                    bottom + 0.68 * span,
                    0.55 * radius * math.sin(angle),
                ),
                (0.45 * radius * thin, 0.18 * span * thin, 0.45 * radius * thin),
            )
        )
    for index in range(_CURTAINS):
        angle = math.radians(index * 360 / _CURTAINS)
        half = 0.33 * span * (0.9 + 0.1 * (index % 3 - 1))
        solids.append(
            (
                "blob",
                (
                    0.85 * radius * math.cos(angle),
                    bottom + 0.7 * span - half,
                    0.85 * radius * math.sin(angle),
                ),
                (0.2 * radius * thin, half * thin, 0.2 * radius * thin),
            )
        )
    return solids


def _crown(data: dict[str, Any], density: float) -> list[tuple[Any, ...]]:
    """The solids of the foliage: (kind, centre or base, sizes), once thinned out.

    The crown fills the box between the top of the trunk and the top of the tree,
    `crown_radius` wide. A thinner foliage keeps that spread: each clump of leaves
    shrinks where it is, and the branches show between them.
    """
    top, radius = data["height"]["default"], data["crown_radius"]
    bottom = data["trunk"]["height"]
    middle, half = (bottom + top) / 2, (top - bottom) / 2
    thin = density**0.6
    solids: list[tuple] = []
    if data["shape"] == "weeping":
        return _weeping(top, radius, bottom, thin)
    if data["shape"] == "palm":
        return _palm(top, radius, bottom, thin)
    if data["shape"] == "round":
        reach = max(abs(c[axis]) + c[3] for c in _CLUMPS for axis in range(3))
        for x, y, z, size in _CLUMPS:
            size *= thin / reach
            solids.append(
                (
                    "blob",
                    (x * radius / reach, middle + y * half / reach, z * radius / reach),
                    (size * radius, size * half, size * radius),
                )
            )
        return solids
    step = 2 * half / _TIERS
    for tier in range(_TIERS):
        base = bottom + tier * step * 5 / 6
        solids.append(
            (
                "cone",
                (0.0, base, 0.0),
                (radius * (1 - 0.2 * tier) * thin, step * 1.5, 0.0),
            )
        )
    return solids


def _on_crown(
    solids: list[tuple[Any, ...]], rng: random.Random
) -> tuple[float, float, float]:
    """A point on the surface of the foliage, taken at random."""
    kind, centre, sizes, *turn = rng.choice(solids)
    angle = rng.random() * 2 * math.pi
    if kind == "blob":
        y = rng.uniform(-0.6, 1)
        ring = math.sqrt(1 - y * y)
        dx, dz = sizes[0] * ring * math.cos(angle), sizes[2] * ring * math.sin(angle)
        yaw = turn[0] if turn else 0.0
        return (
            centre[0] + dx * math.cos(yaw) + dz * math.sin(yaw),
            centre[1] + sizes[1] * y,
            centre[2] - dx * math.sin(yaw) + dz * math.cos(yaw),
        )
    up = rng.uniform(0.05, 0.9)
    return (
        centre[0] + sizes[0] * (1 - up) * math.cos(angle),
        centre[1] + sizes[1] * up,
        centre[2] + sizes[0] * (1 - up) * math.sin(angle),
    )


def tree_mesh(data: dict[str, Any], season: str) -> Mesh:
    """A tree of the default height, as a season renders it."""
    look = data["seasons"].get(season, data["seasons"]["summer"])
    density = look.get("density", 1)
    top, radius = data["height"]["default"], data["crown_radius"]
    trunk = data["trunk"]
    bark = rgb(trunk["color"])
    rng = random.Random(f"{data.get('latin', '')}:{season}")
    mesh = Mesh()

    # The trunk goes on into the crown, where the branches leave it
    fork = trunk["height"] + (top - trunk["height"]) * 0.3
    if data["shape"] != "palm":
        mesh.add(
            frustum((0, 0, 0), (0, fork, 0), trunk["radius"], trunk["radius"] * 0.6),
            bark,
        )
    if data["shape"] in ("round", "weeping"):
        for index in range(5):
            angle = index * 2.4 + 0.5
            reach = radius * (0.5 + 0.12 * (index % 3))
            end = (
                reach * math.cos(angle),
                fork + (top - fork) * (0.35 + 0.1 * (index % 2)),
                reach * math.sin(angle),
            )
            start = (0, fork - (fork - trunk["height"]) * 0.5 * (index % 2), 0)
            mesh.add(
                frustum(start, end, trunk["radius"] * 0.4, trunk["radius"] * 0.1, 5),
                bark,
            )
    elif data["shape"] == "palm":
        # one slender trunk, a little thicker at its foot, up to the tuft of fronds
        mesh.add(
            frustum(
                (0, 0, 0),
                (0, top * 0.97, 0),
                trunk["radius"],
                trunk["radius"] * 0.62,
                8,
            ),
            bark,
        )
        mesh.add(
            frustum(
                (0, 0, 0), (0, top * 0.06, 0), trunk["radius"] * 1.5, trunk["radius"], 8
            ),
            bark,
        )
    else:
        mesh.add(
            frustum((0, fork, 0), (0, top * 0.97, 0), trunk["radius"] * 0.6, 0.01, 6),
            bark,
        )

    solids = _crown(data, density) if density > 0.03 else []
    leaf = rgb(look["foliage"])
    for index, (kind, centre, sizes, *turn) in enumerate(solids):
        tone = 1 - 0.05 * (index % 3)
        color = (leaf[0] * tone, leaf[1] * tone, leaf[2] * tone)
        if kind == "blob":
            mesh.add(blob(centre, sizes, rng, yaw=turn[0] if turn else 0.0), color)
        else:
            tip = (centre[0], centre[1] + sizes[1], centre[2])
            mesh.add(frustum(centre, tip, sizes[0], 0, 10), color)

    # Flowers and fruits sit on the foliage (on the bare branches of a round crown)
    bare = (
        _crown(data, 0.75)
        if not solids and data["shape"] in ("round", "weeping")
        else solids
    )
    for key, count, size in (("flowers", 170, 0.075), ("fruits", 110, 0.05)):
        if key in look and bare:
            dot = radius * size
            for _ in range(round(look[key]["amount"] * count)):
                point = _on_crown(bare, rng)
                mesh.add(
                    blob(point, (dot, dot, dot), level=0),
                    rgb(look[key]["color"]),
                    DOT_SHADE,
                )
    if "fallen" in look:
        dot = radius * 0.06
        for _ in range(round(look["fallen"]["amount"] * 150)):
            angle, reach = (
                rng.random() * 2 * math.pi,
                radius * 1.1 * math.sqrt(rng.random()),
            )
            point = (reach * math.cos(angle), dot * 0.15, reach * math.sin(angle))
            mesh.add(
                blob(point, (dot, dot * 0.15, dot), level=0),
                rgb(look["fallen"]["color"]),
                DOT_SHADE,
            )
    return mesh


# -- drawing --------------------------------------------------------------------


def _camera(view: tuple[float, float]) -> np.ndarray:
    """Matrix from the scene to the screen: x right, y up, z toward the viewer."""
    turn, tilt = np.array(rotation(-view[0], 0, 0)), np.array(rotation(0, view[1], 0))
    return tilt @ turn


def render(
    mesh: Mesh,
    size: int,
    view: tuple[float, float],
    box: tuple[Sequence[float], Sequence[float]],
    supersample: int = SUPERSAMPLE,
) -> Image.Image:
    """Draw a mesh on a transparent square, framed on the `box` (low, high corners)."""
    triangles, normals, colors, shades = mesh.arrays()
    camera = _camera(view)
    corners = np.array(
        [
            [box[i][0], box[j][1], box[k][2]]
            for i in (0, 1)
            for j in (0, 1)
            for k in (0, 1)
        ]
    )
    framed = corners @ camera.T
    low, high = framed.min(axis=0), framed.max(axis=0)
    pixels = size * supersample
    scale = pixels * 0.9 / max(high[0] - low[0], high[1] - low[1])
    centre = (low + high) / 2

    light = np.array(LIGHT) / np.linalg.norm(LIGHT)
    shade = shades + (1 - shades) * np.clip(normals @ light, 0, None)
    facing = (normals @ camera.T)[:, 2] > 0
    screen = triangles @ camera.T
    sx = (screen[:, :, 0] - centre[0]) * scale + pixels / 2
    sy = pixels / 2 - (screen[:, :, 1] - centre[1]) * scale
    depth = screen[:, :, 2]

    canvas = np.zeros((pixels, pixels, 4), dtype=np.uint8)
    nearest = np.full((pixels, pixels), -np.inf)
    for index in np.flatnonzero(facing):
        xs, ys, zs = sx[index], sy[index], depth[index]
        x0, x1 = max(int(xs.min()), 0), min(int(xs.max()) + 1, pixels - 1)
        y0, y1 = max(int(ys.min()), 0), min(int(ys.max()) + 1, pixels - 1)
        area = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
        if x0 > x1 or y0 > y1 or area == 0:
            continue
        px, py = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((xs[1] - px) * (ys[2] - py) - (xs[2] - px) * (ys[1] - py)) / area
        w1 = ((xs[2] - px) * (ys[0] - py) - (xs[0] - px) * (ys[2] - py)) / area
        w2 = 1 - w0 - w1
        z = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
        window = nearest[y0 : y1 + 1, x0 : x1 + 1]
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0) & (z > window)
        window[inside] = z[inside]
        color = np.clip(colors[index] * shade[index], 0, 255)
        canvas[y0 : y1 + 1, x0 : x1 + 1][inside] = (*color, 255)
    return Image.fromarray(canvas, "RGBA").resize(
        (size, size), Image.Resampling.LANCZOS
    )


def _on_ground(picture: Image.Image, strength: int = 46) -> Image.Image:
    """The picture over a soft shadow, where its lowest pixels touch the ground."""
    rows = np.flatnonzero(np.array(picture)[:, :, 3].max(axis=1) > 40)
    columns = np.flatnonzero(np.array(picture)[:, :, 3].max(axis=0) > 40)
    shadow = Image.new("RGBA", picture.size, (0, 0, 0, 0))
    if len(rows):
        width = (columns[-1] - columns[0]) * 0.42
        middle, bottom = (columns[0] + columns[-1]) / 2, rows[-1] - width * 0.16
        ImageDraw.Draw(shadow).ellipse(
            (
                middle - width,
                bottom - width * 0.3,
                middle + width,
                bottom + width * 0.3,
            ),
            fill=(30, 40, 30, strength),
        )
    return Image.alpha_composite(shadow, picture)


def tree_box(data: dict[str, Any]) -> tuple[tuple, tuple]:
    """The box every season of a tree is framed on: the pictures compare."""
    reach, top = data["crown_radius"] * 1.12, data["height"]["default"]
    return (-reach, 0, -reach), (reach, top, reach)


def tree_pictures(
    data: dict[str, Any], size: int = IMAGE_SIZE, thumb: int = THUMB_SIZE
) -> tuple[Image.Image, Image.Image]:
    """The four seasons side by side, and the summer alone for the lists."""
    box = tree_box(data)
    tile = size // 2
    sheet = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for index, season in enumerate(SEASONS):
        picture = _on_ground(render(tree_mesh(data, season), tile, TREE_VIEW, box))
        sheet.paste(picture, ((index % 2) * tile, (index // 2) * tile))
    summer = _on_ground(render(tree_mesh(data, "summer"), thumb, TREE_VIEW, box))
    return sheet, summer


def object_pictures(
    data: dict[str, Any], size: int = IMAGE_SIZE, thumb: int = THUMB_SIZE
) -> tuple[Image.Image, Image.Image]:
    """An object seen from three quarters, in two sizes."""
    mesh = object_mesh(data)
    box = object_bounds(data["parts"])
    return (
        _on_ground(render(mesh, size, OBJECT_VIEW, box)),
        _on_ground(render(mesh, thumb, OBJECT_VIEW, box)),
    )


# -- fish, seen from above ---------------------------------------------------------

#: Patches of each size drawn for a layer (their total area follows `amount`)
PATCH_COUNT = {"small": 12, "medium": 5, "large": 2}
#: Part of the body, from the root of the tail (0) to the snout (1), patches go to
PATCH_SPAN = {"anywhere": (0.06, 0.94), "back": (0.12, 0.76), "head": (0.8, 0.9)}


def body_halfwidth(u: float) -> float:
    """Half width of the body seen from above, as a share of its widest point.

    `u` goes from the root of the tail (0) to the snout (1): narrow at the tail,
    widest a little ahead of the middle, rounded at the head.
    """
    u = min(max(u, 0.0), 1.0)
    if u < 0.62:
        return 0.28 + 0.72 * math.sin(math.pi / 2 * u / 0.62)
    return math.cos(math.pi / 2 * (u - 0.62) / 0.38) ** 0.6


def fish_patches(
    variety: dict[str, Any], body: dict[str, Any], seed: int
) -> list[tuple[str, float, float, float, float]]:
    """The patches of one fish: (colour, x, y, rx, ry), the fish being 1 long.

    x goes from the end of the tail (-0.5) to the snout (0.5), y across the body.
    Two fish of a variety get two seeds, so two robes of their own.
    """
    rng = random.Random(seed)
    tail = body.get("tail", 0.2)
    start, span = -0.5 + tail, 1 - tail
    width = body["width"]
    area = width * span * 0.7  # rough area of the body seen from above
    out = []
    for patch in variety.get("patches", []):
        where = patch.get("where", "anywhere")
        count = 1 if where == "head" else PATCH_COUNT[patch.get("size", "medium")]
        each = patch["amount"] * area / count
        low, high = PATCH_SPAN[where]
        for _ in range(count):
            u = rng.uniform(low, high)
            half = width / 2 * body_halfwidth(u)
            y = 0.0 if where == "head" else rng.uniform(-0.55, 0.55) * half
            stretch = 1.0 if where == "head" else 1.5
            rx = math.sqrt(each / math.pi * stretch)
            out.append((patch["color"], start + u * span, y, rx, rx / stretch))
    return out


def fish_picture(
    data: dict[str, Any], variety: dict[str, Any], size: int, seed: int = 1
) -> Image.Image:
    """One fish of a variety seen from above, head to the right, on a clear ground."""
    big = size * SUPERSAMPLE
    body = data["body"]
    tail = body.get("tail", 0.2)
    width = body["width"]
    long_fins = body.get("fins", "short") == "long"
    scale = big * 0.86

    def at(x: float, y: float) -> tuple[float, float]:
        return (big / 2 + x * scale, big / 2 + y * scale)

    start, span = -0.5 + tail, 1 - tail
    steps = 48
    side = [
        (start + span * k / steps, width / 2 * body_halfwidth(k / steps))
        for k in range(steps + 1)
    ]
    outline = [at(x, -y) for x, y in side] + [at(x, y) for x, y in reversed(side)]
    fins_color = rgb(variety.get("fins", variety["base"]))
    fin = (*map(int, fins_color), 200)
    picture = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(picture)
    # tail fin: a fan behind the root of the tail, notched in the middle
    root = width / 2 * body_halfwidth(0)
    spread = width * (0.75 if long_fins else 0.55)
    draw.polygon(
        [
            at(start + 0.01, -root),
            at(-0.5, -spread),
            at(-0.5 + tail * 0.4, 0),
            at(-0.5, spread),
            at(start + 0.01, root),
        ],
        fill=fin,
    )
    # pectoral fins, on both sides a little behind the head
    reach = width * (0.6 if long_fins else 0.42)
    for sign in (-1, 1):
        x0 = start + span * 0.66
        y0 = sign * width / 2 * body_halfwidth(0.66) * 0.8
        draw.polygon(
            [
                at(x0, y0),
                at(x0 - reach * 0.9, y0 + sign * reach),
                at(x0 - reach * 0.2, y0),
            ],
            fill=fin,
        )
    # body: flanks in the colour of the belly, the back over them
    draw.polygon(
        outline, fill=(*map(int, rgb(variety.get("belly", variety["base"]))), 255)
    )
    back = [at(x, -y * 0.78) for x, y in side] + [
        at(x, y * 0.78) for x, y in reversed(side)
    ]
    draw.polygon(back, fill=(*map(int, rgb(variety["base"])), 255))
    # patches, kept inside the body
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).polygon(back, fill=255)
    layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    paint = ImageDraw.Draw(layer)
    for color, x, y, rx, ry in fish_patches(variety, body, seed):
        x0, y0 = at(x - rx, y - ry)
        x1, y1 = at(x + rx, y + ry)
        paint.ellipse((x0, y0, x1, y1), fill=(*map(int, rgb(color)), 255))
    layer.putalpha(
        Image.fromarray(np.minimum(np.array(layer)[:, :, 3], np.array(mask)))
    )
    picture = Image.alpha_composite(picture, layer)
    if variety.get("metallic"):
        # shiny scales: a light streak along the back
        shine = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        streak = [at(x, -y * 0.25) for x, y in side] + [
            at(x, y * 0.25) for x, y in reversed(side)
        ]
        ImageDraw.Draw(shine).polygon(streak, fill=(255, 255, 255, 90))
        picture = Image.alpha_composite(picture, shine)
    # eyes
    for sign in (-1, 1):
        ex, ey = start + span * 0.9, sign * width / 2 * body_halfwidth(0.9) * 0.7
        cx, cy = at(ex, ey)
        r = scale * 0.012
        draw = ImageDraw.Draw(picture)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(20, 20, 20, 255))
    return picture.resize((size, size), Image.Resampling.LANCZOS)


def fish_pictures(
    data: dict[str, Any], size: int = IMAGE_SIZE, thumb: int = THUMB_SIZE
) -> tuple[Image.Image, Image.Image]:
    """Every variety on the picture (up to 16, in a grid), the first one on the thumbnail."""
    varieties = data["varieties"][:16]
    columns = math.ceil(math.sqrt(len(varieties)))
    tile = size // columns
    sheet = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for index, variety in enumerate(varieties):
        picture = fish_picture(data, variety, tile, seed=index + 1)
        sheet.paste(picture, ((index % columns) * tile, (index // columns) * tile))
    return sheet, fish_picture(data, varieties[0], thumb)


PICTURES = {
    "tree": tree_pictures,
    "object": object_pictures,
    "pond_fish": fish_pictures,
}


def write_pictures(
    root: Path, force: bool = False, only: Iterable[str] = ()
) -> list[str]:
    """Draw the entries that have no picture (all of them, or `only`, when forced)."""
    wanted = set(only)
    written = []
    for section in SECTIONS:
        for entry in collect(root, section):
            descriptor = entry.files.get(DESCRIPTORS[entry.kind])
            if descriptor is None or (wanted and entry_id(entry) not in wanted):
                continue
            drawn = any(name.startswith(("image.", "thumb.")) for name in entry.files)
            if drawn and not (force or wanted):
                continue
            image, thumb = PICTURES[entry.kind](read_json(descriptor))
            folder = descriptor.parent
            image.save(folder / "image.webp", "WEBP", quality=88, method=6)
            thumb.save(folder / "thumb.webp", "WEBP", quality=88, method=6)
            written.append(f"{section}/{entry_id(entry)}")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="draw again the entries that have a picture",
    )
    parser.add_argument("ids", nargs="*", help="only these entries (drawn again)")
    args = parser.parse_args(argv)
    written = write_pictures(args.root, args.force, args.ids)
    for name in written:
        print(f"drawn: {name}")
    print(f"{len(written)} entr{'y' if len(written) == 1 else 'ies'} drawn")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
