"""Write the lists of the catalog into README.md.

The trees, the objects, the fish, the paths, the terraces, the walls, the copings and the
fences of the catalog are listed, with their pictures, between two markers of the README; the rest of the
file is left alone:

    <!-- catalog:begin -->
    ...generated...
    <!-- catalog:end -->

    python scripts/readme_catalog.py [--root .] [--check]

--check writes nothing and fails when the README is not up to date.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

from catalog import folders, read_json
from house_catalog_rules import SEASONS, object_size

BEGIN = "<!-- catalog:begin -->"
END = "<!-- catalog:end -->"

# Size of the pictures in the tables, in pixels
THUMB_WIDTH = 48


def _cell(text: object) -> str:
    """Text safe in a markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _details(summary: str, body: list[str]) -> list[str]:
    """A block that folds: closed by default, its summary always shown.

    Blank lines around the body keep the markdown table working inside the HTML
    element, on GitHub as elsewhere.
    """
    return ["<details>", f"<summary>{summary}</summary>", "", *body, "", "</details>"]


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    """A markdown table; the cells are expected to be safe already."""
    return [
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


def _name(data: dict, fallback: str) -> str:
    """English name of a descriptor."""
    name = data.get("name")
    return str(name.get("en") or fallback) if isinstance(name, dict) else fallback


def _visual(root: Path, folder: Path) -> str:
    """The thumbnail (else the picture) of an entry folder, as an <img>."""
    for file in ("thumb.webp", "image.webp", "image.png"):
        path = folder / file
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            return f'<img src="{rel}" width="{THUMB_WIDTH}" alt="">'
    return ""


def _metres(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def trees_table(root: Path) -> list[str]:
    rows = []
    entries = folders(root / "trees" / "items")
    for folder in entries:
        data = read_json(folder / "tree.json")
        height = data["height"]
        seasons = [season for season in SEASONS if season in data["seasons"]]
        rows.append(
            [
                _visual(root, folder),
                # name and id in one cell: one column less, so that the picture keeps its width
                f"{_cell(_name(data, folder.name))}<br>`{folder.name}`",
                f"<i>{_cell(data['latin'])}</i>" if "latin" in data else "",
                _cell(data["shape"]),
                "evergreen" if data["evergreen"] else "deciduous",
                f"{_metres(height['default'])} m ({_metres(height['min'])}-{_metres(height['max'])})",
                # short, like the other cells: a table wider than the page squeezes
                # its narrowest column, the picture, down to nothing
                "4 seasons"
                if len(seasons) == len(SEASONS)
                else _cell(", ".join(seasons)),
            ]
        )
    return _details(
        f"<b>Trees</b> ({len(entries)})",
        _table(
            [
                "",
                "Tree",
                "Botanical name",
                "Shape",
                "Foliage",
                "Height",
                "Seasons",
            ],
            rows,
        ),
    )


def objects_table(root: Path) -> list[str]:
    rows = []
    entries = folders(root / "objects" / "items")
    for folder in entries:
        data = read_json(folder / "object.json")
        width, height, depth = object_size(data["parts"])
        rows.append(
            [
                _visual(root, folder),
                f"`{folder.name}`",
                _cell(_name(data, folder.name)),
                _cell(data["category"]),
                f"{_metres(width)} x {_metres(depth)} x {_metres(height)} m",
                str(len(data["parts"])),
            ]
        )
    rows.sort(key=lambda row: (row[3], row[2].lower()))
    return _details(
        f"<b>Objects</b> ({len(entries)})",
        _table(
            ["", "Id", "Object", "Category", "Width x depth x height", "Parts"], rows
        ),
    )


def fish_table(root: Path) -> list[str]:
    rows = []
    entries = folders(root / "pond_fish" / "items")
    for folder in entries:
        data = read_json(folder / "pond_fish.json")
        length = data["length"]
        rows.append(
            [
                _visual(root, folder),
                f"`{folder.name}`",
                _cell(_name(data, folder.name)),
                f"<i>{_cell(data['latin'])}</i>" if "latin" in data else "",
                f"{_metres(length['default'])} m ({_metres(length['min'])}-{_metres(length['max'])})",
                _cell(", ".join(variety["id"] for variety in data["varieties"])),
            ]
        )
    return _details(
        f"<b>Fish</b> ({len(entries)})",
        _table(["", "Id", "Fish", "Scientific name", "Length", "Varieties"], rows),
    )


def paths_table(root: Path) -> list[str]:
    rows = []
    entries = folders(root / "paths" / "items")
    for folder in entries:
        data = read_json(folder / "path.json")
        width = data.get("width")
        if data["kind"] == "surface":
            made_of = data["surface"]
            detail = "laid units" if "joints" in made_of else "unbroken"
            if "wheels" in made_of:
                detail = "wheel tracks"
        else:
            made_of = data["module"]
            detail = _cell(", ".join(made_of["shapes"]))
        rows.append(
            [
                _visual(root, folder),
                f"{_cell(_name(data, folder.name))}<br>`{folder.name}`",
                _cell(data["kind"]),
                detail,
                f"{_metres(width['default'])} m ({_metres(width['min'])}-{_metres(width['max'])})"
                if width
                else "",
            ]
        )
    rows.sort(key=lambda row: (row[2], row[1].lower()))
    return _details(
        f"<b>Paths</b> ({len(entries)})",
        _table(["", "Path", "Kind", "Made of", "Width"], rows),
    )


def _made_of(surface: dict) -> str:
    """A painted surface in two words: laid in units, or one piece."""
    joints = surface.get("joints")
    if joints is None:
        return "unbroken"
    depth, length = joints["cell"]
    if joints.get("pattern") == "irregular":
        return f"irregular stones, about {_metres(length)} x {_metres(depth)} m"
    units = f"units {_metres(length)} x {_metres(depth)} m"
    return f"{units}, uneven" if joints.get("vary") else units


def terraces_table(root: Path) -> list[str]:
    rows = []
    entries = folders(root / "terraces" / "items")
    for folder in entries:
        data = read_json(folder / "terrace.json")
        rows.append(
            [
                _visual(root, folder),
                f"{_cell(_name(data, folder.name))}<br>`{folder.name}`",
                _made_of(data["surface"]),
                f"{_metres(data.get('thickness', 0.05))} m",
            ]
        )
    return _details(
        f"<b>Terraces</b> ({len(entries)})",
        _table(["", "Terrace", "Made of", "Thickness"], rows),
    )


def walls_table(root: Path) -> list[str]:
    rows = []
    entries = folders(root / "walls" / "items")
    for folder in entries:
        data = read_json(folder / "wall.json")
        rows.append(
            [
                _visual(root, folder),
                f"{_cell(_name(data, folder.name))}<br>`{folder.name}`",
                _made_of(data["surface"]),
                "yes" if "coping" in data else "",
            ]
        )
    return _details(
        f"<b>Walls</b> ({len(entries)})",
        _table(["", "Wall", "Made of", "Coping"], rows),
    )


def copings_table(root: Path) -> list[str]:
    rows = []
    entries = folders(root / "copings" / "items")
    for folder in entries:
        data = read_json(folder / "coping.json")
        drop = data.get("drop", 0)
        rows.append(
            [
                _visual(root, folder),
                f"{_cell(_name(data, folder.name))}<br>`{folder.name}`",
                _made_of(data["surface"]),
                f"{_metres(data.get('height', 0.05))} m",
                f"{_metres(data.get('overhang', 0.03))} m",
                f"{_metres(drop)} m" if drop else "",
            ]
        )
    return _details(
        f"<b>Copings</b> ({len(entries)})",
        _table(["", "Coping", "Made of", "Height", "Overhang", "Folded edges"], rows),
    )


def fences_table(root: Path) -> list[str]:
    rows = []
    entries = folders(root / "fences" / "items")
    for folder in entries:
        data = read_json(folder / "fence.json")
        height = data["height"]
        if "open" in data:
            family = f"see-through ({data['open']['pattern']})"
        elif data.get("foliage"):
            family = "hedge"
        else:
            family = "solid"
        rows.append(
            [
                _visual(root, folder),
                f"{_cell(_name(data, folder.name))}<br>`{folder.name}`",
                family,
                f"{_metres(height['default'])} m ({_metres(height['min'])}-{_metres(height['max'])})",
                f"{_metres(data.get('thickness', 0))} m",
                "yes" if "posts" in data else "",
                "yes" if data.get("coping") else "",
            ]
        )
    rows.sort(key=lambda row: (row[2], row[1].lower()))
    return _details(
        f"<b>Fences</b> ({len(entries)})",
        _table(["", "Fence", "Family", "Height", "Thickness", "Posts", "Coping"], rows),
    )


def render(root: Path) -> str:
    """The generated block, markers included."""
    lines = [
        BEGIN,
        "<!-- Generated by scripts/readme_catalog.py: do not edit by hand -->",
        "",
        *trees_table(root),
        "",
        *objects_table(root),
        "",
        *fish_table(root),
        "",
        *paths_table(root),
        "",
        *terraces_table(root),
        "",
        *walls_table(root),
        "",
        *copings_table(root),
        "",
        *fences_table(root),
        "",
        END,
    ]
    return "\n".join(lines)


def update(text: str, block: str) -> str:
    """The README with its generated block replaced (appended when missing).

    @raise ValueError: markers out of order
    """
    start = text.find(BEGIN)
    end = text.find(END)
    if start == -1 and end == -1:
        return text.rstrip("\n") + "\n\n## Catalog content\n\n" + block + "\n"
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"README markers {BEGIN} / {END} are broken")
    return text[:start] + block + text[end + len(END) :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--check", action="store_true", help="fail if README.md is not up to date"
    )
    args = parser.parse_args(argv)
    readme = args.root / "README.md"
    text = readme.read_text(encoding="utf-8")
    try:
        new = update(text, render(args.root))
    except ValueError as err:
        print(err, file=sys.stderr)
        return 1
    if new == text:
        print("README.md is up to date")
        return 0
    if args.check:
        print(
            "README.md is not up to date: run python scripts/readme_catalog.py",
            file=sys.stderr,
        )
        return 1
    readme.write_text(new, encoding="utf-8")
    print("README.md updated")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
