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
