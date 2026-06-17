"""DU core sizes and the honeycomb material palette.

Calibration (anchored to in-game ground truth, 2026-06-16): a real DU dynamic S core
fits exactly ONE XL space engine (18.15 m long), so real S build volume = 32 m. The
real DU build volumes are HALF du-blueprint's CoreSize::size() — there was a systematic
2x error. Confirmed values: XS=16, S=32, M=64, L=128, XL=256, XXL=512, XXXL=1024 m.
Element placeholder sizes (from real mesh AABBs) are in real metres and are correct.

Export scaling: du-blueprint maps real_DU_m = obj_units * --scale, so the exporter writes
coords * (1/scale); at scale 1, 1 Blender metre = 1 DU metre.
"""

# name -> real DU build-volume edge length in metres (cube)
CORE_SIZES = {
    "XS": 16,
    "S": 32,
    "M": 64,
    "L": 128,
    "XL": 256,
    "XXL": 512,
    "XXXL": 1024,
}

# Constraint: test/ship cores are M or larger. UI defaults to M and hides XS/S.
CORE_MIN = "M"
CORE_ORDER = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]

# DU honeycomb palette. The NAME is what matters: it must be one of du-blueprint's
# MATERIAL_TABLE colours (white/grey/darkgray/black/blue/green/red/yellow) or the
# converter falls back to white. RGB here is only the Blender viewport swatch
# (albedo from game data; accents approximate — final colour is remappable in-game).
#   name        R    G    B     description
DU_PALETTE = [
    ("white",    230, 230, 230, "Aluminium pattern, white (lightest neutral)"),
    ("grey",     128, 128, 128, "Gray aluminium pattern"),
    ("darkgray",  79,  79,  79, "Dark-gray aluminium pattern"),
    ("black",     31,  31,  31, "Black aluminium pattern"),
    ("blue",      15, 102, 232, "Steel tile, blue (accent)"),
    ("green",     71, 186,  18, "Steel tile, green (accent)"),
    ("red",      194,  18,  18, "Steel tile, red (accent)"),
    ("yellow",   252, 209,   0, "Steel tile, yellow (accent)"),
]

DU_COLOR_NAMES = [p[0] for p in DU_PALETTE]
DEFAULT_COLOR = "grey"


def core_build_m(name):
    """Build-volume edge length (metres) for a core size name."""
    return float(CORE_SIZES.get(name, CORE_SIZES[CORE_MIN]))
