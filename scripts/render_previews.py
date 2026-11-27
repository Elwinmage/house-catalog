"""Draw the pictures of the entries from their descriptors.

    python scripts/render_previews.py [--root .] [--force] [id ...]

Writes `image.webp` (512 px) and `thumb.webp` (128 px) next to each descriptor
that has no picture yet (`--force`: every entry, or the given ids). A tree gets
its four seasons on the picture (spring, summer / autumn, winter) and its summer
on the thumbnail; an object is seen from three quarters; a fish is seen from
above, one fish per variety on the picture and the first variety on the
thumbnail; a path and a terrace are seen from above, a wall and a fence from
the front.

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
from PIL import Image, ImageDraw, ImageFilter

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

#: Tiers of a columnar crown: [height of the centre, width, height of the blob], as shares of the span the
#: foliage covers. Barely narrower at the foot than at the middle, rounded off at the top (yew, cypress).
_COLUMN_TIERS = (
    (0.13, 0.86, 0.13),
    (0.28, 1.0, 0.17),
    (0.46, 1.0, 0.17),
    (0.63, 0.95, 0.16),
    (0.77, 0.82, 0.14),
    (0.88, 0.6, 0.11),
    (0.94, 0.3, 0.06),
)


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
    if data["shape"] == "columnar":
        # the foliage of a column comes down almost to the ground, the trunk hardly showing
        foot = min(bottom * 0.4, top * 0.06)
        span = top - foot
        for height, width, size in _COLUMN_TIERS:
            solids.append(
                (
                    "blob",
                    (0.0, foot + span * height, 0.0),
                    (radius * width * thin, span * size * thin, radius * width * thin),
                )
            )
        return solids
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


# -- paths, seen from above --------------------------------------------------------

#: Share of the picture a path covers across it
PATH_STRIP = 0.78
#: Width of a path on the picture when the entry offers none, in metres
PATH_WIDTH = 1.5
#: How strongly `grain` lightens and darkens the pixels of a surface
GRAIN_SPREAD = 0.17
#: Points drawn on the outline of a round, an oval or a stone element
ROUND_STEPS = 36
#: Corner radius of a slab, as a share of its smaller side
SLAB_CORNER = 0.18
#: Elements of a module path shown along the picture
MODULE_RUN = 3.3
#: Shadow of a module element: how far it falls, as a share of the thickness
MODULE_DROP = 0.5
# Irregular stones: the share of them left out at `vary` 1 (their neighbours grow
# into larger blocks), how far a corner is pulled towards the middle of its stone
# at `vary` 1, how far along its sides a corner is rounded and in how many steps,
# and the shortest side a stone keeps (as a share of its size: shorter ones would
# show as a notch once their two ends are pulled apart).
STONE_DROP = 0.3
STONE_PULL = 0.14
STONE_CORNER = 0.14
STONE_CORNER_STEPS = 2
STONE_SHORT = 0.35
# A stone that bulges, at `relief` 1: how much darker its rim is, how wide that
# rim is (as a share of the stone) and how far towards the upper left its lit face
# sits (as a share of the room there is around its middle).
RELIEF_SHADE = 0.4
RELIEF_RIM = 0.24
RELIEF_SHIFT = 0.6


def _shade(color: Color, factor: float) -> tuple[int, int, int, int]:
    """A colour lightened (factor above 1) or darkened, as an opaque RGBA."""
    r, g, b = (min(255.0, max(0.0, c * factor)) for c in color)
    return int(r), int(g), int(b), 255


def _speckle(
    layer: Image.Image, speckles: Sequence[dict[str, Any]], px_per_m: float, rng
) -> None:
    """Scatter the grains of a surface over a layer, in the order given."""
    draw = ImageDraw.Draw(layer)
    width, height = layer.size
    for grain in speckles:
        stretch = grain.get("stretch", 1)
        radius = max(0.6, grain["size"] * px_per_m / 2)
        count = round(grain["amount"] * width * height / (math.pi * radius**2))
        fill = _shade(rgb(grain["color"]), 1.0)
        for _ in range(count):
            x, y = rng.uniform(0, width), rng.uniform(0, height)
            r = radius * rng.uniform(0.6, 1.4) / math.sqrt(stretch)
            if stretch == 1:
                draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)
                continue
            # a chip or a shard: an ellipse laid down any way round
            angle = rng.uniform(0, math.pi)
            cos, sin = math.cos(angle), math.sin(angle)
            draw.polygon(
                [
                    (
                        x + r * stretch * math.cos(t) * cos - r * math.sin(t) * sin,
                        y + r * stretch * math.cos(t) * sin + r * math.sin(t) * cos,
                    )
                    for t in (math.tau * k / 10 for k in range(10))
                ],
                fill=fill,
            )


Point = tuple[float, float]


def stone_sites(cols: int, rows: int, vary: float, rng) -> list[Point]:
    """Middles of the stones of an irregular surface, as shares of its width and height.

    One to a square of a grid `cols` by `rows`, every other row set off by half a
    square so that no joint runs straight up the wall, each moved about by `vary`.
    Some are left out, the more so as `vary` grows: their neighbours take their
    place and make larger blocks. The middles wrap around, so the surface joins up
    with itself on all four sides.
    """
    sites = []
    for row in range(rows):
        for col in range(cols):
            x = (col + 0.5 + (row % 2) * 0.5 + rng.uniform(-0.5, 0.5) * vary) / cols
            y = (row + 0.5 + rng.uniform(-0.5, 0.5) * vary) / rows
            if rng.random() < vary * STONE_DROP:
                continue
            sites.append((x % 1, y % 1))
    return sites or [(0.5, 0.5)]


def clip_polygon(
    polygon: list[Point], nx: float, ny: float, limit: float
) -> list[Point]:
    """The part of a convex polygon on the near side of a line: x * nx + y * ny <= limit."""
    out = []
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        da = a[0] * nx + a[1] * ny - limit
        db = b[0] * nx + b[1] * ny - limit
        if da <= 0:
            out.append(a)
        if da * db < 0:
            t = da / (da - db)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def stone_cells(
    sites: Sequence[Point], width: float, height: float, gap: float
) -> list[tuple[Point, list[Point]]]:
    """The stone around each middle: (middle, corners), in pixels.

    A stone is all that lies nearer to its middle than to any other, less half a
    joint on every side: the stones fit into one another like those of a wall,
    whatever their shapes. The surface repeats on all sides, so the stones of an
    edge are cut by those of the opposite one. A joint wider than a stone leaves
    no stone at all.
    """
    points = [(x * width, y * height) for x, y in sites]
    around = [
        (x + dx * width, y + dy * height)
        for x, y in points
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
    ]
    cells = []
    for px, py in points:
        reach = width + height
        polygon = [
            (px - reach, py - reach),
            (px + reach, py - reach),
            (px + reach, py + reach),
            (px - reach, py + reach),
        ]
        others = sorted((math.hypot(qx - px, qy - py), qx, qy) for qx, qy in around)
        for dist, qx, qy in others:
            if dist < 1e-9:
                continue  # the middle itself
            if (dist - gap) / 2 > max(math.hypot(x - px, y - py) for x, y in polygon):
                break  # too far away to cut anything off, and so are the next ones
            nx, ny = (qx - px) / dist, (qy - py) / dist
            polygon = clip_polygon(
                polygon, nx, ny, px * nx + py * ny + (dist - gap) / 2
            )
            if len(polygon) < 3:
                break
        if len(polygon) >= 3:
            cells.append(((px, py), polygon))
    return cells


def stone_outline(
    corners: Sequence[Point], middle: Point, vary: float, rng
) -> list[Point]:
    """The outline of a stone, from the corners of its cell.

    The sides too short to show are dropped, then each corner is pulled a little
    towards the middle, by as much as `vary` says: the joints open unevenly, as
    between stones that were not cut. The corners are then rounded.
    """
    cx, cy = middle
    size = sum(math.hypot(x - cx, y - cy) for x, y in corners) / len(corners)
    kept: list[Point] = []
    for x, y in corners:
        if kept and math.hypot(x - kept[-1][0], y - kept[-1][1]) < size * STONE_SHORT:
            continue  # the end of a side too short to show
        kept.append((x, y))
    if (
        len(kept) > 3
        and math.hypot(kept[0][0] - kept[-1][0], kept[0][1] - kept[-1][1])
        < size * STONE_SHORT
    ):
        kept.pop()
    pulled = []
    for x, y in kept:
        k = rng.uniform(0, vary) * STONE_PULL
        pulled.append((x + (cx - x) * k, y + (cy - y) * k))
    out = []
    for index, (vx, vy) in enumerate(pulled):
        px, py = pulled[index - 1]
        qx, qy = pulled[(index + 1) % len(pulled)]
        ax, ay = vx + (px - vx) * STONE_CORNER, vy + (py - vy) * STONE_CORNER
        bx, by = vx + (qx - vx) * STONE_CORNER, vy + (qy - vy) * STONE_CORNER
        for step in range(STONE_CORNER_STEPS + 1):
            t = step / STONE_CORNER_STEPS
            u = 1 - t
            out.append(
                (
                    u * u * ax + 2 * u * t * vx + t * t * bx,
                    u * u * ay + 2 * u * t * vy + t * t * by,
                )
            )
    return out


def stone_face(outline: Sequence[Point], middle: Point, relief: float) -> list[Point]:
    """The lit face of a stone that bulges out of the wall.

    The outline drawn in towards a point up and left of the middle: what is left
    around it, wider below and on the right, is the rim in shade.
    """
    cx, cy = middle
    room = math.inf  # from the middle to the nearest side
    for index, (ax, ay) in enumerate(outline):
        bx, by = outline[(index + 1) % len(outline)]
        length = math.hypot(bx - ax, by - ay)
        if length > 1e-9:
            room = min(
                room, abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / length
            )
    shift = room * RELIEF_SHIFT / math.sqrt(2) if math.isfinite(room) else 0.0
    ox, oy = cx - shift, cy - shift
    k = 1 - RELIEF_RIM * relief
    return [(ox + (x - ox) * k, oy + (y - oy) * k) for x, y in outline]


def _unit_colour(base: Color, tints: Sequence[dict[str, Any]], rng) -> Color:
    """The colour of one unit: a tint for its share of the units, else the base colour."""
    if not tints:
        return base
    pick = rng.random()
    for tint in tints:
        pick -= tint["amount"]
        if pick < 0:
            return rgb(tint["color"])
    return base


def _paint_stones(
    layer: Image.Image, joints: dict[str, Any], base: Color, px_per_m: float, rng
) -> None:
    """Fit stones of uneven shapes and sizes into one another over their bed.

    `cell` is their usual size (height, then length), `vary` how uneven they are,
    `relief` how much they bulge. The layer joins up with itself on all sides.
    """
    draw = ImageDraw.Draw(layer)
    width, height = layer.size
    along, across = (value * px_per_m for value in joints["cell"])
    gap = max(1.0, joints.get("width", 0.015) * px_per_m)
    spread = joints.get("shade", 0.08)
    vary = joints.get("vary", 0)
    relief = joints.get("relief", 0)
    tints = joints.get("tints", [])
    cols = max(1, round(width / across))
    rows = max(2, 2 * round(height / along / 2))  # even: the rows set off wrap around
    sites = stone_sites(cols, rows, vary, rng)
    for middle, corners in stone_cells(sites, width, height, gap):
        colour = _unit_colour(base, tints, rng)
        factor = 1 + rng.uniform(-spread, spread)
        outline = stone_outline(corners, middle, vary, rng)
        shapes = [(outline, factor)]
        if relief:
            shapes = [
                (outline, factor * (1 - RELIEF_SHADE * relief)),
                (stone_face(outline, middle, relief), factor),
            ]
        # a stone that goes over an edge comes back on the opposite one
        for dx in (-width, 0, width):
            for dy in (-height, 0, height):
                for shape, light in shapes:
                    draw.polygon(
                        [(x + dx, y + dy) for x, y in shape],
                        fill=_shade(colour, light),
                    )


def _paint_joints(
    layer: Image.Image, joints: dict[str, Any], base: Color, px_per_m: float, rng
) -> None:
    """Lay the units of a surface over their bed of mortar: pavers, slabs, boards.

    A row is `cell[0]` deep (down the picture) and its units `cell[1]` long (across
    it). With `vary` the units of a row differ in length: their lengths are drawn,
    then fitted to the row, so that a texture laid in tiles still joins up. Some
    units take one of the `tints` instead of the base colour. With the `irregular`
    pattern there are no rows: see `_paint_stones`.
    """
    draw = ImageDraw.Draw(layer)
    width, height = layer.size
    draw.rectangle((0, 0, width, height), fill=_shade(rgb(joints["color"]), 1.0))
    if joints.get("pattern", "rows") == "irregular":
        _paint_stones(layer, joints, base, px_per_m, rng)
        return
    along, across = (value * px_per_m for value in joints["cell"])
    gap = max(1.0, joints.get("width", 0.015) * px_per_m)
    stagger = joints.get("stagger", 0) * across
    spread = joints.get("shade", 0.08)
    vary = joints.get("vary", 0)
    tints = joints.get("tints", [])
    row = 0
    y = -along
    while y < height:
        start = -across + (row % 2) * stagger
        if vary:
            count = max(1, round(width / across))
            lengths = [1 + rng.uniform(-vary, vary) for _ in range(count)]
            fit = width / sum(lengths)
            x = start
            # twice over: the units pushed out on the right by the stagger come back on the left
            for length in lengths * 2:
                draw.rectangle(
                    (
                        x + gap / 2,
                        y + gap / 2,
                        x + length * fit - gap / 2,
                        y + along - gap / 2,
                    ),
                    fill=_shade(
                        _unit_colour(base, tints, rng),
                        1 + rng.uniform(-spread, spread),
                    ),
                )
                x += length * fit
        else:
            x = start
            while x < width:
                draw.rectangle(
                    (
                        x + gap / 2,
                        y + gap / 2,
                        x + across - gap / 2,
                        y + along - gap / 2,
                    ),
                    fill=_shade(
                        _unit_colour(base, tints, rng),
                        1 + rng.uniform(-spread, spread),
                    ),
                )
                x += across
        y += along
        row += 1


def _paint_wheels(
    layer: Image.Image, wheels: dict[str, Any], px_per_m: float, rng
) -> None:
    """Wear two tracks across the width of a surface, the rest left as it was."""
    width, height = layer.size
    draw = ImageDraw.Draw(layer)
    for low, high in wheels["bands"]:
        x0, x1 = round(low * width), round(high * width)
        if x1 <= x0:
            continue
        draw.rectangle((x0, 0, x1 - 1, height), fill=_shade(rgb(wheels["color"]), 1.0))
    for low, high in wheels["bands"]:
        x0, x1 = round(low * width), round(high * width)
        if x1 <= x0:
            continue
        band = Image.new("RGBA", (x1 - x0, height), (0, 0, 0, 0))
        _speckle(band, wheels.get("speckles", []), px_per_m, rng)
        layer.alpha_composite(band, (x0, 0))


def surface_layer(
    surface: dict[str, Any], width: int, height: int, px_per_m: float, rng
) -> Image.Image:
    """A strip of surface seen from above, painted from the numbers of the entry."""
    base = rgb(surface["color"])
    layer = Image.new("RGBA", (width, height), _shade(base, 1.0))
    if "joints" in surface:
        _paint_joints(layer, surface["joints"], base, px_per_m, rng)
    _speckle(layer, surface.get("speckles", []), px_per_m, rng)
    if "wheels" in surface:
        _paint_wheels(layer, surface["wheels"], px_per_m, rng)
    grain = surface.get("grain", 0.3)
    if grain:
        pixels = np.array(layer, dtype=float)
        spread = np.random.default_rng(rng.randrange(1 << 30)).uniform(
            1 - grain * GRAIN_SPREAD, 1 + grain * GRAIN_SPREAD, (height, width, 1)
        )
        pixels[:, :, :3] = np.clip(pixels[:, :, :3] * spread, 0, 255)
        layer = Image.fromarray(pixels.astype(np.uint8), "RGBA")
    return layer


def element_outline(
    shape: str, along: float, across: float, rng
) -> list[tuple[float, float]]:
    """Outline of one module element, centred on the origin: `along` by `across`."""
    a, c = along / 2, across / 2
    if shape == "half-moon":
        # a disc of the width of the path, cut through the middle: the cut lies
        # across the path, the round side ahead of it, so it is half as deep as wide
        steps = ROUND_STEPS // 2
        return [
            (
                c * (math.sin(math.pi * k / steps) - 0.5),
                c * math.cos(math.pi * k / steps),
            )
            for k in range(steps + 1)
        ]
    if shape == "slab":
        corner = min(along, across) * SLAB_CORNER
        out = []
        for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            cx, cy = sx * (a - corner), sy * (c - corner)
            start = math.atan2(sy, sx) - math.pi / 4
            for k in range(5):
                angle = start + math.pi / 2 * k / 4
                out.append(
                    (cx + corner * math.cos(angle), cy + corner * math.sin(angle))
                )
        return out
    jitter = shape == "stone"
    out = []
    for k in range(ROUND_STEPS):
        angle = 2 * math.pi * k / ROUND_STEPS
        reach = rng.uniform(0.76, 1.1) if jitter else 1.0
        out.append((a * reach * math.cos(angle), c * reach * math.sin(angle)))
    return out


def module_elements(
    module: dict[str, Any], width: int, height: int, px_per_m: float, rng
) -> list[tuple[list[tuple[float, float]], tuple[int, int, int, int]]]:
    """The elements along the strip, as drawn: outline in pixels, and colour."""
    along, across = module["size"]
    gap = module.get("gap", 0.2)
    vary = module.get("vary", {})
    stretch = vary.get("size", 0.15)
    turn = vary.get("angle", 0.08)
    side = vary.get("side", 0.1)
    spread = vary.get("shade", 0.08)
    out = []
    y = along / 2
    while (y - along / 2) * px_per_m < height:
        scale = 1 + rng.uniform(-stretch, stretch)
        a, c = along * scale, min(across * scale, width / px_per_m)
        angle = rng.uniform(-turn, turn) * 2 * math.pi
        offset = rng.uniform(-side, side) * c
        color = _shade(
            rgb(rng.choice(module["colors"])), 1 + rng.uniform(-spread, spread)
        )
        shape = rng.choice(module["shapes"])
        cos, sin = math.cos(angle), math.sin(angle)
        points = [
            (
                width / 2 + (px * sin + py * cos + offset) * px_per_m,
                (y + px * cos - py * sin) * px_per_m,
            )
            for px, py in element_outline(shape, a, c, rng)
        ]
        out.append((points, color))
        y += a / 2 + gap + along / 2
    return out


def module_layer(
    module: dict[str, Any], width: int, height: int, px_per_m: float, rng
) -> Image.Image:
    """Elements set one after another along the strip, the ground showing between."""
    elements = module_elements(module, width, height, px_per_m, rng)
    drop = module.get("thickness", 0.06) * px_per_m * MODULE_DROP
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    paint = ImageDraw.Draw(shadow)
    for points, _ in elements:
        paint.polygon(
            [(x + drop * 0.6, y + drop) for x, y in points], fill=(0, 0, 0, 90)
        )
    layer = shadow.filter(ImageFilter.GaussianBlur(max(2.0, drop * 0.5)))
    draw = ImageDraw.Draw(layer)
    for points, color in elements:
        draw.polygon(points, fill=color)
    return layer


def path_picture(data: dict[str, Any], size: int) -> Image.Image:
    """A piece of path seen from straight above, running from top to bottom."""
    big = size * SUPERSAMPLE
    across = data.get("width", {}).get("default", PATH_WIDTH)
    rng = random.Random(f"{data['kind']}:{data['name']['en']}")
    if data["kind"] == "surface":
        # a surface fills the picture: its texture is what there is to see
        strip = round(big * PATH_STRIP)
        px_per_m = strip / across
        layer = surface_layer(data["surface"], strip, big, px_per_m, rng)
    else:
        # a module path is drawn far enough back for a few elements to show
        module = data["module"]
        pitch = module["size"][0] + module.get("gap", 0.2)
        px_per_m = big / (MODULE_RUN * pitch)
        strip = min(round(across * px_per_m), round(big * PATH_STRIP))
        layer = module_layer(module, strip, big, px_per_m, rng)
    picture = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    picture.alpha_composite(layer, ((big - strip) // 2, 0))
    return picture.resize((size, size), Image.Resampling.LANCZOS)


def path_pictures(
    data: dict[str, Any], size: int = IMAGE_SIZE, thumb: int = THUMB_SIZE
) -> tuple[Image.Image, Image.Image]:
    """The same piece of path at both sizes: the texture reads at its real scale."""
    return path_picture(data, size), path_picture(data, thumb)


# -- terraces, seen from above -----------------------------------------------------

#: Share of the picture a terrace covers, and the metres of it shown across
TERRACE_SIDE = 0.84
TERRACE_SPAN = 2.4
#: Shadow of a slab: how far it falls, as a share of its thickness
SLAB_DROP = 1.5


def _shadow(
    size: int, box: tuple[float, float, float, float], radius: float, blur: float
) -> Image.Image:
    """A soft shadow under a box of the picture."""
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(box, radius=radius, fill=(0, 0, 0, 100))
    return shadow.filter(ImageFilter.GaussianBlur(max(2.0, blur)))


def terrace_picture(data: dict[str, Any], size: int) -> Image.Image:
    """A square of terrace seen from straight above, its rows running across."""
    big = size * SUPERSAMPLE
    side = round(big * TERRACE_SIDE)
    px_per_m = side / TERRACE_SPAN
    rng = random.Random(f"terrace:{data['name']['en']}")
    layer = surface_layer(data["surface"], side, side, px_per_m, rng)
    corner = round(side * 0.035)
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, side - 1, side - 1), radius=corner, fill=255
    )
    layer.putalpha(mask)
    at = (big - side) // 2
    # the thicker the terrace, the further its shadow falls
    drop = data.get("thickness", 0.05) * px_per_m * SLAB_DROP
    picture = _shadow(
        big,
        (at + drop * 0.6, at + drop, at + side + drop * 0.6, at + side + drop),
        corner,
        drop * 0.6,
    )
    picture.alpha_composite(layer, (at, at))
    return picture.resize((size, size), Image.Resampling.LANCZOS)


def terrace_pictures(
    data: dict[str, Any], size: int = IMAGE_SIZE, thumb: int = THUMB_SIZE
) -> tuple[Image.Image, Image.Image]:
    """The same square of terrace at both sizes."""
    return terrace_picture(data, size), terrace_picture(data, thumb)


# -- walls, copings and fences, seen from the front --------------------------------

#: Share of the picture a wall covers across it, and the wall shown: metres along, metres high
WALL_STRIP = 0.92
WALL_RUN = 2.0
WALL_HEIGHT = 1.2
#: Metres of fence shown, and the tallest fence the picture holds
FENCE_RUN = 2.6
FENCE_TALLEST = 2.6
#: Bumps along the top of a hedge on the picture, and how deep they are (m)
HEDGE_BUMPS = 9
HEDGE_BUMP = 0.12
#: Where the two rails of a fence of bars sit, as shares of its height
RAILS = (0.14, 0.86)
#: Upright wires between two level ones on a welded panel
GRID_RATIO = 4


def wall_picture(data: dict[str, Any], size: int) -> Image.Image:
    """A piece of wall seen from the front, standing on the ground, capped if it is."""
    big = size * SUPERSAMPLE
    width = round(big * WALL_STRIP)
    px_per_m = width / WALL_RUN
    height = round(WALL_HEIGHT * px_per_m)
    rng = random.Random(f"wall:{data['name']['en']}")
    layer = surface_layer(data["surface"], width, height, px_per_m, rng)
    left = (big - width) // 2
    top = (big - height) // 2
    foot = top + height
    picture = _shadow(
        big,
        (left, foot - big * 0.01, left + width, foot + big * 0.035),
        big * 0.02,
        big * 0.012,
    )
    picture.alpha_composite(layer, (left, top))
    coping = data.get("coping")
    if coping is not None:
        draw = ImageDraw.Draw(picture)
        thick = max(2.0, coping.get("height", 0.05) * px_per_m)
        out = min(left, coping.get("overhang", 0.03) * px_per_m)
        colour = rgb(coping["color"])
        draw.rectangle(
            (left - out, top - thick, left + width + out, top),
            fill=_shade(colour, 1.0),
        )
        # lit on top, in shade underneath: the capping juts out
        draw.rectangle(
            (left - out, top - thick, left + width + out, top - thick * 0.7),
            fill=_shade(colour, 1.12),
        )
        draw.rectangle(
            (left, top, left + width, top + max(1.0, thick * 0.25)),
            fill=(0, 0, 0, 70),
        )
    return picture.resize((size, size), Image.Resampling.LANCZOS)


def wall_pictures(
    data: dict[str, Any], size: int = IMAGE_SIZE, thumb: int = THUMB_SIZE
) -> tuple[Image.Image, Image.Image]:
    """The same piece of wall at both sizes."""
    return wall_picture(data, size), wall_picture(data, thumb)


#: Metres of wall shown under a coping, how thick that wall is and its colour, and how much of
#: the top of the coping shows when the wall is seen from the front and a little from above
COPING_RUN = 1.2
COPING_ON = 0.4
COPING_WALL = "#d8d1c3"
COPING_TILT = 0.5
#: Share of the picture the piece of wall under the coping takes, top to bottom
COPING_FACE = 0.42


def coping_picture(data: dict[str, Any], size: int) -> Image.Image:
    """The top of a piece of wall seen from the front and a little from above, capped."""
    big = size * SUPERSAMPLE
    width = round(big * WALL_STRIP)
    px_per_m = width / COPING_RUN
    out = data.get("overhang", 0.03)
    across = COPING_ON + 2 * out
    rise = data.get("height", 0.05) + data.get("drop", 0.0)
    depth = max(2, round(across * px_per_m))
    edge = max(2, round(rise * px_per_m))
    rng = random.Random(f"coping:{data['name']['en']}")
    # laid flat it is `depth` deep; the edge towards us is the same surface, in shade
    layer = surface_layer(data["surface"], width, depth + edge, px_per_m, rng)
    top = layer.crop((0, 0, width, depth)).resize(
        (width, max(2, round(depth * COPING_TILT))), Image.Resampling.LANCZOS
    )
    front = layer.crop((0, depth, width, depth + edge))
    front.alpha_composite(Image.new("RGBA", front.size, (0, 0, 0, 52)))
    face = round(big * COPING_FACE)
    left = (big - width) // 2
    upper = (big - (top.height + edge + face)) // 2
    picture = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(picture)
    # the wall under it, narrower than the coping by what it juts out, the shade of the overhang on it
    inset = min(width // 4, round(out * px_per_m))
    foot = upper + top.height + edge
    # (edges that come down over the faces hide the top of the wall: the face starts under them)
    draw.rectangle(
        (left + inset, foot, left + width - inset, foot + face),
        fill=_shade(rgb(COPING_WALL), 1.0),
    )
    shade = max(2.0, (out + 0.02) * px_per_m)
    draw.rectangle(
        (left + inset, foot, left + width - inset, foot + shade),
        fill=_shade(rgb(COPING_WALL), 0.76),
    )
    picture.alpha_composite(top, (left, upper))
    picture.alpha_composite(front, (left, upper + top.height))
    return picture.resize((size, size), Image.Resampling.LANCZOS)


def coping_pictures(
    data: dict[str, Any], size: int = IMAGE_SIZE, thumb: int = THUMB_SIZE
) -> tuple[Image.Image, Image.Image]:
    """The same capped piece of wall at both sizes."""
    return coping_picture(data, size), coping_picture(data, thumb)


def open_lines(
    spec: dict[str, Any], width: float, height: float, px_per_m: float
) -> list[tuple[tuple[float, float, float, float], float]]:
    """The wires or bars of a see-through fence: segments (x0, y0, x1, y1) and width.

    `fill` is the share of the sheet they cover: a mesh and a grid are made of two
    sets of wires, so each wire is half as wide as a bar would be.
    """
    pitch = spec.get("pitch", 0.1) * px_per_m
    fill = spec.get("fill", 0.35)
    pattern = spec["pattern"]
    lines = []
    if pattern == "mesh":
        wire = pitch * fill / 2
        reach = width + height
        x = -height
        while x < reach:
            lines.append(((x, 0.0, x + height, height), wire))
            lines.append(((x + height, 0.0, x, height), wire))
            x += pitch * math.sqrt(2)
        return lines
    if pattern == "grid":
        wire = pitch * fill / 2
        x = 0.0
        while x <= width:
            lines.append(((x, 0.0, x, height), wire))
            x += pitch
        y = height
        while y >= 0:
            lines.append(((0.0, y, width, y), wire))
            y -= pitch * GRID_RATIO
        return lines
    bar = pitch * fill
    x = pitch / 2
    while x < width:
        lines.append(((x, 0.0, x, height), bar))
        x += pitch
    for share in RAILS:
        lines.append(((0.0, height * share, width, height * share), bar))
    return lines


def fence_panel(
    data: dict[str, Any], width: int, height: int, px_per_m: float, rng
) -> Image.Image:
    """What stands between two posts: wires, a solid sheet or clipped foliage."""
    surface = data["surface"]
    spec = data.get("open")
    if spec is not None:
        panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(panel)
        colour = _shade(rgb(surface["color"]), 1.0)
        for box, wire in open_lines(spec, width, height, px_per_m):
            draw.line(box, fill=colour, width=max(1, round(wire)))
        return panel
    panel = surface_layer(surface, width, height, px_per_m, rng)
    if data.get("foliage"):
        # clipped foliage: an uneven top, rounded at both ends
        bump = HEDGE_BUMP * px_per_m
        outline = [(0.0, float(height)), (0.0, bump)]
        for k in range(HEDGE_BUMPS + 1):
            outline.append((width * k / HEDGE_BUMPS, rng.uniform(0, bump)))
        outline += [(float(width), bump), (float(width), float(height))]
        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).polygon(outline, fill=255)
        panel.putalpha(mask)
    return panel


def fence_picture(data: dict[str, Any], size: int) -> Image.Image:
    """A run of fence seen from the front, at its usual height, with its posts."""
    big = size * SUPERSAMPLE
    px_per_m = big * 0.9 / max(FENCE_RUN, FENCE_TALLEST)
    width = round(FENCE_RUN * px_per_m)
    tall = min(data["height"]["default"], FENCE_TALLEST)
    height = max(2, round(tall * px_per_m))
    rng = random.Random(f"fence:{data['name']['en']}")
    left = (big - width) // 2
    foot = round(big * 0.93)
    top = foot - height
    # the shadow of a thick hedge stays a line on the ground, not a second hedge
    depth = min(max(data.get("thickness", 0), 0.05), 0.3) * px_per_m
    picture = _shadow(
        big,
        (left, foot - depth * 0.2, left + width, foot + depth * 0.5 + big * 0.012),
        big * 0.01,
        big * 0.01,
    )
    picture.alpha_composite(
        fence_panel(data, width, height, px_per_m, rng), (left, top)
    )
    posts = data.get("posts")
    if posts is not None:
        draw = ImageDraw.Draw(picture)
        side = max(2.0, posts.get("size", 0.07) * px_per_m)
        spacing = posts.get("spacing", 2.5) * px_per_m
        colour = rgb(posts["color"])
        x = float(left)
        # a post at each end of the run, and one every `spacing` between them
        stops = []
        while x < left + width - side:
            stops.append(x)
            x += spacing
        stops.append(left + width - side)
        for at in stops:
            draw.rectangle(
                (at, top - side * 0.4, at + side, foot), fill=_shade(colour, 1.0)
            )
            draw.rectangle(
                (at, top - side * 0.4, at + side * 0.35, foot),
                fill=_shade(colour, 1.18),
            )
    return picture.resize((size, size), Image.Resampling.LANCZOS)


def fence_pictures(
    data: dict[str, Any], size: int = IMAGE_SIZE, thumb: int = THUMB_SIZE
) -> tuple[Image.Image, Image.Image]:
    """The same run of fence at both sizes."""
    return fence_picture(data, size), fence_picture(data, thumb)


PICTURES = {
    "tree": tree_pictures,
    "object": object_pictures,
    "pond_fish": fish_pictures,
    "path": path_pictures,
    "terrace": terrace_pictures,
    "wall": wall_pictures,
    "coping": coping_pictures,
    "fence": fence_pictures,
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
