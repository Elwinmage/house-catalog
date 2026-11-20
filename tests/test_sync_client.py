"""Copy of the rules and of the built-in snapshots into the tools using the catalog."""

from __future__ import annotations

from pathlib import Path

from conftest import TREE, dump

import sync_client

RULES = "catalog-editor/house_catalog_rules.py"
SECTIONS = "catalog-editor/house_catalog_sections.py"
HOUSE_SECTIONS = "ha-house-view-component/house_catalog_sections.py"
HEADER = (
    "# Generated from house-catalog/client/{name} by "
    "scripts/sync_client.py: do not edit this copy.\n"
)


def client(root: Path) -> None:
    """The modules of the catalog a tool gets a copy of."""
    (root / "client").mkdir()
    (root / "client/house_catalog_rules.py").write_text("RULES = 1\n")
    (root / "client/house_catalog_sections.py").write_text("SECTIONS = {}\n")


def checkouts(base: Path) -> tuple[Path, Path]:
    editor = base / "catalog-editor/custom_components/catalog_editor"
    house = base / "ha-house-view-component/custom_components/house_view"
    editor.mkdir(parents=True)
    house.mkdir(parents=True)
    return editor, house


def test_nothing_to_do_without_a_checkout(tmp_path: Path, root: Path, capsys):
    assert sync_client.sync(tmp_path, root=root) == []
    out = capsys.readouterr().out
    assert "skip catalog-editor" in out and "skip ha-house-view-component" in out


def test_the_editor_gets_the_sections_and_the_rules(tmp_path: Path, root: Path):
    editor, _ = checkouts(tmp_path)
    client(root)
    stale = sync_client.sync(tmp_path, check=True, root=root)
    assert stale[:2] == [SECTIONS, RULES]
    assert list(editor.iterdir()) == []

    assert sync_client.sync(tmp_path, root=root)[:2] == [SECTIONS, RULES]
    assert (editor / "house_catalog_rules.py").read_text(encoding="utf-8") == (
        HEADER.format(name="house_catalog_rules.py") + "RULES = 1\n"
    )
    assert (editor / "house_catalog_sections.py").read_text(encoding="utf-8") == (
        HEADER.format(name="house_catalog_sections.py") + "SECTIONS = {}\n"
    )
    assert not (editor / "catalog_builtin").exists()  # an editor reads the releases
    assert sync_client.sync(tmp_path, check=True, root=root) == []

    (editor / "house_catalog_rules.py").write_text("edited", encoding="utf-8")
    assert sync_client.sync(tmp_path, check=True, root=root) == [RULES]
    (root / "client/house_catalog_sections.py").write_text("SECTIONS = {'a': {}}\n")
    assert sync_client.sync(tmp_path, check=True, root=root) == [
        SECTIONS,
        RULES,
        HOUSE_SECTIONS,
    ]


def test_the_house_view_gets_a_snapshot_of_each_section(tmp_path: Path, root: Path):
    _, house = checkouts(tmp_path)
    client(root)
    (root / "trees/items/oak/thumb.webp").write_bytes(b"picture")
    trees = "ha-house-view-component/catalog_builtin"
    objects = "ha-house-view-component/catalog_builtin_objects"
    fish = "ha-house-view-component/catalog_builtin_pond_fish"

    assert sync_client.sync(tmp_path, check=True, root=root) == [
        SECTIONS,
        RULES,
        HOUSE_SECTIONS,
        trees,
        objects,
        fish,
    ]
    assert list(house.iterdir()) == []
    sync_client.sync(tmp_path, root=root)
    assert not (house / "house_catalog_rules.py").exists()  # it does not edit
    # ...but it declares the sections it reads to the catalog client
    assert (house / "house_catalog_sections.py").read_text().startswith("# Generated")
    # the first section has the plain name, the others carry theirs
    assert sorted(p.relative_to(house).as_posix() for p in house.rglob("*.*")) == [
        "catalog_builtin/items/oak/thumb.webp",
        "catalog_builtin/items/oak/tree.json",
        "catalog_builtin_objects/items/stool/object.json",
        "catalog_builtin_pond_fish/items/goldfish/pond_fish.json",
        "house_catalog_sections.py",
    ]
    assert sync_client.sync(tmp_path, check=True, root=root) == []

    # an entry changed, one added, one removed, a stray file: each makes it stale
    dump(root / "trees/items/oak/tree.json", TREE | {"crown_radius": 4})
    assert sync_client.sync(tmp_path, check=True, root=root) == [trees]
    sync_client.sync(tmp_path, root=root)
    dump(root / "trees/items/pine/tree.json", TREE | {"latin": "Pinus"})
    assert sync_client.sync(tmp_path, check=True, root=root) == [trees]
    sync_client.sync(tmp_path, root=root)
    (root / "trees/items/oak/thumb.webp").unlink()
    assert sync_client.sync(tmp_path, check=True, root=root) == [trees]
    sync_client.sync(tmp_path, root=root)
    assert not (house / "catalog_builtin/items/oak/thumb.webp").exists()
    (house / "catalog_builtin_objects/items/stool/notes.txt").write_text("x")
    assert sync_client.sync(tmp_path, check=True, root=root) == [objects]
    sync_client.sync(tmp_path, root=root)
    assert sync_client.sync(tmp_path, check=True, root=root) == []

    # a section emptied keeps an empty snapshot folder
    (root / "objects/items/stool/object.json").unlink()
    (root / "objects/items/stool").rmdir()
    assert sync_client.sync(tmp_path, root=root) == [objects]
    assert list((house / "catalog_builtin_objects").iterdir()) == []
    assert sync_client.sync(tmp_path, check=True, root=root) == []


def test_command(tmp_path: Path, capsys):
    editor, house = checkouts(tmp_path)
    args = ["--base", str(tmp_path)]
    assert sync_client.main([*args, "--check"]) == 1
    out = capsys.readouterr().out
    assert f"out of date: {RULES}" in out
    assert f"out of date: {HOUSE_SECTIONS}" in out
    assert "out of date: ha-house-view-component/catalog_builtin_objects" in out
    assert sync_client.main(args) == 0
    assert f"updated: {RULES}" in capsys.readouterr().out
    assert (house / "catalog_builtin/items/oak/tree.json").is_file()
    assert (house / "catalog_builtin_objects/items/chair/image.webp").is_file()
    assert (house / "catalog_builtin_pond_fish/items/koi/pond_fish.json").is_file()
    assert (editor / "house_catalog_rules.py").read_text().startswith("# Generated")
    # the copy of the description is the one the scripts of the catalog use
    copied = (house / "house_catalog_sections.py").read_text().split("\n", 1)[1]
    assert copied == (sync_client.REPO / "client/house_catalog_sections.py").read_text()
    assert sync_client.main([*args, "--check"]) == 0
    assert "everything up to date" in capsys.readouterr().out
