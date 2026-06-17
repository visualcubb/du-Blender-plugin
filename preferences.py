"""Add-on preferences: where du-blueprint.exe lives + default axis."""
import os
import shutil

import bpy

from . import extract


def _autodetect_exe():
    # 1) on PATH
    for cand in ("du-blueprint", "du-blueprint.exe"):
        p = shutil.which(cand)
        if p:
            return p
    # 2) bundled next to the add-on (blender-du/bin/du-blueprint.exe)
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in ("bin/du-blueprint.exe", "du-blueprint.exe"):
        p = os.path.join(here, rel)
        if os.path.isfile(p):
            return p
    # 3) common dev location: repo tools/
    for up in (here, os.path.dirname(here)):
        p = os.path.join(up, "tools", "du-blueprint.exe")
        if os.path.isfile(p):
            return p
    return ""


def _autodetect_epb_js():
    """Fast check only (addon-relative) — used for the property default at import time."""
    here = os.path.dirname(os.path.abspath(__file__))
    for up in (here, os.path.dirname(here)):
        p = os.path.join(up, "epb-converter", "src", "index.js")
        if os.path.isfile(p):
            return p
    return ""


def find_epb_js():
    """Locate epb-converter/src/index.js: addon-relative first, then a bounded search of
    common dev locations under the user's home. Returns '' if not found."""
    import glob
    p = _autodetect_epb_js()
    if p:
        return p
    home = os.path.expanduser("~")
    roots = [home] + [os.path.join(home, r) for r in (
        "source", "source/repos", "Documents", "Downloads", "Desktop",
        "git", "projects", "dev", "code", "src", "repos", "OneDrive")]
    # depth 0..3 under each root so e.g. ~/source/repos/<repo>/epb-converter/src/index.js matches
    pats = ("epb-converter/src/index.js",
            "*/epb-converter/src/index.js",
            "*/*/epb-converter/src/index.js",
            "*/*/*/epb-converter/src/index.js")
    seen = set()
    for root in roots:
        if not os.path.isdir(root) or root in seen:
            continue
        seen.add(root)
        for pat in pats:
            hits = glob.glob(os.path.join(root, pat))
            if hits:
                return hits[0]
    return ""


class DUAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    exe_path: bpy.props.StringProperty(
        name="du-blueprint executable",
        subtype="FILE_PATH",
        default=_autodetect_exe(),
    )
    du_data_path: bpy.props.StringProperty(
        name="DU game data folder",
        description="Your Dual Universe install's data folder (used to extract element "
                    "dimensions + icons locally; nothing is bundled or uploaded)",
        subtype="DIR_PATH",
        default=extract.DEFAULT_DATA_PATH if extract.is_valid_data_path(extract.DEFAULT_DATA_PATH) else "",
    )
    scale: bpy.props.IntProperty(
        name="Voxel scale",
        description="du-blueprint --scale. The exporter pre-scales coords by 1/(2*scale) so "
                    "1 Blender metre = 1 DU metre at native 0.25 m voxels regardless of this value; "
                    "leave at 1",
        default=1, min=1, max=8,
    )
    node_path: bpy.props.StringProperty(
        name="Node.js executable",
        description="node(.exe) for the EPB importer (Empyrion blueprints). Leave 'node' to use PATH",
        subtype="FILE_PATH",
        default="node",
    )
    epb_converter_js: bpy.props.StringProperty(
        name="epb-converter src/index.js",
        description="Path to the epb-converter entry script (for importing .epb files)",
        subtype="FILE_PATH",
        default=_autodetect_epb_js(),
    )
    du_up_axis: bpy.props.EnumProperty(
        name="Up axis",
        items=[
            ("Y", "Y up (Dual Universe)", "Convert Blender Z-up to DU Y-up (x, z, -y) — ship aims horizontally"),
            ("Z", "Z up (raw Blender — advanced)", "Write raw Blender coordinates (ship will stand vertical in DU)"),
        ],
        default="Y",
    )

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "exe_path")
        if not self.exe_path:
            col.label(text="du-blueprint.exe not found — set the path above.", icon="ERROR")
        col.prop(self, "scale")
        col.prop(self, "du_up_axis")
        col.separator()
        col.label(text="EPB import (Empyrion blueprints) — optional, needs Node.js:")
        col.prop(self, "node_path")
        row = col.row(align=True)
        row.prop(self, "epb_converter_js")
        row.operator("du.detect_epb", icon="VIEWZOOM", text="Detect")
        col.label(text="(auto-located on first import; Detect to fill manually)")
        col.separator()
        col.prop(self, "du_data_path")
        col.operator("du.extract_assets", icon="IMPORT")
        if not extract.is_valid_data_path(self.du_data_path):
            col.label(text="Point this at your DU 'Game/data' folder, then Extract.", icon="INFO")


def prefs(context):
    return context.preferences.addons[__package__].preferences
