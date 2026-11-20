"""House catalog rules: what an entry must follow, beyond its JSON Schema.

Canonical copy: house-catalog/client/. `scripts/validate.py` (CI, pre-commit,
releases) and the tools editing the catalog (catalog editor) share this one
implementation, so that a draft is accepted by the editor exactly when the CI
accepts it. Tools get a copy through `scripts/sync_client.py`; edit it here,
never in a copy.

Same interface as `catalog_rules.py` of reeftech-catalog, so that a tool
handling both catalogs drives them the same way. No Home Assistant dependency;
needs `jsonschema` and `referencing`. Everything works on data already read
(dicts, file names and sizes), never on the repository layout:

    validators = load_validators(schema_dir)        # schema/ of the repository,
                                                    # or schema.zip of a release
    ctx = Context(trees=..., objects=..., fish=...)
    report = validate_draft("tree", "oak", data, {"tree.json": 900}, ctx, validators)
    report.errors, report.warnings

`Context` holds the *other* entries a draft is checked against: when a draft
replaces an entry, leave that entry out of the context.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

# Languages of the ecosystem. English is mandatory, the others are reported
# as missing (warning) so translators know what to fill in.
KNOWN_LANGS = ("en", "fr", "de", "es", "it", "pl", "pt")

# Files allowed next to a descriptor, with their size limit in bytes.
ASSET_FILES = {
    "image.webp": 300_000,
    "image.png": 300_000,
    "thumb.webp": 40_000,
}
DESCRIPTOR_MAX = 32_000

SEASONS = ("spring", "summer", "autumn", "winter")

#: How far the footprint of an object may be off its origin, in metres
CENTER_TOLERANCE = 0.02
#: A part reaching lower than this under the ground is an error, in metres
GROUND_TOLERANCE = 0.01
#: Largest size of an object along any axis, in metres
OBJECT_MAX = 20.0
#: Longest fish, in metres
FISH_MAX = 2.0

#: Descriptor file of each kind of entry
DESCRIPTORS = {
    "tree": "tree.json",
    "object": "object.json",
    "fish": "fish.json",
}
#: Folder of each kind, from the root of the repository
FOLDERS = {
    "tree": "trees/items",
    "object": "objects/items",
    "fish": "fish/items",
}


@dataclass
class Report:
    """Errors (the entry is refused) and warnings (it is accepted, but could be better)."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")


@dataclass
class Context:
    """The entries a draft is checked against, by id."""

    trees: dict[str, dict[str, Any]] = field(default_factory=dict)
    objects: dict[str, dict[str, Any]] = field(default_factory=dict)
    fish: dict[str, dict[str, Any]] = field(default_factory=dict)


def where_of(kind: str, entry_id: str) -> str:
    """Location of an entry in the repository, as shown in the reports."""
    return f"{FOLDERS[kind]}/{entry_id}"


def load_validators(schema_dir: Path) -> dict[str, Draft202012Validator]:
    """One validator per kind of entry, from a folder of `<kind>.schema.json`."""
    resources = []
    schemas = {}
    for path in schema_dir.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
        schemas[path.name.split(".")[0]] = schema
    registry = Registry().with_resources(resources)
    return {
        name: Draft202012Validator(schema, registry=registry)
        for name, schema in schemas.items()
        if name != "common"
    }


# -- generic checks -------------------------------------------------------------


def check_schema(
    report: Report, where: str, data: Any, validator: Draft202012Validator
) -> bool:
    """Report what the JSON Schema refuses; True when it accepts the data."""
    errors = sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.path])
    for err in errors:
        location = "/".join(str(p) for p in err.path) or "(root)"
        report.error(where, f"{location}: {err.message}")
    return not errors


def check_files(
    report: Report, where: str, files: Mapping[str, int], descriptor: str
) -> None:
    """The files of an entry (name -> size in bytes): descriptor, visuals, limits."""
    if descriptor not in files:
        report.error(where, f"missing {descriptor}")
    for name, size in files.items():
        if name == descriptor:
            limit = DESCRIPTOR_MAX
        elif name in ASSET_FILES:
            limit = ASSET_FILES[name]
        else:
            report.error(
                where,
                f"unexpected file {name!r} (allowed: {descriptor}, {', '.join(ASSET_FILES)})",
            )
            continue
        if size > limit:
            report.error(where, f"{name} is {size} bytes, limit {limit}")
    if "image.webp" in files and "image.png" in files:
        report.error(where, "image.webp and image.png both present, keep one")


def _check_i18n(report: Report, where: str, texts: dict[str, str]) -> None:
    missing = [lang for lang in KNOWN_LANGS if lang not in texts]
    if missing:
        report.warn(where, f"missing translations: {', '.join(missing)}")


def _has_image(files: Mapping[str, int]) -> bool:
    return any(name.startswith("image.") for name in files)


# -- geometry of an object --------------------------------------------------------


def rotation(yaw: float, pitch: float, roll: float) -> list[list[float]]:
    """Matrix turning a part: yaw about y, then pitch about x, then roll about z.

    Angles in degrees; the matrix is Ry(yaw) . Rx(pitch) . Rz(roll), the order
    `YXZ` of three.js, applied to column vectors (x, y, z).
    """
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cx, sx = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    cz, sz = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    return [
        [cy * cz + sy * sx * sz, -cy * sz + sy * sx * cz, sy * cx],
        [cx * sz, cx * cz, -sx],
        [-sy * cz + cy * sx * sz, sy * sz + cy * sx * cz, cy * cx],
    ]


def part_center(part: Mapping[str, Any]) -> tuple[float, float, float]:
    """Centre of a part: where it turns about."""
    return (
        float(part.get("x", 0)),
        float(part.get("elevation", 0)) + part["height"] / 2,
        float(part.get("z", 0)),
    )


def part_extent(part: Mapping[str, Any]) -> tuple[float, float, float]:
    """Half sizes, along x, y and z, of the box around a turned part.

    Exact for a box and for an ellipsoid; for a cylinder and a cone it is the box
    around their own box, slightly larger than them when they are turned.
    """
    half = (part["width"] / 2, part["height"] / 2, part["depth"] / 2)
    matrix = rotation(part.get("yaw", 0), part.get("pitch", 0), part.get("roll", 0))
    if part["shape"] == "sphere":
        values = [
            math.sqrt(sum((row[k] * half[k]) ** 2 for k in range(3))) for row in matrix
        ]
    else:
        values = [sum(abs(row[k]) * half[k] for k in range(3)) for row in matrix]
    return values[0], values[1], values[2]


def object_bounds(
    parts: Iterable[Mapping[str, Any]],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Lowest and highest corner (x, y, z) of the box around all the parts."""
    low = [math.inf] * 3
    high = [-math.inf] * 3
    for part in parts:
        center = part_center(part)
        extent = part_extent(part)
        for axis in range(3):
            low[axis] = min(low[axis], center[axis] - extent[axis])
            high[axis] = max(high[axis], center[axis] + extent[axis])
    return (low[0], low[1], low[2]), (high[0], high[1], high[2])


def object_size(parts: Iterable[Mapping[str, Any]]) -> tuple[float, float, float]:
    """Width, height and depth of an object, in metres (height from the ground)."""
    low, high = object_bounds(parts)
    return (high[0] - low[0], high[1], high[2] - low[2])


# -- one rule set per kind ------------------------------------------------------


def _check_tree(report, where, entry_id, data, files, ctx) -> None:
    _check_i18n(report, where, data["name"])

    height = data["height"]
    if not height["min"] <= height["default"] <= height["max"]:
        report.error(where, f"height needs min <= default <= max, got {height}")
    trunk = data["trunk"]
    if trunk["height"] >= height["default"]:
        report.error(
            where,
            f"trunk height {trunk['height']} must be below the tree height {height['default']}",
        )
    if trunk["radius"] >= data["crown_radius"]:
        report.error(
            where,
            f"trunk radius {trunk['radius']} must be below the crown radius {data['crown_radius']}",
        )
    if data["crown_radius"] > height["default"]:
        report.error(
            where,
            f"crown radius {data['crown_radius']} is implausible for a tree of {height['default']} m",
        )

    latin = data.get("latin")
    if latin is not None:
        for other_id, other in ctx.trees.items():
            if str(other.get("latin", "")).lower() == latin.lower():
                report.error(where, f"latin {latin!r} already used by {other_id!r}")
                break

    missing = [season for season in SEASONS if season not in data["seasons"]]
    if missing and not data["evergreen"]:
        report.warn(
            where,
            f"deciduous tree without {', '.join(missing)}: drawn like summer then",
        )
    if not _has_image(files):
        report.warn(where, "no picture, only the icon will be shown")


def _check_object(report, where, entry_id, data, files, ctx) -> None:
    _check_i18n(report, where, data["name"])

    low, high = object_bounds(data["parts"])
    width, height, depth = high[0] - low[0], high[1], high[2] - low[2]
    if max(width, height, depth) > OBJECT_MAX:
        report.error(
            where,
            f"{width:.2f} x {height:.2f} x {depth:.2f} m is larger than {OBJECT_MAX:g} m",
        )
    if low[1] < -GROUND_TOLERANCE:
        report.error(where, f"a part reaches {-low[1]:.3f} m under the ground")
    elif low[1] > GROUND_TOLERANCE:
        report.warn(where, f"floats {low[1]:.3f} m above the ground")
    for axis, name in ((0, "x"), (2, "z")):
        offset = (low[axis] + high[axis]) / 2
        if abs(offset) > CENTER_TOLERANCE:
            report.error(
                where,
                f"footprint off centre along {name}: shift every part by {-offset:+.3f} m",
            )
    if not _has_image(files):
        report.warn(where, "no picture, only the icon will be shown")


def _check_fish(report, where, entry_id, data, files, ctx) -> None:
    _check_i18n(report, where, data["name"])

    length = data["length"]
    if not length["min"] <= length["default"] <= length["max"]:
        report.error(where, f"length needs min <= default <= max, got {length}")
    if length["max"] > FISH_MAX:
        report.error(
            where, f"a fish of {length['max']} m is larger than {FISH_MAX:g} m"
        )

    latin = data.get("latin")
    if latin is not None:
        for other_id, other in ctx.fish.items():
            if str(other.get("latin", "")).lower() == latin.lower():
                report.error(where, f"latin {latin!r} already used by {other_id!r}")
                break

    seen: set[str] = set()
    for variety in data["varieties"]:
        here = f"{where} variety {variety['id']}"
        if variety["id"] in seen:
            report.error(here, "id used twice")
        seen.add(variety["id"])
        _check_i18n(report, here, variety["name"])
        patches = variety.get("patches", [])
        covered = sum(
            p["amount"] for p in patches if p.get("where", "anywhere") != "head"
        )
        if covered > 1:
            report.error(
                here,
                f"the patches cover {covered:.2f} of the back, more than all of it",
            )
        if any(p["color"] == variety["base"] for p in patches):
            report.warn(here, "a patch has the colour of the body: it does not show")
    if not _has_image(files):
        report.warn(where, "no picture, only the icon will be shown")


_RULES = {
    "tree": _check_tree,
    "object": _check_object,
    "fish": _check_fish,
}
#: Group of `Context` the accepted entries of each kind join
_GROUPS = {
    "tree": "trees",
    "object": "objects",
    "fish": "fish",
}


# -- entry points ---------------------------------------------------------------


def validate_entry(
    report: Report,
    kind: str,
    entry_id: str,
    data: dict[str, Any],
    files: Mapping[str, int],
    ctx: Context,
    validators: Mapping[str, Draft202012Validator],
) -> bool:
    """Schema, then the rules of the kind. True when the schema accepted the data.

    An accepted entry joins the context: the next ones are checked against it.
    """
    where = where_of(kind, entry_id)
    if not check_schema(report, where, data, validators[kind]):
        return False
    _RULES[kind](report, where, entry_id, data, files, ctx)
    getattr(ctx, _GROUPS[kind])[entry_id] = data
    return True


def validate_draft(
    kind: str,
    entry_id: str,
    data: dict[str, Any],
    files: Mapping[str, int],
    ctx: Context,
    validators: Mapping[str, Draft202012Validator],
) -> Report:
    """Everything the CI checks about one entry, for a tool that edits the catalog.

    `files` maps the file names of the entry, descriptor included, to their
    sizes in bytes. The context is left as it was given.
    """
    report = Report()
    check_files(report, where_of(kind, entry_id), files, DESCRIPTORS[kind])
    scratch = Context(
        trees=dict(ctx.trees), objects=dict(ctx.objects), fish=dict(ctx.fish)
    )
    validate_entry(report, kind, entry_id, data, files, scratch, validators)
    return report
