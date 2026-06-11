# Scenario art

Art is **convention, not configuration** — there's nothing to wire up in code. Drop image
files here and they're picked up automatically by `art.py`.

## Layout

```
scenarios/assets/<scenario-id>/
    scene.png          # the wide scene banner shown above the room
    <character>.png    # one avatar per character, named after them (lowercased, slugged)
```

- `<scenario-id>` is the scenario's `id` field — `hero`, `blessing`, … (see each `scenarios/*.py`).
- `<character>` is the character's `name`, slugged: lowercased, non-alphanumerics → `-`.
  So `Korg` → `korg.png`, `Sal "the Whale"` → `sal-the-whale.png`.
- Supported extensions, in order: `.png`, `.jpg`, `.jpeg`, `.webp`.

Any missing file falls back to a generated placeholder (a coloured initial disc for an
avatar, a title card for a scene), so a half-filled folder still runs.

## Example (hero)

```
scenarios/assets/hero/
    scene.png   korg.png   vesh.png   brull.png
```

## Authored scenarios

Create-your-own scenarios get a fresh random `id` each build and so have no folder here —
they use the generated placeholders. To give one permanent art, save it, add it as a
`scenarios/*.py` scenario with a fixed `id`, and drop images in a matching folder here.
