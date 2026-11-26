"""What the house catalog publishes: its repository and the layout of its sections.

Canonical copy: house-catalog/client/. The scripts of the catalog read it, and
so do the tools using the catalog (the house view integration, the catalog
editor), which get a copy through `scripts/sync_client.py`; edit it here, never
in a copy.

The catalog client (`catalog_pack.py`, from reeftech-catalog) only knows the
sections of its own repository: a tool declares the ones of this catalog before
using it, when its package is imported:

    from . import house_catalog_sections as house
    from .catalog_pack import register_section

    for section, kinds in house.SECTIONS.items():
        register_section(section, kinds, house.REPO)

No dependency: plain data.
"""

from __future__ import annotations

#: `owner/name` of the GitHub repository publishing the releases
REPO = "Elwinmage/house-catalog"

#: section -> {kind of entry: (folder, descriptor file)}; an entry is the folder
#: `<section>/<folder>/<id>/` holding its descriptor and its pictures
SECTIONS: dict[str, dict[str, tuple[str, str]]] = {
    "trees": {"tree": ("items", "tree.json")},
    "objects": {"object": ("items", "object.json")},
    "pond_fish": {"pond_fish": ("items", "pond_fish.json")},
    "paths": {"path": ("items", "path.json")},
}
