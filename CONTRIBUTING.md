# Contributing

The [catalog editor](https://github.com/Elwinmage/catalog-editor) is the easy
way once it lists these catalogs: it shows the form of an entry, checks it and
opens the pull request. By hand:

## Add a tree

1. Create `trees/items/<id>/tree.json`, the id in lower case with `-`
   (`cherry-tree`, `silver-birch`), from the English name.
2. Give its `shape`, its sizes for a usual adult tree in a garden, and its
   seasons: all four for a deciduous tree, `summer` at least for an evergreen.
   [doc/format.md](doc/format.md) says what each field means; the entries of
   the catalog are good starting points.
3. Give the `name` in English at least, and the `latin` name.

## Add an object

1. Create `objects/items/<id>/object.json`.
2. List its `parts`, in metres, centred on the footprint of the object, its
   front toward +z. Keep it simple: a dozen parts draw most furniture, and
   the card draws many objects at once.
3. Mark with `"tint": true` the parts that should take the colour chosen when
   the object is placed.

## Add a fish

1. Create `pond_fish/items/<id>/pond_fish.json` (`koi`, `goldfish`).
2. Give its usual adult `length` and the bounds offered in a pond, the shape of
   its `body` (shares of the length), how it swims, and its `varieties`: the
   colour of the body, of the flanks and fins if they differ, and the layers of
   patches over the back.
3. Give the `name` in English at least, the scientific name in `latin`, and
   the names of the varieties.

## Add a kind of path

1. Create `paths/items/<id>/path.json`.
2. Choose the family: `kind: surface` for an unbroken strip (asphalt, gravel,
   decking), `kind: module` for elements set one after another with the ground
   showing between them (stepping stones, sleepers, log rounds).
3. For a surface, give its base `color`, then only what it needs: `grain`,
   `speckles` (with `stretch` for chips and shards), `joints` for a laid
   surface, `wheels` for a grass track. No code is added to the card: the
   texture is painted from these numbers.
4. For modules, give the `shapes` they are taken from, their `size` (along the
   path, then across), `thickness`, `gap`, `colors` and how much they `vary`.
5. Give a `width` (the usual one and the bounds the user may choose within)
   and the `draft` colour the editor draws the path in.

## Add a terrace surface, a wall facing or a fence

1. Create `terraces/items/<id>/terrace.json`, `walls/items/<id>/wall.json` or
   `fences/items/<id>/fence.json`.
2. Describe its `surface` as for a path: a base `color`, then only what it
   needs (`grain`, `speckles`, `joints`). In `joints`, `cell` is the depth of a
   row, then the length of a unit: on a wall or a fence a row is a course, so
   the height of a brick comes first. Choose a `tile` holding a whole number of
   rows and of units (an even number of rows when they are staggered), so the
   texture joins up; `vary` makes the units of a row uneven (coursed rubble).
   For stones of uneven shapes fitted into one another, without rows, set
   `"pattern": "irregular"`: `cell` is then their usual size, `vary` how uneven
   they are, `relief` how much they bulge, and a tile of any size joins up
   (see `doc/format.md`).
3. A terrace takes its `thickness`; a wall may take a `coping`; a fence takes
   its `height` (the usual one and its bounds), its `thickness`, its `posts`,
   and either `open` (see-through: `mesh`, `grid` or `bars`) or `foliage` (a
   hedge), or neither when it is a plain solid fence.
4. Give the `draft` colour the editor draws it in: for a fence, a bright one no
   other fence uses, since it is how the sides are told apart.

## Add a coping

1. Create `copings/items/<id>/coping.json`: what caps a wall, whatever it is
   faced with.
2. Describe its `surface` as above. A row runs along the wall: `cell` gives the
   depth of a row across the wall first, then the length of a unit along the
   wall. A coping is 0.4 m plus twice its `overhang` wide: give the rows at
   least that depth for a single unit across (bricks on edge, slabs), or the
   check warns that a joint runs along the wall.
3. Give its `height` above the top of the wall, its `overhang` on each side
   and, for a folded metal sheet, the `drop` of its edges over the faces.

## Pictures

```
python scripts/render_previews.py <id>
```

draws `image.webp` and `thumb.webp` from the descriptor. You may replace them
by a photo or a drawing **of your own** (transparent background, about 512 px
and under 300 KB; 128 px and under 40 KB for the thumbnail): only pictures you
are allowed to share under CC BY 4.0, nothing copied from a site or a shop.

## Before opening the pull request

```
python scripts/validate.py
pytest
```

The lists of `README.md` are refreshed automatically after the merge: a pull
request only adds the folder of its entry, so that two open pull requests never
conflict on the README.
