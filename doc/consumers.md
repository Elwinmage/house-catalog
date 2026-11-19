# Consuming the catalog

Contract between this repository and what reads it: the house_view integration
(which downloads the sections and serves them to its card) and the
[catalog editor](https://github.com/Elwinmage/catalog-editor). It is the
contract of [reeftech-catalog](https://github.com/Elwinmage/reeftech-catalog)
(`doc/consumers.md` there), applied to two more sections.

## Releases

Each section (`trees`, `objects`) has:

- versioned releases `<section>-<version>` (`trees-2026.11.0`) holding the
  archives that changed in that version: `<kind>.<id>.zip` per entry (flat:
  the descriptor and its pictures) and `schema.zip` (the JSON Schemas of the
  section, `common.schema.json` included);
- a rolling release `<section>-latest` holding only the current
  `manifest.json`, at a fixed URL:
  `https://github.com/Elwinmage/house-catalog/releases/download/<section>-latest/manifest.json`.

```json
{
  "format": 1,
  "section": "trees",
  "version": "2026.11.0",
  "min_integration": { "house_view": "0.2.0" },
  "notes": "# trees 2026.11.0 ...",
  "entries": {
    "tree.oak": {
      "kind": "tree", "shape": "round", "evergreen": false,
      "content_hash": "<hex>", "archive": "trees-2026.11.0/tree.oak.zip",
      "sha256": "<hex>", "size": 28113, "since": "2026.11.0"
    }
  },
  "schema": { "content_hash": "<hex>", "archive": "trees-2026.11.0/schema.zip", "sha256": "<hex>", "size": 2540, "since": "2026.11.0" }
}
```

An entry whose content did not change keeps pointing to the archive of the
release that built it, so versioned releases are never deleted. Objects carry
their `category` in the manifest instead of `shape` and `evergreen`.

## What an entry may hold

The limits of the catalog client (`catalog_pack.py`) and of the editor, which
the checks of this repository apply too:

- ids: `^[a-z0-9]+(?:[-_][a-z0-9]+)*$`, 64 characters at most;
- files of an entry: its descriptor (`tree.json`, `object.json`, 32 KB at
  most), `image.webp` or `image.png` (300 KB), `thumb.webp` (40 KB), and
  nothing else;
- a descriptor is a JSON object, and never uses the keys `image`, `thumb` and
  `source`: the merged view of the client adds them to every entry;
- schemas: shared definitions live in `common.schema.json` and are referenced
  as `common.schema.json#/$defs/<name>`; fields are strings, numbers,
  booleans, enums, objects with `properties` and arrays of those, which the
  editor turns into a form without knowing the catalog. `tests/test_contract.py`
  keeps it that way.

## In the catalog editor

The editor builds its forms from `schema.zip` and checks drafts with the rules
of the catalog, so supporting these sections needs no knowledge of trees or
objects, only their declaration. The lists below are the whole wiring.

In the catalog client (`reeftech-catalog/client/catalog_pack.py`, then
`sync_client.py`):

```python
KIND_LAYOUT |= {"tree": ("items", "tree.json"), "object": ("items", "object.json")}
SECTION_KINDS |= {"trees": frozenset({"tree"}), "objects": frozenset({"object"})}
```

In the editor:

| Where | What |
|---|---|
| `const.py` | `SECTION_KINDS`: `"trees": ("tree",)`, `"objects": ("object",)`; `VIEW_GROUPS`: `"tree": "items"`, `"object": "items"` |
| `hints.py` | `ID_FROM`: `("name.en",)` for both kinds; `HAS_VISUAL`: `True` for both |
| `source.py`, `schemas.py`, GitHub client | the repository of these two sections is `Elwinmage/house-catalog` (`async_acquire_pack(..., repo=)`, `PackClient(session, section, repo)`, `GithubClient(upstream=)`) |
| rules | `house_catalog_rules.py`, copied by `scripts/sync_client.py` of this repository: same interface as `catalog_rules.py` (`DESCRIPTORS`, `FOLDERS`, `Context`, `validate_draft`), to use for the kinds `tree` and `object`; its `Context` takes the other `trees` and `objects` |
| translations | names of the two catalogs (config flow) and of the two kinds (card) |
| `forms.py` (optional) | `_WIDGETS["color"] = "color"` for a colour picker; a colour is a text field otherwise |

`scripts/sync_client.py --check` fails when the copy of the rules in the
editor is out of date.

## In the house_view integration

The integration reads the sections with the catalog client
(`catalog_pack.py`, `catalog_runtime.py`), with the repository given:

```python
REPO = "Elwinmage/house-catalog"
TREES = CatalogSpec(DOMAIN, "trees", "Trees", device_title="House view catalog", repo=REPO)
OBJECTS = CatalogSpec(DOMAIN, "objects", "Objects", repo=REPO, by_section=True)
```

(one `CatalogSpec` per section, the second one with `by_section=True`: see
"Several sections" in `doc/consumers.md` of reeftech-catalog).

The pack is shared (`<config>/reeftech_catalog/pack/<section>/`) with the
editor, and the user layer written by the editor
(`<config>/reeftech_catalog/user/<section>/`) is merged over it: an entry
saved in the editor is usable at once. The card reads the merged view and
draws the entries as [format.md](format.md) says.
