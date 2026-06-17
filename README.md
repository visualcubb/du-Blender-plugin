# DU Ship Builder — Blender → Dual Universe

Model your Dual Universe ship in Blender and export it straight to a `.blueprint`.
Building in-game is slow; this lets you sculpt the hull in a real 3D tool, paint it,
check element fitment, and import the result.

> ⚠️ **Beta / not pixel-perfect.** The exporter voxelizes your mesh onto DU's 0.25 m grid, so
> the import is a faithful *approximation* of what you model. Cleaning up a few spots
> in-game is still far faster than building the whole shape by hand.

---

## See it in action

**1. Model your ship in Blender** (shown here is a hull brought in via the optional Empyrion
importer — see [Advanced](#advanced-import-an-empyrion-blueprint)):

![A ship in Blender](docs/01-import-epb.png)

**2. Place real DU elements as fitment guides** — every category, with the real in-game
icons and readable names, sized to the actual part dimensions:

![Element categories](docs/02-element-categories.png)
![Element picker with icons and names](docs/03-element-picker.png)

**3. Export, then deploy in Dual Universe:**

![The exported ship in Dual Universe](docs/04-in-dual-universe.png)

---

## Features
- **Pick a core size** (XS–XXXL) and get a correctly-sized build-volume box, with metric
  units (grid snapping optional via the magnet toggle; parts move freely).
- **Choose the construct type** — Dynamic (a ship), Static (a planet-anchored base), or
  Space (a station) — so the blueprint deploys on the right core.
- **Paint with the DU palette** — honeycomb colours mapped to in-game materials.
- **Element placeholders** — drop correctly-sized proxies of any engine, wing, container,
  seat, cannon, fuel tank, etc., with the real in-game icon, to check fitment.
- **One-click export** to a `.blueprint` you import in DU. **1 Blender metre = 1 DU metre.**
- **Hollow interiors** — the export leaves the inside of the hull hollow (keeping a thin solid
  shell), so ships and bases use far less honeycomb without changing how they look.

## Requirements
- **Blender 4.2+** (works on 5.x).
- **Windows** — the `du-blueprint` engine is a Windows `.exe`.
- **`du-blueprint` engine** (the voxelizer/exporter). Download `du-blueprint.exe` from this
  repo's [Releases](../../releases) and note where you save it.
- **Dual Universe installed** — element dimensions and icons are read from your own install
  on first run (nothing is bundled or uploaded).
- *(Optional, for Empyrion import only)* **Node.js** + the **epb-converter** tool — see
  [Advanced](#advanced-import-an-empyrion-blueprint). Not needed to model and export normally.

## Install
1. Download the add-on `.zip` from [Releases](../../releases) (and `du-blueprint.exe` while you're there).
2. Blender → **Edit → Preferences → Add-ons → ▾ → Install from Disk…** → select the zip.
3. Enable **"Dual Universe Blueprint Exporter."**
4. Expand its preferences and set:
   - **du-blueprint executable** → the `du-blueprint.exe` you downloaded.
   - **DU game data folder** → your install's `…/Dual Universe/Game/data` (usually auto-found).
5. Click **Extract DU Element Data** (one time) to build your local element catalogue + icons.

## Quick start
Open the **DU** tab in the 3D viewport sidebar (press **N**):
1. **Core** → choose the **Type** (Dynamic = ship, Static = base, Space = station) and a
   **Size** → **Set Up DU Core** (draws the build box, sets metric units).
   Parts and meshes move freely; toggle the **magnet** for grid snapping when aligning the hull.
2. Model your hull. 1 unit = 1 metre = 1 DU metre.
3. **Materials → Create DU Materials**, assign them to faces (`white/grey/darkgray/black`
   neutrals, `blue/green/red/yellow` accents — all remappable in-game).
4. **Element placeholders** → pick a part from the icon browser → **Add** → position it for fitment.
   (Placeholders are guides only; they aren't exported.)
5. **Export → Export DU Blueprint** → import the `.blueprint` in DU.

## How it works
The add-on writes an OBJ grouped as `o mat_<color>` objects and runs:

```
du-blueprint generate <name>.obj <name>.blueprint -t <dynamic|static|space> --scale 1 -s <core> -n <name>
```

`du-blueprint` dual-contours the mesh, bakes the LOD pyramid, picks/uses the core, assigns
materials, and hollows the interior to a thin solid shell. Coordinates are pre-scaled so the
in-game size matches what you modelled.

## Advanced: import an Empyrion blueprint
The **Import Empyrion Blueprint** button converts an Empyrion ship to a mesh you can edit
and re-export. Click it and the add-on scans your Empyrion library (your own saved ships **and
your downloaded Steam Workshop blueprints**) and shows a **thumbnail gallery** built from each
ship's in-game preview screenshot:

- **Browse a grid of 30 ships at a time** with ◀ / ▶ page buttons, or **type in the search box**
  to filter by name. Click a thumbnail to select it, then press OK to import.
- A progress count shows in the status bar while it scans (libraries with thousands of Workshop
  blueprints can take a moment; press Esc to cancel).
- Imported ships are **scaled ×1.5 by default** (Empyrion blocks are smaller than DU voxels, so
  most ships need roughly 1.5× to fit a real core). Change the factor in the import dialog, or set
  a new default under **Empyrion import scale** in preferences.
- Tick **Separate by block shape** to import one object per Empyrion shape (cubes, ramps, corners,
  …) so you can select and delete whole shapes in the Outliner. (Default off = one object per colour.)
- The Empyrion folder is **auto-detected from Steam**; if it isn't found, set
  **Empyrion install folder** in preferences (or hit Detect).
- Use **Browse for .epb file…** to import an `.epb` from anywhere else instead.

It's optional and needs extra tooling that is **not** bundled here:
- **Node.js** installed, and
- the **epb-converter** tool (a separate project). Set its `src/index.js` path in the add-on
  preferences (it auto-detects if it's somewhere under your home folder).

Without these, the rest of the plugin (model → paint → export) works fine — only import needs them.

## Roadmap
- In-Blender voxel preview ("show me what DU will actually build").
- Snap placeholders to the voxel grid; mount-point hints.
- Write element *placement* into the blueprint (today the export is the voxel hull only).

## Disclaimer & credits
Not affiliated with or endorsed by **Novaquark**. *Dual Universe* and its assets are property
of Novaquark; this tool reads element dimensions and icons from **your own local install** and
does not redistribute them. Voxelization is handled by the **du-blueprint** engine (see its own
project/licence). The Blender add-on is released under the [MIT License](LICENSE).
