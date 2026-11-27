"""Lists of the README, written from the catalog."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FENCE, PATH, TERRACE, TREE, WALL, dump

import readme_catalog


def test_tables(root: Path):
    (root / "trees/items/oak/thumb.webp").write_bytes(b"x")
    (root / "objects/items/stool/image.png").write_bytes(b"x")
    fir = {key: value for key, value in TREE.items() if key != "latin"}
    dump(
        root / "trees/items/fir/tree.json",
        fir | {"name": {"en": "Fir | spruce"}, "evergreen": True},
    )
    block = readme_catalog.render(root)
    assert block.startswith(readme_catalog.BEGIN) and block.endswith(readme_catalog.END)
    assert "<summary><b>Trees</b> (2)</summary>" in block
    assert (
        '| <img src="trees/items/oak/thumb.webp" width="48" alt=""> | Oak<br>`oak` '
        "| <i>Quercus robur</i> | round | deciduous | 9 m (4-25) "
        "| 4 seasons |"
    ) in block
    assert "|  | Fir \\| spruce<br>`fir` |  | round | evergreen |" in block
    assert "<summary><b>Objects</b> (1)</summary>" in block
    assert (
        '| <img src="objects/items/stool/image.png" width="48" alt=""> | `stool` '
        "| Stool | seating | 0.3 x 0.3 x 0.45 m | 2 |"
    ) in block


def test_the_paths_table_says_what_each_is_made_of(root: Path):
    surface = PATH["surface"]
    dump(
        root / "paths/items/pavers/path.json",
        PATH | {"name": {"en": "Pavers"}, "surface": surface | {"joints": {}}},
    )
    dump(
        root / "paths/items/tracks/path.json",
        PATH | {"name": {"en": "Grass track"}, "surface": surface | {"wheels": {}}},
    )
    dump(
        root / "paths/items/sleepers/path.json",
        {
            "name": {"en": "Sleepers"},
            "kind": "module",
            "draft": "#8a6a45",
            "module": {
                "shapes": ["slab", "stone"],
                "size": [0.22, 1.2],
                "colors": ["#6b4f33"],
            },
        },
    )
    block = readme_catalog.render(root)
    assert "<summary><b>Paths</b> (4)</summary>" in block
    # modules first, then the surfaces, each in its own kind
    assert "|  | Sleepers<br>`sleepers` | module | slab, stone |  |" in block
    assert "|  | Gravel<br>`gravel` | surface | unbroken | 3 m (0.5-12) |" in block
    assert "|  | Pavers<br>`pavers` | surface | laid units | 3 m (0.5-12) |" in block
    assert (
        "|  | Grass track<br>`tracks` | surface | wheel tracks | 3 m (0.5-12) |"
        in block
    )


def test_the_terraces_walls_and_fences_tables(root: Path):
    (root / "walls/items/rubble-stone/thumb.webp").write_bytes(b"x")
    dump(
        root / "terraces/items/painted/terrace.json",
        {"name": {"en": "Plain colour"}, "draft": "#f2f2f2", "surface": {}},
    )
    dump(
        root / "walls/items/render/wall.json",
        {"name": {"en": "Render"}, "draft": "#ffe9b8", "surface": {}},
    )
    solid = {key: value for key, value in FENCE.items() if key not in ("open", "posts")}
    dump(
        root / "fences/items/wall/fence.json",
        solid | {"name": {"en": "Wall"}, "thickness": 0.2, "coping": True},
    )
    dump(
        root / "fences/items/hedge/fence.json",
        solid | {"name": {"en": "Hedge"}, "thickness": 0.6, "foliage": True},
    )
    dump(
        root / "copings/items/zinc/coping.json",
        {"name": {"en": "Zinc"}, "surface": {"color": "#9aa1a6"}, "drop": 0.04},
    )
    block = readme_catalog.render(root)
    assert "<summary><b>Terraces</b> (2)</summary>" in block
    assert (
        "|  | Wooden decking<br>`wood-decking` | units 2.4 x 0.15 m | 0.12 m |" in block
    )
    assert "|  | Plain colour<br>`painted` | unbroken | 0.05 m |" in block
    assert "<summary><b>Walls</b> (2)</summary>" in block
    assert (
        '| <img src="walls/items/rubble-stone/thumb.webp" width="48" alt=""> '
        "| Rubble stone<br>`rubble-stone` | units 0.3 x 0.2 m, uneven | yes |"
    ) in block
    assert "|  | Render<br>`render` | unbroken |  |" in block
    # stones without rows are said so
    surface = WALL["surface"] | {
        "joints": WALL["surface"]["joints"] | {"pattern": "irregular"}
    }
    dump(root / "walls/items/rubble-stone/wall.json", WALL | {"surface": surface})
    assert (
        "| Rubble stone<br>`rubble-stone` | irregular stones, about 0.3 x 0.2 m | yes |"
        in readme_catalog.render(root)
    )
    # the copings: what they are made of and their sizes, the folded edges of a sheet
    assert "<summary><b>Copings</b> (2)</summary>" in block
    assert (
        "|  | Bricks on edge<br>`brick` | units 0.07 x 0.6 m | 0.07 m | 0.01 m |  |"
        in block
    )
    assert "|  | Zinc<br>`zinc` | unbroken | 0.05 m | 0.03 m | 0.04 m |" in block
    assert "<summary><b>Fences</b> (3)</summary>" in block
    # hedges first, then the see-through ones, then the solid ones
    rows = [line for line in block.splitlines() if "(0.5-3)" in line]
    assert rows == [
        "|  | Hedge<br>`hedge` | hedge | 1.5 m (0.5-3) | 0.6 m |  |  |",
        "|  | Wire mesh<br>`mesh` | see-through (mesh) | 1.5 m (0.5-3) | 0 m | yes |  |",
        # a wall says that a coping can be laid on it
        "|  | Wall<br>`wall` | solid | 1.5 m (0.5-3) | 0.2 m |  | yes |",
    ]
    assert TERRACE["thickness"] == 0.12 and "coping" in WALL


def test_name_falls_back_to_the_id(root: Path):
    dump(root / "trees/items/oak/tree.json", TREE | {"name": "Oak"})
    assert "| oak<br>`oak` |" in readme_catalog.render(root)
    dump(root / "trees/items/oak/tree.json", TREE | {"name": {"fr": "Chêne"}})
    assert "| oak<br>`oak` |" in readme_catalog.render(root)


def test_update_replaces_or_appends():
    block = f"{readme_catalog.BEGIN}\nnew\n{readme_catalog.END}"
    text = f"# Title\n\n{readme_catalog.BEGIN}\nold\n{readme_catalog.END}\n\ntail\n"
    assert readme_catalog.update(text, block) == f"# Title\n\n{block}\n\ntail\n"
    assert readme_catalog.update("# Title\n", block) == (
        f"# Title\n\n## Catalog content\n\n{block}\n"
    )
    for broken in (
        f"{readme_catalog.END}\n{readme_catalog.BEGIN}",
        readme_catalog.BEGIN,
        readme_catalog.END,
    ):
        with pytest.raises(ValueError, match="markers"):
            readme_catalog.update(broken, block)


def test_command(root: Path, capsys):
    readme = root / "README.md"
    readme.write_text("# Catalog\n", encoding="utf-8")
    args = ["--root", str(root)]
    assert readme_catalog.main([*args, "--check"]) == 1
    assert "not up to date" in capsys.readouterr().err
    assert readme.read_text(encoding="utf-8") == "# Catalog\n"
    assert readme_catalog.main(args) == 0
    assert "README.md updated" in capsys.readouterr().out
    assert "<b>Trees</b> (1)" in readme.read_text(encoding="utf-8")
    assert readme_catalog.main([*args, "--check"]) == 0
    assert "up to date" in capsys.readouterr().out

    readme.write_text(readme_catalog.END, encoding="utf-8")
    assert readme_catalog.main(args) == 1
    assert "markers" in capsys.readouterr().err
