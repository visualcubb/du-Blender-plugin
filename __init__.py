"""Dual Universe blueprint exporter for Blender.

Model a ship at real scale (1 Blender unit = 1 metre), paint with the DU palette,
and export straight to a .blueprint via du-blueprint. See README.md.
"""
bl_info = {
    "name": "Dual Universe Blueprint Exporter",
    "author": "Emerius",
    "version": (0, 2, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > DU",
    "description": "Model DU ships on a core grid and export to .blueprint",
    "category": "Import-Export",
}

import importlib

from . import (core_data, materials, export_obj, extract, elements, empyrion,
               preferences, operators, panel)

# allow reload from Blender's "Reload Scripts"
for _m in (core_data, materials, export_obj, extract, elements, empyrion,
           preferences, operators, panel):
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
    bpy.types.Scene.du_construct_type = bpy.props.EnumProperty(
        name="Construct", default="dynamic",
        description="What kind of construct to build: a Dynamic core (a ship that flies), "
                    "a Static core (a base anchored to a planet), or a Space core (a "
                    "space station)",
        items=[
            ("dynamic", "Dynamic (ship)", "Movable construct — ships, vehicles"),
            ("static", "Static (base)", "Planet-anchored construct — bases, buildings"),
            ("space", "Space (station)", "Space construct — space stations"),
        ],
    )
    bpy.types.Scene.du_elem_category = bpy.props.EnumProperty(
        name="Element type", items=elements.category_items,
    )
    bpy.types.Scene.du_elem_name = bpy.props.EnumProperty(
        name="Element", items=elements.element_items,
    )
    bpy.types.WindowManager.du_epb_selected = bpy.props.StringProperty(
        name="Selected blueprint", description="Key of the blueprint clicked in the gallery",
    )
    bpy.types.WindowManager.du_epb_page = bpy.props.IntProperty(
        name="Page", default=0, min=0,
    )
    bpy.types.WindowManager.du_epb_search = bpy.props.StringProperty(
        name="Search", description="Filter blueprints by name",
        options={"TEXTEDIT_UPDATE"}, update=empyrion.on_search_update,
    )
    bpy.types.WindowManager.du_epb_show_all = bpy.props.BoolProperty(
        name="Show ships without a preview",
        description="Also list blueprints that have no in-game screenshot (e.g. bundled "
                    "scenario/prefab packs). Off by default to keep the gallery clean",
        default=False, update=empyrion.on_search_update,
    )
    bpy.types.WindowManager.du_epb_fit_only = bpy.props.BoolProperty(
        name="Only ships that fit the core",
        description="Hide blueprints whose size (read from the .epb) is too big for the "
                    "selected core at the current import scale",
        default=False, update=empyrion.on_search_update,
    )
    elements.register_previews()
    empyrion.register_previews()
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    elements.unregister_previews()
    empyrion.unregister_previews()
    del bpy.types.Scene.du_core_size
    del bpy.types.Scene.du_construct_type
    del bpy.types.Scene.du_elem_category
    del bpy.types.Scene.du_elem_name
    del bpy.types.WindowManager.du_epb_selected
    del bpy.types.WindowManager.du_epb_page
    del bpy.types.WindowManager.du_epb_search
    del bpy.types.WindowManager.du_epb_show_all
    del bpy.types.WindowManager.du_epb_fit_only


if __name__ == "__main__":
    register()
