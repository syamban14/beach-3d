"""Generate a smooth stylized & rigged human character asset (person.blend & person.glb)."""

import math
import os
import bpy
import bmesh
from mathutils import Euler, Matrix, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(BASE_DIR, "assets", "blend", "person.blend")
GLB_PATH = os.path.join(BASE_DIR, "assets", "models", "person.glb")
PREVIEW_PATH = "/Users/syamban/.gemini/antigravity-cli/brain/a2810c20-f453-4255-9182-bae8a0819dcc/scratch/person_preview.png"

os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(PREVIEW_PATH), exist_ok=True)


def hex_to_rgba(hex_str, alpha=1.0):
    """Convert hex color string (#RRGGBB) to linear RGBA tuple for Blender."""
    s = hex_str.lstrip("#")
    r, g, b = (int(s[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

    def srgb_to_linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), alpha)


def smoothstep(edge0, edge1, x):
    """Hermite interpolation between 0 and 1."""
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0))) if edge1 != edge0 else 0.0
    return t * t * (3.0 - 2.0 * t)


def make_material(name, base_color, roughness=0.6, metallic=0.0, coat=0.0, subsurface=0.0, double_sided=False):
    """Create a Principled BSDF material compatible with Blender 5.2 and glTF 2.0."""
    mat = bpy.data.materials.new(name=name)
    if double_sided and hasattr(mat, "use_backface_culling"):
        mat.use_backface_culling = False
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True

    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")

    bsdf.inputs["Base Color"].default_value = hex_to_rgba(base_color)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    if subsurface > 0.0 and "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = subsurface
        if "Subsurface Scale" in bsdf.inputs:
            bsdf.inputs["Subsurface Scale"].default_value = 0.02

    return mat


def set_smooth(obj):
    """Enable smooth shading across all polygons of a mesh object."""
    if obj.type == "MESH" and obj.data is not None:
        for poly in obj.data.polygons:
            poly.use_smooth = True


def add_subsurf(obj, levels=1, render_levels=1):
    """Attach a Catmull-Clark Subdivision Surface modifier."""
    mod = obj.modifiers.new(name="Subsurf", type="SUBSURF")
    mod.levels = levels
    mod.render_levels = render_levels
    set_smooth(obj)
    return mod


def add_bevel(obj, width=0.012, segments=2):
    """Attach an angle-limited Bevel modifier."""
    mod = obj.modifiers.new(name="Bevel", type="BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(32)
    set_smooth(obj)
    return mod


def create_mesh_object(name, bm, material=None, collection=None):
    """Finalize a BMesh into a smooth Blender mesh object in the target collection."""
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    if material is not None:
        obj.data.materials.append(material)
    target_col = collection or bpy.context.scene.collection
    target_col.objects.link(obj)
    set_smooth(obj)
    return obj


def bind_armature_weighted(obj, arm_obj, weight_fn):
    """Bind a mesh object to PersonRig via Armature modifier and per-vertex weight function."""
    obj.parent = arm_obj
    mod = obj.modifiers.new(name="Armature", type="ARMATURE")
    mod.object = arm_obj

    vgroups = {}
    for idx, v in enumerate(obj.data.vertices):
        weights = weight_fn(v.co)
        total = sum(weights.values()) or 1.0
        for bname, w in weights.items():
            if w <= 1e-4:
                continue
            if bname not in vgroups:
                vgroups[bname] = obj.vertex_groups.new(name=bname)
            vgroups[bname].add([idx], w / total, "REPLACE")


def bone_parent_objects(arm_obj, mappings):
    """Parent rigid accessory meshes (eyes, hat, shoes, belt) to specific bones."""
    bpy.context.view_layer.update()
    for obj, bone_name in mappings:
        pbone = arm_obj.pose.bones[bone_name]
        tail_mat = arm_obj.matrix_world @ pbone.matrix @ Matrix.Translation((0.0, pbone.length, 0.0))
        world_before = obj.matrix_world.copy()
        obj.parent = arm_obj
        obj.parent_type = "BONE"
        obj.parent_bone = bone_name
        obj.matrix_parent_inverse = tail_mat.inverted()
        obj.matrix_world = world_before


def make_continuous_tube(name, points_radii, segs=18, sx=1.0, sy=1.0, material=None, collection=None, cap_start=True, cap_end=True):
    """Loft a continuous multi-point tube along a 3D centerline [(Vector, radius), ...]."""
    bm = bmesh.new()
    rings = []
    n_pts = len(points_radii)
    prev_tangent = None
    x_axis = None

    for i, (pt, rad) in enumerate(points_radii):
        p = Vector(pt)
        if i == 0:
            tangent = (Vector(points_radii[1][0]) - p).normalized()
        elif i == n_pts - 1:
            tangent = (p - Vector(points_radii[i - 1][0])).normalized()
        else:
            tangent = (Vector(points_radii[i + 1][0]) - Vector(points_radii[i - 1][0])).normalized()

        # Parallel transport frame prevents gimbal-flip twisting when tubes bend or approach vertical
        if x_axis is None:
            ref = Vector((1.0, 0.0, 0.0)) if abs(tangent.dot(Vector((1.0, 0.0, 0.0)))) < 0.9 else Vector((0.0, 1.0, 0.0))
            x_axis = (ref - tangent * ref.dot(tangent)).normalized()
        else:
            rot_q = prev_tangent.rotation_difference(tangent)
            x_axis = rot_q @ x_axis
            x_axis = (x_axis - tangent * x_axis.dot(tangent)).normalized()
        y_axis = tangent.cross(x_axis).normalized()
        prev_tangent = tangent

        ring = []
        for s in range(segs):
            ang = (s / segs) * math.pi * 2.0
            offset = x_axis * (math.cos(ang) * rad * sx) + y_axis * (math.sin(ang) * rad * sy)
            ring.append(bm.verts.new(p + offset))
        rings.append(ring)

    for i in range(n_pts - 1):
        r0, r1 = rings[i], rings[i + 1]
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))

    if cap_start:
        t0 = (Vector(points_radii[1][0]) - Vector(points_radii[0][0])).normalized()
        c0 = bm.verts.new(Vector(points_radii[0][0]) - t0 * (points_radii[0][1] * 0.25))
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((rings[0][sn], rings[0][s], c0))

    if cap_end:
        t1 = (Vector(points_radii[-1][0]) - Vector(points_radii[-2][0])).normalized()
        c1 = bm.verts.new(Vector(points_radii[-1][0]) + t1 * (points_radii[-1][1] * 0.25))
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((rings[-1][s], rings[-1][sn], c1))

    obj = create_mesh_object(name, bm, material=material, collection=collection)
    add_subsurf(obj, levels=1, render_levels=1)
    return obj


def make_sphere_part(name, center, radius, scale=(1.0, 1.0, 1.0), rot=(0.0, 0.0, 0.0), material=None, collection=None, subsurf=1):
    """Create a smooth subdivided ellipsoid part."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=18, v_segments=12, radius=radius)
    obj = create_mesh_object(name, bm, material=material, collection=collection)
    obj.location = center
    obj.scale = scale
    obj.rotation_euler = rot
    if subsurf > 0:
        add_subsurf(obj, levels=subsurf, render_levels=subsurf)
    return obj


def build_character_rig(collection):
    """Create a full humanoid Armature (PersonRig) aligned to joint pivots."""
    arm_data = bpy.data.armatures.new("PersonRigData")
    arm_data.display_type = "OCTAHEDRAL"
    arm_obj = bpy.data.objects.new("PersonRig", arm_data)
    arm_obj.show_in_front = True
    collection.objects.link(arm_obj)

    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones

    def add_bone(name, head, tail, parent=None, connect=False):
        b = eb.new(name)
        b.head = Vector(head)
        b.tail = Vector(tail)
        if parent is not None:
            b.parent = parent
            b.use_connect = connect
        return b

    root = add_bone("Root", (0.0, 0.0, 0.0), (0.0, 0.25, 0.0))
    pelvis = add_bone("Pelvis", (0.0, 0.0, 0.84), (0.0, 0.0, 0.96), parent=root)
    spine = add_bone("Spine", (0.0, 0.0, 0.96), (0.0, 0.0, 1.18), parent=pelvis, connect=True)
    chest = add_bone("Chest", (0.0, 0.0, 1.18), (0.0, 0.0, 1.43), parent=spine, connect=True)
    neck = add_bone("Neck", (0.0, 0.0, 1.43), (0.0, 0.0, 1.52), parent=chest, connect=True)
    add_bone("Head", (0.0, 0.0, 1.52), (0.0, 0.0, 1.75), parent=neck, connect=True)

    for suffix, sgn in [("L", 1.0), ("R", -1.0)]:
        shoulder = (sgn * 0.19, 0.0, 1.37)
        elbow = (sgn * 0.34, 0.02, 1.14)
        wrist = (sgn * 0.45, -0.03, 0.91)
        hand_tip = (sgn * 0.49, -0.05, 0.77)

        upper_arm = add_bone(f"UpperArm.{suffix}", shoulder, elbow, parent=chest)
        forearm = add_bone(f"Forearm.{suffix}", elbow, wrist, parent=upper_arm, connect=True)
        add_bone(f"Hand.{suffix}", wrist, hand_tip, parent=forearm, connect=True)

        hip = (sgn * 0.102, 0.0, 0.87)
        knee = (sgn * 0.108, -0.015, 0.49)
        ankle = (sgn * 0.108, 0.015, 0.09)
        toe = (sgn * 0.108, -0.15, 0.03)

        thigh = add_bone(f"Thigh.{suffix}", hip, knee, parent=pelvis)
        shin = add_bone(f"Shin.{suffix}", knee, ankle, parent=thigh, connect=True)
        add_bone(f"Foot.{suffix}", ankle, toe, parent=shin, connect=True)

    bpy.ops.object.mode_set(mode="OBJECT")
    return arm_obj


def build_torso_and_pelvis(mats, col, arm_obj):
    """Build one continuous smooth coastal shirt torso + sleeves, shorts, and belt."""
    bone_map = []

    # 1. Single continuous Torso Shirt (z = 0.91 .. 1.44) — NO waist seam!
    bm_shirt = bmesh.new()
    segs = 28
    stations = [
        (0.91, 0.172, 0.118, 0.000),
        (1.00, 0.165, 0.114, 0.002),
        (1.10, 0.174, 0.118, 0.000),
        (1.20, 0.188, 0.125, -0.004),
        (1.30, 0.206, 0.132, -0.006),
        (1.38, 0.212, 0.120, -0.002),
        (1.42, 0.140, 0.092, 0.002),
        (1.44, 0.078, 0.068, 0.004),
    ]
    rings = []
    for zp, rx, ry, yc in stations:
        ring = []
        for s in range(segs):
            a = (s / segs) * math.pi * 2.0
            ca, sa = math.cos(a), math.sin(a)
            y_val = yc + sa * ry
            # Gentle front chest contour
            if sa < 0 and 1.24 <= zp <= 1.38:
                y_val -= 0.012 * (-sa)
            ring.append(bm_shirt.verts.new((ca * rx, y_val, zp)))
        rings.append(ring)

    for i in range(len(rings) - 1):
        for s in range(segs):
            sn = (s + 1) % segs
            bm_shirt.faces.new((rings[i][s], rings[i][sn], rings[i + 1][sn], rings[i + 1][s]))

    cap_bot = bm_shirt.verts.new((0.0, 0.0, 0.90))
    cap_top = bm_shirt.verts.new((0.0, 0.004, 1.44))
    for s in range(segs):
        sn = (s + 1) % segs
        bm_shirt.faces.new((rings[0][sn], rings[0][s], cap_bot))
        bm_shirt.faces.new((rings[-1][s], rings[-1][sn], cap_top))

    shirt_obj = create_mesh_object("TorsoShirt", bm_shirt, material=mats["shirt"], collection=col)
    add_subsurf(shirt_obj, levels=1, render_levels=1)

    def shirt_weights(co):
        w_pelvis = 1.0 - smoothstep(0.91, 1.02, co.z)
        w_chest = smoothstep(1.10, 1.26, co.z)
        w_spine = max(0.0, 1.0 - w_pelvis - w_chest)
        return {"Pelvis": w_pelvis, "Spine": w_spine, "Chest": w_chest}

    bind_armature_weighted(shirt_obj, arm_obj, shirt_weights)

    # Flush V-neck undershirt inset + open shirt collar lapels
    vneck = make_sphere_part(
        "UndershirtCollar",
        (0.0, -0.052, 1.396),
        0.050,
        scale=(0.66, 0.22, 0.52),
        rot=(0.45, 0.0, 0.0),
        material=mats["undershirt"],
        collection=col,
    )
    bone_map.append((vneck, "Chest"))

    for side in (-1.0, 1.0):
        bm_col = bmesh.new()
        bmesh.ops.create_cube(bm_col, size=1.0)
        for v in bm_col.verts:
            v.co.x *= 0.052
            v.co.y *= 0.075
            v.co.z *= 0.018
        flap = create_mesh_object(f"ShirtCollar_{'L' if side > 0 else 'R'}", bm_col, material=mats["shirt"], collection=col)
        flap.location = (side * 0.050, -0.066, 1.422)
        flap.rotation_euler = (0.38, side * -0.42, side * 0.40)
        add_bevel(flap, width=0.005, segments=2)
        bone_map.append((flap, "Chest"))

    # Smooth tapered short sleeves emerging naturally from torso shoulders with rolled cuffs
    for suffix, sgn in [("L", 1.0), ("R", -1.0)]:
        shoulder = Vector((sgn * 0.165, 0.0, 1.365))
        elbow = Vector((sgn * 0.34, 0.02, 1.14))
        sleeve_pts = [
            (shoulder, 0.078),
            (shoulder.lerp(elbow, 0.18), 0.076),
            (shoulder.lerp(elbow, 0.38), 0.071),
            (shoulder.lerp(elbow, 0.52), 0.067),
            (shoulder.lerp(elbow, 0.55), 0.063),
            (shoulder.lerp(elbow, 0.56), 0.052),
        ]
        sleeve = make_continuous_tube(
            f"Sleeve.{suffix}",
            sleeve_pts,
            segs=18,
            sx=0.96,
            sy=0.94,
            material=mats["shirt"],
            collection=col,
            cap_end=False,
        )

        def sleeve_weights(co, s=sgn, bname=f"UpperArm.{suffix}"):
            t = smoothstep(0.16, 0.25, abs(co.x))
            return {"Chest": 1.0 - t, bname: t}

        bind_armature_weighted(sleeve, arm_obj, sleeve_weights)

    # 2. Pelvis Shorts Block + Belt
    bm_pel = bmesh.new()
    pel_stations = [
        (0.76, 0.188, 0.128),
        (0.84, 0.192, 0.130),
        (0.93, 0.174, 0.120),
    ]
    p_rings = []
    for zp, rx, ry in pel_stations:
        ring = []
        for s in range(24):
            a = (s / 24) * math.pi * 2.0
            ring.append(bm_pel.verts.new((math.cos(a) * rx, math.sin(a) * ry, zp)))
        p_rings.append(ring)
    for i in range(len(p_rings) - 1):
        for s in range(24):
            sn = (s + 1) % 24
            bm_pel.faces.new((p_rings[i][s], p_rings[i][sn], p_rings[i + 1][sn], p_rings[i + 1][s]))
    cap_pb = bm_pel.verts.new((0, 0, 0.74))
    cap_pt = bm_pel.verts.new((0, 0, 0.94))
    for s in range(24):
        sn = (s + 1) % 24
        bm_pel.faces.new((p_rings[0][sn], p_rings[0][s], cap_pb))
        bm_pel.faces.new((p_rings[-1][s], p_rings[-1][sn], cap_pt))

    pelvis_obj = create_mesh_object("PelvisShorts", bm_pel, material=mats["shorts"], collection=col)
    add_subsurf(pelvis_obj, levels=1, render_levels=1)
    bone_map.append((pelvis_obj, "Pelvis"))

    # Leather belt & brass buckle
    bm_belt = bmesh.new()
    b_rings = []
    for zp in (0.898, 0.952):
        ring = []
        for s in range(24):
            a = (s / 24) * math.pi * 2.0
            ring.append(bm_belt.verts.new((math.cos(a) * 0.178, math.sin(a) * 0.124, zp)))
        b_rings.append(ring)
    for s in range(24):
        sn = (s + 1) % 24
        bm_belt.faces.new((b_rings[0][s], b_rings[0][sn], b_rings[1][sn], b_rings[1][s]))
    belt_obj = create_mesh_object("WaistBelt", bm_belt, material=mats["belt"], collection=col)
    sol_belt = belt_obj.modifiers.new("Solidify", "SOLIDIFY")
    sol_belt.thickness = 0.014
    sol_belt.offset = 1.0
    add_subsurf(belt_obj, levels=1, render_levels=1)
    bone_map.append((belt_obj, "Pelvis"))

    bm_buck = bmesh.new()
    bmesh.ops.create_cube(bm_buck, size=1.0)
    for v in bm_buck.verts:
        v.co.x *= 0.055
        v.co.y *= 0.024
        v.co.z *= 0.064
    buckle = create_mesh_object("BeltBuckle", bm_buck, material=mats["buckle"], collection=col)
    buckle.location = (0.0, -0.132, 0.925)
    add_bevel(buckle, width=0.006, segments=2)
    bone_map.append((buckle, "Pelvis"))

    return bone_map


def build_head_and_hat(mats, col, arm_obj):
    """Build neck, sculpted head, facial features, hair, and coastal straw sun hat."""
    bone_map = []

    # Continuous Neck weighted Chest -> Neck -> Head
    neck_pts = [
        (Vector((0.0, 0.005, 1.40)), 0.062),
        (Vector((0.0, 0.002, 1.46)), 0.055),
        (Vector((0.0, 0.000, 1.54)), 0.052),
    ]
    neck = make_continuous_tube("NeckMesh", neck_pts, segs=16, material=mats["skin"], collection=col)
    bind_armature_weighted(
        neck,
        arm_obj,
        lambda co: {
            "Chest": 1.0 - smoothstep(1.41, 1.46, co.z),
            "Neck": smoothstep(1.41, 1.46, co.z) * (1.0 - smoothstep(1.49, 1.54, co.z)),
            "Head": smoothstep(1.49, 1.54, co.z),
        },
    )

    # Sculpted Head Cranium + Jaw (center around z=1.635)
    bm_head = bmesh.new()
    bmesh.ops.create_uvsphere(bm_head, u_segments=26, v_segments=18, radius=0.115)
    for v in bm_head.verts:
        v.co.x *= 0.88
        v.co.y *= 0.98
        v.co.z *= 1.12
        if v.co.z < -0.02:
            t = min(1.0, (-v.co.z - 0.02) / 0.10)
            v.co.x *= 1.0 - 0.24 * t
            if v.co.y < 0:
                v.co.y *= 1.0 - 0.12 * t
        v.co.z += 1.635
        v.co.y -= 0.004
    head_obj = create_mesh_object("HeadMesh", bm_head, material=mats["skin"], collection=col)
    add_subsurf(head_obj, levels=1, render_levels=1)
    bone_map.append((head_obj, "Head"))

    # Nose
    nose = make_sphere_part(
        "Nose",
        (0.0, -0.118, 1.615),
        0.017,
        scale=(0.82, 1.15, 1.25),
        rot=(-0.22, 0.0, 0.0),
        material=mats["skin"],
        collection=col,
    )
    bone_map.append((nose, "Head"))

    # Subtle friendly smile contour
    smile = make_continuous_tube(
        "MouthSmile",
        [
            (Vector((-0.025, -0.104, 1.572)), 0.0032),
            (Vector((0.000, -0.110, 1.566)), 0.0038),
            (Vector((0.025, -0.104, 1.572)), 0.0032),
        ],
        segs=8,
        material=mats["mouth"],
        collection=col,
    )
    bone_map.append((smile, "Head"))

    # Ears, Eyes, Eyebrows
    for suffix, sgn in [("L", 1.0), ("R", -1.0)]:
        ear = make_sphere_part(
            f"Ear.{suffix}",
            (sgn * 0.103, 0.006, 1.625),
            0.021,
            scale=(0.45, 0.78, 1.25),
            rot=(0.0, sgn * 0.12, sgn * -0.15),
            material=mats["skin"],
            collection=col,
        )
        bone_map.append((ear, "Head"))

        eye_white = make_sphere_part(
            f"EyeWhite.{suffix}",
            (sgn * 0.038, -0.098, 1.648),
            0.0155,
            scale=(0.95, 0.60, 1.08),
            material=mats["eye_white"],
            collection=col,
        )
        bone_map.append((eye_white, "Head"))

        pupil = make_sphere_part(
            f"EyePupil.{suffix}",
            (sgn * 0.038, -0.107, 1.648),
            0.0085,
            scale=(0.95, 0.55, 1.05),
            material=mats["eye_dark"],
            collection=col,
        )
        bone_map.append((pupil, "Head"))

        brow = make_continuous_tube(
            f"Eyebrow.{suffix}",
            [
                (Vector((sgn * 0.020, -0.103, 1.674)), 0.0048),
                (Vector((sgn * 0.038, -0.101, 1.676)), 0.0052),
                (Vector((sgn * 0.056, -0.095, 1.670)), 0.0035),
            ],
            segs=8,
            material=mats["hair"],
            collection=col,
        )
        bone_map.append((brow, "Head"))

    # Hair cap kept neatly off cheeks & above forehead
    bm_hair = bmesh.new()
    bmesh.ops.create_uvsphere(bm_hair, u_segments=24, v_segments=16, radius=0.120)
    for v in bm_hair.verts:
        v.co.x *= 0.89
        v.co.y *= 1.00
        v.co.z *= 1.08
        # Lift front & side hairline cleanly so cheeks & center forehead stay completely clear
        if v.co.y < 0.01:
            v.co.z = max(0.044, v.co.z)
        else:
            v.co.z = max(-0.075, v.co.z)
        v.co.z += 1.656
        v.co.y += 0.012
    hair_obj = create_mesh_object("HairCap", bm_hair, material=mats["hair"], collection=col)
    add_subsurf(hair_obj, levels=1, render_levels=1)
    bone_map.append((hair_obj, "Head"))

    # Removable Straw Sun Hat + Outer Coral Band
    bm_hat = bmesh.new()
    rings = []
    segs = 32
    profile = [
        (0.245, 1.706),
        (0.185, 1.720),
        (0.118, 1.725),
        (0.114, 1.775),
        (0.096, 1.818),
        (0.045, 1.825),
    ]
    for rad, zp in profile:
        ring = []
        for s in range(segs):
            a = (s / segs) * math.pi * 2.0
            wave = math.cos(a * 2.0) * 0.012 if rad > 0.16 else 0.0
            ring.append(bm_hat.verts.new((math.cos(a) * rad * 0.96, math.sin(a) * rad * 1.04, zp + wave)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for s in range(segs):
            sn = (s + 1) % segs
            bm_hat.faces.new((rings[i][s], rings[i][sn], rings[i + 1][sn], rings[i + 1][s]))
    hat_top = bm_hat.verts.new((0.0, 0.0, 1.822))
    for s in range(segs):
        sn = (s + 1) % segs
        bm_hat.faces.new((rings[-1][s], rings[-1][sn], hat_top))

    hat_obj = create_mesh_object("SunHat", bm_hat, material=mats["hat"], collection=col)
    sol_hat = hat_obj.modifiers.new("Solidify", "SOLIDIFY")
    sol_hat.thickness = 0.007
    add_subsurf(hat_obj, levels=1, render_levels=1)
    bone_map.append((hat_obj, "Head"))

    # Outer Coral Ribbon Band (clearly visible outside straw crown)
    bm_band = bmesh.new()
    band_rings = []
    for rad, zp in ((0.123, 1.726), (0.121, 1.756)):
        ring = []
        for s in range(segs):
            a = (s / segs) * math.pi * 2.0
            ring.append(bm_band.verts.new((math.cos(a) * rad * 0.96, math.sin(a) * rad * 1.04, zp)))
        band_rings.append(ring)
    for s in range(segs):
        sn = (s + 1) % segs
        bm_band.faces.new((band_rings[0][s], band_rings[0][sn], band_rings[1][sn], band_rings[1][s]))
    band_obj = create_mesh_object("SunHatBand", bm_band, material=mats["hat_band"], collection=col)
    sol_b = band_obj.modifiers.new("Solidify", "SOLIDIFY")
    sol_b.thickness = 0.006
    sol_b.offset = 1.0
    add_subsurf(band_obj, levels=1, render_levels=1)
    bone_map.append((band_obj, "Head"))

    return bone_map


def build_arms_and_hands(mats, col, arm_obj):
    """Build seamless continuous left & right arms (shoulder -> elbow -> wrist) + sculpted hands."""
    bone_map = []

    for suffix, sgn in [("L", 1.0), ("R", -1.0)]:
        shoulder = Vector((sgn * 0.19, 0.0, 1.37))
        elbow = Vector((sgn * 0.34, 0.02, 1.14))
        wrist = Vector((sgn * 0.45, -0.03, 0.91))

        # Single continuous arm mesh from inside sleeve through elbow to wrist (no elbow seam!)
        arm_start = shoulder.lerp(elbow, 0.25)
        arm_pts = [
            (arm_start, 0.052),
            (shoulder.lerp(elbow, 0.50), 0.049),
            (shoulder.lerp(elbow, 0.78), 0.045),
            (elbow, 0.043),
            (elbow.lerp(wrist, 0.25), 0.046),
            (elbow.lerp(wrist, 0.58), 0.039),
            (wrist, 0.032),
        ]
        arm_mesh = make_continuous_tube(
            f"ArmSkin.{suffix}", arm_pts, segs=18, material=mats["skin"], collection=col
        )

        # Smooth vertex weights blending across the elbow plane (projected along arm axis)
        def arm_weights(co, elb=elbow, sh=shoulder, wr=wrist, suf=suffix):
            axis = (wr - sh).normalized()
            dist_from_elbow = (co - elb).dot(axis)
            w_fore = smoothstep(-0.045, 0.045, dist_from_elbow)
            return {f"UpperArm.{suf}": 1.0 - w_fore, f"Forearm.{suf}": w_fore}

        bind_armature_weighted(arm_mesh, arm_obj, arm_weights)

        # Sculpted Hand (palm + curved finger mitt + thumb)
        hand_dir = (Vector((sgn * 0.49, -0.05, 0.77)) - wrist).normalized()
        palm_center = wrist + hand_dir * 0.055
        palm = make_sphere_part(
            f"HandPalm.{suffix}",
            palm_center,
            0.042,
            scale=(0.45, 0.85, 1.25),
            rot=(0.12, sgn * -0.40, sgn * 0.15),
            material=mats["skin"],
            collection=col,
        )
        bone_map.append((palm, f"Hand.{suffix}"))

        fingers_center = wrist + hand_dir * 0.115 + Vector((0.0, -0.012, 0.0))
        fingers = make_sphere_part(
            f"HandFingers.{suffix}",
            fingers_center,
            0.036,
            scale=(0.38, 0.76, 1.15),
            rot=(-0.18, sgn * -0.40, sgn * 0.15),
            material=mats["skin"],
            collection=col,
        )
        bone_map.append((fingers, f"Hand.{suffix}"))

        thumb_p0 = wrist + hand_dir * 0.035 + Vector((-sgn * 0.012, -0.025, 0.0))
        thumb_p1 = thumb_p0 + Vector((-sgn * 0.025, -0.038, -0.035))
        thumb = make_continuous_tube(
            f"HandThumb.{suffix}",
            [(thumb_p0, 0.015), (thumb_p0.lerp(thumb_p1, 0.5), 0.013), (thumb_p1, 0.010)],
            segs=10,
            material=mats["skin"],
            collection=col,
        )
        bone_map.append((thumb, f"Hand.{suffix}"))

    return bone_map


def build_legs_and_shoes(mats, col, arm_obj):
    """Build shorts legs, seamless continuous thigh-to-ankle legs, and matching deck shoes."""
    bone_map = []

    for suffix, sgn in [("L", 1.0), ("R", -1.0)]:
        hip = Vector((sgn * 0.102, 0.0, 0.87))
        knee = Vector((sgn * 0.108, -0.015, 0.49))
        ankle = Vector((sgn * 0.108, 0.015, 0.09))

        # Shorts leg weighted smoothly from Pelvis to Thigh with open rolled hem cuff (no bulging cap)
        shorts_pts = [
            (hip + Vector((0, 0, 0.02)), 0.096),
            (hip.lerp(knee, 0.35), 0.090),
            (hip.lerp(knee, 0.72), 0.080),
            (hip.lerp(knee, 0.755), 0.076),
            (hip.lerp(knee, 0.765), 0.063),
        ]
        shorts_leg = make_continuous_tube(
            f"ShortsLeg.{suffix}",
            shorts_pts,
            segs=18,
            material=mats["shorts"],
            collection=col,
            cap_end=False,
        )
        bind_armature_weighted(
            shorts_leg,
            arm_obj,
            lambda co, suf=suffix: {
                "Pelvis": smoothstep(0.78, 0.88, co.z),
                f"Thigh.{suf}": 1.0 - smoothstep(0.78, 0.88, co.z),
            },
        )

        # Seamless continuous leg skin emerging cleanly from inside shorts through knee down to ankle
        leg_pts = [
            (hip.lerp(knee, 0.45), 0.065),
            (hip.lerp(knee, 0.68), 0.061),
            (hip.lerp(knee, 0.85), 0.056),
            (knee, 0.054),
            (knee.lerp(ankle, 0.28), 0.060),
            (knee.lerp(ankle, 0.62), 0.048),
            (ankle, 0.038),
        ]
        leg_mesh = make_continuous_tube(
            f"LegSkin.{suffix}", leg_pts, segs=18, material=mats["skin"], collection=col
        )
        bind_armature_weighted(
            leg_mesh,
            arm_obj,
            lambda co, kn=knee, suf=suffix: {
                f"Thigh.{suf}": smoothstep(kn.z - 0.045, kn.z + 0.045, co.z),
                f"Shin.{suf}": 1.0 - smoothstep(kn.z - 0.045, kn.z + 0.045, co.z),
            },
        )

        # Matching rounded Deck Shoe (oval sole + navy canvas upper)
        shoe_cx = sgn * 0.108
        shoe_cy = -0.052

        bm_sole = bmesh.new()
        bmesh.ops.create_uvsphere(bm_sole, u_segments=20, v_segments=10, radius=0.078)
        for v in bm_sole.verts:
            v.co.x *= 0.68
            v.co.y *= 1.62
            v.co.z = max(0.0, (v.co.z + 0.078) * 0.19)
            v.co.x += shoe_cx
            v.co.y += shoe_cy
        sole = create_mesh_object(f"ShoeSole.{suffix}", bm_sole, material=mats["undershirt"], collection=col)
        add_subsurf(sole, levels=1, render_levels=1)
        bone_map.append((sole, f"Foot.{suffix}"))

        bm_up = bmesh.new()
        bmesh.ops.create_uvsphere(bm_up, u_segments=20, v_segments=12, radius=0.075)
        for v in bm_up.verts:
            v.co.x *= 0.64
            v.co.y *= 1.54
            v.co.z *= 0.72
            if v.co.z < 0:
                v.co.z *= 0.15
            if v.co.y < -0.04:
                v.co.z *= 0.78
            v.co.x += shoe_cx
            v.co.y += shoe_cy
            v.co.z += 0.032
        shoe_upper = create_mesh_object(f"ShoeUpper.{suffix}", bm_up, material=mats["shoe"], collection=col)
        add_subsurf(shoe_upper, levels=1, render_levels=1)
        bone_map.append((shoe_upper, f"Foot.{suffix}"))

    return bone_map


def setup_studio_and_viewport(studio_col):
    """Set up studio lights, camera, and Material Preview viewport framing."""
    world = bpy.data.worlds.new("StudioWorld")
    bpy.context.scene.world = world
    if hasattr(world, "use_nodes") and not world.use_nodes:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_rgba("#d8e6f2")
        bg.inputs["Strength"].default_value = 0.85

    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 2.6
    key_data.color = (1.0, 0.96, 0.90)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(52), math.radians(18), math.radians(-38))
    studio_col.objects.link(key_obj)

    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_data.energy = 45.0
    fill_data.size = 3.0
    fill_data.color = (0.85, 0.93, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    fill_obj.location = (2.2, -2.5, 1.7)
    direction = Vector((0.0, 0.0, 0.95)) - fill_obj.location
    fill_obj.rotation_mode = "QUATERNION"
    fill_obj.rotation_quaternion = direction.to_track_quat("-Z", "Y")
    studio_col.objects.link(fill_obj)

    rim_data = bpy.data.lights.new("RimLight", type="AREA")
    rim_data.energy = 55.0
    rim_data.size = 2.5
    rim_data.color = (1.0, 0.90, 0.78)
    rim_obj = bpy.data.objects.new("RimLight", rim_data)
    rim_obj.location = (-1.6, 2.4, 2.0)
    rim_dir = Vector((0.0, 0.0, 1.0)) - rim_obj.location
    rim_obj.rotation_mode = "QUATERNION"
    rim_obj.rotation_quaternion = rim_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(rim_obj)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 45.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (-1.35, -3.15, 1.28)
    cam_dir = Vector((0.0, 0.0, 0.95)) - cam_obj.location
    cam_obj.rotation_mode = "QUATERNION"
    cam_obj.rotation_quaternion = cam_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.shading.type = "MATERIAL"
                space.shading.use_scene_lights = True
                space.shading.use_scene_world = False
                if space.region_3d is not None:
                    space.region_3d.view_perspective = "PERSP"
                    space.region_3d.view_location = Vector((0.0, 0.0, 0.92))
                    space.region_3d.view_rotation = Euler((math.radians(78.0), 0.0, math.radians(-24.0)), "XYZ").to_quaternion()
                    space.region_3d.view_distance = 3.15


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    char_col = bpy.data.collections.new("Character")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(char_col)
    bpy.context.scene.collection.children.link(studio_col)

    mats = {
        "skin": make_material("SkinWarm", "#e0a37c", roughness=0.54, subsurface=0.18),
        "hair": make_material("HairDark", "#261c16", roughness=0.66),
        "mouth": make_material("MouthWarm", "#8a483b", roughness=0.55),
        "shirt": make_material("ShirtCoastal", "#1d6f8a", roughness=0.72),
        "undershirt": make_material("UndershirtCream", "#f4efe6", roughness=0.75),
        "shorts": make_material("ShortsSand", "#c8a675", roughness=0.78),
        "belt": make_material("BeltLeather", "#52321b", roughness=0.52),
        "buckle": make_material("BeltBuckleBrass", "#d4a448", roughness=0.28, metallic=0.85),
        "shoe": make_material("ShoeCanvasNavy", "#1d4f6e", roughness=0.68),
        "eye_dark": make_material("EyeDark", "#14181f", roughness=0.15),
        "eye_white": make_material("EyeWhite", "#f8fafc", roughness=0.25),
        "hat": make_material("HatStraw", "#dfbe7d", roughness=0.82, double_sided=True),
        "hat_band": make_material("HatBandCoral", "#c94a38", roughness=0.65, double_sided=True),
    }

    arm_obj = build_character_rig(char_col)

    bone_mappings = []
    bone_mappings.extend(build_torso_and_pelvis(mats, char_col, arm_obj))
    bone_mappings.extend(build_head_and_hat(mats, char_col, arm_obj))
    bone_mappings.extend(build_arms_and_hands(mats, char_col, arm_obj))
    bone_mappings.extend(build_legs_and_shoes(mats, char_col, arm_obj))

    bone_parent_objects(arm_obj, bone_mappings)
    setup_studio_and_viewport(studio_col)

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[Saved] {BLEND_PATH}")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 960
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True)
    print(f"[Rendered preview] {PREVIEW_PATH}")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in char_col.objects:
        obj.select_set(True)

    bpy.ops.export_scene.gltf(
        filepath=GLB_PATH,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_skins=True,
        export_animations=False,
    )
    print(f"[Exported] {GLB_PATH}")


if __name__ == "__main__":
    main()
