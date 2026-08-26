#!/usr/bin/env python3
"""rookery enclosure generator -- the penguin.

Builds every printed part and writes STL plus one 3MF per print plate.
Plates are grouped by filament colour so a single-extruder machine never
needs a mid-print swap.

    pip install trimesh manifold3d shapely numpy
    python3 generate.py

Everything is parametric. The two numbers you are most likely to change are
INSERT_OD (measure your heat-set inserts) and BOARD_L/BOARD_W (measure your
dev board).

    python3 generate.py --insert-od 4.2 --text "BUSY"

FASTENERS
    Every screw in the build is the same one: M3 x 1/4" (6.35 mm), the
    standard PC case screw -- e.g. Micro Connectors SCW-50M3. Six of them,
    into six M3 heat-set inserts. Nothing else.

PRINT ORIENTATION
    The shell prints open-back-down. That puts the whole penguin silhouette
    in the build plate's XY plane, so the outline can be any shape it likes
    without a single overhang. Everything that has to be self-supporting --
    the belly seat, the insert lead-ins, the reflector cone -- is chamfered
    at 45 degrees or shallower.

SELF-CHECKS
    Every run measures what it just built and exits non-zero if anything is
    wrong: manifoldness after welding at file precision, plate fit,
    unsupported downward-facing area, the widest bridge in the shell's front
    skin, screw thread engagement, LED-to-board clearance, and a boolean
    interference test of the assembled parts against each other and against
    a solid standing in for the dev board. A bad parameter should fail here,
    not at the printer.
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

# -- silhouette, in the X-Z plane. Z is up; z=0 is the desk.
# A stack of circles along the spine plus two flipper lobes, closed with a
# fillet so the junctions blend, then clipped flat at the base.
BODY_CIRCLES = [(0.0, 97.0, 20.0),    # head
                (0.0, 80.0, 18.0),    # neck
                (0.0, 62.0, 31.0),    # shoulders
                (0.0, 45.0, 37.0),    # belly
                (0.0, 25.0, 33.0),
                (0.0, 10.0, 25.0)]    # base
FLIPPER = (37.0, 40.0, 7.5, 22.0, 12.0)   # x, z, semi-x, semi-z, tilt deg
BLEND_R = 3.5             # fills the concave junctions between circles
BASE_ROUND = 1.5          # takes the sharp corners off the clipped base

# -- depth
DEPTH = 46.0              # back plane (y=0) to the flat front face
EDGE_R = 11.0             # quarter-round fillet all around the front edge
WALL = 2.6
BACK_T = 3.0              # backplate thickness
SPIGOT_H = 2.0            # backplate locating lip, sits inside the shell
SPIGOT_CLEAR = 0.35

# -- dev board (ESP32-S3-DevKitC-1). MEASURE YOURS.
# Mounted upright on the backplate, USB connector pointing down.
BOARD_L, BOARD_W = 63.5, 25.5
BOARD_CLEAR = 0.6
BOARD_POST_H = 3.5        # clearance under the board for wires and solder
BOARD_CZ = 58.0           # centre height of the board
BOARD_TALL = 8.0          # tallest thing standing on the board
BOARD_WALL = 2.0

# -- cable exit, a notch in the back rim at desk level
CABLE_W, CABLE_H = 15.0, 10.0

# -- fasteners. One screw type for the whole build: M3 x 1/4".
SCREW_LEN = 25.4 / 4      # 6.35 mm under-head length
SCREW_D = 3.4             # M3 clearance

# Heat-set inserts. INSERT_OD is the INSERT's diameter; the hole is cut
# INSERT_GRIP smaller so there is material for the iron to melt and the
# knurls to bite. A hole at the insert's nominal OD leaves nothing to grip,
# and the insert spins the first time a screw is tightened.
INSERT_OD = 4.0
INSERT_LEN = 5.0          # the common M3 length; 3.0 and 5.7 also fit
INSERT_GRIP = 0.15
INSERT_LEADIN = 0.8       # 45-degree countersink, starts it straight
SCREW_RUNOUT = 2.0        # empty hole past the insert for the screw tip
BOSS_D = 9.0
BOSS_H = 14.0             # short enough to stay clear of the belly flange
POST_H = 22.0             # nest posts, floor to nest plate

# -- belly: the swappable white diffuser
BELLY_A, BELLY_B = 24.0, 27.0   # window semi-axes -> 48 x 54 mm of glow
BELLY_CZ = 41.0
BELLY_CLEAR = 0.2
BELLY_FLANGE = 3.0              # radial width of the retaining flange
BELLY_RING_T = 2.0              # straight section behind the 45-degree seat
BELLY_POCKET = 1.5              # how far the back pocket stops short of the rim
GLYPH_FLOOR = 0.9               # material left where the glyph glows
SMILEY_SCALE = 1.75             # the stock smiley was drawn for a smaller window
LENS_D0, LENS_D1, LENS_H = 26.0, 14.0, 2.6   # hotspot-killer boss
LENS_SIDES = 12                 # faceted: the glyph has to cut through it

# -- nest: LED holder plus reflector cone
LED_D = 5.0                     # LED body diameter; use 3.0 for 3mm LEDs
LED_CLEAR = 0.25
LED_CIRCLE_D = 15.0
LED_BODY = 8.6            # a 5mm LED, base of the dome to the flange
LED_COUNT = 6
NEST_Y = 22.0                   # y of the nest plate's back face
NEST_T = 3.0                    # deep bores hold the LEDs square
NEST_PLATE_A, NEST_PLATE_B = 13.0, 16.0
NEST_WALL = 1.8
NEST_PRELOAD = 0.5              # cone overshoots the belly and springs on to it
NEST_SCREW_X, NEST_SCREW_Z = 28.5, 41.0
NEST_EAR_D = 9.0
NEST_SPILL_W = 13.0             # gap in the cone's crown; lights the head

# -- alternative: one WS2812B ring instead of six discrete LEDs.
# The firmware already has this backend (env:esp32s3-neopixel). Three wires
# instead of thirteen -- see PRODUCTION.md for why that matters.
LEDS = "discrete"               # or "ring"
RING_OD, RING_ID, RING_T = 37.0, 23.0, 2.2   # MEASURE YOURS
RING_CLEAR = 0.4
RING_WALL = 3.5                 # plate material outboard of the ring

# -- face
EYE_D = 9.0
EYE_X, EYE_Z = 10.0, 97.0
EYE_TAPER = 1.2                 # bore narrows toward the front: cannot fall out
EYE_FLANGE = 2.5
BEAK_W, BEAK_H, BEAK_OUT = 16.0, 12.0, 7.0
BEAK_CZ = 84.0
PRESS_CLEAR = 0.18

EPS = 0.01
SEG = 64
OVERLAP = 0.15                # CSG union overlap
SIMPLIFY = 0.03               # polygon chord tolerance, mm. Well under a
                              # nozzle width, and it keeps the meshes to a
                              # size a slicer opens instantly.
SLAB = 0.2                    # loft slab height: one layer, so the staircase
                              # lands on layer boundaries and slices out flat
PLATE = 180.0                 # Bambu A1 mini build plate
PLATE_Z = 180.0


# ---------------------------------------------------------------------------
# helpers
#
# Everything is built from 2D shapely polygons that get extruded, then
# combined with manifold3d booleans. Two conventions matter:
#
#   * The SILHOUETTE lives in shapely's XY, where shapely-y means world Z.
#     `stand()` rotates a silhouette extrusion upright afterwards.
#   * Round features (nest, belly boss, screw bores) are built directly in
#     world XY and extruded along world Z, then rotated into place, because
#     they are bodies of revolution about the Y axis.
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


# ---------------------------------------------------------------------------
# SILHOUETTE AND LOFT
# ---------------------------------------------------------------------------

def silhouette() -> Polygon:
    """The penguin outline in the X-Z plane, z=0 at the desk."""
    parts = [Point(x, z).buffer(r, quad_segs=SEG // 4)
             for x, z, r in BODY_CIRCLES]
    cx, cz, a, b, tilt = FLIPPER
    for sx in (-1, 1):
        e = Polygon([(a * math.cos(t), b * math.sin(t))
                     for t in np.linspace(0, 2 * math.pi, 120, endpoint=False)])
        e = srotate(e, sx * tilt, origin=(0, 0))
        parts.append(stranslate(e, xoff=sx * cx, yoff=cz))
    s = unary_union(parts)
    s = (s.buffer(BLEND_R, quad_segs=SEG // 2)
          .buffer(-BLEND_R, quad_segs=SEG // 2))
    s = s.intersection(sbox(-300.0, 0.0, 300.0, 400.0))          # flat base
    s = (s.buffer(-BASE_ROUND, quad_segs=SEG // 4)
          .buffer(BASE_ROUND, quad_segs=SEG // 4))
    if s.geom_type == "MultiPolygon":
        s = max(s.geoms, key=lambda g: g.area)
    return s.simplify(SIMPLIFY)


def oval(a: float, b: float, cz: float = 0.0, n: int = 96) -> Polygon:
    """An ellipse in the X-Z plane."""
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return Polygon(np.column_stack([a * np.cos(t), cz + b * np.sin(t)]))


def half_width(poly: Polygon, z: float) -> float:
    """How far out the outline reaches at height z. Used to park bosses
    against the inner wall instead of hard-coding coordinates that quietly
    break the moment anyone edits the silhouette."""
    band = poly.intersection(sbox(-300.0, z - 0.25, 300.0, z + 0.25))
    if band.is_empty:
        return 0.0
    return max(abs(band.bounds[0]), abs(band.bounds[2]))


def _profile(edge_r: float, total: float, steps: int):
    """Distances behind the front face, and the inset at each.

    inset(0) = edge_r, so the flat front face is the silhouette pulled in by
    the fillet radius; inset(edge_r) = 0, the full silhouette. A quarter
    circle in between.
    """
    es = list(np.linspace(0.0, edge_r, steps + 1))
    if total > edge_r:
        es.append(total)
    out = []
    for e in es:
        if e >= edge_r:
            out.append((e, 0.0))
        else:
            out.append((e, edge_r - math.sqrt(max(edge_r ** 2 - (edge_r - e) ** 2, 0.0))))
    return out


def _slabs(prof, poly):
    """Stack extrusions between profile points. Every slab but the last
    overshoots into its neighbour so the union has no coplanar seam; the
    last one stops exactly, so the part's back face is a real plane."""
    out = []
    for k, ((e0, i0), (e1, i1)) in enumerate(zip(prof, prof[1:])):
        h = e1 - e0
        if h <= 1e-9:
            continue
        mid = 0.5 * (i0 + i1)
        p = poly.buffer(-mid, quad_segs=SEG // 4) if abs(mid) > 1e-9 else poly
        p = p.simplify(SIMPLIFY)
        if p.is_empty:
            continue
        last = k == len(prof) - 2
        out.append(solid(p, h if last else h + OVERLAP, e0))
    return out


def loft(poly: Polygon, edge_r: float, total: float, steps: int = 0):
    """Prism of depth `total` with a quarter-round fillet on the front edge.

    Built as a stack of slabs, each taking the inset at its own midpoint so
    the staircase error splits either side of the true surface. Extrusion
    runs 0..total measured BACK from the front face; `stand()` puts it in
    world coordinates.
    """
    steps = steps or max(4, int(math.ceil(edge_r / SLAB)))
    return union(*_slabs(_profile(edge_r, total, steps), poly))


def body(poly: Polygon, edge_r: float, total: float, y_front: float):
    """A filleted prism, placed with its flat front face at y_front."""
    return stand(loft(poly, edge_r, total), y_front)


def ytaper(poly: Polygon, y_front: float, length: float,
           off_front: float, off_back: float, steps: int = 0):
    """A solid whose cross-section is `poly` offset by a linearly varying
    amount, running back from y_front. Used for every 45-degree seat in the
    build: the belly, the shell's countersunk window, the reflector cone."""
    if abs(off_back - off_front) < 1e-9:
        # Constant offset. Stacking identical slabs would leave coincident
        # faces that only survive at full float precision -- one prism.
        return yprism(poly.buffer(off_front, quad_segs=SEG // 4)
                      if abs(off_front) > 1e-9 else poly, y_front, length)
    steps = steps or max(4, int(math.ceil(abs(off_back - off_front) / SLAB)))
    es = np.linspace(0.0, length, steps + 1)
    prof = [(e, -(off_front + (off_back - off_front) * (e / length)))
            for e in es]
    return stand(union(*_slabs(prof, poly)), y_front)


def surface_y(sil: Polygon, x: float, z: float) -> float:
    """Where the shell's front skin sits at (x, z).

    Flat at y=DEPTH across the middle, curving back through the EDGE_R
    fillet as you approach the outline. Lets features be placed against the
    real surface instead of a guessed plane."""
    d = Point(x, z).distance(sil.exterior)
    if not sil.contains(Point(x, z)):
        return 0.0
    if d >= EDGE_R:
        return DEPTH
    return DEPTH - EDGE_R + math.sqrt(max(EDGE_R ** 2 - (EDGE_R - d) ** 2, 0.0))


# ---------------------------------------------------------------------------
# derived geometry
# ---------------------------------------------------------------------------

Y_INNER = DEPTH - WALL                       # inner face of the front skin
BELLY_RUN = WALL + BELLY_FLANGE              # length of the 45-degree seat
BELLY_BACK = DEPTH - BELLY_RUN - BELLY_RING_T
INSERT_BORE = INSERT_OD - INSERT_GRIP
INSERT_DEPTH = INSERT_LEN + 0.6
BORE_DEPTH = INSERT_DEPTH + SCREW_RUNOUT
NEST_FRONT = NEST_Y + NEST_T                 # front face of the nest plate
CONE_LEN = (BELLY_BACK + NEST_PRELOAD) - NEST_FRONT


def boss_positions(sil: Polygon):
    """Park the four backplate bosses against the inner wall, low and high
    on each side, wherever the silhouette actually is."""
    inner = sil.buffer(-WALL)
    out = []
    for z in (18.0, 64.0):
        w = half_width(inner, z)
        out += [(sx * (w - BOSS_D / 2 - 0.4), z) for sx in (-1, 1)]
    return out


def rrect(w: float, h: float, r: float, cx=0.0, cz=0.0) -> Polygon:
    r = min(r, w / 2 - 0.01, h / 2 - 0.01)
    return sbox(cx - w / 2 + r, cz - h / 2 + r,
                cx + w / 2 - r, cz + h / 2 - r).buffer(r, quad_segs=SEG // 4)


def beak_poly() -> Polygon:
    """A rounded triangle pointing down, blended into the head."""
    tri = Polygon([(-BEAK_W / 2 + 2, BEAK_CZ + BEAK_H / 2),
                   (BEAK_W / 2 - 2, BEAK_CZ + BEAK_H / 2),
                   (0.0, BEAK_CZ - BEAK_H / 2)])
    return tri.buffer(2.0, quad_segs=SEG // 4)


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
# SHELL -- the black outer body. Prints open-back-down, no supports.
# ---------------------------------------------------------------------------

def build_shell():
    sil = silhouette()
    outer = body(sil, EDGE_R, DEPTH, DEPTH)
    cavity = body(sil.buffer(-WALL, quad_segs=SEG // 4),
                  max(EDGE_R - WALL, 1.5), DEPTH + 3.0, Y_INNER)

    # --- the beak, an integral 45-degree wedge on the front skin. It is
    # unioned on BEFORE hollowing: cut afterwards, its buried tail would hang
    # a flat slab of plastic in mid-air inside the shell.
    tip = surface_y(sil, 0.0, BEAK_CZ) + BEAK_OUT
    beak = ytaper(beak_poly(), tip, BEAK_OUT + 5.0, -BEAK_OUT, 5.0)

    shell = diff(union(outer, beak), cavity)

    # --- backplate bosses, clipped to the outer skin so nothing pokes out
    adds = []
    for (x, z) in boss_positions(sil):
        adds.append(ybore(BOSS_D, BOSS_H, x, z, 0.0))
        adds.append(ycone(BOSS_D + 5.0, BOSS_D, 3.0, x, z, 0.0))   # base fillet
    shell = union(shell, inter(union(*adds), outer))

    cuts = []
    # --- belly window: a 45-degree countersink through the front skin. The
    # belly's own 45-degree rim wedges into it, self-centring, and cannot
    # pass forward.
    cuts.append(ytaper(oval(BELLY_A + BELLY_CLEAR, BELLY_B + BELLY_CLEAR,
                            BELLY_CZ),
                       DEPTH + 1.0, 1.0 + WALL, -1.0, WALL))

    # --- eyes: bores that narrow toward the front, so the plugs seat from
    # inside and cannot fall out forward.
    for sx in (-1, 1):
        cuts.append(ycone(EYE_D + EYE_TAPER, EYE_D, 14.0,
                          sx * EYE_X, EYE_Z, DEPTH - 12.0))

    # --- heat-set pockets for the backplate, mouths facing out of the open
    # back. Every insert in the build goes in from a face you can stand an
    # iron on: these four here, and the nest's two on the backplate.
    for (x, z) in boss_positions(sil):
        cuts.extend(insert_pocket(x, z, 0.0, True))

    # --- rubber-foot recesses underneath. The flat part of the base only
    # runs y=0 to DEPTH-EDGE_R; past that the front fillet has curved away,
    # so keep both pairs inside it.
    for sx in (-1, 1):
        for fy in (9.0, DEPTH - EDGE_R - 6.0):
            cuts.append(cyl(11.0, 0.7, sx * 13.0, fy, -EPS))

    shell = diff(shell, *cuts)
    # loft slabs overlap by OVERLAP, so the back runs a hair past y=0.
    # Trim it: the backplate has to seat on a real plane.
    return inter(shell, cube(400, 400, 400, 0, 200, -200))


# ---------------------------------------------------------------------------
# BACKPLATE -- the black rear panel. The board mounts here, so the whole
# electrical assembly is built on the bench and dropped in as one piece.
# ---------------------------------------------------------------------------

def build_backplate():
    sil = silhouette()
    plate = yprism(sil, 0.0, BACK_T)                     # y -BACK_T .. 0

    # Everything that stands on the plate starts a hair below y=0. A feature
    # that lands exactly on the plate's face unions into a coincident pair of
    # faces that looks watertight until someone else's slicer welds it.
    def stand_on(poly, h):
        return yprism(poly, h, h + OVERLAP)

    # locating lip: sits inside the shell wall, stops the plate sliding
    spigot_o = sil.buffer(-(WALL + SPIGOT_CLEAR), quad_segs=SEG // 4)
    spigot = stand_on(spigot_o.difference(
        spigot_o.buffer(-2.4, quad_segs=SEG // 4)), SPIGOT_H)
    # ...with reliefs where the shell's bosses and posts land, sized for the
    # cone fillet at their base rather than the boss itself
    relief = []
    for (x, z) in boss_positions(sil):
        relief.append(ybore(BOSS_D + 6.4, SPIGOT_H + 2, x, z, -1.0))
    spigot = diff(spigot, *relief)

    # --- board pocket
    bw, bl = BOARD_W + 2 * BOARD_CLEAR, BOARD_L + 2 * BOARD_CLEAR
    ring = rrect(bw + 2 * BOARD_WALL, bl + 2 * BOARD_WALL, 2.0, cz=BOARD_CZ)
    ring = ring.difference(rrect(bw, bl, 1.0, cz=BOARD_CZ))
    # open the bottom end so the USB connector and its plug clear the wall
    ring = ring.difference(sbox(-bw / 2 + 1.0, 0.0, bw / 2 - 1.0,
                                BOARD_CZ - bl / 2 + 1.0))
    adds = [plate, spigot, stand_on(ring, BOARD_POST_H + 2.4)]
    # --- nest posts. These live on the backplate rather than in the shell so
    # that their heat-set pockets face up off a flat part on the bench, and
    # so the nest, the loom and the board all come together as one
    # sub-assembly that drops into the shell in a single move.
    for sx in (-1, 1):
        x = sx * NEST_SCREW_X
        adds.append(ybore(BOSS_D, POST_H + OVERLAP, x, NEST_SCREW_Z, -OVERLAP))
        adds.append(ycone(BOSS_D + 5.0, BOSS_D, 4.0 + OVERLAP, x,
                          NEST_SCREW_Z, -OVERLAP))
    for sx in (-1, 1):
        for sz in (-1, 1):
            adds.append(ybore(6.0, BOARD_POST_H + OVERLAP,
                              sx * (bw / 2 - 5.0),
                              BOARD_CZ + sz * (bl / 2 - 5.0), -OVERLAP))
    # retention tabs: press the board down and it clicks under these
    for sx in (-1, 1):
        for sz in (-1, 1):
            adds.append(cube(2.6, 1.4, 12.0, sx * (bw / 2 - 0.3),
                             BOARD_POST_H + 1.6, BOARD_CZ + sz * 16.0 - 6.0))
    # zip-tie posts either side of the cable slot: strain relief, so a tug on
    # the cable pulls on the enclosure and not on the USB connector
    for sx in (-1, 1):
        adds.append(ybore(3.2, 6.0 + OVERLAP, sx * (CABLE_W / 2 + 3.5),
                          4.0, -OVERLAP))

    plate = union(*adds)

    cuts = []
    for (x, z) in boss_positions(sil):
        cuts.append(ybore(SCREW_D, BACK_T + 2, x, z, -BACK_T - 1))
    for sx in (-1, 1):
        cuts.extend(insert_pocket(sx * NEST_SCREW_X, NEST_SCREW_Z,
                                  POST_H, False))
    # cable slot: thread the USB cable through this before plugging it in
    cuts.append(yprism(rrect(CABLE_W, CABLE_H, 4.0, cz=4.0 + CABLE_H / 2),
                       1.0, BACK_T + 2))
    # vents: a column each side, clear of the board pocket and the cable slot
    for sx in (-1, 1):
        for i in range(4):
            z = 22.0 + i * 9.0
            w = half_width(sil.buffer(-7.0), z)
            cuts.append(yprism(rrect(4.0, 16.0, 2.0,
                                     cx=sx * (w - 4.0), cz=z),
                               1.0, BACK_T + 2))
    return diff(plate, *cuts)


# ---------------------------------------------------------------------------
# NEST -- LED holder and reflector cone, in white PLA.
#
# Six LEDs in a 15 mm circle, only ever one of them lit, sitting 18 mm behind
# a 48 x 54 mm window: on its own that is a bright spot with a dim rim. The
# cone flares out to the full window and bounces the spill into the edges,
# and it presses the belly forward into its seat at the same time.
# ---------------------------------------------------------------------------

def build_nest():
    if LEDS == "ring":
        # The cone's front rim has to land on the belly's flange, so the
        # plate is an oval with the same 3 mm of extra height as the belly:
        # a constant buffer then reaches both axes at once.
        a = RING_OD / 2 + RING_WALL
        plate_o = oval(a, a + 3.0, BELLY_CZ)
    else:
        plate_o = oval(NEST_PLATE_A, NEST_PLATE_B, BELLY_CZ)
    cone_off = (BELLY_A + BELLY_CLEAR + 1.0) - plate_o.bounds[2]
    bar = rrect(2 * NEST_SCREW_X + NEST_EAR_D, NEST_EAR_D, NEST_EAR_D / 2,
                cz=NEST_SCREW_Z)
    plate = yprism(unary_union([plate_o, bar]), NEST_FRONT, NEST_T)

    cone = diff(ytaper(plate_o, BELLY_BACK + NEST_PRELOAD, CONE_LEN,
                       cone_off, 0.0),
                ytaper(plate_o, BELLY_BACK + NEST_PRELOAD + EPS,
                       CONE_LEN + EPS, cone_off - NEST_WALL, -NEST_WALL))
    # a gap in the crown: spill light goes up the body and reaches the eyes
    cone = diff(cone, cube(NEST_SPILL_W, CONE_LEN + 2, 40.0, 0.0,
                           NEST_FRONT, BELLY_CZ + NEST_PLATE_B + 1.0))

    nest = union(plate, cone)

    cuts = []
    if LEDS == "ring":
        # Seat in the front face; the ring's own LEDs point forward out of
        # it. Located, not clamped -- a dab of hot glue or a scrap of foam
        # tape holds it, which is what everyone does with these anyway.
        # Only as deep as the plate can spare -- the ring sits a little
        # proud rather than leaving a floppy floor under it. The recess
        # locates the ring; it does not have to swallow it.
        depth = min(RING_T, NEST_T - 1.4)
        cuts.append(ybore(RING_OD + 2 * RING_CLEAR, depth + EPS, 0.0,
                          BELLY_CZ, NEST_FRONT - depth))
        cuts.append(yprism(rrect(12.0, 7.0, 3.0,
                                 cz=BELLY_CZ - (RING_OD + RING_ID) / 4),
                           NEST_FRONT + EPS, NEST_T + 2 * EPS))
    else:
        for i in range(LED_COUNT):
            a = 2 * math.pi * i / LED_COUNT + math.pi / 6
            cuts.append(ybore(LED_D + 2 * LED_CLEAR, NEST_T + 2 * EPS,
                              LED_CIRCLE_D / 2 * math.cos(a),
                              BELLY_CZ + LED_CIRCLE_D / 2 * math.sin(a),
                              NEST_Y - EPS))
    for sx in (-1, 1):
        cuts.append(ybore(SCREW_D, NEST_T + 2 * EPS, sx * NEST_SCREW_X,
                          NEST_SCREW_Z, NEST_Y - EPS))
    return diff(nest, *cuts)


# ---------------------------------------------------------------------------
# EYES -- two translucent plugs on a bridge, white PLA.
# ---------------------------------------------------------------------------

def build_eyes(outer):
    eye_back = DEPTH - 12.0
    parts = []
    for sx in (-1, 1):
        parts.append(inter(outer,
                           ycone(EYE_D + EYE_TAPER - 2 * PRESS_CLEAR,
                                 EYE_D - 2 * PRESS_CLEAR, 14.0,
                                 sx * EYE_X, EYE_Z, eye_back)))
        parts.append(ybore(EYE_D + 2 * EYE_FLANGE, 2.0, sx * EYE_X, EYE_Z,
                           eye_back))
    parts.append(yprism(rrect(2 * EYE_X, 6.0, 3.0, cz=EYE_Z),
                        eye_back + 2.0, 2.0))
    return union(*parts)


# ---------------------------------------------------------------------------
# GLYPHS
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
    return pixels_to_poly(CHICK, 3.1, cy=BELLY_CZ)


def smiley_at() -> Polygon:
    # The stock smiley was drawn for the old 44 x 24 mm window. This one is
    # 48 x 54, so scale it up to actually fill the belly.
    return stranslate(sscale(smiley_poly(), xfact=SMILEY_SCALE,
                             yfact=SMILEY_SCALE, origin=(0, 0)),
                      yoff=BELLY_CZ)


def text_poly(text: str) -> Polygon:
    rows = text_rows(text)
    w_px = max(len(r) for r in rows)
    # Fit inside the oval window with a margin, capped so it stays legible.
    px = min(3.4, (2 * BELLY_A - 8) / w_px, (2 * BELLY_B - 16) / 7)
    return pixels_to_poly(rows, px, cy=BELLY_CZ)


# ---------------------------------------------------------------------------
# BELLY -- the swappable white diffuser, and the only part that is ever
# meant to come out again.
#
# Profile, front face to back:
#     0.0 .. 2.6   the window plug, a 45-degree cone that wedges into the
#                  shell's countersunk opening -- self-centring, cannot fall
#                  forward, and flush with the skin
#     2.6 .. 5.6   the seat carries on at 45 degrees into the flange
#     5.6 .. 7.6   flange, straight
# The middle is pocketed out from the back, leaving a 2.6 mm window with a
# conical boss at its centre. That boss is the point: it puts extra material
# exactly where the LED beam is strongest and taper everywhere else, which
# is what turns a bright spot into an even glow.
# ---------------------------------------------------------------------------

def build_belly(kind: str, text: str = "AFK"):
    o = oval(BELLY_A, BELLY_B, BELLY_CZ)
    part = union(ytaper(o, DEPTH, BELLY_RUN, 0.0, BELLY_RUN),
                 ytaper(o, DEPTH - BELLY_RUN, BELLY_RING_T,
                        BELLY_RUN, BELLY_RUN))
    pocket = yprism(o.buffer(-BELLY_POCKET, quad_segs=SEG // 4),
                    Y_INNER, (Y_INNER - BELLY_BACK) + 1.0)
    part = diff(part, pocket)
    # Extend the boss a little past the pocket ceiling so the union has no
    # coplanar face to leave a duplicate at.
    slope = (LENS_D0 - LENS_D1) / LENS_H
    part = union(part, ycone(LENS_D1, LENS_D0 + slope * 0.6, LENS_H + 0.6,
                             0.0, BELLY_CZ, Y_INNER - LENS_H, sides=LENS_SIDES))

    if kind == "blank":
        return part
    if kind == "smiley":
        poly = smiley_at()
    elif kind == "chick":
        poly = chick_poly()
    elif kind == "text":
        poly = text_poly(text)
    else:
        raise ValueError(kind)

    # Thin the glyph from the BACK to a uniform GLYPH_FLOOR. The front face
    # stays flat and smooth -- it prints against the build plate.
    depth = (DEPTH - GLYPH_FLOOR) - (BELLY_BACK - 1.0)
    return diff(part, yprism(poly, DEPTH - GLYPH_FLOOR, depth))


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


def pack(items, plate=PLATE, gap=8.0, margin=8.0):
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

def fastener_report():
    """Every screw in the build is an M3 x 1/4" PC case screw. Print the
    arithmetic rather than asserting it silently, so anyone changing a
    thickness can see immediately what it did to thread engagement."""
    print("\nFASTENERS -- M3 x 1/4\" (6.35 mm), 6 off, into 6 M3 heat-set inserts")
    print(f"  insert pocket        {INSERT_BORE:.2f} mm dia x {INSERT_DEPTH:.1f} mm"
          f"  ({INSERT_GRIP:.2f} mm under a {INSERT_OD:.1f} mm insert, to melt into)")
    print(f"  bore depth           {BORE_DEPTH:.2f} mm"
          f"  (insert {INSERT_DEPTH:.1f} + {SCREW_RUNOUT:.1f} runout for the tip)")
    ok = True
    for label, stack, count in (("backplate", BACK_T, 4), ("nest", NEST_T, 2)):
        eng = SCREW_LEN - stack
        free = BORE_DEPTH - eng
        good = eng >= 3.0 and free > 0.4
        ok &= good
        print(f"  {label:<10} x{count}       through {stack:.1f} mm -> "
              f"{eng:.2f} mm engaged ({eng / 3.0:.2f}xD), "
              f"{free:.2f} mm past the tip   {'ok' if good else 'FAIL'}")
    print("  head                 pan head sits proud on the outside by design;"
          " nothing bears on it")

    # The LEDs stick out the back of the nest, straight at the dev board.
    # Nothing in the mesh represents them, so check the number here.
    tail = 0.0 if LEDS == "ring" else LED_BODY
    what = "ring, flush" if LEDS == "ring" else f"{LED_D:.0f} mm LED"
    gap = (NEST_FRONT - tail) - (BOARD_POST_H + 1.6 + BOARD_TALL)
    good = gap >= 2.0
    ok &= good
    print(f"\n  LED tails clear the board by {gap:.1f} mm"
          f"  ({what}, {BOARD_TALL:.0f} mm of headers)"
          f"   {'ok' if good else 'TIGHT -- raise NEST_Y'}")
    return ok


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


def max_bridge(sil: Polygon) -> float:
    """Widest unsupported span in the shell's front skin.

    Printed open-back-down, the skin closes over the cavity, so it bridges.
    Bridges are fine; long ones are not. This measures the worst one instead
    of hoping."""
    region = (sil.buffer(-(WALL + EDGE_R - WALL), quad_segs=SEG // 4)
              .difference(oval(BELLY_A + BELLY_CLEAR + WALL,
                               BELLY_B + BELLY_CLEAR + WALL, BELLY_CZ)))
    for sx in (-1, 1):
        region = region.difference(
            Point(sx * EYE_X, EYE_Z).buffer(EYE_D / 2, quad_segs=SEG // 4))
    lo, hi = 0.0, 60.0
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        if region.buffer(-mid, quad_segs=SEG // 4).is_empty:
            hi = mid
        else:
            lo = mid
    return 2 * hi


def board_envelope():
    """The dev board plus the tallest thing on it, as a solid, so the fit
    check can see whether anything is parked where the board goes."""
    return yprism(rrect(BOARD_W, BOARD_L, 1.0, cz=BOARD_CZ),
                  BOARD_POST_H + 1.6 + BOARD_TALL, 1.6 + BOARD_TALL)


def interference(parts):
    """Boolean-intersect the assembled parts. Anything above a rounding
    error is two pieces of plastic trying to occupy the same place."""
    print("\nFIT -- assembled interference (cm3)")
    parts = dict(parts, board=board_envelope())
    pairs = [("shell", "backplate"), ("shell", "belly_blank"),
             ("shell", "nest"), ("shell", "eyes"),
             ("nest", "belly_blank"), ("backplate", "belly_blank"),
             ("backplate", "nest"),
             ("board", "shell"), ("board", "nest"), ("board", "belly_blank"),
             ("board", "eyes")]
    ok = True
    for a, b in pairs:
        if a not in parts or b not in parts:
            continue
        v = inter(parts[a], parts[b]).volume / 1000.0
        # the nest is meant to press on the belly; everything else must clear
        limit = 0.60 if (a, b) == ("nest", "belly_blank") else 0.02
        good = v <= limit
        ok &= good
        note = "  <- preload, by design" if (a, b) == ("nest", "belly_blank") else ""
        print(f"  {a:<10} / {b:<12} {v:8.3f}   {'ok' if good else 'CLASH'}{note}")
    return ok


# ---------------------------------------------------------------------------

# Which filament each part wants. Plates are grouped by colour so a
# single-extruder machine never needs a mid-print swap.
COLOUR = {
    "shell": "black",
    "backplate": "black",
    "nest": "white",
    "eyes": "white",
    "belly_blank": "white",
    "belly_smiley": "white",
    "belly_chick": "white",
    "belly_text": "white",
}

# False = back face on the plate, True = visible front face on the plate.
FRONT_DOWN = {"belly_blank", "belly_smiley", "belly_chick", "belly_text"}


def main():
    global INSERT_OD, INSERT_BORE, LED_D, BELLY_CLEAR, LEDS, RING_OD, RING_ID

    ap = argparse.ArgumentParser(description="Generate rookery penguin parts.")
    ap.add_argument("--out", default="stl")
    ap.add_argument("--insert-od", type=float, default=INSERT_OD,
                    help="heat-set insert outer diameter (measure yours)")
    ap.add_argument("--led-d", type=float, default=LED_D,
                    help="LED body diameter: 5.0 or 3.0")
    ap.add_argument("--leds", choices=("discrete", "ring"), default=LEDS,
                    help="six through-hole LEDs, or one WS2812B ring "
                         "(firmware env:esp32s3-neopixel)")
    ap.add_argument("--ring-od", type=float, default=RING_OD,
                    help="WS2812B ring outer diameter -- measure yours")
    ap.add_argument("--ring-id", type=float, default=RING_ID,
                    help="WS2812B ring inner diameter")
    ap.add_argument("--belly-clear", type=float, default=BELLY_CLEAR,
                    help="belly-to-shell clearance per side; raise it if the "
                         "belly is tight, lower it if it rattles")
    ap.add_argument("--text", default="AFK",
                    help="text belly content; <=4 chars lights most evenly")
    ap.add_argument("--plate", type=float, default=PLATE,
                    help="build plate size; 180 = Bambu A1 mini, 256 = A1/P1/X1")
    ap.add_argument("--no-check", action="store_true",
                    help="skip the assembled interference check (slow)")
    args = ap.parse_args()

    INSERT_OD = args.insert_od
    INSERT_BORE = INSERT_OD - INSERT_GRIP
    LED_D = args.led_d
    BELLY_CLEAR = args.belly_clear
    LEDS = args.leds
    RING_OD, RING_ID = args.ring_od, args.ring_id

    os.makedirs(args.out, exist_ok=True)

    sil = silhouette()
    outer = body(sil, EDGE_R, DEPTH, DEPTH)
    parts = {
        "shell": build_shell(),
        "backplate": build_backplate(),
        "nest": build_nest(),
        "eyes": build_eyes(outer),
        "belly_blank": build_belly("blank"),
        "belly_smiley": build_belly("smiley"),
        "belly_chick": build_belly("chick"),
        "belly_text": build_belly("text", args.text),
    }

    print(f"{'part':<16}{'solid':>8}{'vol cm3':>10}{'~g':>6}"
          f"{'size mm':>26}{'plate':>8}{'ovrhng':>7}{'bridged':>9}")
    bad = 0
    for name, m in parts.items():
        e = m.extents
        # Weld coincident vertices before judging: a mesh that only holds
        # together at full float precision will fail in someone else's slicer.
        w = trimesh.Trimesh(vertices=np.round(m.vertices, 6),
                            faces=m.faces.copy(), process=True)
        ok = w.is_watertight and w.is_winding_consistent
        p = orient(m, name in FRONT_DOWN)
        fits = (p.extents[0] <= args.plate and p.extents[1] <= args.plate
                and p.extents[2] <= PLATE_Z)
        bad += (not ok) + (not fits)
        slope, bridged = overhangs(p)
        bad += slope > 40.0
        print(f"  {name:<14}{('ok' if ok else 'BROKEN'):>8}{m.volume / 1000:>10.1f}"
              f"{m.volume / 1000 * 1.24:>6.0f}"
              f"{f'{e[0]:.1f} x {e[1]:.1f} x {e[2]:.1f}':>26}"
              f"{('ok' if fits else 'TOO BIG'):>8}"
              f"{f'{slope:.0f}':>7}{f'{bridged:.0f}':>9}")
        p.export(os.path.join(args.out, f"{name}.stl"))

    span = max_bridge(sil)
    print(f"\n  front skin bridges the cavity, widest span {span:.0f} mm"
          f"   {'ok' if span < 32 else 'TOO WIDE'}")
    bad += span >= 32

    if not fastener_report():
        bad += 1
    if not args.no_check and not interference(parts):
        bad += 1

    # --- plates, grouped by filament colour
    print()
    n = 0
    for colour in ("black", "white"):
        items = [(k, orient(v, k in FRONT_DOWN))
                 for k, v in parts.items() if COLOUR[k] == colour]
        for layout in pack(items, plate=args.plate):
            n += 1
            fn = f"plate{n}_{colour}.3mf"
            write_3mf(os.path.join(args.out, fn), layout)
            print(f"  {fn:<24} {', '.join(nm for nm, _, _ in layout)}")

    if bad:
        print(f"\n  !! {bad} problem(s) above")
        raise SystemExit(1)
    print(f"\nwrote {len(parts)} STLs + {n} plate 3MFs to {args.out}/")


if __name__ == "__main__":
    main()
