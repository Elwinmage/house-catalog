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
def root(tmp_path: Path) -> Path:
    """A minimal valid catalog: one tree, one object, no picture."""
    shutil.copytree(REPO / "schema", tmp_path / "schema")
    dump(tmp_path / "trees/items/oak/tree.json", TREE)
    dump(tmp_path / "objects/items/stool/object.json", OBJECT)
    return tmp_path
