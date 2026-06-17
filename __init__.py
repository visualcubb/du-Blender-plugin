"""Dual Universe blueprint exporter for Blender.

Model a ship at real scale (1 Blender unit = 1 metre), paint with the DU palette,
and export straight to a .blueprint via du-blueprint. See README.md.
"""
bl_info = {
    "name": "Dual Universe Blueprint Exporter",
    "author": "Emerius",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > DU",
    "description": "Model DU ships on a core grid and export to .blueprint",
    "category": "Import-Export",
}

import importlib

from . import core_data, materials, export_obj, extract, elements, preferences, operators, panel

# allow reload from Blender's "Reload Scripts"
for _m in (core_data, materials, export_obj, extract, elements, preferences, operators, panel):
    importlib.reload(_m)

import bpy

_CLASSES = (preferences.DUAddonPreferences,) + operators.CLASSES + panel.CLASSES


def _core_items():
    items = [(name, f"{name} ({core_data.CORE_SIZES[name]:g} m)", f"{name} dynamic core")
             for name in core_data.CORE_ORDER]
    items.append(("AUTO", "Auto", "Let du-blueprint pick the smallest core >= M that fits"))
    return items


def register():
    bpy.types.Scene.du_core_size = bpy.props.EnumProperty(
        name="Core size", items=_core_items(), default="M",
    )
    bpy.types.Scene.du_elem_category = bpy.props.EnumProperty(
        name="Element type", items=elements.category_items,
    )
    bpy.types.Scene.du_elem_name = bpy.props.EnumProperty(
        name="Element", items=elements.element_items,
    )
    elements.register_previews()
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    elements.unregister_previews()
    del bpy.types.Scene.du_core_size
    del bpy.types.Scene.du_elem_category
    del bpy.types.Scene.du_elem_name


if __name__ == "__main__":
    register()
