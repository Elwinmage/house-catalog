"""Lists of the README, written from the catalog."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import TREE, dump

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
        '| <img src="trees/items/oak/thumb.webp" width="48" alt=""> | `oak` | Oak '
        "| <i>Quercus robur</i> | round | deciduous | 9 m (4-25) "
        "| 4 seasons |"
    ) in block
    assert "|  | `fir` | Fir \\| spruce |  | round | evergreen |" in block
    assert "<summary><b>Objects</b> (1)</summary>" in block
    assert (
        '| <img src="objects/items/stool/image.png" width="48" alt=""> | `stool` '
        "| Stool | seating | 0.3 x 0.3 x 0.45 m | 2 |"
    ) in block


def test_name_falls_back_to_the_id(root: Path):
    dump(root / "trees/items/oak/tree.json", TREE | {"name": "Oak"})
    assert "| `oak` | oak |" in readme_catalog.render(root)
    dump(root / "trees/items/oak/tree.json", TREE | {"name": {"fr": "Chêne"}})
    assert "| `oak` | oak |" in readme_catalog.render(root)


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
