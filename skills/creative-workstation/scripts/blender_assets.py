"""Procedural 3D assets for the creative workstation, rendered headless with Blender Cycles (CPU).

Run with Blender, not system Python:

    blender -b -P blender_assets.py -- --out /path/to/media-library/3d-assets \
        --kind turntable --pieces king,queen,knight --material pearl --frames 120 --size 600x800

    blender -b -P blender_assets.py -- --out ... --kind board-orbit --frames 150 --size 1920x1080

    blender -b -P blender_assets.py -- --out ... --kind objects --frames 120 --size 512x512

Everything here is original geometry: chess pieces are lathed from hand-written profiles
(the knight is an extruded, bevelled silhouette), floating objects are primitives with
lavender/obsidian materials. Turntables render with a transparent film so they composite
over any background as PNG sequences with alpha. Each output folder gets a meta.json.
"""

import argparse
import json
import math
import os
import sys
import time

import bmesh
import bpy
from mathutils import Vector

# ---------------------------------------------------------------- arguments

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--kind", choices=["turntable", "board-orbit", "objects", "still"], default="turntable")
ap.add_argument("--pieces", default="king,queen,bishop,knight,rook,pawn")
ap.add_argument("--objects", default="orb,ring,cube,pill")
ap.add_argument("--material", choices=["pearl", "obsidian", "gold"], default="pearl")
ap.add_argument("--frames", type=int, default=120)
ap.add_argument("--size", default="600x800")
ap.add_argument("--samples", type=int, default=24)
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--only-frame", type=int, default=None, help="render a single frame (speed test)")
args = ap.parse_args(argv)
W, H = (int(v) for v in args.size.lower().split("x"))

# ---------------------------------------------------------------- scene setup


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = args.samples
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.cycles.max_bounces = 6
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.resolution_percentage = 100
    sc.render.fps = args.fps
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.color_depth = "8"
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "None"
    except Exception:
        sc.view_settings.view_transform = "Filmic"
    sc.render.threads_mode = "AUTO"
    sc.cycles.film_transparent_glass = True
    return sc


def world(color=(0.035, 0.018, 0.07), strength=1.0):
    w = bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*color, 1)
    bg.inputs["Strength"].default_value = strength


def principled(name, base, rough=0.2, coat=0.6, metallic=0.0, sss=0.0, emission=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*base, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metallic
    for key, val in (("Coat Weight", coat), ("Coat Roughness", 0.05), ("Subsurface Weight", sss)):
        if key in p.inputs:
            p.inputs[key].default_value = val
    if emission and "Emission Color" in p.inputs:
        p.inputs["Emission Color"].default_value = (*emission, 1)
        p.inputs["Emission Strength"].default_value = 1.5
    return m


MATERIALS = {
    "pearl": lambda: principled("pearl", (0.60, 0.47, 0.93), rough=0.2, coat=0.8, sss=0.08),
    "obsidian": lambda: principled("obsidian", (0.045, 0.018, 0.09), rough=0.1, coat=1.0),
    "gold": lambda: principled("gold", (0.95, 0.74, 0.45), rough=0.22, coat=0.2, metallic=1.0),
}


def area_light(name, loc, energy, color, size, target=(0, 0, 0.8)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.color, ld.size = energy, color, size
    ob = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    direction = Vector(target) - Vector(loc)
    ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return ob


def studio_lights(scale=1.0):
    area_light("key", (-2.6 * scale, -2.8 * scale, 3.4 * scale), 520 * scale**2, (1.0, 0.92, 0.97), 2.2 * scale)
    area_light("rim", (2.4 * scale, 2.6 * scale, 2.6 * scale), 900 * scale**2, (0.72, 0.62, 1.0), 1.6 * scale)
    area_light("fill", (3.0 * scale, -2.2 * scale, 1.0 * scale), 60 * scale**2, (0.80, 0.68, 1.0), 3.0 * scale)


def camera(loc, target, lens=50, dof_target=None, fstop=2.8):
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    ob = bpy.data.objects.new("cam", cd)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = ob
    if dof_target is not None:
        cd.dof.use_dof = True
        cd.dof.focus_object = dof_target
        cd.dof.aperture_fstop = fstop
    return ob


# ---------------------------------------------------------------- geometry


def catmull(points, per_seg=10):
    """Catmull-Rom resample of a 2D (r, z) profile; endpoints kept."""
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(per_seg):
            t = s / per_seg
            t2, t3 = t * t, t * t * t
            out.append(tuple(
                0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                       + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in range(2)))
    out.append(points[-1])
    return [(max(0.0, r), z) for r, z in out]


BASE = [(0.0, 0.0), (0.43, 0.0), (0.44, 0.05), (0.40, 0.09), (0.41, 0.13), (0.33, 0.18), (0.26, 0.24)]

PROFILES = {
    "pawn": BASE + [(0.19, 0.34), (0.15, 0.50), (0.13, 0.62), (0.21, 0.66), (0.21, 0.70), (0.13, 0.73),
                    (0.17, 0.78), (0.20, 0.88), (0.17, 0.98), (0.10, 1.04), (0.0, 1.06)],
    "rook": BASE + [(0.25, 0.34), (0.23, 0.60), (0.22, 0.92), (0.30, 0.98), (0.31, 1.06), (0.30, 1.22),
                    (0.22, 1.22), (0.22, 1.14), (0.0, 1.14)],
    "bishop": BASE + [(0.20, 0.36), (0.15, 0.62), (0.13, 0.92), (0.23, 0.98), (0.23, 1.03), (0.14, 1.06),
                      (0.18, 1.16), (0.20, 1.28), (0.17, 1.42), (0.09, 1.54), (0.05, 1.58), (0.075, 1.62),
                      (0.06, 1.68), (0.0, 1.70)],
    "queen": BASE + [(0.21, 0.36), (0.16, 0.70), (0.14, 1.08), (0.25, 1.14), (0.25, 1.19), (0.15, 1.22),
                     (0.19, 1.34), (0.27, 1.52), (0.27, 1.56), (0.12, 1.58), (0.10, 1.66), (0.07, 1.74),
                     (0.0, 1.76)],
    "king": BASE + [(0.22, 0.36), (0.17, 0.75), (0.15, 1.16), (0.26, 1.22), (0.26, 1.27), (0.16, 1.30),
                    (0.21, 1.44), (0.25, 1.62), (0.13, 1.70), (0.0, 1.72)],
}


def lathe(name, profile, steps=72):
    pts = catmull(profile, per_seg=8)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = [bm.verts.new((r, 0.0, z)) for r, z in pts]
    for a, b in zip(verts, verts[1:]):
        bm.edges.new((a, b))
    bmesh.ops.spin(bm, geom=bm.verts[:] + bm.edges[:], cent=(0, 0, 0), axis=(0, 0, 1),
                   angle=math.tau, steps=steps, use_duplicate=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def add_mod_subsurf(ob, level=1):
    m = ob.modifiers.new("subsurf", "SUBSURF")
    m.levels, m.render_levels = level, level + 1


def boolean_cut(ob, cutter):
    m = ob.modifiers.new("cut", "BOOLEAN")
    m.operation, m.object, m.solver = "DIFFERENCE", cutter, "EXACT"
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def box(name, size, loc, rot_z=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    ob.rotation_euler[2] = rot_z
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    return ob


def sphere(name, r, loc):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=32, ring_count=16)
    ob = bpy.context.active_object
    ob.name = name
    bpy.ops.object.shade_smooth()
    return ob


def join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    objs[0].name = name
    return objs[0]


def knight():
    base = lathe("knight_base", BASE + [(0.24, 0.32), (0.0, 0.34)])
    sil = [(-0.22, 0.30), (-0.25, 0.60), (-0.21, 0.86), (-0.12, 1.10), (-0.02, 1.30), (0.04, 1.42),
           (0.08, 1.53), (0.13, 1.41), (0.23, 1.31), (0.35, 1.15), (0.43, 1.02), (0.43, 0.93),
           (0.34, 0.89), (0.24, 0.92), (0.14, 0.85), (0.10, 0.71), (0.17, 0.53), (0.23, 0.30)]
    me = bpy.data.meshes.new("knight_head")
    bm = bmesh.new()
    vs = [bm.verts.new((x, -0.13, z)) for x, z in sil]
    face = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=moved, vec=(0, 0.26, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    head = bpy.data.objects.new("knight_head", me)
    bpy.context.collection.objects.link(head)
    bev = head.modifiers.new("bevel", "BEVEL")
    bev.width, bev.segments, bev.limit_method = 0.06, 5, "ANGLE"
    bpy.context.view_layer.objects.active = head
    bpy.ops.object.modifier_apply(modifier=bev.name)
    eye_l = sphere("eye_l", 0.035, (0.22, -0.13, 1.17))
    eye_r = sphere("eye_r", 0.035, (0.22, 0.13, 1.17))
    head = join([head, eye_l, eye_r], "knight_head")
    for p in head.data.polygons:
        p.use_smooth = True
    add_mod_subsurf(head, 1)
    ob = join([base, head], "knight")
    return ob


def build_piece(kind):
    if kind == "knight":
        ob = knight()
    else:
        ob = lathe(kind, PROFILES[kind])
        if kind == "rook":
            for ang in (math.radians(45), math.radians(135)):
                boolean_cut(ob, box("notch", (0.8, 0.09, 0.2), (0, 0, 1.2), ang))
        if kind == "bishop":
            cutter = box("slit", (0.5, 0.03, 0.22), (0.12, 0, 1.40), 0)
            cutter.rotation_euler = (0, math.radians(-35), math.radians(90))
            boolean_cut(ob, cutter)
        if kind == "queen":
            balls = [sphere(f"q{i}", 0.045, (0.25 * math.cos(i * math.tau / 10), 0.25 * math.sin(i * math.tau / 10), 1.58))
                     for i in range(10)]
            balls.append(sphere("qtop", 0.07, (0, 0, 1.80)))
            ob = join([ob] + balls, "queen")
        if kind == "king":
            v = box("cross_v", (0.08, 0.08, 0.36), (0, 0, 1.86))
            h = box("cross_h", (0.26, 0.066, 0.08), (0, 0, 1.90))
            ob = join([ob, v, h], "king")
        bev = ob.modifiers.new("bevel", "BEVEL")
        bev.width, bev.segments, bev.limit_method = 0.012, 2, "ANGLE"
    ob.name = kind
    return ob


def floating_object(kind, mat):
    if kind == "orb":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.6, segments=64, ring_count=32)
        ob = bpy.context.active_object
        glass = bpy.data.materials.new("glass")
        glass.use_nodes = True
        p = glass.node_tree.nodes["Principled BSDF"]
        p.inputs["Base Color"].default_value = (0.86, 0.80, 1.0, 1)
        p.inputs["Roughness"].default_value = 0.04
        if "Transmission Weight" in p.inputs:
            p.inputs["Transmission Weight"].default_value = 1.0
        p.inputs["IOR"].default_value = 1.45
        ob.data.materials.append(glass)
        bpy.ops.object.shade_smooth()
        return ob
    if kind == "ring":
        bpy.ops.mesh.primitive_torus_add(major_radius=0.55, minor_radius=0.14, major_segments=96, minor_segments=32)
    elif kind == "cube":
        bpy.ops.mesh.primitive_cube_add(size=0.85)
        ob = bpy.context.active_object
        bev = ob.modifiers.new("bevel", "BEVEL")
        bev.width, bev.segments = 0.08, 6
    elif kind == "pill":
        bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=0.7, vertices=64)
        ob = bpy.context.active_object
        bev = ob.modifiers.new("bevel", "BEVEL")
        bev.width, bev.segments = 0.21, 10
    ob = bpy.context.active_object
    ob.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return ob


# ---------------------------------------------------------------- renders


def write_meta(folder, meta):
    with open(os.path.join(folder, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)


def render_sequence(folder, frames):
    os.makedirs(folder, exist_ok=True)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 0, frames - 1
    sc.render.filepath = os.path.join(folder, "f_")
    t0 = time.time()
    if args.only_frame is not None:
        sc.frame_set(args.only_frame)
        sc.render.filepath = os.path.join(folder, f"test_{args.only_frame:04d}.png")
        bpy.ops.render.render(write_still=True)
    else:
        bpy.ops.render.render(animation=True)
    return time.time() - t0


def turntable_pieces():
    for kind in [p.strip() for p in args.pieces.split(",") if p.strip()]:
        reset_scene()
        world((0.03, 0.015, 0.06), 0.6)
        bpy.context.scene.render.film_transparent = True
        mat = MATERIALS[args.material]()
        piece = build_piece(kind)
        piece.data.materials.append(mat)
        top = max((piece.matrix_world @ Vector(c)).z for c in piece.bound_box)
        pivot = bpy.data.objects.new("pivot", None)
        bpy.context.collection.objects.link(pivot)
        piece.parent = pivot
        studio_lights()
        aspect = W / H
        dist = 3.4 + top * 0.9
        camera((0, -dist, top * 0.62 + 0.55), (0, 0, top * 0.5), lens=55 if aspect < 1 else 45)
        n = args.frames
        pivot.rotation_euler = (0, 0, 0)
        pivot.keyframe_insert("rotation_euler", index=2, frame=0)
        pivot.rotation_euler = (0, 0, math.tau * (n / (n + 0.0)))
        pivot.keyframe_insert("rotation_euler", index=2, frame=n)
        for fc in pivot.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
        folder = os.path.join(args.out, f"chess-{kind}-{args.material}")
        secs = render_sequence(folder, n)
        write_meta(folder, {"asset": f"chess-{kind}-{args.material}", "type": "png-sequence-alpha",
                            "frames": n, "loop": True, "pattern": "f_%04d.png", "width": W, "height": H,
                            "degrees_per_frame": 360 / n, "render_seconds": round(secs, 1),
                            "engine": f"Blender {bpy.app.version_string} Cycles CPU {args.samples}spp",
                            "license": "Original procedural asset generated by this workstation (no third-party content)"})
        print(f"[blender_assets] {kind}: {n} frames in {secs:.1f}s -> {folder}", flush=True)


def turntable_objects():
    for kind in [p.strip() for p in args.objects.split(",") if p.strip()]:
        reset_scene()
        world((0.03, 0.015, 0.06), 0.8)
        bpy.context.scene.render.film_transparent = True
        mat = MATERIALS[args.material]()
        ob = floating_object(kind, mat)
        pivot = bpy.data.objects.new("pivot", None)
        bpy.context.collection.objects.link(pivot)
        ob.parent = pivot
        ob.rotation_euler = (math.radians(62), math.radians(18), 0)
        studio_lights(0.8)
        camera((0, -3.6, 0.6), (0, 0, 0), lens=55)
        n = args.frames
        for f, rz, rx in ((0, 0, 0), (n, math.tau, math.tau)):
            pivot.rotation_euler = (rx * 0.25 * 0, 0, rz)
            pivot.keyframe_insert("rotation_euler", frame=f)
        for fc in pivot.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
        folder = os.path.join(args.out, f"object-{kind}-{args.material}")
        secs = render_sequence(folder, n)
        write_meta(folder, {"asset": f"object-{kind}-{args.material}", "type": "png-sequence-alpha", "frames": n,
                            "loop": True, "pattern": "f_%04d.png", "width": W, "height": H,
                            "render_seconds": round(secs, 1),
                            "engine": f"Blender {bpy.app.version_string} Cycles CPU {args.samples}spp",
                            "license": "Original procedural asset generated by this workstation (no third-party content)"})
        print(f"[blender_assets] {kind}: {n} frames in {secs:.1f}s -> {folder}", flush=True)


def board_orbit():
    reset_scene()
    world((0.05, 0.022, 0.10), 1.0)
    pearl, obsidian = MATERIALS["pearl"](), MATERIALS["obsidian"]()
    sq = 0.62
    for i in range(8):
        for j in range(8):
            bpy.ops.mesh.primitive_cube_add(size=1, location=((i - 3.5) * sq, (j - 3.5) * sq, -0.06))
            t = bpy.context.active_object
            t.scale = (sq * 0.98, sq * 0.98, 0.12)
            t.data.materials.append(pearl if (i + j) % 2 else obsidian)
    layout = [("king", 3, 3, obsidian), ("queen", 4, 4, pearl), ("knight", 2, 4, pearl), ("bishop", 5, 2, obsidian),
              ("rook", 1, 1, obsidian), ("pawn", 4, 2, pearl), ("pawn", 3, 5, obsidian), ("pawn", 6, 4, pearl)]
    focus = None
    for kind, i, j, m in layout:
        ob = build_piece(kind)
        ob.location = ((i - 3.5) * sq, (j - 3.5) * sq, 0)
        ob.scale = (0.62, 0.62, 0.62)
        ob.rotation_euler[2] = math.radians(30 * (i + j))
        ob.data.materials.append(m)
        if kind == "king":
            focus = ob
    studio_lights(1.6)
    target = bpy.data.objects.new("focus", None)
    bpy.context.collection.objects.link(target)
    target.location = focus.location + Vector((0, 0, 0.6))
    cam = camera((0, -4.0, 1.6), target.location, lens=40, dof_target=target, fstop=2.2)
    con = cam.constraints.new("TRACK_TO")
    con.target, con.track_axis, con.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    n = args.frames
    for f in range(0, n + 1, max(1, n // 12)):
        a = math.radians(-110 + 70 * f / n)
        r = 4.3 - 0.9 * f / n
        cam.location = (target.location.x + r * math.cos(a), target.location.y + r * math.sin(a), 1.5 - 0.35 * f / n)
        cam.keyframe_insert("location", frame=f)
    folder = os.path.join(args.out, "chess-board-orbit")
    secs = render_sequence(folder, n)
    write_meta(folder, {"asset": "chess-board-orbit", "type": "png-sequence", "frames": n, "loop": False,
                        "pattern": "f_%04d.png", "width": W, "height": H, "fps": args.fps,
                        "render_seconds": round(secs, 1),
                        "engine": f"Blender {bpy.app.version_string} Cycles CPU {args.samples}spp DOF f/2.2",
                        "license": "Original procedural asset generated by this workstation (no third-party content)"})
    print(f"[blender_assets] board-orbit: {n} frames in {secs:.1f}s -> {folder}", flush=True)


if args.kind == "turntable":
    turntable_pieces()
elif args.kind == "objects":
    turntable_objects()
elif args.kind == "board-orbit":
    board_orbit()
