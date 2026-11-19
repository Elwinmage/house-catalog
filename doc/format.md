# Format of the entries

What a descriptor means, for anyone drawing the entries: the card of the house
view, `scripts/render_previews.py` (the reference reading, in a few hundred
lines), or another tool. The JSON Schemas of [`schema/`](../schema) say what is
allowed; this page says what it means. How it is drawn (number of clumps,
smoothness, shading) is left to the renderer.

Lengths are in metres, colours are `#rrggbb` in lower case, angles in degrees.

## Trees

A tree is described at its default height (`height.default`). A renderer
placing a tree of another height scales the whole tree by
`height / height.default`.

```
        top ─────────  y = height.default
            ╭──────╮
            │ crown│   crown_radius wide (from the axis of the trunk)
            ╰──┬───╯
 trunk.height ─┤       the crown starts here
               │       trunk.radius at the ground
     ground ───┴─────  y = 0
```

- The **crown** fills the box between `trunk.height` and the top of the tree,
  `crown_radius` wide on every side.
  - `round`: leafy clumps (rough ellipsoids) filling that box.
  - `conical`: stacked cones, the widest at the bottom (`crown_radius`), the
    last one ending at the top.
- The **trunk** goes from the ground into the crown, thinner toward the top,
  in `trunk.color`. A `round` tree has a few branches inside its crown: they
  show when the foliage is thin or gone.

### Seasons

`seasons` holds up to four renderings: `spring`, `summer`, `autumn`, `winter`.
A missing season is drawn like `summer`. Between two seasons a renderer may
blend colours and amounts (the house view does, day after day).

| Field | Meaning |
|---|---|
| `foliage` | Colour of the leaves or needles. |
| `density` | Share of the full foliage, 1 by default. The crown keeps its spread; the foliage gets thinner (each clump shrinks where it is) down to bare branches at 0. |
| `flowers` | Dots of `color` on the foliage (on the branches when there is no foliage); `amount` from just above 0 (a few) to 1 (the crown is covered). |
| `fruits` | Same, smaller: fruits, cones, berries. |
| `fallen` | Dots of `color` on the ground under the crown: fallen leaves, petals, needles. |

`evergreen` says the tree keeps its foliage in winter: the house view lets snow
settle on it.

## Objects

An object is the sum of its `parts`. Axes: **x** is the width (to the right
when looking at the front), **y** the height (up), **z** the depth, the front
of the object toward **+z**. The origin is on the ground, at the centre of the
footprint: the checks refuse an object whose parts are not centred on it
(within 2 cm), so that it is placed and turned about its middle.

Each part:

| Field | Meaning |
|---|---|
| `shape` | `box`; `cylinder` (upright, `width` and `depth` are its diameters); `sphere` (an ellipsoid of the three sizes); `cone` (upright, point up). |
| `width`, `height`, `depth` | Sizes along x, y and z, before any rotation. |
| `x`, `z` | Centre of the part (0 by default). |
| `elevation` | Height of the bottom of the part above the ground, before any rotation (0 by default). |
| `yaw`, `pitch`, `roll` | Rotations about the centre of the part: `yaw` about y (positive turns the front toward +x), `pitch` about x (positive leans the top toward the front), `roll` about z (positive leans the top toward -x). Applied as `Ry(yaw) · Rx(pitch) · Rz(roll)`, the `YXZ` order of three.js. |
| `color` | Colour of the part. |
| `tint` | `true`: the part takes the colour chosen for the object when it is placed; `color` is then its default one. |

The centre of a part is at `(x, elevation + height / 2, z)`. The size of the
object is the box around its parts (`object_size` in
[`client/house_catalog_rules.py`](../client/house_catalog_rules.py)); a
renderer fitting an object to a piece of furniture of a plan scales that box.

## Shared fields

| Field | Meaning |
|---|---|
| `name` | Name per language; English is mandatory and is the fallback. |
| `icon` | Material Design Icon shown in lists when there is no picture. |
| `keywords` | Words naming the entry in a Sweet Home 3D plan, in any language, in lower case without accents. A plant or a piece of furniture whose name holds one of these words (whole word, case and accents ignored) is drawn with the entry. |

## Pictures

`image.webp` (about 512 px, under 300 KB) and `thumb.webp` (128 px, under
40 KB), transparent background. They are only shown in lists and editors: the
house view never draws them in the scene.
