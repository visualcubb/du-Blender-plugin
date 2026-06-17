"""Write an OBJ that du-blueprint understands: one ``o mat_<color>`` object per DU
colour, faces grouped underneath, sharing a single vertex pool.

Faces are coloured by their Blender material's ``du_color`` (see materials.py);
anything else falls back to ``core_data.DEFAULT_COLOR``.
"""
import bmesh
import mathutils

from . import core_data, materials

# Blender is Z-up. "up_axis" selects what becomes the OBJ vertical:
#   'Z' -> write raw Blender coords (X, Y, Z)
#   'Y' -> standard OBJ convention (X, Z, -Y)
_AXIS = {
    "Z": lambda v: (v.x, v.y, v.z),
    "Y": lambda v: (v.x, v.z, -v.y),
}


def _eval_tris(obj, depsgraph):
    """Yield (world-space triangle verts, du_color) for a mesh object."""
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        mw = obj.matrix_world
        # map material slot index -> du colour
        slot_color = []
        for slot in obj.material_slots:
            slot_color.append(materials.color_of(slot.material) or core_data.DEFAULT_COLOR)
        if not slot_color:
            slot_color = [core_data.DEFAULT_COLOR]
        for f in bm.faces:
            color = slot_color[min(f.material_index, len(slot_color) - 1)]
            verts = [mw @ v.co for v in f.verts]
            yield verts, color
        bm.free()
    finally:
        eval_obj.to_mesh_clear()


def write_obj(filepath, objects, depsgraph, up_axis="Z", coord_scale=1.0):
    """Write objects to an OBJ grouped by DU colour. Returns per-colour face counts.

    ``coord_scale`` pre-scales coordinates so the in-game size matches the modelled
    size: du-blueprint maps real_DU_metres = obj_units * --scale, so the exporter
    passes coord_scale = 1/scale to make 1 Blender metre = 1 DU metre.
    """
    conv = _AXIS.get(up_axis, _AXIS["Z"])
    verts = []                 # list of (x, y, z)
    groups = {}                # color -> list of (i0, i1, i2) 1-based global indices
    counts = {}
    for obj in objects:
        for tri, color in _eval_tris(obj, depsgraph):
            base = len(verts)
            for co in tri:
                x, y, z = conv(co)
                verts.append((x * coord_scale, y * coord_scale, z * coord_scale))
            groups.setdefault(color, []).append((base + 1, base + 2, base + 3))
            counts[color] = counts.get(color, 0) + 1

    with open(filepath, "w") as fh:
        fh.write("# DU blueprint export (Blender DU plugin)\n")
        fh.write(f"# {len(verts)} verts, colours: {sorted(counts)}\n")
        for x, y, z in verts:
            fh.write(f"v {x:.5f} {y:.5f} {z:.5f}\n")
        for color in sorted(groups):
            fh.write(f"o mat_{color}\n")
            fh.write(f"usemtl mat_{color}\n")
            for a, b, c in groups[color]:
                fh.write(f"f {a} {b} {c}\n")
    return counts


def model_bounds_m(objects, up_axis="Z"):
    """World-space bounding-box edge lengths (Blender metres) of the given objects."""
    conv = _AXIS.get(up_axis, _AXIS["Z"])
    lo = mathutils.Vector((1e18, 1e18, 1e18))
    hi = mathutils.Vector((-1e18, -1e18, -1e18))
    found = False
    for obj in objects:
        for corner in obj.bound_box:
            w = obj.matrix_world @ mathutils.Vector(corner)
            x, y, z = conv(w)
            v = mathutils.Vector((x, y, z))
            lo.x, lo.y, lo.z = min(lo.x, v.x), min(lo.y, v.y), min(lo.z, v.z)
            hi.x, hi.y, hi.z = max(hi.x, v.x), max(hi.y, v.y), max(hi.z, v.z)
            found = True
    if not found:
        return (0.0, 0.0, 0.0)
    return (hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)
