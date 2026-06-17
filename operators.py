"""Operators: set up a core build volume, refresh the palette, and export to .blueprint."""
import math
import os
import subprocess
import tempfile

import bpy
import mathutils

from . import core_data, elements, export_obj, extract, materials, preferences

CORE_BOX_NAME = "DU_CoreVolume"
FRONT_ARROW_NAME = "DU Front (aim +Y)"


def _scene_mesh_objects(context):
    """Exportable meshes: visible mesh objects that are NOT the core box or placeholders."""
    out = []
    for obj in context.scene.objects:
        if obj.type != "MESH":
            continue
        if obj.get("du_helper"):       # core box / placeholders
            continue
        if not obj.visible_get():
            continue
        out.append(obj)
    return out


class DU_OT_setup_core(bpy.types.Operator):
    bl_idname = "du.setup_core"
    bl_label = "Set Up DU Core"
    bl_description = "Create the build-volume guide box for the chosen core and set metric/0.25 m snapping"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        size_name = scene.du_core_size
        edge = core_data.core_build_m(size_name)

        # metric units, 0.25 m grid snap
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0
        ts = context.tool_settings
        ts.use_snap = True
        if "INCREMENT" not in ts.snap_elements:
            ts.snap_elements = {"INCREMENT"}

        # (re)build the wireframe build-volume box centred on origin
        old = bpy.data.objects.get(CORE_BOX_NAME)
        if old:
            bpy.data.objects.remove(old, do_unlink=True)
        mesh = bpy.data.meshes.new(CORE_BOX_NAME)
        h = edge / 2.0
        verts = [mathutils.Vector((x * h, y * h, z * h))
                 for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
        edges = [(0, 1), (0, 2), (1, 3), (2, 3), (4, 5), (4, 6), (5, 7), (6, 7),
                 (0, 4), (1, 5), (2, 6), (3, 7)]
        mesh.from_pydata(verts, edges, [])
        mesh.update()
        box = bpy.data.objects.new(CORE_BOX_NAME, mesh)
        box["du_helper"] = "core"
        box.hide_select = True
        box.display_type = "WIRE"
        context.collection.objects.link(box)

        # orientation indicator: DU "front" = +Y (aim direction), up = +Z.
        # Model the ship's nose toward this arrow so it aims horizontally in DU.
        old_arrow = bpy.data.objects.get(FRONT_ARROW_NAME)
        if old_arrow:
            bpy.data.objects.remove(old_arrow, do_unlink=True)
        arrow = bpy.data.objects.new(FRONT_ARROW_NAME, None)
        arrow.empty_display_type = "SINGLE_ARROW"
        arrow.empty_display_size = edge * 0.65
        arrow.rotation_euler = (math.radians(-90), 0.0, 0.0)  # +Z arrow -> points +Y (front)
        arrow["du_helper"] = "front"
        arrow.show_name = True
        arrow.hide_select = True
        context.collection.objects.link(arrow)

        materials.ensure_palette()
        self.report({"INFO"},
                    f"{size_name} core: {edge:g} m build volume. Nose toward the +Y 'front' arrow.")
        return {"FINISHED"}


class DU_OT_make_palette(bpy.types.Operator):
    bl_idname = "du.make_palette"
    bl_label = "Create DU Materials"
    bl_description = "Create the DU honeycomb palette as Blender materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        created = materials.ensure_palette()
        self.report({"INFO"}, f"DU palette ready ({len(created)} new).")
        return {"FINISHED"}


class DU_OT_export_blueprint(bpy.types.Operator):
    bl_idname = "du.export_blueprint"
    bl_label = "Export DU Blueprint"
    bl_description = "Write an OBJ from the scene and run du-blueprint to produce a .blueprint"
    bl_options = {"REGISTER"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filename_ext = ".blueprint"
    filter_glob: bpy.props.StringProperty(default="*.blueprint", options={"HIDDEN"})

    def invoke(self, context, event):
        if not self.filepath:
            base = bpy.path.basename(bpy.data.filepath) or "ship"
            base = os.path.splitext(base)[0]
            self.filepath = base + ".blueprint"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        pr = preferences.prefs(context)
        exe = bpy.path.abspath(pr.exe_path)
        if not exe or not os.path.isfile(exe):
            self.report({"ERROR"}, "du-blueprint.exe not set (Add-on Preferences).")
            return {"CANCELLED"}

        objs = _scene_mesh_objects(context)
        if not objs:
            self.report({"ERROR"}, "No exportable mesh objects in the scene.")
            return {"CANCELLED"}

        bp_path = bpy.path.abspath(self.filepath)
        if not bp_path.endswith(".blueprint"):
            bp_path += ".blueprint"
        obj_path = os.path.splitext(bp_path)[0] + ".obj"

        # 1 Blender metre -> 1 DU metre: real_DU_m = obj_units * scale, so pre-scale by 1/scale
        coord_scale = 1.0 / pr.scale
        depsgraph = context.evaluated_depsgraph_get()
        counts = export_obj.write_obj(obj_path, objs, depsgraph, up_axis=pr.du_up_axis,
                                      coord_scale=coord_scale)
        dims = export_obj.model_bounds_m(objs, up_axis=pr.du_up_axis)

        name = os.path.splitext(os.path.basename(bp_path))[0]
        cmd = [exe, "generate", obj_path, bp_path,
               "-t", "dynamic", "--scale", str(pr.scale), "-n", name]
        # honour the chosen core size (>= M); omit for auto if set to AUTO.
        # du-blueprint expects a lowercase size token (m/l/xl/...).
        if context.scene.du_core_size != "AUTO":
            cmd += ["-s", context.scene.du_core_size.lower()]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, f"du-blueprint failed to launch: {exc}")
            return {"CANCELLED"}

        if res.returncode != 0:
            msg = (res.stderr or res.stdout or "").strip().splitlines()
            self.report({"ERROR"}, "du-blueprint error: " + (msg[-1] if msg else "unknown"))
            print("\n".join(msg))
            return {"CANCELLED"}

        print(res.stdout)
        print(res.stderr)
        self.report(
            {"INFO"},
            f"Wrote {os.path.basename(bp_path)}  |  model {dims[0]:.1f}x{dims[1]:.1f}x{dims[2]:.1f} m, "
            f"colours: {dict(counts)}",
        )
        return {"FINISHED"}


class DU_OT_add_placeholder(bpy.types.Operator):
    bl_idname = "du.add_placeholder"
    bl_label = "Add Element Placeholder"
    bl_description = "Drop a correctly-sized proxy box for a DU element (for fitment; not exported)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        key = context.scene.du_elem_name
        if not key or key == "none":
            self.report({"ERROR"}, "Pick a category and element first.")
            return {"CANCELLED"}
        obj = elements.make_placeholder(context, key)
        if obj is None:
            self.report({"ERROR"}, f"Element '{key}' not in catalog.")
            return {"CANCELLED"}
        # switch the 3D viewport to Material Preview so the element icon is visible
        # (only upgrade from Solid/Wireframe; don't downgrade a Rendered view)
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D" and space.shading.type in {"SOLID", "WIREFRAME"}:
                        space.shading.type = "MATERIAL"
        entry = elements.catalog()[key]
        sx, sy, sz = entry["size_m"]
        self.report({"INFO"}, f"Placeholder '{key}'  {sx:g} x {sy:g} x {sz:g} m (at 3D cursor).")
        return {"FINISHED"}


class DU_OT_detect_epb(bpy.types.Operator):
    bl_idname = "du.detect_epb"
    bl_label = "Detect"
    bl_description = "Search common locations for epb-converter/src/index.js"
    bl_options = {"REGISTER"}

    def execute(self, context):
        js = preferences.find_epb_js()
        if not js:
            self.report({"WARNING"}, "epb-converter not found — set the path manually.")
            return {"CANCELLED"}
        preferences.prefs(context).epb_converter_js = js
        self.report({"INFO"}, f"Found: {js}")
        return {"FINISHED"}


class DU_OT_import_epb(bpy.types.Operator):
    bl_idname = "du.import_epb"
    bl_label = "Import Empyrion Blueprint (.epb)"
    bl_description = "Convert an Empyrion .epb to a mesh (via epb-converter) and import it to edit/export"
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.epb", options={"HIDDEN"})
    smooth_grey_speckle: bpy.props.BoolProperty(
        name="Smooth grey speckle",
        description="Consolidate finely-intermixed grey shades into coherent regions "
                    "(fixes 'colour sawtooth' on ships like the Infiltrator). Leave OFF for "
                    "ships with intentional two-tone panelling/bands",
        default=False,
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        pr = preferences.prefs(context)
        epb = bpy.path.abspath(self.filepath)
        if not epb or not os.path.isfile(epb):
            self.report({"ERROR"}, "Pick a .epb file.")
            return {"CANCELLED"}
        js = bpy.path.abspath(pr.epb_converter_js) if pr.epb_converter_js else ""
        if not js or not os.path.isfile(js):
            js = preferences.find_epb_js()          # auto-locate on disk
            if js:
                pr.epb_converter_js = js            # remember it
        if not js or not os.path.isfile(js):
            self.report({"ERROR"}, "epb-converter not found. Set its src/index.js path in preferences.")
            return {"CANCELLED"}

        out_obj = os.path.join(tempfile.gettempdir(), "du_epb_import.obj")
        node = bpy.path.abspath(pr.node_path) if os.path.sep in pr.node_path else pr.node_path
        env = os.environ.copy()
        if self.smooth_grey_speckle:
            env["EPB_GREY_DENOISE"] = "1"
        try:
            res = subprocess.run([node, js, epb, out_obj], env=env,
                                 capture_output=True, text=True, timeout=600)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, f"Could not run Node/epb-converter: {exc}")
            return {"CANCELLED"}
        if res.returncode != 0 or not os.path.isfile(out_obj):
            tail = (res.stderr or res.stdout or "").strip().splitlines()
            self.report({"ERROR"}, "epb-converter failed: " + (tail[-1] if tail else "no output"))
            print("\n".join(tail))
            return {"CANCELLED"}

        before = set(context.scene.objects)
        bpy.ops.wm.obj_import(filepath=out_obj)
        imported = [o for o in context.scene.objects if o not in before]

        # map each imported group (named mat_<color>) to the DU palette material
        materials.ensure_palette()
        for obj in imported:
            color = obj.name.split(".")[0].replace("mat_", "")
            mat = bpy.data.materials.get(materials.material_name(color))
            if mat and obj.type == "MESH":
                obj.data.materials.clear()
                obj.data.materials.append(mat)
        self.report({"INFO"}, f"Imported {len(imported)} object(s) from {os.path.basename(epb)}. "
                              f"Scale to taste, then export.")
        return {"FINISHED"}


class DU_OT_extract_assets(bpy.types.Operator):
    bl_idname = "du.extract_assets"
    bl_label = "Extract DU Element Data"
    bl_description = ("Read element dimensions + icons from your local DU install into a "
                      "private cache (nothing is bundled or uploaded)")
    bl_options = {"REGISTER"}

    def execute(self, context):
        pr = preferences.prefs(context)
        path = bpy.path.abspath(pr.du_data_path)
        if not extract.is_valid_data_path(path):
            self.report({"ERROR"}, "Set 'DU game data folder' to your DU Game/data folder first.")
            return {"CANCELLED"}
        try:
            n_el, n_ic = extract.extract(path)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, f"Extraction failed: {exc}")
            return {"CANCELLED"}
        elements.reload_catalog()
        self.report({"INFO"}, f"Extracted {n_el} elements, {n_ic} icons.")
        return {"FINISHED"}


CLASSES = (DU_OT_setup_core, DU_OT_make_palette, DU_OT_export_blueprint,
           DU_OT_add_placeholder, DU_OT_extract_assets, DU_OT_import_epb, DU_OT_detect_epb)
