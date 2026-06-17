"""N-panel UI in the 3D viewport: DU tab."""
import bpy

from . import core_data, elements, materials


class DU_PT_panel(bpy.types.Panel):
    bl_label = "Dual Universe"
    bl_idname = "DU_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DU"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label(text="Core", icon="MESH_CUBE")
        box.prop(scene, "du_core_size", text="Size")
        edge = core_data.core_build_m(scene.du_core_size) if scene.du_core_size != "AUTO" else 0
        if edge:
            box.label(text=f"Build volume: {edge:g} m cube")
        box.operator("du.setup_core", icon="GRID")

        box = layout.box()
        box.label(text="Materials", icon="MATERIAL")
        box.operator("du.make_palette", icon="ADD")
        row = box.row(align=True)
        obj = context.active_object
        if obj and obj.type == "MESH" and obj.active_material:
            c = materials.color_of(obj.active_material)
            box.label(text=f"Active: {c or '(non-DU)'}")

        box = layout.box()
        box.label(text="Element placeholders", icon="OUTLINER_OB_EMPTY")
        if not elements.has_data():
            box.label(text="No element data yet.", icon="INFO")
            box.label(text="Preferences > Extract DU Element Data.")
            box.operator("du.extract_assets", icon="IMPORT")
        else:
            box.prop(scene, "du_elem_category", text="Type")
            box.template_icon_view(scene, "du_elem_name", show_labels=True, scale=6.0, scale_popup=5.0)
            box.prop(scene, "du_elem_name", text="")
            box.operator("du.add_placeholder", icon="ADD")
            box.label(text="Switch to Material Preview to see icons.", icon="SHADING_TEXTURE")
            box.label(text="Dropped at the 3D cursor; not exported.")

        box = layout.box()
        box.label(text="Import / Export", icon="EXPORT")
        box.operator("du.import_epb", icon="IMAGE_DATA", text="Import Empyrion Blueprint")
        box.operator("du.import_epb_file", icon="FILEBROWSER", text="Browse for .epb file…")
        box.operator("du.export_blueprint", icon="FILE_BLEND")


CLASSES = (DU_PT_panel,)
