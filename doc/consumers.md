# Consuming the catalog

Contract between this repository and what reads it: the house_view integration
(which downloads the sections and serves them to its card) and the
[catalog editor](https://github.com/Elwinmage/catalog-editor). It is the
contract of [reeftech-catalog](https://github.com/Elwinmage/reeftech-catalog)
(`doc/consumers.md` there), applied to two more sections.

## Releases

Each section (`trees`, `objects`, `pond_fish`) has:

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

## Declaring the sections to the catalog client

The catalog client (`catalog_pack.py`, `catalog_runtime.py`, from
reeftech-catalog) only knows the sections of its own repository. This catalog
describes itself in [`client/house_catalog_sections.py`](../client/house_catalog_sections.py)
(its repository, its sections, the folder and the descriptor of each kind of
entry: plain data, no dependency), which `scripts/sync_client.py` copies into
the tools using it. Each of them declares the sections to its copy of the
client when its package is imported:

```python
from . import house_catalog_sections as house
from .catalog_pack import register_section

for section, kinds in house.SECTIONS.items():
    register_section(section, kinds, house.REPO)
```

From then on the sections are downloaded from this repository, checked and
merged like the ones of reeftech-catalog. A new section here (sprinklers, for
instance) is a change of that file and of the rules, with no change in
reeftech-catalog.

## In the catalog editor

The editor builds its forms from `schema.zip` and checks drafts with the rules
of the catalog, so it needs no knowledge of trees or objects:

| Where | What |
|---|---|
| `catalogs.py` | declares the sections of `house_catalog_sections.py` to the client; the tables of the editor (kinds of a section, group in the merged view, id from the English name, picture, order in a pull request) follow from it |
| `rules.py` | picks the rules of a kind: `house_catalog_rules.py` for the kinds of this catalog (same interface as `catalog_rules.py`), copied by `scripts/sync_client.py` |
| card and translations | the names of the catalogs and of the kinds; a colour (`common.schema.json#/$defs/color`) is a colour picker |

A pull request of the editor goes to the repository of its entry
(`repo_of(section)`); proposing entries of both catalogs at once opens one pull
request per repository. `scripts/sync_client.py --check` fails when a copy in
the editor is out of date.

## In the house_view integration

The integration declares the sections as above (in its `catalog.py`), then
reads them with the catalog client (`catalog_pack.py`, `catalog_runtime.py`,
copied by `sync_client.py` of reeftech-catalog):

```python
TREES = CatalogSpec(DOMAIN, "trees", "Trees", device_title="House view catalog")
OBJECTS = CatalogSpec(DOMAIN, "objects", "Objects", by_section=True)
FISH = CatalogSpec(DOMAIN, "pond_fish", "Pond fish", by_section=True)
```

(one `CatalogSpec` per section, the ones after the first with `by_section=True`: see
"Several sections" in `doc/consumers.md` of reeftech-catalog).

`scripts/sync_client.py` of this repository writes `house_catalog_sections.py`
and the built-in snapshots the integration ships, used before the first
download and offline:
`catalog_builtin/` (trees), `catalog_builtin_objects/` (objects) and
`catalog_builtin_pond_fish/` (pond fish), and its
`--check` fails when one is out of date.

The pack is shared (`<config>/reeftech_catalog/pack/<section>/`) with the
editor, and the user layer written by the editor
(`<config>/reeftech_catalog/user/<section>/`) is merged over it: an entry
saved in the editor is usable at once. The card asks the integration
(`house_view/catalog`, `house_view/catalog/subscribe`), never the network, and
draws the entries as [format.md](format.md) says: `card/src/catalog-lib.js`
reads the descriptors, `card/src/engine/catalog.js` draws them.
