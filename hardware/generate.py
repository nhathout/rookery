#!/usr/bin/env python3
"""rookery enclosure generator -- the voxel penguin.

Everything is built on an 8 mm voxel grid, from a pixel map you can read in
the source. Nothing is smooth, nothing is filleted, and that is the point:
the shape reads as a low-res sprite standing on your desk.

    pip install trimesh manifold3d shapely numpy
    python3 generate.py

THREE PARTS THAT MATTER
    chassis   white. A hollow box. Its front face IS the belly -- the panel
              that glows -- and everything else bolts inside it: the LED
              shelf, the dev board, the cable. Build the whole electrical
              assembly on this one part, on the bench, then drop it in.
    body      black. The voxel penguin around it: head, flippers, feet, and
              a window the chassis's face fills flush. Hollow, open at the
              back, with room behind the chassis for anything you add later.
    back      black. The rear cover, four screws.

    Plus two press-fits with no fasteners at all: eyes and beak.

FASTENERS
    Every screw in the build is the same one: M3 x 1/4" (6.35 mm), the
    standard PC case screw -- e.g. Micro Connectors SCW-50M3. Six of them,
    into six M3 heat-set inserts. Nothing else.

PRINT ORIENTATION
    Both large parts print open-side-down, so the whole voxel silhouette
    lies flat in the build plate's XY plane and the pixel steps never become
    overhangs. The chassis prints belly-face-down: the glowing face lands
    against the plate, which is the best surface it can get, and every
    mount inside it grows upward off that face.

SELF-CHECKS
    Every run measures what it just built and exits non-zero if anything is
    wrong: manifoldness after welding at file precision, plate fit,
    unsupported downward-facing area, bridge spans, screw thread
    engagement, LED-to-board clearance, and a boolean interference test of
    the assembled parts against each other and against a solid standing in
    for the dev board. A bad parameter should fail here, not at the printer.
"""
from __future__ import annotations

import argparse
import math
import os
import zipfile
from xml.sax.saxutils import escape

import numpy as np
import trimesh
from shapely.affinity import rotate as srotate
from shapely.affinity import scale as sscale
from shapely.affinity import translate as stranslate
from shapely.geometry import Point, Polygon
from shapely.geometry import box as sbox
from shapely.ops import unary_union
from trimesh.creation import box, cylinder, extrude_polygon

# ---------------------------------------------------------------------------
# PARAMETERS
# ---------------------------------------------------------------------------

# -- the grid. Everything else is a multiple of this.
PITCH = 10.0

# The penguin, one character per voxel, row 0 at the top. Edit this and the
# whole enclosure changes shape; the window, the eyes, the beak and the feet
# are all addressed by grid coordinates below, so they follow.
#
# Rows 3-8 have to stay at least six voxels wide: that is the band the
# chassis occupies, and it has to fit inside the body wall there.
PIXELS = [
    "..####..",   # 0   crown
    ".######.",   # 1   eyes
    ".######.",   # 2   beak
    ".######.",   # 3   neck -- the black band above the belly
    "########",   # 4   shoulders, window top
    "########",   # 5   flippers
    "########",   # 6
    "########",   # 7
    "########",   # 8
    ".######.",   # 9   window bottom
    ".######.",   # 10
    ".######.",   # 11  base -- the black band below the belly
]

DEPTH = 50.0          # back plane (y=0) to the front face, 5 voxels
WALL = 2.4
BACK_T = 3.0          # rear cover
GROOVE_W, GROOVE_D = 1.2, 0.9    # the pixel grid, engraved into every face
FACE_GROOVE_D = 0.6              # shallower on the belly: it stays opaque

# -- the belly window, in grid coordinates (col0, col1, row0, row1) inclusive
WINDOW = (2, 5, 4, 9)            # 40 x 60 mm, 4 x 6 lit pixels
WINDOW_CLEAR = 0.2               # per side, chassis plug to window
FLARE = 4.0                      # 45-degree seat, on the X sides only

# -- eyes and beak, in grid coordinates
EYE_COLS, EYE_ROW = (2, 5), 1
EYE_SIZE = 8.4                   # nearly the whole voxel: big eyes read cuter
EYE_DEPTH = 7.0
PUPIL_SIZE = 4.4                 # goes right through: the dark behind it
                                 # is the inside of the head
PUPIL_DROP = 0.6                 # pupils sit low: it reads as looking at you
BEAK_COLS, BEAK_ROW = (3, 4), 2
BEAK_W, BEAK_H = 12.0, 7.0       # smaller than its cells: a beak, not a muzzle
BEAK_OUT = 8.0                   # straight out the front
PRESS_CLEAR = 0.18

# -- feet: cubes stuck on the front at the base
FOOT_COLS = ((1, 2), (5, 6))
FOOT_ROW = 11
FOOT_OUT = 10.0                  # one voxel forward

# -- chassis: the white box. CH_W/CH_H/CH_D are derived, further down.
CH_WALL = 1.8
CH_D = 45.0
GLYPH_FLOOR = 0.9                # material left where an optional glyph glows
SMILEY_SCALE = 2.2               # the stock smiley was drawn for a smaller window

# -- dev board (ESP32-S3-DevKitC-1), upright, USB pointing down. MEASURE YOURS.
#
# The board is LONGER than the chassis is tall, on purpose. Its top passes
# through a slot in the chassis roof into the head, and its USB connector
# sits low enough that a plug has somewhere to go -- which is the one thing
# a box sized to the window cannot give you.
BOARD_L, BOARD_W = 63.5, 25.5
BOARD_CLEAR = 0.6
BOARD_TALL = 8.0                 # tallest thing standing on it
BOARD_POST_D = 6.0
BOARD_RISE = 7.0                 # board centre, above the window centre
BOARD_Y = 32.0                   # front face of the board, from the belly face

# -- the USB plug. Nothing in the mesh represents it, so it is checked
# explicitly: a plug that does not fit is a build you cannot finish.
PLUG_W, PLUG_T, PLUG_L = 13.0, 9.0, 22.0

# -- LED shelf inside the chassis
LED_D = 5.0
LED_CLEAR = 0.25
LED_BODY = 8.6                   # 5 mm LED, dome tip to flange
LED_CIRCLE_D = 17.0
LED_LEAD = 4.0                   # straight lead behind the shelf before you
                                 # bend them outward. Nothing may occupy it.
LED_COUNT = 6
SHELF_Y = 23.0                   # front face of the shelf, from the belly face
SHELF_T = 3.0
SHELF_GAP = 7.0                  # wire route past the shelf, one side
SHELF_DROP = 1.75                # the shelf stops this far above the USB
                                 # connector, so the plug has a clear run
                                 # down past it and out through the floor
MOUNT_DZ = (-17.0, 20.0)         # board posts and tabs, either side of the
                                 # LED cluster. Nothing may stand in front
                                 # of an LED.

# -- alternative: one WS2812B ring instead of six discrete LEDs. The firmware
# already has this backend (env:esp32s3-neopixel). Three wires instead of
# thirteen -- see PRODUCTION.md for why that matters.
LEDS = "discrete"                # or "ring"
RING_OD, RING_ID, RING_T = 37.0, 23.0, 2.2   # MEASURE YOURS
RING_CLEAR = 0.4

# -- cable exit, a slot in the rear cover
CABLE_W, CABLE_H = 15.0, 10.0

# -- fasteners. One screw type for the whole build: M3 x 1/4".
SCREW_LEN = 25.4 / 4             # 6.35 mm under-head length
SCREW_D = 3.4                    # M3 clearance

# Heat-set inserts. INSERT_OD is the INSERT's diameter; the hole is cut
# INSERT_GRIP smaller so there is material for the iron to melt and the
# knurls to bite. A hole at the insert's nominal OD leaves nothing to grip,
# and the insert spins the first time a screw is tightened.
INSERT_OD = 4.0
INSERT_LEN = 5.0                 # the common M3 length; 3.0 and 5.7 also fit
INSERT_GRIP = 0.15
INSERT_LEADIN = 0.8              # 45-degree countersink, starts it straight
SCREW_RUNOUT = 2.0               # empty hole past the insert for the screw tip
BOSS_D = 9.0
BOSS_H = 11.0

# derived
INSERT_BORE = INSERT_OD - INSERT_GRIP
INSERT_DEPTH = INSERT_LEN + 0.6
BORE_DEPTH = INSERT_DEPTH + SCREW_RUNOUT

EPS = 0.01
SEG = 64
OVERLAP = 0.15                   # CSG union overlap
SIMPLIFY = 0.03                  # polygon chord tolerance, mm
SLAB = 0.2                       # loft slab height: one layer, so the
                                 # staircase lands on layer boundaries
PLATE = 180.0                    # Bambu A1 mini build plate
PLATE_Z = 180.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def solid(poly, height: float, z: float = 0.0) -> trimesh.Trimesh:
    """Extrude a Polygon or MultiPolygon along +Z.

    Glyphs are usually several disjoint islands (a ring, two eyes, a mouth),
    so handle both. manifold requires every operand to be a proper volume, so
    disjoint islands are combined with a real union rather than concatenated
    shells.
    """
    geoms = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
    parts = [extrude_polygon(p, height) for p in geoms if not p.is_empty]
    if not parts:
        raise ValueError("nothing to extrude")
    m = parts[0] if len(parts) == 1 else union(*parts)
    m.apply_translation((0, 0, z))
    return m


def stand(m: trimesh.Trimesh, depth: float) -> trimesh.Trimesh:
    """Rotate a silhouette extrusion upright.

    Input lives in (x, silhouette_z, extrusion) with the extrusion running
    0..depth. Output is world (x, y, z) with y running 0..depth from the
    open back forward, and z up.
    """
    m = m.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    m.apply_translation((0, depth, 0))
    return m


def cyl(d: float, h: float, x=0.0, y=0.0, z=0.0) -> trimesh.Trimesh:
    m = cylinder(radius=d / 2, height=h, sections=SEG)
    m.apply_translation((x, y, z + h / 2))
    return m


def ybore(d: float, length: float, x: float, z: float, y0: float) -> trimesh.Trimesh:
    """A cylindrical bore running along +Y, starting at y0."""
    m = cylinder(radius=d / 2, height=length, sections=SEG)
    m.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
    m.apply_translation((x, y0 + length / 2, z))
    return m


def ycone(d0: float, d1: float, length: float, x: float, z: float,
         y0: float, sides: int = SEG) -> trimesh.Trimesh:
    """A truncated cone along +Y, diameter d0 at y0 growing to d1.

    `sides` is worth turning down where the cone has to be cut by something
    round: two finely-tessellated curved surfaces that graze each other leave
    slivers thinner than float precision, and the result stops being a solid
    when anyone welds it. Flat facets intersect cleanly."""
    n = sides
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    v = np.vstack([
        np.column_stack([np.cos(a) * d0 / 2, np.zeros(n), np.sin(a) * d0 / 2]),
        np.column_stack([np.cos(a) * d1 / 2, np.full(n, length), np.sin(a) * d1 / 2]),
        [[0, 0, 0], [0, length, 0]],
    ])
    lo, hi = 2 * n, 2 * n + 1
    f = []
    for i in range(n):
        j = (i + 1) % n
        f += [[i, n + j, j], [i, n + i, n + j]]      # side wall
        f += [[lo, i, j]]                            # cap at y0
        f += [[hi, n + j, n + i]]                    # cap at y0+length
    # Wound outward by construction -- trimesh's fix_normals() needs scipy,
    # and this generator deliberately has no scipy dependency.
    m = trimesh.Trimesh(vertices=v, faces=np.array(f), process=True)
    m.apply_translation((x, y0, z))
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


def inter(*ms):
    return trimesh.boolean.intersection(list(ms), engine="manifold")


def orient(m, front_down: bool = False):
    """Lay a part flat for printing and seat it on z=0.

    The model is authored standing up, in the orientation it is assembled in.
    Printing is a different question, so every part gets rotated here rather
    than being authored lying down:

      front_down=False  the back face goes on the plate (shell, backplate,
                        nest, eyes) -- print Z runs along +Y
      front_down=True   the visible front face goes on the plate (belly), so
                        it comes out smooth and the thin glow floor is laid
                        down first with no bridging at all
    """
    m = m.copy()
    ang = -np.pi / 2 if front_down else np.pi / 2
    m.apply_transform(trimesh.transformations.rotation_matrix(ang, [1, 0, 0]))
    m.apply_translation((0, 0, -m.bounds[0][2]))
    return m


def yprism(poly: Polygon, y_front: float, length: float):
    """A straight prism along Y, front face at y_front."""
    return stand(solid(poly, length), y_front)


def rrect(w: float, h: float, r: float, cx=0.0, cz=0.0) -> Polygon:
    r = min(r, w / 2 - 0.01, h / 2 - 0.01)
    return sbox(cx - w / 2 + r, cz - h / 2 + r,
                cx + w / 2 - r, cz + h / 2 - r).buffer(r, quad_segs=SEG // 4)


def insert_pocket(x: float, z: float, y_mouth: float, into_plus_y: bool):
    """Heat-set pocket plus its 45-degree lead-in, drilled from y_mouth."""
    d = 1.0 if into_plus_y else -1.0
    y0 = y_mouth if into_plus_y else y_mouth - BORE_DEPTH
    bore = ybore(INSERT_BORE, BORE_DEPTH, x, z, y0)
    lead = ycone(INSERT_BORE + 2 * INSERT_LEADIN, INSERT_BORE,
                 INSERT_LEADIN, x, z,
                 y_mouth if into_plus_y else y_mouth - INSERT_LEADIN) \
        if into_plus_y else \
        ycone(INSERT_BORE, INSERT_BORE + 2 * INSERT_LEADIN,
              INSERT_LEADIN, x, z, y_mouth - INSERT_LEADIN)
    return bore, lead

# ---------------------------------------------------------------------------
# THE GRID
#
# Grid coordinates are (col, row) with row 0 at the top, matching PIXELS as
# it is written. World coordinates are X right, Y forward from the open back
# at y=0, Z up from the desk at z=0.
# ---------------------------------------------------------------------------

NCOL = len(PIXELS[0])
NROW = len(PIXELS)
BODY_W = NCOL * PITCH
BODY_H = NROW * PITCH


def cell(col: int, row: int) -> Polygon:
    """One voxel as an X-Z square."""
    x0 = (col - NCOL / 2) * PITCH
    z0 = (NROW - 1 - row) * PITCH
    return sbox(x0, z0, x0 + PITCH, z0 + PITCH)


def span(c0: int, c1: int, r0: int, r1: int) -> Polygon:
    """A rectangle of whole voxels, inclusive on both ends."""
    a, b = cell(c0, r1), cell(c1, r0)
    return sbox(a.bounds[0], a.bounds[1], b.bounds[2], b.bounds[3])


def pixel_poly() -> Polygon:
    """The lit voxels of PIXELS, merged into one outline.

    Squares that share only a corner would triangulate into a non-manifold
    mess, so grow each one by a hair before merging: diagonal contacts
    become real overlaps.
    """
    g = 0.01
    cells = []
    for r, line in enumerate(PIXELS):
        for c, ch in enumerate(line):
            if ch != ".":
                b = cell(c, r).bounds
                cells.append(sbox(b[0] - g, b[1] - g, b[2] + g, b[3] + g))
    p = unary_union(cells).buffer(0)
    if p.geom_type == "MultiPolygon":
        p = max(p.geoms, key=lambda q: q.area)
    return p.simplify(SIMPLIFY)


def grid_bars(clip: Polygon, inset: float = 0.0) -> Polygon:
    """Thin bars along every internal voxel boundary, clipped to `clip`.

    Cut into a face they turn a smooth slab into visible pixels, which is
    the whole look. The belly gets the same grid as the body, so the glow
    reads as a block of lit pixels rather than one lit rectangle.
    """
    bars = []
    h = GROOVE_W / 2
    for c in range(1, NCOL):
        x = (c - NCOL / 2) * PITCH
        bars.append(sbox(x - h, -1.0, x + h, BODY_H + 1.0))
    for r in range(1, NROW):
        z = (NROW - r) * PITCH
        bars.append(sbox(-BODY_W, z - h, BODY_W, z + h))
    region = clip.buffer(-inset) if inset else clip
    return unary_union(bars).intersection(region)


def grid_lines() -> Polygon:
    """Thin bars along every internal voxel boundary.

    Cut GROOVE_D into the front face they turn a smooth slab into visible
    pixels, which is the whole look. Clipped to the silhouette so no groove
    runs off into space.
    """
    return grid_bars(pixel_poly(), GROOVE_W)


# ---------------------------------------------------------------------------
# BODY -- the black voxel penguin. Prints open-back-down, no supports.
# ---------------------------------------------------------------------------

def window_rect(grow: float = 0.0) -> Polygon:
    w = span(*WINDOW)
    return w.buffer(grow, join_style=2) if grow else w


def boss_positions():
    """Four bosses for the rear cover, tucked into the corners of the body
    cavity, clear of the chassis."""
    inner = pixel_poly().buffer(-WALL)
    out = []
    for row in (4, NROW - 1):
        z = cell(0, row).bounds[1] + PITCH / 2
        band = inner.intersection(sbox(-BODY_W, z - 0.25, BODY_W, z + 0.25))
        w = max(abs(band.bounds[0]), abs(band.bounds[2]))
        out += [(sx * (w - BOSS_D / 2 - 0.4), z) for sx in (-1, 1)]
    return out


def build_body():
    poly = pixel_poly()
    outer = yprism(poly, DEPTH, DEPTH)
    cavity = yprism(poly.buffer(-WALL).simplify(SIMPLIFY), DEPTH - WALL,
                    DEPTH + 3.0)

    adds = [diff(outer, cavity)]

    # --- feet: cubes stuck on the front at the base, one voxel deep. They
    # widen the footprint forward, which is the direction this thing would
    # otherwise be happy to fall over in.
    fz = cell(0, FOOT_ROW).bounds[1]
    for (c0, c1) in FOOT_COLS:
        b = span(c0, c1, FOOT_ROW, FOOT_ROW).bounds
        adds.append(cube(b[2] - b[0], FOOT_OUT + OVERLAP, PITCH,
                         (b[0] + b[2]) / 2, DEPTH + FOOT_OUT / 2 - OVERLAP / 2,
                         fz))

    # --- bosses for the rear cover, clipped to the skin so nothing pokes out
    bosses = []
    for (x, z) in boss_positions():
        bosses.append(ybore(BOSS_D, BOSS_H, x, z, 0.0))
        bosses.append(ycone(BOSS_D + 5.0, BOSS_D, 3.0, x, z, 0.0))
    adds.append(inter(union(*bosses), outer))

    body = union(*adds)

    cuts = []
    # --- the belly window, straight through the front skin
    cuts.append(yprism(window_rect(WINDOW_CLEAR), DEPTH + 1.0, WALL + 2.0))
    # --- pocket behind it so the chassis's flange has somewhere to sit
    cuts.append(yprism(span(*WINDOW).buffer(6.0, join_style=2),
                       DEPTH - WALL, DEPTH))

    # --- eyes: square bores, one voxel each, inset so they read as pixels
    for c in EYE_COLS:
        b = cell(c, EYE_ROW).bounds
        cuts.append(cube(EYE_SIZE, EYE_DEPTH + 2.0, EYE_SIZE,
                         (b[0] + b[2]) / 2, DEPTH - EYE_DEPTH / 2 + 1.0,
                         (b[1] + b[3]) / 2 - EYE_SIZE / 2))
    # --- beak socket
    bb = span(BEAK_COLS[0], BEAK_COLS[1], BEAK_ROW, BEAK_ROW).bounds
    cuts.append(cube(BEAK_W - 3.0, WALL + 2.0, BEAK_H - 3.0,
                     (bb[0] + bb[2]) / 2, DEPTH - WALL / 2 + 1.0,
                     (bb[1] + bb[3]) / 2 - (BEAK_H - 3.0) / 2))

    # --- the pixel grid, engraved. On the front face, and wrapped around
    # the sides and the top as well: from any angle the thing has to read as
    # a stack of cubes, not as a slab with a picture on it.
    cuts.append(yprism(grid_lines(), DEPTH + EPS, GROOVE_D + EPS))
    rim = poly.difference(poly.buffer(-GROOVE_D)).simplify(SIMPLIFY)
    for r in range(1, NROW):                      # lines around the sides
        z = (NROW - r) * PITCH
        cuts.append(yprism(rim.intersection(
            sbox(-BODY_W, z - GROOVE_W / 2, BODY_W, z + GROOVE_W / 2)),
            DEPTH + 1.0, DEPTH + 2.0))
    for k in range(1, int(round(DEPTH / PITCH))):  # lines around the depth
        cuts.append(yprism(rim, DEPTH - k * PITCH + GROOVE_W / 2, GROOVE_W))

    # --- heat-set pockets, mouths facing out of the open back
    for (x, z) in boss_positions():
        cuts.extend(insert_pocket(x, z, 0.0, True))

    body = diff(body, *cuts)
    # loft/prism overlaps run a hair past y=0; the cover needs a real plane
    return inter(body, cube(400, 400, 400, 0, 200, -200))

# ---------------------------------------------------------------------------
# CHASSIS -- the white box. This is the belly and the carrier in one part.
#
# Printed belly-face-down, so the face that glows lands against the build
# plate and every mount inside grows upward off it. Depth, from that face:
#
#     0.0 .. 2.4    the plug -- fills the body's window, flush with the skin
#     2.4 .. 6.4    45-degree flare out to the flange. Self-supporting, and
#                   it cannot pass forward through the window.
#     6.4 .. 34.0   box walls
#    15.0 .. 18.0   the LED shelf, spanning the box
#    18.0 .. 21.5   board posts standing on the shelf
# ---------------------------------------------------------------------------

_WB = span(*WINDOW).bounds
CH_W = _WB[2] - _WB[0] + 2 * FLARE
CH_H = _WB[3] - _WB[1]
CH_CZ = (_WB[1] + _WB[3]) / 2
BOARD_CZ = CH_CZ + BOARD_RISE
# The LED cluster sits dead centre on the belly. It is a parameter because
# it is the one thing worth nudging by eye once you have printed one.
LED_CZ = CH_CZ


def ch_rect(grow: float = 0.0) -> Polygon:
    """The chassis outline, grown OUTWARD IN X ONLY.

    Being oversize in one direction is all it takes to stop the chassis
    passing forward through the window, and growing in X only keeps the box
    inside the body wall at the top and bottom of its travel -- where the
    penguin narrows to six voxels and there is no room to spare.
    """
    b = window_rect(-WINDOW_CLEAR).bounds
    return sbox(b[0] - grow, b[1], b[2] + grow, b[3])


def yflare(poly: Polygon, y_front: float, run: float, steps: int = 0):
    """A 45-degree square flare, built as a stack of slabs one layer high so
    the staircase lands on layer boundaries and slices out flat."""
    steps = steps or max(4, int(math.ceil(run / SLAB)))
    es = np.linspace(0.0, run, steps + 1)
    b = poly.bounds
    slabs = []
    for k, (e0, e1) in enumerate(zip(es, es[1:])):
        off = 0.5 * (e0 + e1)
        p = sbox(b[0] - off, b[1], b[2] + off, b[3])
        last = k == steps - 1
        slabs.append(solid(p, (e1 - e0) + (0.0 if last else OVERLAP), e0))
    return stand(union(*slabs), y_front)


def build_chassis(face: str = "blank", text: str = "AFK"):
    y_face = DEPTH                      # flush with the body's front skin
    y_flange = y_face - WALL            # where the flare starts
    y_back = y_face - CH_D

    ob = ch_rect(FLARE).bounds                       # outer footprint
    ib = (ob[0] + CH_WALL, ob[1] + CH_WALL, ob[2] - CH_WALL, ob[3] - CH_WALL)

    plug = yprism(ch_rect(), y_face, WALL)
    flare = yflare(ch_rect(), y_flange, FLARE)
    shell = yprism(ch_rect(FLARE), y_flange - FLARE,
                   (y_flange - FLARE) - y_back)
    # A real box: walls on all four sides, not just the two the flare
    # happened to leave behind. The board and the plug get their own slots
    # through the roof and the floor further down.
    inner = yprism(sbox(*ib), y_flange - FLARE - CH_WALL,
                   (y_flange - FLARE) - y_back + 2.0)

    ch = diff(union(plug, flare, shell), inner)

    # --- LED shelf. Full width, wall to wall, and it stops short of the USB
    # connector at the bottom so the plug has a clear run past it. The wire
    # gap down one side is how the loom gets through.
    z_conn = BOARD_CZ - BOARD_L / 2
    shelf_rect = sbox(ob[0], z_conn + SHELF_DROP, ob[2], ob[3])
    shelf = diff(yprism(shelf_rect, y_face - SHELF_Y, SHELF_T),
                 yprism(sbox(ib[2] - SHELF_GAP, -500, ib[2], 500),
                        y_face - SHELF_Y + EPS, SHELF_T + 2 * EPS))
    adds = [ch, shelf]

    # --- board posts, standing on the shelf so nothing crosses the light
    # chamber and casts a shadow on the belly
    # --- board posts, standing on the shelf so nothing crosses the light
    # chamber and casts a shadow on the belly. The board is longer than the
    # box is tall, so the posts grip it well inboard of its ends rather than
    # at its corners.
    bw = BOARD_W + 2 * BOARD_CLEAR
    y_shelf_back = y_face - SHELF_Y - SHELF_T
    post_h = y_shelf_back - (y_face - BOARD_Y)
    y_board = y_face - BOARD_Y
    for sx in (-1, 1):
        for dz in MOUNT_DZ:
            adds.append(ybore(BOARD_POST_D, post_h + OVERLAP,
                              sx * (bw / 2 - 5.0), CH_CZ + dz, y_board))
    # --- retention tabs. Each one is a column standing on the shelf just
    # outboard of the board, with a lip that reaches back over its edge:
    # press the board in and it clicks under. The column matters -- a lip
    # on its own is a piece of plastic attached to nothing, which prints as
    # a blob on the plate and holds precisely no boards.
    tab_w, tab_z = 3.4, 12.0
    tab_x = bw / 2 + tab_w / 2 + 0.3
    lip_in = bw / 2 - 1.6
    for sx in (-1, 1):
        for dz in MOUNT_DZ:
            zc = CH_CZ + dz - tab_z / 2
            adds.append(cube(tab_w, y_shelf_back - (y_board - 2.4), tab_z,
                             sx * tab_x,
                             (y_shelf_back + y_board - 2.4) / 2, zc))
            adds.append(cube(tab_x + tab_w / 2 - lip_in, 1.4, tab_z,
                             sx * (tab_x + tab_w / 2 + lip_in) / 2,
                             y_board - 1.7, zc))

    ch = union(*adds)

    cuts = []
    if LEDS == "ring":
        depth = min(RING_T, SHELF_T - 1.2)
        cuts.append(ybore(RING_OD + 2 * RING_CLEAR, depth + EPS, 0.0, LED_CZ,
                          y_face - SHELF_Y - depth))
        cuts.append(ybore(12.0, SHELF_T + 2 * EPS, 0.0,
                          LED_CZ - (RING_OD + RING_ID) / 4,
                          y_face - SHELF_Y - SHELF_T - EPS))
    else:
        for i in range(LED_COUNT):
            a = 2 * math.pi * i / LED_COUNT + math.pi / 6
            cuts.append(ybore(LED_D + 2 * LED_CLEAR, SHELF_T + 2 * EPS,
                              LED_CIRCLE_D / 2 * math.cos(a),
                              LED_CZ + LED_CIRCLE_D / 2 * math.sin(a),
                              y_face - SHELF_Y - SHELF_T - EPS))

    # --- pass-throughs. The board is longer than the box, and its USB
    # connector needs somewhere for a plug to go: a slot in the roof lets
    # the top of the board out into the head, and a slot in the floor lets
    # the plug down into the base. Without the second one you cannot plug
    # the thing in at all.
    # Cut these from the REAL bounds, not from CH_H: the outer footprint is
    # the window rect shrunk by the fit clearance, so a slot sized off the
    # nominal height leaves a fifth-of-a-millimetre membrane across it --
    # invisible in a render, and enough to stop a plug.
    slot_y0, slot_y1 = y_back - 1.0, y_flange - FLARE
    slot_d, slot_yc = slot_y1 - slot_y0, (slot_y0 + slot_y1) / 2
    cuts.append(cube(BOARD_W + 2.0, slot_d, CH_WALL + 2 * EPS, 0.0,
                     slot_yc, ib[3] - EPS))
    cuts.append(cube(PLUG_W + 2.0, slot_d, CH_WALL + 2 * EPS, 0.0,
                     slot_yc, ob[1] - EPS))

    # --- the same pixel grid as the body, carried across the belly. Cut
    # shallower here: the face is only WALL thick and it still has to be
    # opaque enough that the grooves read as lines rather than as gaps.
    cuts.append(yprism(grid_bars(ch_rect(), GROOVE_W), y_face + EPS,
                       FACE_GROOVE_D + EPS))

    if face != "blank":
        poly = {"smiley": smiley_at, "chick": chick_poly}.get(face)
        poly = poly() if poly else text_poly(text)
        cuts.append(yprism(poly, y_face - GLYPH_FLOOR,
                           WALL - GLYPH_FLOOR + SHELF_Y))

    return diff(ch, *cuts)


# ---------------------------------------------------------------------------
# GLYPHS -- optional, cut into the belly with --face
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

# A chick, for the penguin's own belly. Lit pixels glow; the gaps stay full
# thickness and read as dark features -- that is how the eyes and beak show
# up on a single-colour backlit panel.
CHICK = [
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


def chick_poly():
    return pixels_to_poly(CHICK, 3.4, cy=CH_CZ)


def smiley_at() -> Polygon:
    # The stock smiley was drawn for the old 44 x 24 mm window. This one is
    # 48 x 54, so scale it up to actually fill the belly.
    return stranslate(sscale(smiley_poly(), xfact=SMILEY_SCALE,
                             yfact=SMILEY_SCALE, origin=(0, 0)),
                      yoff=CH_CZ)


def text_poly(text: str) -> Polygon:
    rows = text_rows(text)
    w_px = max(len(r) for r in rows)
    # Fit inside the oval window with a margin, capped so it stays legible.
    px = min(3.6, (CH_W - 16) / w_px, (CH_H - 26) / 7)
    return pixels_to_poly(rows, px, cy=CH_CZ)
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
        v, f = mesh.vertices, mesh.faces
        out.append(f'<object id="{i}" type="model" name="{escape(name)}">'
                   f'<mesh><vertices>')
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
    # Fixed timestamps: a 3MF is a zip, and zip entries carry the wall clock
    # by default. Without this, re-running the generator rewrites four files
    # that contain identical geometry, and the diff is pure noise.
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in (("[Content_Types].xml", CT), ("_rels/.rels", RELS),
                           ("3D/3dmodel.model", "".join(out))):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)


def pack(items, plate=PLATE, gap=6.0, margin=6.0):
    """Shelf-pack parts onto as many plates as it takes. Returns a list of
    plates, each a list of (name, mesh, offset)."""
    plates, cur = [], []
    x = y = margin
    row_h = 0.0
    for name, m in items:
        w, d = m.extents[0], m.extents[1]
        if x + w > plate - margin:
            x, y, row_h = margin, y + row_h + gap, 0.0
        if y + d > plate - margin:
            plates.append(cur)
            cur, x, y, row_h = [], margin, margin, 0.0
        mn = m.bounds[0]
        cur.append((name, m, (x - mn[0], y - mn[1], -mn[2])))
        x += w + gap
        row_h = max(row_h, d)
    if cur:
        plates.append(cur)
    return plates


# ---------------------------------------------------------------------------
# CHECKS
# ---------------------------------------------------------------------------
def pieces(m) -> int:
    """How many separate lumps of plastic this mesh is.

    Anything above one means a feature is floating in mid-air, attached to
    nothing -- which a slicer will happily print as a blob on the plate, or
    not at all. trimesh's own body_count needs scipy; this is a union-find
    over shared edges and needs nothing."""
    n = len(m.faces)
    parent = np.arange(n)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    e = m.edges_sorted
    order = np.lexsort((e[:, 1], e[:, 0]))
    e, owner = e[order], (order // 3)
    same = np.all(e[1:] == e[:-1], axis=1)
    for i in np.flatnonzero(same):
        a, b = find(owner[i]), find(owner[i + 1])
        if a != b:
            parent[a] = b
    return len({find(i) for i in range(n)})


def overhangs(m, limit_deg: float = 45.0, min_face: float = 1.0):
    """Downward-facing area steeper than `limit_deg`, once the part is laid
    out for printing. This build claims to need no supports anywhere, and
    that claim is worth measuring rather than asserting.

    Faces below `min_face` are ignored: the filleted surfaces are lofted as
    slabs one layer high, so each one leaves a tread a fraction of a square
    millimetre across. Those are the staircase, not an overhang -- the
    slicer quantises to the same layers anyway."""
    n = m.face_normals
    area = m.area_faces
    z0 = m.bounds[0][2]
    on_plate = np.array([m.vertices[f][:, 2].max() < z0 + 1e-3 for f in m.faces])
    facing = n[:, 2] < -math.cos(math.radians(90 - limit_deg))
    live = facing & ~on_plate & (area > min_face)
    # Split flat ceilings off: those are bridges, and a bridge is judged on
    # its span, not its area -- see max_bridge().
    flat = n[:, 2] < -0.996
    return float(area[live & ~flat].sum()), float(area[live & flat].sum())


# ---------------------------------------------------------------------------
# BACK -- the black rear cover. Four screws, and the only fasteners in the
# build: the chassis is captured rather than bolted.
# ---------------------------------------------------------------------------

def build_back():
    poly = pixel_poly()
    plate = yprism(poly, 0.0, BACK_T)

    def stand_on(p, h):
        # A feature landing exactly on the plate's face unions into a
        # coincident pair of faces that looks watertight until it is welded.
        return yprism(p, h, h + OVERLAP)

    rim = poly.buffer(-(WALL + 0.35)).simplify(SIMPLIFY)
    spigot = stand_on(rim.difference(rim.buffer(-2.4)), 2.0)
    relief = [ybore(BOSS_D + 6.4, 3.0, x, z, -0.5) for (x, z) in boss_positions()]
    adds = [plate, diff(spigot, *relief)]

    # --- pillars that press the chassis forward into its window. That is
    # what holds it: no screws, and no rattle either.
    push = DEPTH - CH_D
    for sx in (-1, 1):
        for sz in (-1, 1):
            adds.append(ybore(7.0, push + OVERLAP, sx * (CH_W / 2 - 3.0),
                              CH_CZ + sz * (CH_H / 2 - 3.0), -OVERLAP))
    # zip-tie posts either side of the cable slot: a tug on the cable then
    # pulls on the enclosure and not on the board's USB connector
    for sx in (-1, 1):
        adds.append(ybore(3.2, 6.0 + OVERLAP, sx * (CABLE_W / 2 + 3.5),
                          4.0, -OVERLAP))

    plate = union(*adds)

    cuts = [ybore(SCREW_D, BACK_T + 2, x, z, -BACK_T - 1)
            for (x, z) in boss_positions()]
    cuts.append(yprism(rrect(CABLE_W, CABLE_H, 4.0, cz=4.0 + CABLE_H / 2),
                       1.0, BACK_T + 2))
    # vents, out in the flippers where the chassis is not in the way
    for sx in (-1, 1):
        for i in range(3):
            cuts.append(yprism(rrect(4.0, 8.0, 2.0, cx=sx * 30.0,
                                     cz=46.0 + i * 10.0),
                               1.0, BACK_T + 2))
    return diff(plate, *cuts)


# ---------------------------------------------------------------------------
# EYES and BEAK -- press-fits, no fasteners
# ---------------------------------------------------------------------------

def build_eyes():
    """Two white plugs on a bar, each with a pupil sunk into its face.

    The pupil goes all the way through, plug and bar both. Behind it is the
    inside of the head, which is black PLA: face on, from across the room,
    that reads as a dark pupil. A blind pocket would only have been a
    shadow, and a shadow disappears the moment you look at it straight.

    It also means the pupils pick up a little of the spill light that gets
    into the head, so in a dark room the eyes glow faintly too."""
    s = EYE_SIZE - 2 * PRESS_CLEAR
    t = WALL + 1.6
    parts, cuts, eyes = [], [], []
    for c in EYE_COLS:
        b = cell(c, EYE_ROW).bounds
        cx, cz = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        eyes.append((cx, cz))
        parts.append(cube(s, t, s, cx, DEPTH - t / 2, cz - s / 2))
        cuts.append(cube(PUPIL_SIZE, t + 4.0, PUPIL_SIZE, cx,
                         DEPTH - (t + 4.0) / 2 + EPS,
                         cz - PUPIL_SIZE / 2 - PUPIL_DROP))
    # a bar behind both plugs: they cannot be pushed out the front, and it is
    # one part to fit instead of two to lose
    parts.append(cube(abs(eyes[1][0] - eyes[0][0]) + s, 1.8, s,
                      (eyes[0][0] + eyes[1][0]) / 2, DEPTH - t - 0.9,
                      eyes[0][1] - s / 2))
    return diff(union(*parts), *cuts)


def build_beak():
    """A blunt wedge with a tang. Sits proud of the face by one voxel."""
    b = span(BEAK_COLS[0], BEAK_COLS[1], BEAK_ROW, BEAK_ROW).bounds
    cx, cz = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    tw, th = BEAK_W - 3.0 - 2 * PRESS_CLEAR, BEAK_H - 3.0 - 2 * PRESS_CLEAR
    head = cube(BEAK_W, BEAK_OUT + OVERLAP, BEAK_H, cx,
                DEPTH + BEAK_OUT / 2 - OVERLAP / 2, cz - BEAK_H / 2)
    tang = cube(tw, WALL + 1.6, th, cx, DEPTH - WALL / 2 - 0.8, cz - th / 2)
    return union(head, tang)


# ---------------------------------------------------------------------------

COLOUR = {"body": "black", "back": "black", "beak": "black",
          "chassis": "white", "eyes": "white"}
# False = open side on the plate; True = the glowing face on the plate.
FRONT_DOWN = {"chassis", "beak"}


def fastener_report():
    """Print the screw arithmetic rather than asserting it silently, so that
    changing a thickness shows immediately what it did to engagement."""
    print("\nFASTENERS -- M3 x 1/4\" (6.35 mm), 4 off, into 4 M3 heat-set inserts")
    print(f"  insert pocket        {INSERT_BORE:.2f} mm dia x {INSERT_DEPTH:.1f} mm"
          f"  ({INSERT_GRIP:.2f} mm under a {INSERT_OD:.1f} mm insert, to melt into)")
    print(f"  bore depth           {BORE_DEPTH:.2f} mm"
          f"  (insert {INSERT_DEPTH:.1f} + {SCREW_RUNOUT:.1f} runout for the tip)")
    eng = SCREW_LEN - BACK_T
    free = BORE_DEPTH - eng
    ok = eng >= 3.0 and free > 0.4
    print(f"  back cover x4        through {BACK_T:.1f} mm -> {eng:.2f} mm engaged "
          f"({eng / 3.0:.2f}xD), {free:.2f} mm past the tip   {'ok' if ok else 'FAIL'}")
    print("  chassis              no screws: captured between the window and"
          " the cover's pillars")
    print("  eyes, beak           press fit, no fasteners")

    # The USB connector points down off the bottom of the board. Whether a
    # plug can actually reach it is a number, so print the number.
    z_conn = BOARD_CZ - BOARD_L / 2
    room = z_conn - WALL
    good_plug = room >= PLUG_L
    ok &= good_plug
    print(f"\n  USB connector at z={z_conn:.1f}, {room:.1f} mm of clear"
          f" drop for a {PLUG_L:.0f} mm plug"
          f"   {'ok' if good_plug else 'WILL NOT PLUG IN'}")

    tail = 0.0 if LEDS == "ring" else LED_BODY
    what = "ring, flush" if LEDS == "ring" else f"{LED_D:.0f} mm LED"
    gap = BOARD_Y - (SHELF_Y + SHELF_T)
    good = gap >= 2.0
    ok &= good
    print(f"\n  LEDs sit {SHELF_Y + SHELF_T - tail:.1f}-{SHELF_Y + SHELF_T:.1f} mm"
          f" behind the belly ({what}); board clears them by {gap:.1f} mm"
          f"   {'ok' if good else 'TIGHT'}")
    return ok


def board_envelope():
    """The dev board plus the tallest thing on it, as a solid, so the fit
    check can see whether anything is parked where the board goes."""
    return yprism(rrect(BOARD_W, BOARD_L, 1.0, cz=BOARD_CZ),
                  DEPTH - BOARD_Y, 1.6 + BOARD_TALL)


def led_envelope():
    """The six LEDs, as solids: body through the shelf plus the length of
    lead you need behind it to bend and solder.

    Their holes are cut through the shelf, so this only ever finds something
    that has been parked IN FRONT OF or BEHIND a hole -- a board post, a
    retention tab, a wall. Which is exactly the mistake worth catching."""
    d = LED_D + 2 * LED_CLEAR - 0.1
    back = DEPTH - SHELF_Y - SHELF_T - LED_LEAD
    return union(*[
        ybore(d, LED_BODY + LED_LEAD + 3.0,
              LED_CIRCLE_D / 2 * math.cos(2 * math.pi * i / LED_COUNT + math.pi / 6),
              LED_CZ + LED_CIRCLE_D / 2 * math.sin(2 * math.pi * i / LED_COUNT + math.pi / 6),
              back)
        for i in range(LED_COUNT)])


def plug_envelope():
    """The USB plug, as a solid, hanging off the bottom of the board.

    Nothing in the mesh represents it and nothing forces it to fit, which is
    exactly why it has to be checked: a connector you cannot reach is a
    build you cannot finish."""
    z_conn = BOARD_CZ - BOARD_L / 2
    return cube(PLUG_W, PLUG_T, PLUG_L, 0.0,
                DEPTH - BOARD_Y - 0.8, z_conn - PLUG_L)


def interference(parts):
    """Boolean-intersect the assembled parts. Anything above a rounding
    error is two pieces of plastic trying to occupy the same place."""
    print("\nFIT -- assembled interference (cm3)")
    parts = dict(parts, board=board_envelope(), plug=plug_envelope(),
                 leds=led_envelope())
    pairs = [("body", "back"), ("body", "chassis"), ("body", "eyes"),
             ("body", "beak"), ("back", "chassis"), ("chassis", "eyes"),
             ("board", "body"), ("board", "chassis"), ("board", "back"),
             ("plug", "body"), ("plug", "chassis"), ("plug", "back"),
             ("leds", "chassis"), ("leds", "board"), ("leds", "plug")]
    ok = True
    for a, b in pairs:
        if a not in parts or b not in parts:
            continue
        v = inter(parts[a], parts[b]).volume / 1000.0
        # the retention tabs are meant to overlap the board's edge; that is
        # the whole point of them. Everything else must clear.
        expected = (a, b) == ("board", "chassis")
        good = v <= (0.12 if expected else 0.02)
        ok &= good
        note = "  <- retention tabs, by design" if expected else ""
        print(f"  {a:<9} / {b:<9} {v:8.3f}   {'ok' if good else 'CLASH'}{note}")
    return ok


def max_bridge() -> float:
    """Widest unsupported span in the chassis's LED shelf: it is the only
    ceiling in the build, and a bridge is judged on span, not area."""
    ob = ch_rect(FLARE).bounds
    ib = (ob[0] + CH_WALL, ob[1] + CH_WALL, ob[2] - CH_WALL, ob[3] - CH_WALL)
    region = sbox(ib[0], BOARD_CZ - BOARD_L / 2 + SHELF_DROP, ib[2], ib[3])         .difference(sbox(ib[2] - SHELF_GAP, -500, ib[2], 500))
    lo, hi = 0.0, 60.0
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        if region.buffer(-mid).is_empty:
            hi = mid
        else:
            lo = mid
    return 2 * hi


def main():
    global INSERT_OD, INSERT_BORE, LED_D, LEDS, RING_OD, RING_ID

    ap = argparse.ArgumentParser(description="Generate rookery penguin parts.")
    ap.add_argument("--out", default="stl")
    ap.add_argument("--insert-od", type=float, default=INSERT_OD,
                    help="heat-set insert outer diameter (measure yours)")
    ap.add_argument("--led-d", type=float, default=LED_D,
                    help="LED body diameter: 5.0 or 3.0")
    ap.add_argument("--leds", choices=("discrete", "ring"), default=LEDS,
                    help="six through-hole LEDs, or one WS2812B ring "
                         "(firmware env:esp32s3-neopixel)")
    ap.add_argument("--ring-od", type=float, default=RING_OD)
    ap.add_argument("--ring-id", type=float, default=RING_ID)
    ap.add_argument("--face", choices=("blank", "smiley", "chick", "text"),
                    default="blank",
                    help="cut a glyph into the belly; blank is a plain glow")
    ap.add_argument("--text", default="AFK",
                    help="--face text content; <=4 characters lights evenly")
    ap.add_argument("--plate", type=float, default=PLATE,
                    help="build plate size; 180 = Bambu A1 mini, 256 = A1/P1/X1")
    ap.add_argument("--no-check", action="store_true",
                    help="skip the assembled interference check (slow)")
    args = ap.parse_args()

    INSERT_OD = args.insert_od
    INSERT_BORE = INSERT_OD - INSERT_GRIP
    LED_D = args.led_d
    LEDS = args.leds
    RING_OD, RING_ID = args.ring_od, args.ring_id

    os.makedirs(args.out, exist_ok=True)

    parts = {
        "body": build_body(),
        "chassis": build_chassis(args.face, args.text),
        "back": build_back(),
        "eyes": build_eyes(),
        "beak": build_beak(),
    }

    print(f"{'part':<12}{'solid':>8}{'vol cm3':>10}{'~g':>6}"
          f"{'size mm':>24}{'plate':>8}{'lumps':>7}{'ovrhng':>8}{'bridged':>9}")
    bad = 0
    for name, m in parts.items():
        e = m.extents
        w = trimesh.Trimesh(vertices=np.round(m.vertices, 6),
                            faces=m.faces.copy(), process=True)
        ok = w.is_watertight and w.is_winding_consistent
        p = orient(m, name in FRONT_DOWN)
        fits = (p.extents[0] <= args.plate and p.extents[1] <= args.plate
                and p.extents[2] <= PLATE_Z)
        slope, bridged = overhangs(p)
        lumps = pieces(m)
        bad += (not ok) + (not fits) + (slope > 40.0) + (lumps != 1)
        print(f"  {name:<10}{('ok' if ok else 'BROKEN'):>8}{m.volume / 1000:>10.1f}"
              f"{m.volume / 1000 * 1.24:>6.0f}"
              f"{f'{e[0]:.0f} x {e[1]:.0f} x {e[2]:.0f}':>24}"
              f"{('ok' if fits else 'TOO BIG'):>8}"
              f"{(str(lumps) if lumps == 1 else f'{lumps} !!'):>7}"
              f"{f'{slope:.0f}':>8}{f'{bridged:.0f}':>9}")
        p.export(os.path.join(args.out, f"{name}.stl"))

    span_mm = max_bridge()
    print(f"\n  LED shelf bridges the chassis, widest span {span_mm:.0f} mm"
          f"   {'ok' if span_mm < 46 else 'TOO WIDE'}")
    bad += span_mm >= 46

    if not fastener_report():
        bad += 1
    if not args.no_check and not interference(parts):
        bad += 1

    print()
    n = 0
    for colour in ("black", "white"):
        items = [(k, orient(v, k in FRONT_DOWN))
                 for k, v in parts.items() if COLOUR[k] == colour]
        for layout in pack(items, plate=args.plate):
            n += 1
            fn = f"plate{n}_{colour}.3mf"
            write_3mf(os.path.join(args.out, fn), layout)
            print(f"  {fn:<22} {', '.join(nm for nm, _, _ in layout)}")

    if bad:
        print(f"\n  !! {bad} problem(s) above")
        raise SystemExit(1)
    print(f"\nwrote {len(parts)} STLs + {n} plate 3MFs to {args.out}/")


if __name__ == "__main__":
    main()
