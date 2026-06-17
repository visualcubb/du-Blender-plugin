"""Operators: set up a core build volume, refresh the palette, and export to .blueprint."""
import math
import os
import subprocess
import tempfile

import bpy
import mathutils

from . import core_data, elements, empyrion, export_obj, extract, materials, preferences

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
    bl_description = "Create the build-volume guide box for the chosen core and set metric units (grid snapping available via the magnet, off by default)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        size_name = scene.du_core_size
        edge = core_data.core_build_m(size_name)

        # metric units. Configure grid-increment snapping but DON'T force it on —
        # otherwise everything (including element placeholders) is locked to 1 m steps.
        # The user can toggle the magnet when they want the hull on the grid; the
        # exporter voxelizes to DU's 0.25 m grid regardless of exact placement.
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0
        ts = context.tool_settings
        ts.use_snap = False
        ts.snap_elements = {"INCREMENT"}
        if hasattr(ts, "use_snap_grid_absolute"):
            ts.use_snap_grid_absolute = True

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
        construct = getattr(context.scene, "du_construct_type", "dynamic")
        cmd = [exe, "generate", obj_path, bp_path,
               "-t", construct, "--scale", str(pr.scale), "-n", name]
        # honour the chosen core size (>= M); omit for auto if set to AUTO.
        # du-blueprint expects a lowercase size token (m/l/xl/...).
        if context.scene.du_core_size != "AUTO":
            cmd += ["-s", context.scene.du_core_size.lower()]

        # Hollow the interior (leave only an N-voxel solid shell) to save mass/material.
        env = os.environ.copy()
        if getattr(pr, "hollow_shell", 0) > 0:
            env["DU_HOLLOW_SHELL"] = str(pr.hollow_shell)

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
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


def _do_epb_import(self, context, epb, scale, smooth, split_by_shape=False):
    """Shared core: convert an .epb via epb-converter, import the OBJ, map DU
    materials, and scale the ship. Reports through ``self``. Returns a Blender
    operator result set."""
    pr = preferences.prefs(context)
    if not epb or not os.path.isfile(epb):
        self.report({"ERROR"}, "No .epb file selected.")
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
    if smooth:
        env["EPB_GREY_DENOISE"] = "1"
    if split_by_shape:
        env["EPB_SPLIT_BY_SHAPE"] = "1"
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

    # remap every material slot (named mat_<color>) to the DU palette material.
    # Works for both layouts: color split (one slot, object named mat_<color>) and
    # shape split (object named shape_<Shape>, several mat_<color> slots per object).
    materials.ensure_palette()
    for obj in imported:
        if obj.type != "MESH":
            continue
        if obj.data.materials:
            for slot in obj.material_slots:
                src = slot.material.name if slot.material else obj.name
                color = src.split(".")[0].replace("mat_", "")
                pal = bpy.data.materials.get(materials.material_name(color))
                if pal:
                    slot.material = pal
        else:
            color = obj.name.split(".")[0].replace("mat_", "")
            pal = bpy.data.materials.get(materials.material_name(color))
            if pal:
                obj.data.materials.append(pal)

    # scale the ship up (Empyrion blocks < DU voxels). obj_import places every
    # group at the world origin with absolute verts, so scaling each mesh about
    # its own (origin-at-0) local space scales the whole ship coherently.
    if scale and abs(scale - 1.0) > 1e-6:
        S = mathutils.Matrix.Diagonal((scale, scale, scale, 1.0))
        done = set()
        for obj in imported:
            if obj.type == "MESH" and obj.data.name not in done:
                obj.data.transform(S)
                obj.data.update()
                done.add(obj.data.name)

    extra = "  Split into per-shape objects (delete the ones you don't want)." if split_by_shape else ""
    self.report({"INFO"}, f"Imported {len(imported)} object(s) from {os.path.basename(epb)} "
                          f"at {scale:g}x.{extra} Tweak, then export.")
    return {"FINISHED"}


def _open_later(which):
    """Return a bpy.app.timers callback that opens the gallery / file browser once,
    from a normal context (so a modal scan can hand off to a popup safely)."""
    def _fn():
        try:
            if which == "gallery":
                bpy.ops.du.import_epb_gallery("INVOKE_DEFAULT")
            else:
                bpy.ops.du.import_epb_file("INVOKE_DEFAULT")
        except Exception as exc:  # noqa: BLE001
            print("DU import: could not open dialog:", exc)
        return None  # don't reschedule
    return _fn


class DU_OT_import_epb(bpy.types.Operator):
    bl_idname = "du.import_epb"
    bl_label = "Import Empyrion Blueprint"
    bl_description = ("Scan your Empyrion blueprints (saved + Steam Workshop) and pick one "
                      "from a searchable thumbnail gallery to import")
    bl_options = {"REGISTER"}

    _timer = None
    _gen = None
    _count = 0

    def invoke(self, context, event):
        pr = preferences.prefs(context)
        # keep the last search/page so reopening doesn't start over
        # scan incrementally so the UI stays responsive and shows progress
        self._gen = empyrion.scan_iter(pr.empyrion_path)
        self._count = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)
        context.window.cursor_modal_set("WAIT")
        context.workspace.status_text_set("Scanning Empyrion blueprints… 0 found")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._end(context)
            self.report({"INFO"}, "Blueprint scan cancelled.")
            return {"CANCELLED"}
        if event.type == "TIMER":
            # process a few batches per tick, then yield to let the UI redraw
            try:
                for _ in range(3):
                    self._count = next(self._gen)
                context.workspace.status_text_set(
                    f"Scanning Empyrion blueprints… {self._count} found (Esc to cancel)")
            except StopIteration as stop:
                total = stop.value if stop.value is not None else self._count
                self._end(context)
                bpy.app.timers.register(_open_later("gallery" if total else "file"),
                                        first_interval=0.0)
                if not total:
                    self.report({"WARNING"},
                                "No Empyrion blueprints found. Set the Empyrion folder in "
                                "preferences, or use 'Browse for .epb file'.")
                else:
                    self.report({"INFO"}, f"Found {total} Empyrion blueprint(s).")
                return {"FINISHED"}
        return {"RUNNING_MODAL"}

    def _end(self, context):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)


class DU_OT_import_epb_gallery(bpy.types.Operator):
    bl_idname = "du.import_epb_gallery"
    bl_label = "Choose Empyrion Blueprint"
    bl_description = "Pick a scanned Empyrion blueprint from the thumbnail gallery and import it"
    bl_options = {"REGISTER", "UNDO"}

    smooth_grey_speckle: bpy.props.BoolProperty(
        name="Smooth grey speckle",
        description="Consolidate finely-intermixed grey shades into coherent regions "
                    "(fixes 'colour sawtooth' on ships like the Infiltrator). Leave OFF for "
                    "ships with intentional two-tone panelling/bands",
        default=False,
    )
    split_by_shape: bpy.props.BoolProperty(
        name="Separate by block shape",
        description="Import one object per Empyrion block shape (cubes, ramps, corners, …) "
                    "so you can select and delete whole shapes. Off = one object per colour",
        default=False,
    )
    import_scale: bpy.props.FloatProperty(
        name="Import scale",
        description="Uniform scale applied to the imported ship (~1.5x fits a real DU core)",
        default=1.5, min=0.1, max=20.0,
    )

    def invoke(self, context, event):
        self.import_scale = preferences.prefs(context).epb_import_scale
        wm = context.window_manager
        wm.du_epb_selected = ""
        # restore the last page, clamped to the current (possibly rescanned) range
        _items, page, _n_pages, _total = empyrion.page_view(context, empyrion.PER_PAGE)
        wm.du_epb_page = page
        return wm.invoke_props_dialog(self, width=900)

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        items, page, n_pages, total = empyrion.page_view(context, empyrion.PER_PAGE)

        # search + pager
        top = layout.row(align=True)
        top.prop(wm, "du_epb_search", text="", icon="VIEWZOOM")
        pager = top.row(align=True)
        pager.enabled = n_pages > 1
        pager.operator("du.epb_page", text="", icon="TRIA_LEFT").delta = -1
        pager.label(text=f"Page {page + 1}/{n_pages}")
        pager.operator("du.epb_page", text="", icon="TRIA_RIGHT").delta = 1
        sub = f" matching {wm.du_epb_search!r}" if wm.du_epb_search else ""
        layout.label(text=f"{total} blueprint(s){sub} — click one to select")
        with_prev, all_total = empyrion.counts()
        row2 = layout.row()
        row2.prop(wm, "du_epb_show_all")
        if all_total > with_prev:
            row2.label(text=f"({all_total - with_prev} hidden: no preview)")

        # fit-to-core filter (size read from the .epb header)
        core = context.scene.du_core_size
        row3 = layout.row()
        if core == "AUTO":
            row3.enabled = False
            row3.prop(wm, "du_epb_fit_only", text="Only ships that fit the core (pick a core size)")
        else:
            edge = core_data.core_build_m(core)
            row3.prop(wm, "du_epb_fit_only",
                      text=f"Only ships that fit the {core} core ({edge:g} m) at {self.import_scale:g}x")

        # thumbnail grid (PER_PAGE visible at once)
        if items:
            grid = layout.grid_flow(row_major=True, columns=empyrion.GRID_COLUMNS,
                                    even_columns=True, even_rows=True, align=True)
            for key, name, _epb, icon in items:
                cell = grid.column(align=True)
                selected = (key == wm.du_epb_selected)
                if icon:
                    cell.template_icon(icon_value=icon, scale=empyrion.THUMB_SCALE)
                else:
                    cell.label(text="", icon="IMAGE_DATA")
                op = cell.operator("du.pick_epb", text=name if len(name) <= 18 else name[:17] + "…",
                                   depress=selected)
                op.key = key
        else:
            layout.label(text="No blueprints match your search.", icon="INFO")

        # selection + import options
        layout.separator()
        sel = empyrion.name_for(wm.du_epb_selected)
        if sel:
            sz = empyrion.du_size_m(empyrion.epb_path_for(wm.du_epb_selected), self.import_scale)
            txt = f"Selected: {sel}"
            if sz:
                txt += f"  —  {sz[0]:.0f} x {sz[1]:.0f} x {sz[2]:.0f} m"
                if context.scene.du_core_size != "AUTO":
                    edge = core_data.core_build_m(context.scene.du_core_size)
                    txt += "   ✓ fits" if max(sz) <= edge + 1e-6 else "   ✗ too big for core"
            layout.label(text=txt, icon="CHECKMARK")
        else:
            layout.label(text="Selected: (click a ship above)", icon="INFO")
        layout.prop(self, "import_scale")
        layout.prop(self, "smooth_grey_speckle")
        layout.prop(self, "split_by_shape")

    def execute(self, context):
        key = context.window_manager.du_epb_selected
        epb = empyrion.epb_path_for(key)
        if not epb:
            self.report({"ERROR"}, "Click a blueprint in the gallery first.")
            return {"CANCELLED"}
        return _do_epb_import(self, context, epb, self.import_scale, self.smooth_grey_speckle,
                              self.split_by_shape)


class DU_OT_pick_epb(bpy.types.Operator):
    bl_idname = "du.pick_epb"
    bl_label = "Select Blueprint"
    bl_description = "Select this blueprint (then adjust scale and press OK to import)"
    bl_options = {"REGISTER", "INTERNAL"}

    key: bpy.props.StringProperty()

    def execute(self, context):
        context.window_manager.du_epb_selected = self.key
        return {"FINISHED"}


class DU_OT_epb_page(bpy.types.Operator):
    bl_idname = "du.epb_page"
    bl_label = "Gallery Page"
    bl_description = "Show the previous / next page of blueprints"
    bl_options = {"REGISTER", "INTERNAL"}

    delta: bpy.props.IntProperty(default=1)

    def execute(self, context):
        wm = context.window_manager
        _items, _page, n_pages, _total = empyrion.page_view(context, empyrion.PER_PAGE)
        wm.du_epb_page = max(0, min(wm.du_epb_page + self.delta, n_pages - 1))
        return {"FINISHED"}


class DU_OT_import_epb_file(bpy.types.Operator):
    bl_idname = "du.import_epb_file"
    bl_label = "Import Empyrion Blueprint (browse)"
    bl_description = "Browse for an Empyrion .epb file anywhere on disk and import it"
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.epb", options={"HIDDEN"})
    smooth_grey_speckle: bpy.props.BoolProperty(
        name="Smooth grey speckle",
        description="Consolidate finely-intermixed grey shades into coherent regions",
        default=False,
    )
    split_by_shape: bpy.props.BoolProperty(
        name="Separate by block shape",
        description="Import one object per Empyrion block shape so you can select and delete "
                    "whole shapes. Off = one object per colour",
        default=False,
    )
    import_scale: bpy.props.FloatProperty(
        name="Import scale",
        description="Uniform scale applied to the imported ship (~1.5x fits a real DU core)",
        default=1.5, min=0.1, max=20.0,
    )

    def invoke(self, context, event):
        self.import_scale = preferences.prefs(context).epb_import_scale
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        return _do_epb_import(self, context, bpy.path.abspath(self.filepath),
                              self.import_scale, self.smooth_grey_speckle, self.split_by_shape)


class DU_OT_detect_empyrion(bpy.types.Operator):
    bl_idname = "du.detect_empyrion"
    bl_label = "Detect"
    bl_description = "Auto-detect the Empyrion install folder from Steam"
    bl_options = {"REGISTER"}

    def execute(self, context):
        p = empyrion.autodetect_empyrion()
        if not p:
            self.report({"WARNING"}, "Empyrion install not found — set the folder manually.")
            return {"CANCELLED"}
        pr = preferences.prefs(context)
        pr.empyrion_path = p
        n = empyrion.refresh(p)
        self.report({"INFO"}, f"Empyrion: {p}  ({n} blueprint(s))")
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
           DU_OT_add_placeholder, DU_OT_extract_assets, DU_OT_import_epb,
           DU_OT_import_epb_gallery, DU_OT_pick_epb, DU_OT_epb_page,
           DU_OT_import_epb_file, DU_OT_detect_epb, DU_OT_detect_empyrion)
