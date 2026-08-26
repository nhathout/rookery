#!/usr/bin/env python3
"""rookery enclosure generator.

Builds every printed part and writes both STL and 3MF. 3MF is the native
Bambu Studio format, so `rookery.3mf` opens with all parts already laid out
on the plate.

    pip install trimesh manifold3d shapely numpy
    python3 generate.py

Everything is parametric. The numbers that matter most are at the top; the
two you're most likely to change are INSERT_OD (measure your heat-set
inserts) and BOARD_W/BOARD_L (measure your dev board).

    python3 generate.py --insert-od 4.2 --text "HELLO"
"""

from __future__ import annotations

import argparse
import os
import zipfile
from xml.sax.saxutils import escape

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely.geometry import box as sbox
from shapely.ops import unary_union
from trimesh.creation import box, cylinder, extrude_polygon

# ---------------------------------------------------------------------------
# PARAMETERS
# ---------------------------------------------------------------------------

# -- overall case
CASE_W, CASE_D, CASE_H = 96.0, 66.0, 30.0
CORNER_R = 9.0
WALL = 2.4
FLOOR = 2.2
LID_T = 4.0
LID_CLEAR = 0.25      # per side, lid to rebate
LEDGE = 1.2           # width of the shelf the lid sits on

# -- dev board (ESP32-S3-DevKitC-1). MEASURE YOURS.
BOARD_L, BOARD_W = 63.5, 25.5
BOARD_CLEAR = 0.6
BOARD_POST_H = 3.5    # clearance under the board for wires and solder
BOARD_Y = 0.0         # front edge of the board pocket, in case coords

# -- USB cutout in the left wall
USB_W, USB_H = 23.0, 9.0

# -- heat-set inserts. "M3 x 3mm" inserts are usually 4.0mm OD; some are 4.2.
# If yours are genuinely 3.0mm OD they're M2, so pass --insert-od 3.0 and use
# M2 screws.
INSERT_OD = 4.0
INSERT_LEN = 3.0
INSERT_DEPTH = INSERT_LEN + 0.6
# Drill deeper than the insert so the screw tip has somewhere to go. Without
# this an M3x8 bottoms out in the hole before it ever clamps the lid down.
SCREW_RUNOUT = 2.5
SCREW_D = 3.4         # M3 clearance
SCREW_HEAD_D = 6.0
SCREW_HEAD_DEPTH = 2.2

# -- LED chamber
LED_D = 5.0           # LED body diameter; use 3.0 for 3mm LEDs
LED_CLEAR = 0.25
LED_CIRCLE_D = 14.0   # bolt circle for the 6 LEDs -- keep tight, see notes
LED_COUNT = 6
HOLDER_W, HOLDER_D, HOLDER_T = 44.0, 24.0, 2.5
HOLDER_POST_H = 6.0
HOLDER_SCREW_X = 17.0

# -- plaque window in the lid
WIN_W, WIN_H = 44.0, 24.0     # visible opening
WIN_R = 4.0
PLAQUE_LEDGE = 1.5            # lip that retains the plaque
PLAQUE_T = 2.6
PLAQUE_CLEAR = 0.5
GLYPH_FLOOR = 0.8             # material left where the glyph glows

# The lit area sits over the LED cluster, in the front half of the lid.
CHAMBER_Y = -15.3

# Screw boss centres. Pushed outboard of the board pocket so they never
# collide with it -- the board is 63.5mm long and the pocket ring adds 2mm
# of wall each side.
BOSS_X = 41.0
BOSS_Y = 24.0
BOSS_D = 11.0

EPS = 0.01
SEG = 64
OVERLAP = 0.15   # CSG union overlap


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def rrect(w: float, d: float, r: float, cx=0.0, cy=0.0) -> Polygon:
    """Rounded rectangle as a shapely polygon."""
    r = min(r, w / 2 - 0.01, d / 2 - 0.01)
    return sbox(cx - w / 2 + r, cy - d / 2 + r,
                cx + w / 2 - r, cy + d / 2 - r).buffer(r, quad_segs=SEG // 4)


def solid(poly, height: float, z: float = 0.0) -> trimesh.Trimesh:
    """Extrude a Polygon or MultiPolygon. Glyphs are usually several disjoint
    islands (a ring, two eyes, a mouth), so handle both."""
    geoms = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
    parts = [extrude_polygon(p, height) for p in geoms if not p.is_empty]
    # manifold requires every operand to be a proper volume, so combine
    # disjoint islands with a real union rather than concatenating shells.
    m = parts[0] if len(parts) == 1 else union(*parts)
    m.apply_translation((0, 0, z))
    return m


def cyl(d: float, h: float, x=0.0, y=0.0, z=0.0) -> trimesh.Trimesh:
    m = cylinder(radius=d / 2, height=h, sections=SEG)
    m.apply_translation((x, y, z + h / 2))
    return m


def cube(w, d, h, x=0.0, y=0.0, z=0.0) -> trimesh.Trimesh:
    m = box((w, d, h))
    m.apply_translation((x, y, z + h / 2))
    return m


def diff(a, *bs):
    for b in bs:
        a = trimesh.boolean.difference([a, b], engine="manifold")
    return a


def union(*ms):
    return trimesh.boolean.union(list(ms), engine="manifold")


def flip(m):
    """Rotate 180 deg about X and re-seat on z=0.

    Used for the lid and plaques so the *visible* face prints against the
    build plate. That gives the best surface finish and, on the plaques,
    means the thin glow floor is laid down first -- no bridging at all."""
    m = m.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    m.apply_translation((0, 0, -m.bounds[0][2]))
    return m


def inter(a, b):
    return trimesh.boolean.intersection([a, b], engine="manifold")


# ---------------------------------------------------------------------------
# CASE
# ---------------------------------------------------------------------------

def build_case():
    outer = rrect(CASE_W, CASE_D, CORNER_R)
    cavity = outer.buffer(-WALL)
    rebate = outer.buffer(-LEDGE)

    shell = solid(outer, CASE_H)

    cuts = []
    # main cavity
    cuts.append(solid(cavity, CASE_H - FLOOR + EPS, FLOOR))
    # lid rebate: wider opening in the top LID_T of the wall
    cuts.append(solid(rebate, LID_T + EPS, CASE_H - LID_T))

    # USB cutout, left wall, at the board's connector height
    usb_z = FLOOR + BOARD_POST_H
    cuts.append(cube(WALL * 4, USB_W, USB_H,
                     x=-CASE_W / 2, y=BOARD_Y + BOARD_W / 2, z=usb_z))

    # rear vent slots
    for i in range(4):
        cuts.append(cube(11, WALL * 4, 2.6,
                         x=-18 + i * 12, y=CASE_D / 2, z=CASE_H - 12))

    # rubber-foot recesses underneath
    for sx in (-1, 1):
        for sy in (-1, 1):
            cuts.append(cyl(11, 0.7, sx * (CASE_W / 2 - 14),
                            sy * (CASE_D / 2 - 13), -EPS))

    body = diff(shell, *cuts)

    adds = []
    # --- lid screw bosses, four corners.
    # Kept 0.3mm BELOW the lid rebate so the lid seats on the continuous
    # ledge; a boss even slightly proud would rock it.
    boss_top = CASE_H - LID_T - 0.3
    boss_xy = [(sx * BOSS_X, sy * BOSS_Y)
               for sx in (-1, 1) for sy in (-1, 1)]
    for (x, y) in boss_xy:
        adds.append(cyl(BOSS_D, boss_top - FLOOR + OVERLAP, x, y,
                        FLOOR - OVERLAP))

    # --- board pocket: low walls capture the board laterally, posts set height
    bw, bl = BOARD_W + 2 * BOARD_CLEAR, BOARD_L + 2 * BOARD_CLEAR
    pocket_wall = 2.0
    pocket_h = BOARD_POST_H + 2.4
    ring = rrect(bl + 2 * pocket_wall, bw + 2 * pocket_wall, 2.0,
                 cy=BOARD_Y + BOARD_W / 2)
    ring = ring.difference(rrect(bl, bw, 1.0, cy=BOARD_Y + BOARD_W / 2))
    # open the left end so the USB connector can pass through
    ring = ring.difference(sbox(-CASE_W / 2, BOARD_Y - 2,
                                -bl / 2 + 1.0, BOARD_Y + BOARD_W + 2))
    adds.append(solid(ring, pocket_h + OVERLAP, FLOOR - OVERLAP))
    # retention tabs: the board snaps under these and stays put
    tab_z = FLOOR + BOARD_POST_H + 1.6
    for sx in (-1, 1):
        for ty, sy in ((BOARD_Y, 1), (BOARD_Y + BOARD_W, -1)):
            adds.append(cube(12.0, 2.0, 1.4, sx * 18.0,
                             ty + sy * 0.3, tab_z))
    for sx in (-1, 1):
        for sy in (-1, 1):
            adds.append(cyl(6.0, BOARD_POST_H + OVERLAP,
                            sx * (bl / 2 - 5), BOARD_Y + BOARD_W / 2 + sy * (bw / 2 - 5),
                            FLOOR - OVERLAP))

    # --- LED holder posts
    for sx in (-1, 1):
        adds.append(cyl(8.0, HOLDER_POST_H + OVERLAP, sx * HOLDER_SCREW_X,
                        CHAMBER_Y, FLOOR - OVERLAP))

    body = union(body, *adds)

    # --- insert holes, drilled last so bosses exist to drill into
    depth = INSERT_DEPTH + SCREW_RUNOUT
    holes = []
    for (x, y) in boss_xy:
        # Run the cutter well past the boss top into the empty rebate volume.
        # Stopping a hair above a coplanar face leaves a degenerate sliver.
        holes.append(cyl(INSERT_OD, depth + 2.0, x, y, boss_top - depth))
    post_top = FLOOR + HOLDER_POST_H
    for sx in (-1, 1):
        holes.append(cyl(INSERT_OD, depth + 2.0, sx * HOLDER_SCREW_X,
                         CHAMBER_Y, post_top - depth))
    return diff(body, *holes)


# ---------------------------------------------------------------------------
# LID
# ---------------------------------------------------------------------------

def build_lid():
    outer = rrect(CASE_W, CASE_D, CORNER_R).buffer(-(LEDGE + LID_CLEAR))
    lid = solid(outer, LID_T)

    cuts = []
    # plaque pocket, open from the underside
    pocket = rrect(WIN_W + 2 * PLAQUE_LEDGE, WIN_H + 2 * PLAQUE_LEDGE,
                   WIN_R + PLAQUE_LEDGE, cy=CHAMBER_Y)
    cuts.append(solid(pocket, PLAQUE_T + PLAQUE_CLEAR + EPS, -EPS))
    # the window itself, all the way through
    cuts.append(solid(rrect(WIN_W, WIN_H, WIN_R, cy=CHAMBER_Y),
                      LID_T + 2 * EPS, -EPS))

    # screw holes with counterbores from the top
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * BOSS_X, sy * BOSS_Y
            cuts.append(cyl(SCREW_D, LID_T + 2 * EPS, x, y, -EPS))
            cuts.append(cyl(SCREW_HEAD_D, SCREW_HEAD_DEPTH + EPS, x, y,
                            LID_T - SCREW_HEAD_DEPTH))

    return flip(diff(lid, *cuts))


# ---------------------------------------------------------------------------
# LED HOLDER
# ---------------------------------------------------------------------------

def build_holder():
    plate = solid(rrect(HOLDER_W, HOLDER_D, 4.0), HOLDER_T)
    cuts = []
    for i in range(LED_COUNT):
        a = 2 * np.pi * i / LED_COUNT
        cuts.append(cyl(LED_D + 2 * LED_CLEAR, HOLDER_T + 2 * EPS,
                        LED_CIRCLE_D / 2 * np.cos(a),
                        LED_CIRCLE_D / 2 * np.sin(a), -EPS))
    for sx in (-1, 1):
        cuts.append(cyl(SCREW_D, HOLDER_T + 2 * EPS, sx * HOLDER_SCREW_X, 0, -EPS))
    return diff(plate, *cuts)


# ---------------------------------------------------------------------------
# PLAQUES
# ---------------------------------------------------------------------------

FONT = {
    " ": ["....."] * 7,
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".####", "#....", "#....", "#....", "#....", "#....", ".####"],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".####", "#....", "#....", "#..##", "#...#", "#...#", ".###."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    "J": ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#...#", "#.#.#", "##.##", "#...#"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    "!": ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
}

# The penguin, kept from the earlier design but flattened to a 2D pixel icon.
# Lit pixels glow; the gaps stay full thickness and read as dark features.
# That's how the eyes and beak show up on a single-colour backlit plaque.
PENGUIN = [
    "...###...",
    "..#####..",
    ".#######.",
    ".#.###.#.",   # eyes
    ".###.###.",   # beak
    "..#####..",
    ".#######.",
    "#########",
    "#########",
    "#########",
    ".#######.",
    ".##...##.",
]


def pixels_to_poly(rows, px, cx=0.0, cy=0.0):
    """Merge lit pixels into a single 2D polygon. Row 0 is the TOP row.

    Squares that share an edge exactly merge cleanly in 2D, which is why this
    beats unioning 3D boxes: one extrusion, no sliver intersections.
    """
    h = len(rows)
    w = max(len(r) for r in rows)
    ox = cx - w * px / 2
    oy = cy + h * px / 2
    # Grow each pixel a hair before merging. Squares that meet only at a
    # corner (any diagonal stroke in the font) otherwise stay separate
    # polygons that meet at a single point -- which triangulates into a
    # non-manifold mess. GROW turns those contacts into real overlaps.
    grow = 0.02
    squares = []
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch != ".":
                x0 = ox + c * px
                y0 = oy - (r + 1) * px
                squares.append(sbox(x0 - grow, y0 - grow,
                                    x0 + px + grow, y0 + px + grow))
    return unary_union(squares).buffer(0)


def text_rows(s: str):
    s = s.upper()
    glyphs = [FONT.get(ch, FONT[" "]) for ch in s]
    return ["".join(g[r] + "." for g in glyphs)[:-1] for r in range(7)]


def smiley_poly():
    """Outline ring, two eyes, and a mouth arc -- all in 2D."""
    ring = Point(0, 0).buffer(10.5, quad_segs=SEG).difference(
        Point(0, 0).buffer(9.1, quad_segs=SEG))
    eyes = [Point(sx * 4.0, 3.2).buffer(1.6, quad_segs=SEG // 2)
            for sx in (-1, 1)]
    arc = Point(0, 0).buffer(6.8, quad_segs=SEG).difference(
        Point(0, 0).buffer(5.5, quad_segs=SEG))
    mouth = arc.intersection(sbox(-12, -9, 12, -1.6))
    return unary_union([ring, mouth] + eyes).buffer(0)


def build_plaque(kind: str, text: str = "ROOKERY"):
    body = solid(rrect(WIN_W + 2 * PLAQUE_LEDGE - PLAQUE_CLEAR,
                       WIN_H + 2 * PLAQUE_LEDGE - PLAQUE_CLEAR,
                       WIN_R + PLAQUE_LEDGE - PLAQUE_CLEAR * 0.5), PLAQUE_T)
    depth = PLAQUE_T - GLYPH_FLOOR
    if kind == "blank":
        return flip(body)

    if kind == "smiley":
        poly = smiley_poly()
    elif kind == "penguin":
        poly = pixels_to_poly(PENGUIN, 1.75)
    elif kind == "text":
        rows = text_rows(text)
        w_px = max(len(r) for r in rows)
        # scale to fit the window with a margin, capped so it stays legible
        px = min(1.8, (WIN_W - 9) / w_px, (WIN_H - 9) / 7)
        poly = pixels_to_poly(rows, px)
    else:
        raise ValueError(kind)

    # Pocket the glyph from the BACK: the front face stays flat and smooth
    # (printed face-down), and GLYPH_FLOOR of white PLA glows.
    g = solid(poly, depth + 2 * EPS, -EPS)
    return flip(diff(body, g))


# ---------------------------------------------------------------------------
# 3MF WRITER
# ---------------------------------------------------------------------------

CT = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""


def write_3mf(path, parts):
    """parts: list of (name, mesh, (dx, dy, dz))."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
           "<resources>"]
    items = []
    for i, (name, mesh, off) in enumerate(parts, start=1):
        v = mesh.vertices
        f = mesh.faces
        out.append(f'<object id="{i}" type="model" name="{escape(name)}"><mesh><vertices>')
        out.append("".join(
            f'<vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in v))
        out.append("</vertices><triangles>")
        out.append("".join(
            f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in f))
        out.append("</triangles></mesh></object>")
        dx, dy, dz = off
        items.append(f'<item objectid="{i}" transform="1 0 0 0 1 0 0 0 1 '
                     f'{dx:.4f} {dy:.4f} {dz:.4f}"/>')
    out.append("</resources><build>")
    out.extend(items)
    out.append("</build></model>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", "".join(out))


# ---------------------------------------------------------------------------

def main():
    global INSERT_OD, LED_D

    ap = argparse.ArgumentParser(description="Generate rookery enclosure parts.")
    ap.add_argument("--out", default="stl")
    ap.add_argument("--insert-od", type=float, default=INSERT_OD,
                    help="heat-set insert outer diameter (measure yours)")
    ap.add_argument("--led-d", type=float, default=LED_D,
                    help="LED body diameter: 5.0 or 3.0")
    ap.add_argument("--text", default="AFK",
                    help="text plaque content; <=5 chars lights most evenly")
    args = ap.parse_args()

    INSERT_OD = args.insert_od
    LED_D = args.led_d

    os.makedirs(args.out, exist_ok=True)

    parts = {
        "case": build_case(),
        "lid": build_lid(),
        "holder": build_holder(),
        "plaque_smiley": build_plaque("smiley"),
        "plaque_penguin": build_plaque("penguin"),
        "plaque_text": build_plaque("text", args.text),
        "plaque_blank": build_plaque("blank"),
    }

    print(f"{'part':<16}{'solid':>8}{'vol cm3':>10}{'size mm':>26}")
    bad = 0
    for name, m in parts.items():
        e = m.extents
        # Weld coincident vertices before judging: a mesh that only looks
        # watertight until it's welded will fail in someone else's slicer.
        # Weld at the precision the 3MF writer uses. A mesh that only holds
        # together at full float precision will fail in someone else's tool.
        w = trimesh.Trimesh(vertices=np.round(m.vertices, 6),
                            faces=m.faces.copy(), process=True)
        ok = w.is_watertight and w.is_winding_consistent
        bad += not ok
        print(f"  {name:<14}{('ok' if ok else 'BROKEN'):>8}{m.volume/1000:>10.1f}"
              f"{f'{e[0]:.1f} x {e[1]:.1f} x {e[2]:.1f}':>26}")
        m.export(os.path.join(args.out, f"{name}.stl"))
    if bad:
        print(f"\n  !! {bad} part(s) are not manifold after welding")

    # Shelf-pack onto a 256x256 plate so the 3MF opens ready to slice
    # instead of scattered off the bed.
    PLATE, GAP, MARGIN = 256.0, 8.0, 10.0
    layout = []
    x, y, row_h = MARGIN, MARGIN, 0.0
    for name, m in parts.items():
        w, d = m.extents[0], m.extents[1]
        if x + w > PLATE - MARGIN:
            x, y = MARGIN, y + row_h + GAP
            row_h = 0.0
        mn = m.bounds[0]
        layout.append((name, m, (x - mn[0], y - mn[1], -mn[2])))
        x += w + GAP
        row_h = max(row_h, d)
    used_h = y + row_h
    if used_h > PLATE - MARGIN:
        print(f"  WARNING: layout is {used_h:.0f}mm deep, taller than the plate")
    else:
        print(f"  plate layout: {used_h:.0f}mm deep, fits 256x256")
    write_3mf(os.path.join(args.out, "rookery.3mf"), layout)
    print(f"\nwrote {len(parts)} STLs + rookery.3mf to {args.out}/")


if __name__ == "__main__":
    main()
