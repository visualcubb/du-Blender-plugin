"""Locate Empyrion blueprints on disk and build a thumbnail gallery for import.

Empyrion stores each blueprint as a folder containing ``<Name>.epb`` and a
``<Name>.jpg`` preview screenshot, in two places:
  * your own saved ships:  ``<Empyrion install>/Saves/Blueprints/<SteamID>/<Name>/``
  * Steam Workshop downloads:  ``<library>/steamapps/workshop/content/383120/<id>/``

We discover both, then expose them as an EnumProperty with preview icons so the
importer can show a searchable icon gallery. There can be thousands of Workshop
blueprints, so the full list is built once and the gallery shows a capped, filtered
subset (type to search) with thumbnails loaded lazily only for what's displayed.
"""
import os
import re
import struct

import bpy
import bpy.utils.previews

EMPYRION_APPID = "383120"
GRID_COLUMNS = 4        # thumbnails per row in the gallery
GRID_ROWS = 3           # rows per page  ->  12 ships visible at once (bigger images)
PER_PAGE = GRID_COLUMNS * GRID_ROWS
THUMB_SCALE = 9.0       # template_icon size (UI units)

_PREVIEWS = None
_BP_ALL = None          # full list [(key, name, epb, preview)]
_BP_INDEX = {}          # key -> .epb path
_BP_PREV = {}           # key -> preview-image path (or None)
_BP_ITEMS = None        # last returned EnumProperty items (kept alive)

COMMON_EMPYRION = (
    r"C:\Program Files (x86)\Steam\steamapps\common\Empyrion - Galactic Survival",
    r"C:\Program Files\Steam\steamapps\common\Empyrion - Galactic Survival",
)


def register_previews():
    global _PREVIEWS
    if _PREVIEWS is None:
        _PREVIEWS = bpy.utils.previews.new()


def unregister_previews():
    global _PREVIEWS
    if _PREVIEWS is not None:
        bpy.utils.previews.remove(_PREVIEWS)
        _PREVIEWS = None


def _steam_root():
    try:
        import winreg
        for hive, key, name in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        ):
            try:
                with winreg.OpenKey(hive, key) as k:
                    val, _ = winreg.QueryValueEx(k, name)
                    if val:
                        return os.path.normpath(val)
            except OSError:
                continue
    except Exception:  # noqa: BLE001 (winreg missing on non-Windows)
        pass
    return None


def _steam_libraries():
    """All Steam library roots (handles games installed on a second drive)."""
    roots, seen = [], set()
    cands = []
    sr = _steam_root()
    if sr:
        cands.append(sr)
    cands += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    for c in cands:
        c = os.path.normpath(c)
        key = os.path.normcase(c)            # case-insensitive on Windows
        if key in seen or not os.path.isdir(c):
            continue
        seen.add(key)
        roots.append(c)
        vdf = os.path.join(c, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            try:
                with open(vdf, encoding="utf-8", errors="ignore") as fh:
                    txt = fh.read()
                for m in re.finditer(r'"path"\s*"([^"]+)"', txt):
                    p = os.path.normpath(m.group(1).replace("\\\\", "\\"))
                    pk = os.path.normcase(p)
                    if pk not in seen and os.path.isdir(p):
                        seen.add(pk)
                        roots.append(p)
            except OSError:
                pass
    return roots


def autodetect_empyrion():
    """Best-effort path to the Empyrion install folder, or ''."""
    for lib in _steam_libraries():
        p = os.path.join(lib, "steamapps", "common", "Empyrion - Galactic Survival")
        if os.path.isdir(p):
            return p
    for p in COMMON_EMPYRION:
        if os.path.isdir(p):
            return p
    return ""


def _saves_root(empyrion_path):
    """Folder under which the player's own saved blueprints live."""
    if not empyrion_path:
        return ""
    p = os.path.normpath(bpy.path.abspath(empyrion_path))
    for c in (os.path.join(p, "Saves", "Blueprints"),
              os.path.join(p, "Blueprints"),
              p):
        if os.path.isdir(c):
            return c
    return ""


def _workshop_roots(empyrion_path):
    """Steam Workshop content folders for Empyrion (downloaded blueprints)."""
    roots = []
    if empyrion_path:
        p = os.path.normpath(bpy.path.abspath(empyrion_path))
        parts = p.split(os.sep)
        low = [x.lower() for x in parts]
        if "steamapps" in low:
            sa = os.sep.join(parts[: low.index("steamapps") + 1])
            roots.append(os.path.join(sa, "workshop", "content", EMPYRION_APPID))
    for lib in _steam_libraries():
        roots.append(os.path.join(lib, "steamapps", "workshop", "content", EMPYRION_APPID))
    out, seen = [], set()
    for r in roots:
        r = os.path.normpath(r)
        key = os.path.normcase(r)
        if key not in seen and os.path.isdir(r):
            seen.add(key)
            out.append(r)
    return out


def _scan_roots(empyrion_path):
    roots = []
    saves = _saves_root(empyrion_path)
    if saves:
        roots.append(saves)
    roots += _workshop_roots(empyrion_path)
    return roots


def scan_iter(empyrion_path, batch=400):
    """Incrementally index saved + Workshop blueprints, rebuilding the module state as
    it goes. Yields the running count every ``batch`` files so a modal caller can show
    progress; ``return`` (StopIteration.value) is the final count.

    Uses ``os.walk`` and the already-listed directory contents to find each ship's
    same-name preview, so no per-file disk stats are needed (fast on huge libraries)."""
    global _BP_ALL, _BP_INDEX, _BP_PREV, _BP_ITEMS
    register_previews()
    _BP_ALL, _BP_INDEX, _BP_PREV, _BP_ITEMS = [], {}, {}, None
    _SIZE_CACHE.clear()
    keys = set()
    seen_epb = set()        # guard against the same file via overlapping roots
    processed = 0
    for root in _scan_roots(empyrion_path):
        for dirpath, _dirs, filenames in os.walk(root):
            fileset = {f.lower() for f in filenames}
            for fn in filenames:
                if not fn.lower().endswith(".epb"):
                    continue
                name = fn[:-4]
                epb = os.path.join(dirpath, fn)
                epb_key = os.path.normcase(os.path.abspath(epb))
                if epb_key in seen_epb:
                    continue
                seen_epb.add(epb_key)
                prev = None
                for ext in (".jpg", ".jpeg", ".png"):
                    if (name + ext).lower() in fileset:
                        prev = os.path.join(dirpath, name + ext)
                        break
                rel = os.path.splitext(os.path.relpath(epb, root))[0]
                key = re.sub(r"[^A-Za-z0-9]+", "_", rel).strip("_") or name
                while key in keys:
                    key += "_"
                keys.add(key)
                _BP_ALL.append((key, name, epb, prev))
                _BP_INDEX[key] = epb
                _BP_PREV[key] = prev
                processed += 1
                if processed % batch == 0:
                    yield processed
    _BP_ALL.sort(key=lambda t: t[1].lower())
    return processed


def refresh(empyrion_path):
    """Synchronous index rebuild (drains scan_iter). Returns the blueprint count."""
    gen = scan_iter(empyrion_path)
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value if stop.value is not None else len(_BP_ALL)


def _icon_for(key):
    """Lazily load a blueprint's preview thumbnail; returns an icon id (0 if none)."""
    if _PREVIEWS is None:
        return 0
    prev = _BP_PREV.get(key)
    if not prev:
        return 0
    try:
        if key not in _PREVIEWS:
            _PREVIEWS.load(key, prev, "IMAGE")
        return _PREVIEWS[key].icon_id
    except Exception:  # noqa: BLE001 (unreadable / duplicate)
        return 0


def _filtered(context):
    """Blueprints matching the current gallery filters (search + preview toggle).
    Whole list, no paging."""
    if _BP_ALL is None:
        from . import preferences
        try:
            refresh(preferences.prefs(context).empyrion_path)
        except Exception:  # noqa: BLE001
            pass
    wm = context.window_manager
    pool = _BP_ALL or []
    # by default hide imageless prefab/scenario packs (no in-game screenshot)
    if not getattr(wm, "du_epb_show_all", False):
        pool = [t for t in pool if t[3]]          # t[3] = preview path
    # optionally hide ships that won't fit the selected core
    if getattr(wm, "du_epb_fit_only", False):
        from . import core_data, preferences
        scn = context.scene
        if scn.du_core_size != "AUTO":
            build = core_data.core_build_m(scn.du_core_size)
            sc = preferences.prefs(context).epb_import_scale
            pool = [t for t in pool if fits_core(t[2], sc, build)]   # t[2] = epb path
    search = (getattr(wm, "du_epb_search", "") or "").strip().lower()
    if search:
        pool = [t for t in pool if search in t[1].lower()]
    return pool


def counts():
    """(with_preview, total) across the whole index."""
    pool = _BP_ALL or []
    return sum(1 for t in pool if t[3]), len(pool)


def page_view(context, per_page):
    """Return (page_items, page, n_pages, total) for the gallery grid. ``page_items``
    are (key, name, epb, icon_id) with thumbnails loaded only for this page."""
    pool = _filtered(context)
    total = len(pool)
    n_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(getattr(context.window_manager, "du_epb_page", 0), n_pages - 1))
    start = page * per_page
    items = [(k, name, epb, _icon_for(k))
             for (k, name, epb, _prev) in pool[start:start + per_page]]
    return items, page, n_pages, total


def name_for(key):
    for k, name, _e, _p in (_BP_ALL or []):
        if k == key:
            return name
    return ""


# --- ship size (read straight from the .epb header) -------------------------
# EPB header: magic(u32 LE)=0x78945245, version(i32), type(u8), w/h/d(i32 each).
# Empyrion block sizes: SV/HV = 0.5 m, Base/CV/Voxel = 2 m. The converter writes
# the OBJ in Empyrion metres, and the add-on then scales by the import scale, so
# DU metres = blocks * block_size * import_scale.
_EPB_MAGIC = 0x78945245
_BLOCK_SIZE_M = {0: 2.0, 2: 2.0, 4: 0.5, 8: 2.0, 16: 0.5}   # by type id
_SIZE_CACHE = {}


def _read_epb_dims(epb):
    """(type_id, w, h, d) in blocks from the .epb header, or None."""
    try:
        with open(epb, "rb") as fh:
            head = fh.read(21)
    except OSError:
        return None
    if len(head) < 21 or struct.unpack_from("<I", head, 0)[0] != _EPB_MAGIC:
        return None
    typ = head[8]
    w, h, d = struct.unpack_from("<iii", head, 9)
    if min(w, h, d) < 0 or max(w, h, d) > 100000:
        return None
    return typ, w, h, d


def du_size_m(epb, import_scale):
    """Estimated (x, y, z) size in DU metres after import, or None if unreadable."""
    if not epb:
        return None
    dims = _SIZE_CACHE.get(epb)
    if dims is None:
        dims = _read_epb_dims(epb) or False
        _SIZE_CACHE[epb] = dims
    if not dims:
        return None
    typ, w, h, d = dims
    f = _BLOCK_SIZE_M.get(typ, 2.0) * float(import_scale)
    return (w * f, h * f, d * f)


def fits_core(epb, import_scale, build_m):
    """True if the ship's largest dimension fits inside the core's build cube.
    Unknown sizes are treated as fitting (don't hide them)."""
    s = du_size_m(epb, import_scale)
    if not s:
        return True
    return max(s) <= build_m + 1e-6


def on_search_update(self, context):
    """Reset to page 0 whenever the search text changes."""
    try:
        context.window_manager.du_epb_page = 0
    except Exception:  # noqa: BLE001
        pass


def epb_path_for(key):
    return _BP_INDEX.get(key)


def has_blueprints():
    return bool(_BP_INDEX)
