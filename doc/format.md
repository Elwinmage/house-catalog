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
  - `weeping`: a low dome in the upper part of the box, and ten curtains of
    branches hanging from its rim (0.85 of `crown_radius`) down to the trunk,
    some longer than others (weeping willow). Thinner foliage shortens the
    curtains too, down to bare branches.
  - `palm`: a bare slender trunk, a little thicker at its foot, up to the top of
    the tree, and nine fronds around it that leave the top, rise a little and
    droop (date palm, coconut palm). `trunk.height` is the height of the bare
    trunk, so the tuft is `crown_radius` wide above it.
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

### Varieties

`varieties` lists the colours a tree comes in when it is planted: each one has
an `id`, a `name`, and a colour of its `flowers` and/or of its `fruits` (at
least one). A variety replaces the colour of the blossom or of the fruits in
every season that shows some; `seasons` keeps saying how many there are and
when. A tree planted without choosing a variety has the colours of `seasons`.
The card offers each variety as a species of its own (`<id>:<variety>`), so a
view can hold a red apple tree next to a yellow one.

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

## Fish

A fish is drawn by the renderer from its sizes; every fish of a pond gets a
robe of its own, drawn from its variety. Lengths are shares of the length of
the fish, `length` being in metres (snout to the end of the tail).

```
   tail fin          body                head
   ◁───────┤▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▶   seen from above
   body.tail          body.width at its widest
```

- The **body** goes from the root of the tail to the snout: narrow at the
  tail, widest a little ahead of its middle (`body.width`), rounded at the
  head; `body.height` is its height seen from the side. The **tail fin**,
  `body.tail` long, fans out behind it; `body.fins` says whether the fins are
  `short` or `long` and flowing (butterfly koi).
- `swim` tells how it moves: its cruising `speed` (m/s), the `depth` it keeps
  in warm water (`surface`, `middle`, `bottom`; every fish goes down in cold
  water), and whether it swims in a `school`.

### Varieties

Each variety gives the colour of the body (`base`), of the flanks and belly
(`belly`, the base colour by default) and of the fins (`fins`), `metallic`
for shiny scales, and up to four layers of `patches` drawn in order over the
back:

| Field | Meaning |
|---|---|
| `color` | Colour of the patches of the layer. |
| `amount` | Share of the back they cover together, just above 0 to 1. |
| `size` | `small` spots, `medium` patches (the default) or `large` ones: the same amount is spread over more or fewer patches. |
| `where` | `anywhere` on the back, `back` (behind the head), or `head`: one round patch on the head (tancho koi). |

Where the patches fall is left to the renderer, from a seed of its own for
each fish, so that two fish of a variety are never alike but one fish keeps
its robe; `scripts/render_previews.py` (`fish_patches`) is the reference.

## Shared fields

| Field | Meaning |
|---|---|
| `name` | Name per language; English is mandatory and is the fallback. |
| `icon` | Material Design Icon shown in lists when there is no picture. |
| `latin` | Botanical or scientific name of a tree or a fish, unique in its section. |
| `keywords` | Words naming the entry in a Sweet Home 3D plan, in any language, in lower case without accents. A plant or a piece of furniture whose name holds one of these words (whole word, case and accents ignored) is drawn with the entry. |

## Pictures

`image.webp` (about 512 px, under 300 KB) and `thumb.webp` (128 px, under
40 KB), transparent background. They are only shown in lists and editors: the
house view never draws them in the scene.
