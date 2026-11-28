"""Small catalogs built in a temporary folder, shared by the tests."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

TREE = {
    "name": {"en": "Oak"},
    "latin": "Quercus robur",
    "shape": "round",
    "evergreen": False,
    "height": {"default": 9, "min": 4, "max": 25},
    "crown_radius": 3.8,
    "trunk": {"height": 3.2, "radius": 0.3, "color": "#5c4636"},
    "seasons": {
        "spring": {
            "foliage": "#9ccf62",
            "density": 0.65,
            "flowers": {"color": "#ffffff", "amount": 0.5},
        },
        "summer": {"foliage": "#3f7f35", "fruits": {"color": "#aa0000", "amount": 0.3}},
        "autumn": {
            "foliage": "#c98a2e",
            "density": 0.8,
            "fallen": {"color": "#b8792a", "amount": 0.5},
        },
        "winter": {"foliage": "#8a6a45", "density": 0},
    },
}

OBJECT = {
    "name": {"en": "Stool"},
    "category": "seating",
    "parts": [
        {
            "shape": "cylinder",
            "width": 0.3,
            "height": 0.04,
            "depth": 0.3,
            "elevation": 0.41,
            "color": "#b8915f",
            "tint": True,
        },
        {
            "shape": "box",
            "width": 0.04,
            "height": 0.41,
            "depth": 0.04,
            "color": "#8a6a45",
        },
    ],
}


FISH = {
    "name": {"en": "Goldfish"},
    "latin": "Carassius auratus",
    "length": {"default": 0.2, "min": 0.05, "max": 0.35},
    "body": {"width": 0.24, "height": 0.3, "tail": 0.25, "fins": "long"},
    "swim": {"speed": 0.15, "depth": "surface", "school": True},
    "varieties": [
        {
            "id": "red-white",
            "name": {"en": "Red and white"},
            "base": "#ffffff",
            "fins": "#ff8800",
            "patches": [
                {"color": "#dd2200", "amount": 0.5, "size": "large"},
                {"color": "#000000", "amount": 0.1, "size": "small", "where": "back"},
            ],
        },
        {
            "id": "gold",
            "name": {"en": "Gold"},
            "base": "#ffaa00",
            "belly": "#ffee88",
            "metallic": True,
            "patches": [{"color": "#cc0000", "amount": 0.05, "where": "head"}],
        },
    ],
}


PATH = {
    "name": {"en": "Gravel"},
    "kind": "surface",
    "draft": "#e0d3b4",
    "width": {"default": 3, "min": 0.5, "max": 12},
    "surface": {
        "color": "#bdb29c",
        "roughness": 1,
        "tile": 2,
        "grain": 0.4,
        "speckles": [{"color": "#a99d86", "amount": 0.12, "size": 0.026}],
    },
}


TERRACE = {
    "name": {"en": "Wooden decking"},
    "draft": "#c29660",
    "thickness": 0.12,
    "surface": {
        "color": "#a07b4f",
        "tile": 2.4,
        "grain": 0.18,
        "joints": {
            "color": "#6b5134",
            "cell": [0.15, 2.4],
            "width": 0.007,
            "stagger": 0.5,
        },
    },
}

WALL = {
    "name": {"en": "Rubble stone"},
    "draft": "#d6b77c",
    "surface": {
        "color": "#a89a80",
        "tile": 2.4,
        "joints": {
            "color": "#d0c6b2",
            "cell": [0.2, 0.3],
            "width": 0.02,
            "stagger": 0.5,
            "shade": 0.2,
            "vary": 0.45,
        },
    },
    "coping": {"color": "#b9ad96", "height": 0.06, "overhang": 0.03},
}

COPING = {
    "name": {"en": "Bricks on edge"},
    "surface": {
        "color": "#a5553c",
        "tile": 0.6,
        "joints": {"color": "#c9c0b0", "cell": [0.6, 0.075], "width": 0.01},
    },
    "height": 0.07,
    "overhang": 0.01,
}

FENCE = {
    "name": {"en": "Wire mesh"},
    "draft": "#ff2bd6",
    "height": {"default": 1.5, "min": 0.5, "max": 3},
    "surface": {"color": "#5f7d5c"},
    "open": {"pattern": "mesh", "pitch": 0.1, "fill": 0.38},
    "posts": {"color": "#3d4a3c", "spacing": 2.5, "size": 0.07},
}


SPRINKLER = {
    "name": {"en": "Pro-Spray PSU-04-15A"},
    "brand": "Hunter",
    "kind": "spray",
    "radius": {"default": 4.6, "min": 3.4, "max": 4.6},
    "arc": {"min": 1, "max": 360},
}


def dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def tree() -> dict:
    return copy.deepcopy(TREE)


@pytest.fixture
def thing() -> dict:
    return copy.deepcopy(OBJECT)


@pytest.fixture
def fish() -> dict:
    return copy.deepcopy(FISH)


@pytest.fixture
def path() -> dict:
    return copy.deepcopy(PATH)


@pytest.fixture
def terrace() -> dict:
    return copy.deepcopy(TERRACE)


@pytest.fixture
def wall() -> dict:
    return copy.deepcopy(WALL)


@pytest.fixture
def coping() -> dict:
    return copy.deepcopy(COPING)


@pytest.fixture
def fence() -> dict:
    return copy.deepcopy(FENCE)


@pytest.fixture
def sprinkler() -> dict:
    return copy.deepcopy(SPRINKLER)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A minimal valid catalog: one entry of each kind, no picture."""
    shutil.copytree(REPO / "schema", tmp_path / "schema")
    dump(tmp_path / "trees/items/oak/tree.json", TREE)
    dump(tmp_path / "objects/items/stool/object.json", OBJECT)
    dump(tmp_path / "pond_fish/items/goldfish/pond_fish.json", FISH)
    dump(tmp_path / "paths/items/gravel/path.json", PATH)
    dump(tmp_path / "terraces/items/wood-decking/terrace.json", TERRACE)
    dump(tmp_path / "walls/items/rubble-stone/wall.json", WALL)
    dump(tmp_path / "copings/items/brick/coping.json", COPING)
    dump(tmp_path / "fences/items/mesh/fence.json", FENCE)
    dump(tmp_path / "sprinklers/items/hunter-psu-04-15a/sprinkler.json", SPRINKLER)
    return tmp_path
