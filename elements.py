"""DU element placeholders.

Loads the bundled element catalogue (data/du-elements.json: 522 elements with real
bounding boxes in metres) and drops a correctly-sized proxy box into the scene so you
can reserve space and check fitment. Placeholders are marked ``du_helper`` so the
exporter ignores them.
"""
import json
import os

import bpy
import bpy.utils.previews
import mathutils

from . import extract

_CATALOG = None
# EnumProperty item lists must be kept alive (Blender bug otherwise corrupts strings).
_CAT_ITEMS = None
_ELEM_ITEMS_CACHE = {}
_PREVIEWS = None
_BUNDLED_DIR = os.path.dirname(os.path.abspath(__file__))


def _catalog_file():
    """Extracted cache first, then a bundled data/ file (dev only)."""
    cache = extract.catalog_path()
    if os.path.isfile(cache):
        return cache
    return os.path.join(_BUNDLED_DIR, "data", "du-elements.json")


def _icon_path(key):
    cache = os.path.join(extract.icon_dir(), key + ".png")
    if os.path.isfile(cache):
        return cache
    bundled = os.path.join(_BUNDLED_DIR, "icons", key + ".png")
    return bundled if os.path.isfile(bundled) else None


def reload_catalog():
    """Drop caches so the next access re-reads (after an extraction)."""
    global _CATALOG, _CAT_ITEMS
    _CATALOG = None
    _CAT_ITEMS = None
    _ELEM_ITEMS_CACHE.clear()


def _icon_id(key):
    """Preview icon id for an element key, or 0 if no icon available."""
    global _PREVIEWS
    if _PREVIEWS is None:
        return 0
    if key not in _PREVIEWS:
        path = _icon_path(key)
        if not path:
            return 0
        try:
            _PREVIEWS.load(key, path, "IMAGE")
        except Exception:  # noqa: BLE001 (already loaded / unreadable)
            return 0
    return _PREVIEWS[key].icon_id


def register_previews():
    global _PREVIEWS
    if _PREVIEWS is None:
        _PREVIEWS = bpy.utils.previews.new()


def unregister_previews():
    global _PREVIEWS
    if _PREVIEWS is not None:
        bpy.utils.previews.remove(_PREVIEWS)
        _PREVIEWS = None


def catalog():
    global _CATALOG
    if _CATALOG is None:
        try:
            with open(_catalog_file(), encoding="utf-8") as fh:
                _CATALOG = json.load(fh)
        except Exception:  # noqa: BLE001
            _CATALOG = {}
    return _CATALOG


def has_data():
    return bool(catalog())


def category_items(self, context):
    global _CAT_ITEMS
    cats = sorted({v["category"] for v in catalog().values()})
    _CAT_ITEMS = [(c, c.replace("-", " ").title(), f"{c} elements") for c in cats]
    if not _CAT_ITEMS:
        _CAT_ITEMS = [("none", "(catalog missing)", "")]
    return _CAT_ITEMS


def element_items(self, context):
    cat = getattr(context.scene, "du_elem_category", "")
    items = []
    n = 0
    for key, v in sorted(catalog().items(), key=lambda kv: kv[1].get("name", kv[0])):
        if v["category"] != cat:
            continue
        sx, sy, sz = v["size_m"]
        label = v.get("name", key)
        # 5-tuple form: (id, label, description, icon, unique-number) for template_icon_view
        items.append((key, label, f"{label}  ({sx:g} x {sy:g} x {sz:g} m)", _icon_id(key), n))
        n += 1
    if not items:
        items = [("none", "(no elements)", "", 0, 0)]
    _ELEM_ITEMS_CACHE[cat] = items   # keep alive
    return items


def _element_color(key):
    """Stable distinct colour per element (hashed hue) — visible in Solid shading."""
    import colorsys, hashlib
    h = (int(hashlib.md5(key.encode()).hexdigest(), 16) % 997) / 997.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.55, 0.92)
    return (r, g, b, 1.0)


def _element_material(key):
    """Per-element material: the element's icon as base colour (shown in Material
    Preview), with a distinct per-element viewport colour (shown in Solid)."""
    name = "DU_elem_" + key
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    col = _element_color(key)
    mat.diffuse_color = col                      # Solid-mode (Color=Material) swatch
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    path = _icon_path(key)
    if path:
        try:
            img = bpy.data.images.load(path, check_existing=True)
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = img
            tex.location = (-380, 0)
            if bsdf:
                nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        except Exception:  # noqa: BLE001
            if bsdf:
                bsdf.inputs["Base Color"].default_value = col
    elif bsdf:
        bsdf.inputs["Base Color"].default_value = col
    return mat


def _set_box_uvs(mesh):
    """Map the full icon onto each of the box's 6 quad faces."""
    uv = mesh.uv_layers.new(name="UVMap")
    corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    for poly in mesh.polygons:
        for i, loop_idx in enumerate(poly.loop_indices):
            uv.data[loop_idx].uv = corners[i % 4]


def _box_geometry(sx, sy, sz):
    """Accurate axis-aligned bounding box for the element's real dimensions. This is the
    correct fitment volume — it never under-claims space the way a fitted primitive would."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    verts = [mathutils.Vector((x * hx, y * hy, z * hz))
             for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
             (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return verts, faces


def make_placeholder(context, elem_key):
    entry = catalog().get(elem_key)
    if not entry:
        return None
    sx, sy, sz = entry["size_m"]
    label = entry.get("name", elem_key)
    mesh = bpy.data.meshes.new(label)
    verts, faces = _box_geometry(sx, sy, sz)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    _set_box_uvs(mesh)

    obj = bpy.data.objects.new(label, mesh)
    obj["du_helper"] = "placeholder"
    obj["du_element"] = elem_key
    obj.data.materials.append(_element_material(elem_key))
    obj.color = _element_color(elem_key)   # for Solid shading "Color = Object"
    obj.display_type = "TEXTURED"
    obj.show_name = True
    obj.show_wire = True
    # drop at the 3D cursor so successive adds don't stack on the origin
    obj.location = context.scene.cursor.location.copy()
    context.collection.objects.link(obj)
    return obj
