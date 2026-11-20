"""Tests of the catalog tools, on small catalogs built in a temporary folder."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from conftest import OBJECT, TREE, dump

import catalog
import make_release
import validate

# -- layout ---------------------------------------------------------------------


def test_collect_lists_the_entries_of_a_section(root: Path):
    (root / "trees/items/.git").mkdir()
    (root / "trees/items/oak/.DS_Store").write_text("x")
    (root / "trees/items/oak/image.webp").write_bytes(b"picture")
    (root / "trees/items/readme.txt").write_text("not a folder")
    entries = catalog.collect(root, "trees")
    assert [(e.name, e.kind, sorted(e.files)) for e in entries] == [
        ("tree.oak", "tree", ["image.webp", "tree.json"])
    ]
    assert catalog.entry_id(entries[0]) == "oak"
    assert catalog.collect(root / "nowhere", "objects") == []
    with pytest.raises(ValueError, match="unknown section 'birds'"):
        catalog.collect(root, "birds")


def test_content_hash_follows_the_content_only(root: Path):
    before = catalog.collect(root, "trees")[0].content_hash()
    assert catalog.collect(root, "trees")[0].content_hash() == before
    dump(root / "trees/items/oak/tree.json", TREE | {"crown_radius": 4})
    assert catalog.collect(root, "trees")[0].content_hash() != before


# -- validate -------------------------------------------------------------------


def test_valid_catalog(root: Path, capsys):
    report = validate.validate(root)
    assert report.errors == []
    # translations and pictures of each entry, the names of the two varieties
    assert len(report.warnings) == 8
    assert validate.main(["--root", str(root)]) == 0
    assert validate.main(["--root", str(root), "--strict"]) == 1
    out = capsys.readouterr().out
    assert "warning: trees/items/oak: missing translations" in out
    assert "0 error(s), 8 warning(s)" in out


def test_broken_catalog(root: Path, capsys):
    (root / "trees/items/oak/tree.json").write_text("{not json", encoding="utf-8")
    (root / "trees/items/empty").mkdir()
    (root / "trees/items/extra").mkdir()
    dump(root / "trees/items/extra/tree.json", TREE | {"latin": "Quercus alba"})
    (root / "trees/items/extra/model.glb").write_bytes(b"3d")
    for path in sorted((root / "objects").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    (root / "objects").rmdir()
    errors = validate.validate(root).errors
    assert errors[0] == "trees/items/empty: missing tree.json"
    assert errors[1].startswith("trees/items/extra: unexpected file 'model.glb'")
    assert errors[2].startswith("trees/items/oak: unreadable JSON")
    assert errors[3] == "objects: section folder missing"
    assert len(errors) == 4
    assert validate.main(["--root", str(root)]) == 1
    assert "error: objects: section folder missing" in capsys.readouterr().out


def test_trees_are_checked_against_each_other(root: Path):
    dump(root / "trees/items/second-oak/tree.json", TREE)
    assert validate.validate(root).errors == [
        "trees/items/second-oak: latin 'Quercus robur' already used by 'oak'"
    ]


# -- releases -------------------------------------------------------------------


def build(root: Path, out: Path, section="trees", version="2026.11.0", **kwargs):
    return make_release.build(root, section, version, out, **kwargs)


def test_first_release(root: Path, tmp_path: Path):
    out = tmp_path / "dist"
    manifest = build(root, out, min_integration={"house_view": "0.2.0"})
    assert manifest["format"] == 1 and manifest["section"] == "trees"
    assert manifest["min_integration"] == {"house_view": "0.2.0"}
    entry = manifest["entries"]["tree.oak"]
    assert entry["kind"] == "tree" and entry["shape"] == "round"
    assert entry["evergreen"] is False
    assert entry["archive"] == "trees-2026.11.0/tree.oak.zip"
    assert entry["since"] == "2026.11.0"
    archive = out / "upload" / "tree.oak.zip"
    assert entry["size"] == archive.stat().st_size
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.namelist() == ["tree.json"]
        assert json.loads(zipped.read("tree.json")) == TREE
    with zipfile.ZipFile(out / "upload" / "schema.zip") as zipped:
        assert zipped.namelist() == ["common.schema.json", "tree.schema.json"]
    assert manifest["schema"]["archive"] == "trees-2026.11.0/schema.zip"
    notes = (out / "notes.md").read_text(encoding="utf-8")
    assert notes == manifest["notes"]
    assert "## Added\n\n- `oak` (tree)\n- validation schemas\n" in notes
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8")) == manifest

    chair = build(root, tmp_path / "objects", "objects")["entries"]["object.stool"]
    assert chair["kind"] == "object" and chair["category"] == "seating"
    goldfish = build(root, tmp_path / "fish", "fish")["entries"]["fish.goldfish"]
    assert goldfish["kind"] == "fish" and goldfish["varieties"] == ["red-white", "gold"]


def test_archives_are_reproducible(root: Path, tmp_path: Path):
    first = build(root, tmp_path / "a")["entries"]["tree.oak"]["sha256"]
    assert build(root, tmp_path / "b")["entries"]["tree.oak"]["sha256"] == first


def test_next_release_only_carries_what_changed(root: Path, tmp_path: Path):
    first = build(root, tmp_path / "v1", min_integration={"house_view": "0.2.0"})

    same = build(root, tmp_path / "v2", version="2026.12.0", previous=first)
    assert same["entries"] == first["entries"] and same["schema"] == first["schema"]
    assert same["min_integration"] == {"house_view": "0.2.0"}
    assert "No content change." in same["notes"]
    assert list((tmp_path / "v2" / "upload").iterdir()) == []

    dump(root / "trees/items/oak/tree.json", TREE | {"crown_radius": 4})
    dump(root / "trees/items/pine/tree.json", TREE | {"latin": "Pinus"})
    schema = root / "schema" / "tree.schema.json"
    schema.write_text(schema.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    changed = build(
        root,
        tmp_path / "v3",
        version="2026.12.1",
        previous=same,
        min_integration={"house_view": "0.3.0"},
    )
    assert changed["entries"]["tree.oak"]["since"] == "2026.12.1"
    assert changed["entries"]["tree.pine"]["since"] == "2026.12.1"
    assert changed["schema"]["since"] == "2026.12.1"
    assert changed["min_integration"] == {"house_view": "0.3.0"}
    assert "## Added\n\n- `pine` (tree)" in changed["notes"]
    assert "## Updated\n\n- `oak` (tree)\n- validation schemas" in changed["notes"]

    (root / "trees/items/pine/tree.json").unlink()
    (root / "trees/items/pine").rmdir()
    removed = build(root, tmp_path / "v4", version="2026.12.2", previous=changed)
    assert "tree.pine" not in removed["entries"]
    assert removed["entries"]["tree.oak"] == changed["entries"]["tree.oak"]
    assert "## Removed\n\n- `pine` (tree)" in removed["notes"]


def test_refused_releases(root: Path, tmp_path: Path):
    with pytest.raises(SystemExit, match="unknown section 'birds'"):
        build(root, tmp_path, "birds")
    with pytest.raises(SystemExit, match=r"version must look like 2026\.11\.0"):
        build(root, tmp_path, version="v1")
    objects = build(root, tmp_path / "o", "objects")
    with pytest.raises(SystemExit, match="belongs to another section"):
        build(root, tmp_path, previous=objects)
    (root / "schema" / "common.schema.json").unlink()
    with pytest.raises(SystemExit, match="missing schema file"):
        build(root, tmp_path)


def test_min_integration_arguments(monkeypatch):
    assert make_release._parse_min(["house_view=0.2.0"], "trees") == {
        "house_view": "0.2.0"
    }
    assert make_release._parse_min([], "objects") == {}
    # one list for every section: the consumers of another section are skipped
    monkeypatch.setitem(make_release.CONSUMERS, "objects", ("furniture_tool",))
    both = ["house_view=0.2.0", "furniture_tool=1.0.0"]
    assert make_release._parse_min(both, "trees") == {"house_view": "0.2.0"}
    assert make_release._parse_min(both, "objects") == {"furniture_tool": "1.0.0"}
    for bad in ("redsea=1.0.0", "house_view", "house_view="):
        with pytest.raises(SystemExit, match="--min-integration expects"):
            make_release._parse_min([bad], "trees")


def test_release_command(root: Path, tmp_path: Path, capsys):
    out = tmp_path / "dist"
    args = ["--root", str(root), "--out", str(out)]
    assert make_release.main(["trees", "2026.11.0", *args]) == 0
    assert "trees 2026.11.0: 1 entries, 2 to upload" in capsys.readouterr().out

    previous = tmp_path / "prev.json"
    previous.write_bytes((out / "manifest.json").read_bytes())
    dump(root / "trees/items/oak/tree.json", TREE | {"crown_radius": 4})
    more = [
        *args,
        "--previous",
        str(previous),
        "--min-integration",
        "house_view=0.3.0",
    ]
    assert make_release.main(["trees", "2026.12.0", *more]) == 0
    assert "1 entries, 1 to upload" in capsys.readouterr().out
    assert make_release.main(["trees", "2026.12.0", *args, "--previous", "none"]) == 0

    dump(previous, {"format": 99, "section": "trees"})
    with pytest.raises(SystemExit, match="newer format"):
        make_release.main(["trees", "2026.12.1", *args, "--previous", str(previous)])


def test_the_fixture_object_is_what_the_tests_expect():
    assert OBJECT["parts"][0]["shape"] == "cylinder"
