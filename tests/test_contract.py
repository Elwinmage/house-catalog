"""What the catalog client and the catalog editor expect from this repository.

The limits below are theirs (catalog_pack.py and forms.py of the editor,
doc/consumers.md here): a catalog that leaves them is not downloaded, or gets
fields the editor can only show as raw JSON.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest
from conftest import REPO

import house_catalog_sections
import make_release
from catalog import LAYOUT, SECTIONS, collect, entry_id, read_json
from house_catalog_rules import DESCRIPTORS, FOLDERS

# catalog_pack.py
NAME_RE = re.compile(r"^[a-z]+(?:_[a-z]+)*$")  # sections, kinds, folders
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
#: Kinds of the sections the client publishes itself: taken
REEF_KINDS = {"tasks", "category", "item", "supplement", "parameter", "water_test"}
ID_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
FILE_RE = re.compile(r"^[A-Za-z0-9_@.-]{1,120}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ARCHIVE_RE = re.compile(r"^[a-z_]+-[0-9A-Za-z._+-]{1,40}/[A-Za-z0-9_.-]{1,120}\.zip$")
ALLOWED_SUFFIXES = (".json", ".webp", ".png")
MAX_ENTRY_BYTES = 4 * 1024 * 1024
MAX_JSON_BYTES = 256 * 1024
#: Keys the merged view of the client adds to every entry
VIEW_KEYS = {"image", "thumb", "source"}
# forms.py of the editor: what it draws without falling back to raw JSON
SCALARS = {"string", "number", "integer", "boolean"}
DEF_RE = re.compile(r"^(?:common\.schema\.json)?#/\$defs/([A-Za-z0-9_]+)$")


def schemas() -> dict[str, dict]:
    return {
        path.name.split(".")[0]: read_json(path)
        for path in (REPO / "schema").glob("*.schema.json")
    }


def test_the_catalog_describes_itself_for_the_client():
    """client/house_catalog_sections.py is what a tool gives to `register_section`."""
    assert house_catalog_sections.REPO == "Elwinmage/house-catalog"
    assert REPO_RE.match(house_catalog_sections.REPO)
    assert list(house_catalog_sections.SECTIONS) == list(SECTIONS)
    kinds = {}
    for section, declared in house_catalog_sections.SECTIONS.items():
        assert NAME_RE.match(section) and declared
        assert LAYOUT[section] == tuple((f, k) for k, (f, _) in declared.items())
        for kind, (folder, descriptor) in declared.items():
            # names the client accepts, a kind in one section only, never a reef one
            assert NAME_RE.match(kind) and NAME_RE.match(folder)
            assert kind not in kinds and kind not in REEF_KINDS and kind != "schema"
            assert FILE_RE.match(descriptor) and descriptor.endswith(".json")
            assert DESCRIPTORS[kind] == descriptor
            assert FOLDERS[kind] == f"{section}/{folder}"
            kinds[kind] = section
    assert set(kinds) == set(DESCRIPTORS)
    # plain data: a tool without jsonschema (the house view) imports it too
    source = (REPO / "client/house_catalog_sections.py").read_text(encoding="utf-8")
    imports = [
        line for line in source.splitlines() if line.startswith(("import ", "from "))
    ]
    assert imports == ["from __future__ import annotations"]


def test_layout_is_the_one_of_the_client():
    assert set(SECTIONS) == {"trees", "objects", "fish"}
    for section, kinds in LAYOUT.items():
        assert re.fullmatch(r"[a-z_]+", section)
        for folder, kind in kinds:
            # <section>/items/<id>/<kind>.json, a folder per entry
            assert folder == "items"
            assert DESCRIPTORS[kind] == f"{kind}.json"
            assert FOLDERS[kind] == f"{section}/{folder}"
            assert (REPO / "schema" / f"{kind}.schema.json").is_file()


def test_entries_fit_the_client():
    for section in SECTIONS:
        for entry in collect(REPO, section):
            assert ID_RE.match(entry_id(entry)) and len(entry_id(entry)) <= 64
            assert DESCRIPTORS[entry.kind] in entry.files
            for name, path in entry.files.items():
                assert FILE_RE.match(name) and name.endswith(ALLOWED_SUFFIXES)
                if name.endswith(".json"):
                    assert path.stat().st_size <= MAX_JSON_BYTES
            data = read_json(entry.files[DESCRIPTORS[entry.kind]])
            assert isinstance(data, dict) and not VIEW_KEYS & set(data), entry.name


def drawable(node: dict, common: dict, where: str) -> list[str]:
    """Fields of a schema node the editor could not draw."""
    ref = node.get("$ref")
    if ref is not None:
        match = DEF_RE.match(ref)
        if not match or match.group(1) not in common["$defs"]:
            return [f"{where}: $ref {ref!r} is not a shared definition"]
        node = {**common["$defs"][match.group(1)], **node}
        if match.group(1) in ("i18n", "icon", "id"):
            return []  # widgets of their own
    if "enum" in node:
        return []
    kind = node.get("type")
    if kind in SCALARS:
        return []
    if kind == "array":
        return drawable(node.get("items", {}), common, f"{where}[]")
    if kind == "object" and "properties" in node:
        problems = []
        if node.get("additionalProperties") is not False:
            problems.append(f"{where}: additionalProperties must be false")
        missing = set(node.get("required", [])) - set(node["properties"])
        if missing:
            problems.append(f"{where}: required {sorted(missing)} not in properties")
        for name, sub in node["properties"].items():
            problems += drawable(sub, common, f"{where}.{name}")
        return problems
    return [f"{where}: edited as raw JSON by the editor"]


def test_schemas_only_use_what_the_editor_draws():
    all_schemas = schemas()
    common = all_schemas.pop("common")
    assert sorted(all_schemas) == sorted(DESCRIPTORS)
    ids = {schema["$id"] for schema in (common, *all_schemas.values())}
    assert len(ids) == len(all_schemas) + 1
    for kind, schema in all_schemas.items():
        assert schema["$id"].endswith(f"/{kind}.schema.json")
        assert schema["title"] and schema["description"]
        assert drawable(schema, common, kind) == []
        # an id is suggested from the English name: every kind has one
        assert schema["properties"]["name"]["$ref"].endswith("#/$defs/i18n")
        assert not VIEW_KEYS & set(schema["properties"])


def test_the_check_catches_what_the_editor_cannot_draw():
    common = {"$defs": {"color": {"type": "string"}}}
    bad = {
        "type": "object",
        "required": ["gone"],
        "properties": {
            "choice": {"oneOf": [{"type": "string"}, {"type": "number"}]},
            "local": {"$ref": "#/$defs/missing"},
            "elsewhere": {"$ref": "other.schema.json#/$defs/color"},
            "list": {"type": "array", "items": {"type": "object"}},
            "fine": {
                "type": "array",
                "items": {"$ref": "common.schema.json#/$defs/color"},
            },
        },
    }
    assert drawable(bad, common, "x") == [
        "x: additionalProperties must be false",
        "x: required ['gone'] not in properties",
        "x.choice: edited as raw JSON by the editor",
        "x.local: $ref '#/$defs/missing' is not a shared definition",
        "x.elsewhere: $ref 'other.schema.json#/$defs/color' is not a shared definition",
        "x.list[]: edited as raw JSON by the editor",
    ]


@pytest.mark.parametrize("section", SECTIONS)
def test_release_is_readable_by_the_client(section: str, tmp_path: Path):
    manifest = make_release.build(
        REPO, section, "2026.11.0", tmp_path, min_integration={"house_view": "0.2.0"}
    )
    assert manifest["format"] == 1 and manifest["section"] == section
    assert isinstance(manifest["notes"], str)
    records = {**manifest["entries"], "schema": manifest["schema"]}
    kinds = {kind for _, kind in LAYOUT[section]}
    for name, record in records.items():
        if name != "schema":
            kind, _, entry = name.partition(".")
            assert kind in kinds and record["kind"] == kind and ID_RE.match(entry)
        assert SHA_RE.match(record["sha256"]) and SHA_RE.match(record["content_hash"])
        assert ARCHIVE_RE.match(record["archive"])
        assert record["archive"] == f"{section}-2026.11.0/{name}.zip"
        assert 0 < record["size"] <= MAX_ENTRY_BYTES
        with zipfile.ZipFile(tmp_path / "upload" / f"{name}.zip") as archive:
            names = archive.namelist()
            assert names == sorted(names) and all("/" not in n for n in names)
            assert all(FILE_RE.match(n) and n.endswith(ALLOWED_SUFFIXES) for n in names)
            for inner in names:
                if inner.endswith(".json"):
                    assert isinstance(json.loads(archive.read(inner)), dict)
            if name != "schema":
                assert DESCRIPTORS[record["kind"]] in names
            else:
                assert "common.schema.json" in names
