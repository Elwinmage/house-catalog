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
    last one ending at the top. Tapers all the way down (spruce, fir).
  - `columnar`: a column of leafy clumps, as wide near the foot as in the
    middle (`crown_radius`) and narrowing only over the last fifth, where it is
    rounded off. The foliage comes down almost to the ground, so the trunk
    hardly shows (yew, cypress, thuja, Italian poplar).
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

## Paths

A path is laid along a centre line the house view draws, `width.default`
metres wide (the user may change it between `width.min` and `width.max`).
`draft` is the flat bright colour it is drawn in on the overlay of the editor,
where the path is seen from above and is not lit.

`kind` says which of the two families it belongs to, and the object of that
name holds everything else.

### Surfaces

An unbroken strip. Its texture is painted from numbers alone, so adding a
surface to the catalog never calls for a line of code in the card.

| Field | Meaning |
|---|---|
| `color` | Base colour of the strip. |
| `roughness` | 0 polished (wet asphalt), 1 matt (gravel, earth). |
| `tile` | Metres of path covered by one tile of the texture. |
| `grain` | Strength of the speckled noise over the base colour: 0 flat, 1 coarse. |
| `speckles` | Up to four layers of grains, drawn in order: `color`, `amount` (share of the strip they cover), `size` (across, in metres) and `stretch` (1 a pebble, 4 a chip of bark or a shard of slate, laid any way round). |
| `joints` | The units of a laid surface, over their bed of mortar: `color` of the joints, `cell` (one unit along the path, then across it), `width` of a joint, `stagger` (0 lines up, 0.5 a running bond) and `shade` (how much the units differ from one another). |
| `wheels` | Two ruts worn across the width, the surface showing between and beside them: `color`, `bands` (each rut as the share of the width it covers, from one edge) and `speckles` of its own. A surface with ruts is painted across its whole width rather than repeated. |

The number of grains of a layer follows from its `amount` and its `size`: a
layer covering 0.12 of the strip with grains 2.6 cm across is about one grain
per 50 cm². Where they fall is left to the renderer;
`scripts/render_previews.py` (`surface_layer`) is the reference.

### Modules

Elements set one after another along the centre line, the ground showing
between them: stepping stones, landscape sleepers, log rounds. They are the
same family under different numbers -- a sleeper is a long `slab`, a log round
a thick `round`.

| Field | Meaning |
|---|---|
| `shapes` | Shapes an element is taken from: `round` a disc, `half-moon` a disc of the width of the path cut through the middle (so half as deep as it is wide), `slab` a rectangle with rounded corners, `oval` an ellipse, `stone` an irregular slab. |
| `size` | One element in metres: along the path, then across it. |
| `thickness` | How far it stands over the ground. |
| `gap` | Ground left between two elements; a stride is about 0.6 m from one stepping stone to the next. |
| `colors` | Colours an element is taken from. |
| `vary` | How much the elements differ: `size` (share gained or lost), `angle` (turned off the line, in turns), `side` (set off the centre line, as a share of the width) and `shade` (lightened or darkened). |

Which shape, colour and variation each element gets is left to the renderer,
from a seed of its own, so a path keeps its look while no two elements are
quite alike; `scripts/render_previews.py` (`module_elements`) is the
reference.

## Painted surfaces

Terraces, walls, copings and fences share one `surface`, the same painted texture as
the `surface` of a path without its wheel ruts: no picture is shipped, the
renderer paints a tile of it from these numbers.

| Field | Meaning |
|---|---|
| `color` | Base colour. The user may give a terrace, a wall or a side of a fence a colour of his own: the grains then keep their contrast with it (each is shifted as the base colour was). |
| `roughness` | 0 polished (glazed tiles), 1 matt (render, raw wood). |
| `tile` | Metres covered by one tile of the texture. A whole number of rows and of units in it keeps the tiles joining up; an even number of rows when they are staggered. |
| `grain` | Strength of the speckled noise over the base colour: 0 flat, 1 coarse. |
| `speckles` | Up to four layers of grains, as on a path: `color`, `amount`, `size`, `stretch`. |
| `joints` | The units the surface is laid in: `color` of the joints, `pattern` (`rows`, or `irregular` for stones of uneven shapes fitted into one another), `cell` (the depth of a row, then the length of a unit along it), `width` of a joint, `stagger` (0 lines up, 0.5 a running bond), `shade` (how much the units differ in colour), `vary` (how much the units of a row differ in length: 0 for tiles and bricks, 0.5 for the stones of a coursed rubble wall), `tints` (other colours a share of the units take: `color`, `amount`) and `relief` (how much an irregular stone bulges). |

With `vary`, the lengths of the units of a row are drawn first, then fitted to
the width of the tile, so the texture still joins up from one tile to the
next. `scripts/render_previews.py` (`_paint_joints`) is the reference.

With the `irregular` pattern there are no rows: the wall of a garden built of
stones as they came, a crazy paving. `cell` is then the usual size of a stone
(its height first on a wall, then its length) and `vary` how uneven the stones
are, from much alike (0) to small ones wedged between large blocks (0.8);
`stagger` is not read. The stones are drawn around middles scattered over the
tile, each one taking all that lies nearer to its middle than to any other,
less half a joint: they fit into one another whatever their shapes, and a tile
of any size joins up with the next (it should hold at least two stones each
way, or the same ones show side by side). `relief` leaves the lower right side
of each stone in shade, as rough blocks are, and `tints` gives a share of the
stones another colour: the ochre ones of a grey limestone wall. A dark `color`
of joints with a narrow `width` is a dry stone wall, a pale one with a wider
`width` a pointed one. The reference is `_paint_stones`.

## Terraces

A terrace is laid flat over the outline the house view draws for it (a
rectangle or a free shape), at one altitude, the ground levelled under it.
`thickness` is how far its top stands over that ground: a few centimetres for
tiles, more for a deck on joists. The user may change it.

The texture is laid in the frame of the terrace: a row of the `surface` runs
along the laying direction the user gives it (the first side of the outline by
default), so a decking board -- a long unit in a narrow row -- follows it.
Where a pool is drawn inside the terrace, the terrace is cut out around it.

## Walls

A wall is the facing of a low wall or of a retaining wall, drawn along a line
between two altitudes (its top and its foot, which may both differ from one
end of the wall to the other).

- The `surface` is seen on the upright faces. A row is a course: `cell` gives
  the height of a stone or of a brick first, then its length along the wall.
- `coping` is the capping laid on top: its `color`, its `height` and the
  `overhang` by which it juts out on each side. Without it the top has the
  colour of the faces.

## Copings

A coping caps a wall, whatever the wall is faced with: the user picks one for a
wall in place of the capping of its facing (or on a facing that has none), and
may give it a colour of his own.

| Field | Meaning |
|---|---|
| `name`, `icon` | As for every entry. No `draft`: a coping is not drawn on the overlay of the editor. |
| `surface` | What it is made of, seen on its top and on its edges. A row of its units runs along the wall: `cell` gives the depth of a row, across the wall, first, then the length of a unit along the wall. |
| `height` | Height above the top of the wall (m, 0.05 by default). |
| `overhang` | How far it juts out on each side of the wall (m, 0.03 by default). |
| `drop` | How far its edges come down over the faces of the wall (m, 0 by default): the folded edges of a metal coping. |

The walls of the house view are 0.4 m thick: a coping is 0.4 m plus twice its
`overhang` wide. A row deeper than that gives one unit across the wall -- a
brick laid on edge, a slab -- with no joint running along it: the texture
starts at one edge of the coping, so the first row covers its whole width. A
`drop` needs an `overhang`, or the edges would lie in the faces of the wall.
`scripts/render_previews.py` (`coping_picture`) draws it on a piece of plain
wall, seen from the front and a little from above.

## Fences

A fence follows a line on the ground, side by side; every side has a kind, a
height and, if the user gives it one, a colour of its own. The side of a wall
may carry a coping as well.

| Field | Meaning |
|---|---|
| `height` | The height a side gets when the kind is chosen (`default`) and the bounds offered. |
| `thickness` | 0 for a sheet (wire mesh, welded panel); otherwise a box that thick, sunk a little so that it leaves no gap on a slope. |
| `surface` | What it is made of. A row of its units is a course, as on a wall: vertical boards are units as tall as the fence and as wide as a board. |
| `open` | A see-through fence: only the colour of the surface is used, for wires or bars drawn on nothing. `pattern` is `mesh` (wire netting in diamonds, `pitch` being the side of a diamond), `grid` (upright wires every `pitch`, a level one every four of them: a rigid welded panel) or `bars` (upright bars every `pitch`, between two rails at 14 % and 86 % of the height). `fill` is the share of the sheet covered: a mesh and a grid have two sets of wires, each `pitch * fill / 2` wide; a bar is `pitch * fill` wide. |
| `posts` | Posts along the fence, one every `spacing` and one at each end: their `color` and their `size` (they stand a little over the fence). |
| `foliage` | A hedge: its top is uneven and its faces are faceted, as clipped foliage is. Never with `open`. |
| `coping` | A wall a coping can be laid on: the user caps each of its sides with an entry of the [copings](#copings), in a colour of his own if he wishes, or leaves it bare. The coping is wider than the wall by its `overhang` on each side, goes past the free ends of the wall by as much, and covers the corner two capped sides share. Only a solid fence at least 0.1 m thick: never with `open` or `foliage`. |
| `draft` | Colour of a side on the overlay of the editor. No two fences share it. |

`scripts/render_previews.py` (`open_lines`, `fence_panel`) is the reference.

## Shared fields

| Field | Meaning |
|---|---|
| `name` | Name per language; English is mandatory and is the fallback. |
| `icon` | Material Design Icon shown in lists when there is no picture. |
| `latin` | Botanical or scientific name of a tree or a fish, unique in its section. |
| `width` | A length in metres offered to the user: the usual one (`default`) and the bounds (`min`, `max`). |
| `keywords` | Words naming the entry in a Sweet Home 3D plan, in any language, in lower case without accents. A plant or a piece of furniture whose name holds one of these words (whole word, case and accents ignored) is drawn with the entry. |

## Pictures

`image.webp` (about 512 px, under 300 KB) and `thumb.webp` (128 px, under
40 KB), transparent background. They are only shown in lists and editors: the
house view never draws them in the scene.
