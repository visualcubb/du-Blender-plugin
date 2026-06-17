"""Extract DU element data (bounding boxes + icons) from the user's local DU install.

We do NOT redistribute Novaquark's assets. On first run the user points the add-on at
their installed game data and clicks Extract; this writes a catalogue + icons into a
writable cache directory that the rest of the add-on reads.

Element bbox: each element mesh starts with magic 'ms11' + AABB min(3 f32) + max(3 f32).
The '_col.mesh' (collision hull) is preferred; the readable name comes from the def's
internal element key (camelCase -> words).
"""
import glob
import json
import os
import re
import shutil
import struct

import bpy

SIZES = ("_xs", "_s", "_m", "_l", "_xl", "_xxl", "_xxxl")
DEFAULT_DATA_PATH = r"C:\ProgramData\My Dual Universe\Game\data"


def cache_dir():
    """Writable per-user cache for extracted assets."""
    return bpy.utils.user_resource("DATAFILES", path="du_ship_builder", create=True)


def catalog_path():
    return os.path.join(cache_dir(), "du-elements.json")


def icon_dir():
    d = os.path.join(cache_dir(), "icons")
    os.makedirs(d, exist_ok=True)
    return d


def elements_root(data_path):
    return os.path.join(data_path, "resources_generated", "elements")


def is_valid_data_path(data_path):
    return bool(data_path) and os.path.isdir(elements_root(data_path))


def _read_aabb(path):
    try:
        with open(path, "rb") as fh:
            head = fh.read(28)
    except OSError:
        return None
    if len(head) < 28 or head[:4] != b"ms11":
        return None
    mn = struct.unpack("<3f", head[4:16])
    mx = struct.unpack("<3f", head[16:28])
    if any(mx[i] < mn[i] for i in range(3)) or any(abs(v) > 1e4 for v in mn + mx):
        return None
    return mn, mx


def _display_name(elem_dir, elem_key):
    defp = os.path.join(elem_dir, "defs", "env_" + elem_key + ".nqdef")
    name = None
    if os.path.isfile(defp):
        try:
            with open(defp, encoding="utf-8") as fh:
                keys = list(json.load(fh).get("elements", {}).keys())
            if keys:
                name = keys[0]
        except Exception:  # noqa: BLE001
            pass
    raw = name or elem_key
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)
    s = re.sub(r"(?<=[A-Za-z])(?=[0-9])", " ", s)
    s = s.replace("-", " ").replace("_", " ")
    return " ".join(w for w in s.split() if w).title()


def extract(data_path, copy_icons=True):
    """Build the catalogue + icons in the cache. Returns (n_elements, n_icons)."""
    root = elements_root(data_path)
    if not os.path.isdir(root):
        raise FileNotFoundError(root)

    # prefer _col.mesh, fall back to .mesh, one per element dir
    chosen = {}
    for p in glob.glob(os.path.join(root, "**", "*_col.mesh"), recursive=True):
        chosen[os.path.dirname(p)] = p
    for p in glob.glob(os.path.join(root, "**", "*.mesh"), recursive=True):
        if not p.endswith("_col.mesh"):
            chosen.setdefault(os.path.dirname(p), p)

    out = {}
    idir = icon_dir()
    n_icons = 0
    for meshpath in chosen.values():
        aabb = _read_aabb(meshpath)
        if not aabb:
            continue
        parts = meshpath.replace("\\", "/").split("/")
        try:
            i = parts.index("elements")
        except ValueError:
            continue
        category, elem_key = parts[i + 1], parts[i + 2]
        elem_dir = os.path.dirname(os.path.dirname(meshpath))
        size = next((s[1:] for s in SIZES if elem_key.endswith(s)), "")
        mn, mx = aabb
        out[elem_key] = {
            "category": category,
            "size": size,
            "name": _display_name(elem_dir, elem_key),
            "size_m": [round(mx[k] - mn[k], 3) for k in range(3)],
        }
        if copy_icons:
            cands = glob.glob(os.path.join(elem_dir, "icons", "*icon*.png"))
            if cands:
                try:
                    shutil.copyfile(cands[0], os.path.join(idir, elem_key + ".png"))
                    n_icons += 1
                except OSError:
                    pass

    with open(catalog_path(), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    return len(out), n_icons
