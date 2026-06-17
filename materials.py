"""DU material palette as Blender materials.

Each palette material carries a custom property ``du_color`` holding the DU colour
name. On export, faces are grouped into ``o mat_<du_color>`` OBJ objects, which is
exactly what du-blueprint reads. Materials without a ``du_color`` fall back to the
default colour.
"""
import bpy

from . import core_data


def _srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def material_name(color):
    return "DU_" + color


def ensure_palette():
    """Create (or refresh) one Blender material per DU palette entry. Idempotent."""
    created = []
    for color, r, g, b, desc in core_data.DU_PALETTE:
        name = material_name(color)
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name)
            created.append(name)
        mat.use_nodes = True
        mat["du_color"] = color
        mat["du_desc"] = desc
        lin = (_srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b), 1.0)
        # viewport solid colour
        mat.diffuse_color = lin
        # principled base colour (for material/rendered preview)
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = lin
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = 0.6
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = 0.5
    return created


def color_of(material):
    """DU colour name for a Blender material, or None if not a DU palette material."""
    if material is None:
        return None
    c = material.get("du_color")
    if c in core_data.DU_COLOR_NAMES:
        return c
    return None
