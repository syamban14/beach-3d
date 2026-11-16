"""Generate a realistic detailed coconut palm tree asset (palm_tree.blend & palm_tree.glb) in Blender 5.2."""

import math
import os
import random
import bpy
import bmesh
from mathutils import Color, Euler, Matrix, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(BASE_DIR, "assets", "blend", "palm_tree.blend")
GLB_PATH = os.path.join(BASE_DIR, "assets", "models", "palm_tree.glb")
PREVIEW_PATH = "/Users/syamban/.gemini/antigravity-cli/brain/a2810c20-f453-4255-9182-bae8a0819dcc/scratch/palm_tree_preview.png"

os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(PREVIEW_PATH), exist_ok=True)


def hex_to_rgba(hex_str, alpha=1.0):
    """Convert #rrggbb sRGB hex string to scene-linear RGBA tuple."""
    h = hex_str.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    c = Color((r, g, b)).from_srgb_to_scene_linear()
    return (c.r, c.g, c.b, alpha)


def lerp_color(c_a, c_b, t):
    """Linearly interpolate between two RGBA tuples."""
    t_c = max(0.0, min(1.0, t))
    return (
        c_a[0] + (c_b[0] - c_a[0]) * t_c,
        c_a[1] + (c_b[1] - c_a[1]) * t_c,
        c_a[2] + (c_b[2] - c_a[2]) * t_c,
        1.0,
    )


def create_mesh_with_vcol(name, bm, vert_colors, material, collection, parent=None):
    """Convert BMesh + per-vertex RGBA colors into a smooth Blender Object with active TreeColor."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    for poly in mesh.polygons:
        poly.use_smooth = True

    color_attr = mesh.color_attributes.new(name="TreeColor", type="BYTE_COLOR", domain="POINT")
    mesh.color_attributes.active_color = color_attr
    for idx, rgba in enumerate(vert_colors):
        if idx < len(color_attr.data):
            color_attr.data[idx].color = rgba

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    if material is not None:
        obj.data.materials.append(material)
    return obj


def build_textured_material(
    name,
    roughness=0.75,
    bump_strength=0.55,
    bump_distance=0.04,
    noise_scale=12.0,
    noise_detail=8.0,
    wave_bands=False,
    wave_scale=5.0,
    subsurface=0.0,
    coat=0.0,
    double_sided=False,
):
    """Build procedural material reading TreeColor vertex attribute + procedural micro-bump."""
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    mat.use_backface_culling = not double_sided

    nt = mat.node_tree
    nt.nodes.clear()

    out_node = nt.nodes.new("ShaderNodeOutputMaterial")
    out_node.location = (760, 0)

    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (460, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Subsurface Weight" in bsdf.inputs and subsurface > 0.0:
        bsdf.inputs["Subsurface Weight"].default_value = subsurface
        if "Subsurface Scale" in bsdf.inputs:
            bsdf.inputs["Subsurface Scale"].default_value = 0.015
        if "Subsurface Radius" in bsdf.inputs:
            bsdf.inputs["Subsurface Radius"].default_value = (0.35, 1.0, 0.25)
    if "Coat Weight" in bsdf.inputs and coat > 0.0:
        bsdf.inputs["Coat Weight"].default_value = coat
        if "Coat Roughness" in bsdf.inputs:
            bsdf.inputs["Coat Roughness"].default_value = 0.18
    nt.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])

    # Vertex Color base with subtle procedural variation so surfaces never look flat
    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "TreeColor"
    vcol.location = (-520, 220)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-820, -140)

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-520, -40)
    noise.inputs["Scale"].default_value = noise_scale
    noise.inputs["Detail"].default_value = noise_detail
    noise.inputs["Roughness"].default_value = 0.72
    noise.inputs["Distortion"].default_value = 0.35
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])

    # Darken/modulate vertex color gently by noise for organic bark & leaf mottling
    color_ramp = nt.nodes.new("ShaderNodeValToRGB")
    color_ramp.location = (-260, 40)
    color_ramp.color_ramp.elements[0].position = 0.22
    color_ramp.color_ramp.elements[0].color = (0.68, 0.66, 0.62, 1.0)
    color_ramp.color_ramp.elements[1].position = 0.80
    color_ramp.color_ramp.elements[1].color = (1.06, 1.05, 1.02, 1.0)
    nt.links.new(noise.outputs["Factor"], color_ramp.inputs["Factor"])

    mix_col = nt.nodes.new("ShaderNodeMix")
    mix_col.data_type = "RGBA"
    mix_col.blend_type = "MULTIPLY"
    mix_col.location = (60, 180)
    mix_col.inputs["Factor"].default_value = 0.65
    nt.links.new(vcol.outputs["Color"], mix_col.inputs[6])
    nt.links.new(color_ramp.outputs["Color"], mix_col.inputs[7])
    nt.links.new(mix_col.outputs[2], bsdf.inputs["Base Color"])

    # Optional Wave bands for trunk leaf-scar striations / husk fibers
    height_output = noise.outputs["Factor"]
    if wave_bands:
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.location = (-520, -280)
        wave.wave_type = "BANDS"
        wave.bands_direction = "Z"
        wave.wave_profile = "SAW"
        wave.inputs["Scale"].default_value = wave_scale
        wave.inputs["Distortion"].default_value = 3.2
        wave.inputs["Detail"].default_value = 6.0
        nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])

        add_h = nt.nodes.new("ShaderNodeMath")
        add_h.operation = "ADD"
        add_h.location = (-220, -180)
        nt.links.new(noise.outputs["Factor"], add_h.inputs[0])
        nt.links.new(wave.outputs["Fac"] if "Fac" in wave.outputs else wave.outputs[0], add_h.inputs[1])
        height_output = add_h.outputs["Value"]

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (160, -180)
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = bump_distance
    nt.links.new(height_output, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    return mat


def trunk_centerline(t):
    """Coastal coconut palm curved S-centerline for t in [0, 1] spanning z = -0.18m .. 5.85m."""
    cx = math.sin(t * math.pi * 0.72) * 0.48 - 0.14 * (t ** 2.0)
    cy = math.sin(t * math.pi * 0.48) * 0.22
    cz = -0.18 + t * 6.03
    return Vector((cx, cy, cz))


def parallel_transport_tube(bm, vert_colors, path_points, radii, colors, segs=12, bump_fn=None, cap_end=False):
    """Loft a continuous tube along path_points without gimbal-twist artifacts."""
    rings = []
    n_pts = len(path_points)
    prev_tangent = None
    x_axis = None

    for i, p in enumerate(path_points):
        if i == 0:
            tangent = (path_points[1] - p).normalized()
        elif i == n_pts - 1:
            tangent = (p - path_points[i - 1]).normalized()
        else:
            tangent = (path_points[i + 1] - path_points[i - 1]).normalized()

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
        base_r = radii[i]
        col_i = colors[i]
        for s in range(segs):
            ang = (s / segs) * math.pi * 2.0
            r_eff = base_r * (bump_fn(i, ang) if bump_fn else 1.0)
            offset = x_axis * (math.cos(ang) * r_eff) + y_axis * (math.sin(ang) * r_eff)
            ring.append(bm.verts.new(p + offset))
            vert_colors.append(col_i)
        rings.append(ring)

    for i in range(n_pts - 1):
        r0, r1 = rings[i], rings[i + 1]
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))

    if cap_end and n_pts >= 2:
        t_end = (path_points[-1] - path_points[-2]).normalized()
        c_end = bm.verts.new(path_points[-1] + t_end * max(0.005, radii[-1] * 0.45))
        vert_colors.append(colors[-1])
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((rings[-1][s], rings[-1][sn], c_end))

    return rings


def build_trunk_and_roots(mats, palm_col):
    """Build annular ringed trunk with root bole flare and 20 spreading prop/surface roots."""
    bm_trunk = bmesh.new()
    trunk_vcols = []

    n_rings = 140
    n_sides = 28
    c_soil = hex_to_rgba("#382618")
    c_bark_dark = hex_to_rgba("#594433")
    c_bark_mid = hex_to_rgba("#766250")
    c_bark_ridge = hex_to_rgba("#917f6d")
    c_crown_fiber = hex_to_rgba("#4b321d")

    rings = []
    prev_tangent = None
    x_axis = None

    for i in range(n_rings + 1):
        t = i / n_rings
        p = trunk_centerline(t)
        p_prev = trunk_centerline(max(0.0, t - 0.005))
        p_next = trunk_centerline(min(1.0, t + 0.005))
        tangent = (p_next - p_prev).normalized()

        if x_axis is None:
            ref = Vector((1.0, 0.0, 0.0))
            x_axis = (ref - tangent * ref.dot(tangent)).normalized()
        else:
            rot_q = prev_tangent.rotation_difference(tangent)
            x_axis = rot_q @ x_axis
            x_axis = (x_axis - tangent * x_axis.dot(tangent)).normalized()
        y_axis = tangent.cross(x_axis).normalized()
        prev_tangent = tangent

        # Flared root bole at bottom + steady taper toward top
        bole_flare = 0.145 * ((1.0 - t / 0.13) ** 1.75) if t < 0.13 else 0.0
        base_rad = 0.255 - t * 0.115 + bole_flare

        # Stepped sawtooth annular leaf-scar rings along trunk
        scar_cycle = (t * 36.0) % 1.0
        if t < 0.07:
            scar_amp = 0.008
        elif t > 0.90:
            scar_amp = 0.015
        else:
            scar_amp = 0.020
        scar_step = scar_amp * (scar_cycle ** 0.75) if scar_cycle < 0.85 else scar_amp * (1.0 - (scar_cycle - 0.85) / 0.15) * 0.35

        ring = []
        for s in range(n_sides):
            ang = (s / n_sides) * math.pi * 2.0
            bole_flute = 1.0 + (0.16 * math.cos(ang * 7.0 + t * 5.0) * (1.0 - t / 0.13) if t < 0.13 else 0.0)
            vertical_fissure = (
                0.009 * math.sin(ang * 11.0 + t * 18.0)
                + 0.006 * math.cos(ang * 17.0 - t * 44.0)
            )
            r_vert = (base_rad + scar_step + vertical_fissure) * bole_flute
            offset = x_axis * (math.cos(ang) * r_vert) + y_axis * (math.sin(ang) * r_vert)
            ring.append(bm_trunk.verts.new(p + offset))

            if t < 0.09:
                col = lerp_color(c_soil, c_bark_dark, t / 0.09)
            elif t > 0.88:
                col = lerp_color(c_bark_mid, c_crown_fiber, (t - 0.88) / 0.12)
            else:
                ridge_mix = max(0.0, min(1.0, scar_step / 0.020))
                bark_base = lerp_color(c_bark_dark, c_bark_mid, 0.35 + 0.5 * math.sin(ang * 5 + t * 12) ** 2)
                col = lerp_color(bark_base, c_bark_ridge, ridge_mix * 0.75)
            trunk_vcols.append(col)
        rings.append(ring)

    for i in range(n_rings):
        r0, r1 = rings[i], rings[i + 1]
        for s in range(n_sides):
            sn = (s + 1) % n_sides
            bm_trunk.faces.new((r0[s], r0[sn], r1[sn], r1[s]))

    # Close trunk bottom cleanly inside root mound (no open pipe edge)
    bot_center = bm_trunk.verts.new(trunk_centerline(0.0) + Vector((0.0, 0.0, -0.04)))
    trunk_vcols.append(c_soil)
    for s in range(n_sides):
        sn = (s + 1) % n_sides
        bm_trunk.faces.new((rings[0][sn], rings[0][s], bot_center))

    create_mesh_with_vcol("PalmTrunk", bm_trunk, trunk_vcols, mats["trunk"], palm_col)

    # 28 Spreading Fibrous & Buttress Prop Roots hugging root bole & grounding into soil mound
    rng = random.Random(42)
    bm_roots = bmesh.new()
    root_vcols = []

    for r_idx in range(28):
        is_primary = r_idx < 16
        base_angle = (r_idx / (16.0 if is_primary else 12.0)) * math.pi * 2.0 + rng.uniform(-0.16, 0.16)
        start_z = rng.uniform(0.06, 0.34) if is_primary else rng.uniform(-0.02, 0.18)
        start_r = 0.17 if is_primary else 0.25
        reach = rng.uniform(0.56, 0.88) if is_primary else rng.uniform(0.42, 0.68)
        twist_dir = rng.uniform(-0.36, 0.36)
        root_thick = rng.uniform(0.050, 0.072) if is_primary else rng.uniform(0.028, 0.044)

        pts = []
        rads = []
        cols = []
        steps = 12
        for k in range(steps):
            u = k / (steps - 1)
            ang_u = base_angle + twist_dir * math.sin(u * math.pi * 0.85)
            # Hug steep down the root bole early, then flare out along the ground plane (z ~ -0.10..-0.22)
            radial = start_r + (reach - start_r) * (u ** 0.92)
            z_u = start_z * ((1.0 - u) ** 1.65) - 0.18 * (u ** 1.1) + math.sin(u * math.pi) * 0.025
            pts.append(Vector((math.cos(ang_u) * radial, math.sin(ang_u) * radial, z_u)))
            rads.append(root_thick * (1.0 - 0.70 * u) * (1.0 + 0.16 * math.sin(u * 13.0 + r_idx)))
            cols.append(lerp_color(c_bark_dark, c_soil, min(1.0, u * 1.15)))

        parallel_transport_tube(
            bm_roots,
            root_vcols,
            pts,
            rads,
            cols,
            segs=9,
            bump_fn=lambda i, ang, seed=r_idx: 1.0 + 0.14 * math.sin(ang * 3.0 + i * 1.4 + seed),
            cap_end=True,
        )

    create_mesh_with_vcol("PalmRoots", bm_roots, root_vcols, mats["trunk"], palm_col)
    return trunk_centerline(1.0)


def create_coconut_bmesh(bm, vcols, center, rot_euler, radius_x, height, c_main, c_calyx):
    """Add a trigonal-section fibrous coconut ovoid + 6-lobed top calyx cap into bm."""
    rot_m = Euler(rot_euler, "XYZ").to_matrix()
    rings = []
    n_u = 15
    n_v = 12

    # Trigonal ovoid husk body
    for iv in range(n_v + 1):
        v = iv / n_v
        phi_v = v * math.pi  # 0 = top stem attachment, pi = pointed bottom apex
        profile_r = math.sin(phi_v) * (0.94 + 0.14 * math.sin(phi_v * 1.2))
        z_local = (0.5 - v) * height * (1.0 + 0.08 * math.cos(phi_v))
        if iv == 0 or iv == n_v:
            profile_r = 0.04 if iv == 0 else 0.02

        ring = []
        for iu in range(n_u):
            ang = (iu / n_u) * math.pi * 2.0
            # Characteristic 3 rounded ridges of a real coconut husk
            trigonal = 1.0 + 0.09 * math.cos(ang * 3.0) + 0.02 * math.sin(ang * 9.0 + v * 6.0)
            r_xy = radius_x * profile_r * trigonal
            local_p = Vector((math.cos(ang) * r_xy, math.sin(ang) * r_xy, z_local))
            ring.append(bm.verts.new(center + rot_m @ local_p))
            col_blend = lerp_color(c_calyx, c_main, min(1.0, v / 0.16)) if v < 0.18 else lerp_color(c_main, c_calyx, max(0.0, (v - 0.80) * 1.2))
            vcols.append(col_blend)
        rings.append(ring)

    for iv in range(n_v):
        r0, r1 = rings[iv], rings[iv + 1]
        for iu in range(n_u):
            inext = (iu + 1) % n_u
            bm.faces.new((r0[iu], r0[inext], r1[inext], r1[iu]))

    # Close poles cleanly
    top_cap = bm.verts.new(center + rot_m @ Vector((0.0, 0.0, height * 0.54)))
    vcols.append(c_calyx)
    bot_cap = bm.verts.new(center + rot_m @ Vector((0.0, 0.0, -height * 0.54)))
    vcols.append(c_main)
    for iu in range(n_u):
        inext = (iu + 1) % n_u
        bm.faces.new((rings[0][inext], rings[0][iu], top_cap))
        bm.faces.new((rings[-1][iu], rings[-1][inext], bot_cap))

    # 6-lobed overlapping calyx perianth petals gripping top shoulder
    for lobe in range(6):
        ang_l = (lobe / 6.0) * math.pi * 2.0 + (0.25 if lobe % 2 else 0.0)
        lobe_r = radius_x * (0.44 if lobe % 2 else 0.52)
        p0 = center + rot_m @ Vector((0.0, 0.0, height * 0.53))
        p_left = center + rot_m @ Vector((math.cos(ang_l - 0.42) * lobe_r, math.sin(ang_l - 0.42) * lobe_r, height * 0.44))
        p_mid = center + rot_m @ Vector((math.cos(ang_l) * lobe_r * 1.15, math.sin(ang_l) * lobe_r * 1.15, height * 0.40))
        p_right = center + rot_m @ Vector((math.cos(ang_l + 0.42) * lobe_r, math.sin(ang_l + 0.42) * lobe_r, height * 0.44))
        v0 = bm.verts.new(p0)
        vl = bm.verts.new(p_left)
        vm = bm.verts.new(p_mid)
        vr = bm.verts.new(p_right)
        for _ in range(4):
            vcols.append(c_calyx)
        bm.faces.new((v0, vl, vm, vr))


def build_crownshaft_and_coconuts(mats, palm_col, crown):
    """Build fibrous overlapping crownshaft petiole boots and 3 hanging coconut clusters (14 nuts)."""
    # 1. Fibrous CrownShaft petiole collars wrapping upper trunk neck
    bm_shaft = bmesh.new()
    shaft_vcols = []
    c_fiber_dark = hex_to_rgba("#3b2514")
    c_fiber_mid = hex_to_rgba("#5c3d22")
    c_fiber_edge = hex_to_rgba("#7a5532")

    n_sheaths = 14
    for s_idx in range(n_sheaths):
        tier = s_idx // 5
        ang = (s_idx / 5.0) * math.pi * 2.0 + tier * 0.55
        z_bot = -0.36 + tier * 0.16
        z_top = z_bot + 0.34
        r_bot = 0.155
        r_top = 0.215 + tier * 0.018

        rows = []
        for rv in range(6):
            vv = rv / 5.0
            z_cur = z_bot + (z_top - z_bot) * vv
            r_cur = r_bot + (r_top - r_bot) * (vv ** 1.2)
            # Diamond taper at upper tip
            half_span = 0.62 * (1.0 - 0.55 * (vv ** 2.2))
            row = []
            for ru in range(5):
                uu = (ru / 4.0) * 2.0 - 1.0
                ang_u = ang + uu * half_span
                fray = 0.015 * math.sin(ru * 2.5 + s_idx) if vv > 0.75 else 0.0
                r_u = r_cur + (0.012 * (1.0 - abs(uu))) + fray
                row.append(bm_shaft.verts.new(Vector((math.cos(ang_u) * r_u, math.sin(ang_u) * r_u, z_cur))))
                shaft_vcols.append(lerp_color(c_fiber_dark, c_fiber_edge if abs(uu) > 0.5 else c_fiber_mid, vv))
            rows.append(row)

        for rv in range(5):
            for ru in range(4):
                bm_shaft.faces.new((rows[rv][ru], rows[rv][ru + 1], rows[rv + 1][ru + 1], rows[rv + 1][ru]))

    create_mesh_with_vcol("PalmCrownShaft", bm_shaft, shaft_vcols, mats["fiber"], palm_col, parent=crown)

    # 2. 3 Branched Coconut Clusters (Spadix stalks + 9 young coconuts + 5 mature coconuts)
    bm_stalk = bmesh.new()
    stalk_vcols = []
    bm_young = bmesh.new()
    young_vcols = []
    bm_mature = bmesh.new()
    mature_vcols = []

    c_stalk = hex_to_rgba("#6c5624")
    c_young_main = hex_to_rgba("#65992c")
    c_young_calyx = hex_to_rgba("#404e1e")
    c_mat_main = hex_to_rgba("#593920")
    c_mat_calyx = hex_to_rgba("#301d0e")

    cluster_specs = [
        # (yaw, is_young_cluster, nuts_count, drop_z)
        (0.55, True, 6, -0.34),
        (2.55, True, 5, -0.36),
        (4.55, False, 5, -0.40),
    ]

    rng = random.Random(108)
    for cl_idx, (yaw, is_young, count, drop_z) in enumerate(cluster_specs):
        dir_xy = Vector((math.cos(yaw), math.sin(yaw), 0.0))
        side_xy = Vector((-math.sin(yaw), math.cos(yaw), 0.0))

        # Main arching cluster stem
        stem_pts = [
            dir_xy * 0.13 + Vector((0, 0, 0.04)),
            dir_xy * 0.27 + Vector((0, 0, -0.08)),
            dir_xy * 0.37 + Vector((0, 0, drop_z + 0.10)),
            dir_xy * 0.42 + Vector((0, 0, drop_z - 0.12)),
        ]
        parallel_transport_tube(
            bm_stalk,
            stalk_vcols,
            stem_pts,
            [0.028, 0.023, 0.018, 0.012],
            [c_stalk] * 4,
            segs=7,
            cap_end=True,
        )

        # Individual coconut fruits hanging prominently beneath crownshaft collar
        for k in range(count):
            t_k = k / max(1, count - 1)
            spread_ang = (t_k - 0.5) * 1.25
            radial_dist = 0.30 + (k % 2) * 0.13 + rng.uniform(-0.02, 0.03)
            z_off = drop_z - 0.02 - (k // 2) * 0.13 + rng.uniform(-0.02, 0.02)

            nut_dir = (dir_xy * math.cos(spread_ang) + side_xy * math.sin(spread_ang)).normalized()
            nut_center = nut_dir * radial_dist + Vector((0.0, 0.0, z_off))

            # Twig pedicel connecting stalk to nut top
            top_attach = nut_center + Vector((0.0, 0.0, 0.12))
            stalk_mid = stem_pts[min(3, 1 + k // 2)]
            parallel_transport_tube(
                bm_stalk,
                stalk_vcols,
                [stalk_mid, stalk_mid.lerp(top_attach, 0.55) + Vector((0, 0, 0.02)), top_attach],
                [0.012, 0.009, 0.008],
                [c_stalk] * 3,
                segs=6,
                cap_end=False,
            )

            rad_x = rng.uniform(0.120, 0.142)
            height = rng.uniform(0.26, 0.31)
            tilt_x = rng.uniform(-0.22, 0.22)
            tilt_y = rng.uniform(-0.22, 0.22)

            if is_young:
                c_body = lerp_color(hex_to_rgba("#46751b"), hex_to_rgba("#7f8722"), rng.uniform(0.0, 0.50))
                create_coconut_bmesh(
                    bm_young,
                    young_vcols,
                    nut_center,
                    (tilt_x, tilt_y, yaw + k * 1.1),
                    rad_x,
                    height,
                    c_body,
                    hex_to_rgba("#313c15"),
                )
            else:
                c_body = lerp_color(hex_to_rgba("#4f311b"), hex_to_rgba("#362010"), rng.uniform(0.0, 0.55))
                create_coconut_bmesh(
                    bm_mature,
                    mature_vcols,
                    nut_center,
                    (tilt_x, tilt_y, yaw + k * 1.3),
                    rad_x,
                    height,
                    c_body,
                    hex_to_rgba("#24140a"),
                )

    create_mesh_with_vcol("CoconutStalks", bm_stalk, stalk_vcols, mats["fiber"], palm_col, parent=crown)
    create_mesh_with_vcol("Coconuts_Young", bm_young, young_vcols, mats["coco_young"], palm_col, parent=crown)
    create_mesh_with_vcol("Coconuts_Mature", bm_mature, mature_vcols, mats["coco_mature"], palm_col, parent=crown)


def frond_centerline(v, length, lift, droop, lateral_bend, twist):
    """Compute spine position along frond parameter v in [0, 1]."""
    y = v * length
    x = math.sin(v * math.pi * 0.9) * lateral_bend
    # Rise cleanly out of crown then arch gracefully downward under leaf weight
    z = math.sin(v * math.pi * 0.72) * lift - (v ** 2.25) * droop
    return Vector((x, y, z))


def build_single_frond(name, yaw, length, lift, droop, lateral_bend, twist, is_lower_tier, mat, palm_col, parent):
    """Build 1 pinnate coconut frond mesh with 3D rachis + 29 pairs of V-folded leaflets."""
    bm = bmesh.new()
    vcols = []

    c_petiole = hex_to_rgba("#595022")
    c_rachis = hex_to_rgba("#1c4f15")
    c_leaf_mid = hex_to_rgba("#266b1d")
    c_leaf_edge = hex_to_rgba("#3d8425")
    c_leaf_tip = hex_to_rgba("#7b7d26") if is_lower_tier else hex_to_rgba("#559c31")

    rot_yaw = Matrix.Rotation(yaw, 4, "Z")

    # 1. Central tapered 3D Rachis spine (26 segments x 6-sided flattened stem)
    n_spine = 26
    spine_pts = []
    spine_rads = []
    spine_cols = []
    for i in range(n_spine + 1):
        v = i / n_spine
        p = frond_centerline(v, length, lift, droop, lateral_bend, twist)
        spine_pts.append(rot_yaw @ p)
        spine_rads.append(max(0.008, 0.046 * ((1.0 - v) ** 1.15)))
        spine_cols.append(lerp_color(c_petiole, c_rachis, min(1.0, v / 0.25)))

    parallel_transport_tube(bm, vcols, spine_pts, spine_rads, spine_cols, segs=6, cap_end=True)

    # 2. Individual Pinnate Leaflets along both sides of the rachis (v = 0.14 .. 0.98)
    n_pairs = 29
    n_l_seg = 5  # length segments per leaflet

    for p_idx in range(n_pairs):
        v_base = 0.14 + (p_idx / (n_pairs - 1)) * 0.84
        # Bell envelope: shortest near base & apex, longest (~0.76m) in middle third
        len_env = math.sin(max(0.05, (v_base - 0.06) / 0.96) * math.pi) ** 0.72
        leaf_len = (0.36 + 0.46 * len_env) * (length / 3.25)
        leaf_max_w = 0.031 + 0.021 * len_env

        p_anchor = frond_centerline(v_base, length, lift, droop, lateral_bend, twist)
        p_ahead = frond_centerline(min(1.0, v_base + 0.02), length, lift, droop, lateral_bend, twist)
        fwd = (p_ahead - p_anchor).normalized()
        up_approx = Vector((math.sin(twist * v_base), 0.0, math.cos(twist * v_base))).normalized()
        side_vec = fwd.cross(up_approx).normalized()
        normal_vec = side_vec.cross(fwd).normalized()

        for side_sgn in (-1.0, 1.0):
            # Alternate slightly along rachis like natural coconut pinnae
            stagger = 0.015 if side_sgn > 0 else 0.0
            v_s = min(0.99, v_base + stagger)
            anchor = frond_centerline(v_s, length, lift, droop, lateral_bend, twist)
            anchor += side_vec * (side_sgn * max(0.006, 0.032 * (1.0 - v_s)))

            # Leaflet sweeps forward at ~40-52 deg toward tip and arches out + droops
            sweep_fwd = 0.62 + 0.25 * (v_s ** 1.4)
            leaf_dir = (side_vec * side_sgn + fwd * sweep_fwd).normalized()
            blade_lat = fwd.cross(leaf_dir).normalized()
            # Ensure blade_lat stays roughly tangent horizontally across the blade width
            blade_lat = (fwd - leaf_dir * fwd.dot(leaf_dir)).normalized()

            # Build 5 segments along leaflet length x 3 points across width (V-fold midrib ridge)
            rows = []
            for k in range(n_l_seg + 1):
                u = k / n_l_seg
                # Width tapers smoothly from narrow stem base -> broad mid -> razor tip
                if u < 0.18:
                    w = leaf_max_w * (0.45 + 0.55 * (u / 0.18))
                else:
                    w = leaf_max_w * (max(0.0, math.cos(((u - 0.18) / 0.82) * math.pi * 0.5)) ** 0.78)

                # Natural arched droop under gravity
                droop_z = - (u ** 1.75) * (0.28 + 0.14 * (1.0 - v_s * 0.4)) + math.sin(u * math.pi) * 0.045
                spine_pt = anchor + leaf_dir * (u * leaf_len) + normal_vec * droop_z

                # Crisp V-fold along midrib (center point higher than outer blade edges)
                fold_depth = 0.012 * (1.0 - 0.6 * u)
                p_l = rot_yaw @ (spine_pt - blade_lat * w - normal_vec * fold_depth)
                p_c = rot_yaw @ (spine_pt + normal_vec * (fold_depth * 0.35))
                p_r = rot_yaw @ (spine_pt + blade_lat * w - normal_vec * fold_depth)

                vl = bm.verts.new(p_l)
                vc = bm.verts.new(p_c)
                vr = bm.verts.new(p_r)

                edge_col = lerp_color(c_leaf_mid, c_leaf_edge, min(1.0, u * 0.9))
                if u > 0.72:
                    edge_col = lerp_color(edge_col, c_leaf_tip, (u - 0.72) / 0.28)
                center_col = lerp_color(c_rachis, edge_col, 0.65)

                vcols.append(edge_col)
                vcols.append(center_col)
                vcols.append(edge_col)
                rows.append((vl, vc, vr))

            for k in range(n_l_seg):
                r0 = rows[k]
                r1 = rows[k + 1]
                bm.faces.new((r0[0], r0[1], r1[1], r1[0]))
                bm.faces.new((r0[1], r0[2], r1[2], r1[1]))

    return create_mesh_with_vcol(name, bm, vcols, mat, palm_col, parent=parent)


def build_pinnate_fronds(mats, palm_col, crown):
    """Build 13 multi-tier pinnate coconut fronds + central rising spear shoot."""
    rng = random.Random(2026)

    # 3 canopy tiers: 4 lower drooping, 5 middle spreading, 4 upper ascending
    tiers = [
        # (count, yaw_offset, len_range, lift_range, droop_range, is_lower)
        (4, 0.22, (3.20, 3.45), (0.38, 0.56), (1.72, 2.02), True),
        (5, 0.68, (3.05, 3.35), (0.85, 1.15), (1.35, 1.58), False),
        (4, 1.05, (2.45, 2.85), (1.55, 1.85), (0.92, 1.15), False),
    ]

    frond_idx = 0
    for count, yaw_off, len_r, lift_r, droop_r, is_lower in tiers:
        for i in range(count):
            yaw = yaw_off + (i / count) * math.pi * 2.0 + rng.uniform(-0.14, 0.14)
            length = rng.uniform(*len_r)
            lift = rng.uniform(*lift_r)
            droop = rng.uniform(*droop_r)
            lat_bend = rng.uniform(-0.22, 0.22)
            twist = rng.uniform(-0.32, 0.32)

            build_single_frond(
                f"PalmFrond_{frond_idx}",
                yaw,
                length,
                lift,
                droop,
                lat_bend,
                twist,
                is_lower,
                mats["frond"],
                palm_col,
                crown,
            )
            frond_idx += 1

    # Central emerging spear leaf shoot rising steeply from crown apex
    build_single_frond(
        "PalmSpearLeaf",
        0.9,
        1.75,
        1.68,
        0.16,
        0.08,
        0.12,
        False,
        mats["frond"],
        palm_col,
        crown,
    )


def setup_studio_and_viewport(studio_col):
    """Set up natural tropical sunlight, subtle fill, camera framing whole palm tree, and Material Preview."""
    world = bpy.data.worlds.new("PalmStudioWorld")
    bpy.context.scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_rgba("#bddcf2")
        bg.inputs["Strength"].default_value = 0.55

    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 3.0
    key_data.color = (1.0, 0.95, 0.86)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(48), math.radians(16), math.radians(-42))
    studio_col.objects.link(key_obj)

    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_data.energy = 85.0
    fill_data.size = 7.0
    fill_data.color = (0.82, 0.92, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    fill_obj.location = (5.0, -5.5, 4.0)
    fill_dir = Vector((0.0, 0.0, 3.0)) - fill_obj.location
    fill_obj.rotation_mode = "QUATERNION"
    fill_obj.rotation_quaternion = fill_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(fill_obj)

    rim_data = bpy.data.lights.new("RimLight", type="AREA")
    rim_data.energy = 110.0
    rim_data.size = 6.0
    rim_data.color = (1.0, 0.90, 0.74)
    rim_obj = bpy.data.objects.new("RimLight", rim_data)
    rim_obj.location = (-4.5, 5.5, 6.0)
    rim_dir = Vector((0.0, 0.0, 3.5)) - rim_obj.location
    rim_obj.rotation_mode = "QUATERNION"
    rim_obj.rotation_quaternion = rim_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(rim_obj)

    # Preview camera framing roots -> ringed trunk -> coconuts -> pinnate fronds
    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 34.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (0.0, -8.8, 3.35)
    cam_dir = Vector((0.15, 0.0, 3.15)) - cam_obj.location
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
                space.shading.use_scene_world = True
                if hasattr(space, "clip_end"):
                    space.clip_end = 1000.0
                if space.region_3d is not None:
                    space.region_3d.view_perspective = "PERSP"
                    space.region_3d.view_location = Vector((0.15, 0.0, 3.1))
                    space.region_3d.view_rotation = Euler((math.radians(78.0), 0.0, math.radians(-18.0)), "XYZ").to_quaternion()
                    space.region_3d.view_distance = 9.0


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    palm_col = bpy.data.collections.new("PalmTree")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(palm_col)
    bpy.context.scene.collection.children.link(studio_col)

    mats = {
        "trunk": build_textured_material(
            "PalmTrunkBark",
            roughness=0.90,
            bump_strength=0.68,
            bump_distance=0.05,
            noise_scale=16.0,
            noise_detail=10.0,
            wave_bands=True,
            wave_scale=6.5,
        ),
        "fiber": build_textured_material(
            "PalmCrownFiber",
            roughness=0.92,
            bump_strength=0.65,
            bump_distance=0.04,
            noise_scale=22.0,
            noise_detail=12.0,
        ),
        "coco_young": build_textured_material(
            "CoconutYoung",
            roughness=0.42,
            bump_strength=0.35,
            bump_distance=0.02,
            noise_scale=18.0,
            noise_detail=8.0,
            coat=0.35,
        ),
        "coco_mature": build_textured_material(
            "CoconutMature",
            roughness=0.84,
            bump_strength=0.58,
            bump_distance=0.03,
            noise_scale=24.0,
            noise_detail=10.0,
        ),
        "frond": build_textured_material(
            "PalmFrondReal",
            roughness=0.46,
            bump_strength=0.45,
            bump_distance=0.015,
            noise_scale=14.0,
            noise_detail=8.0,
            subsurface=0.06,
            coat=0.38,
            double_sided=True,
        ),
    }

    top_pos = build_trunk_and_roots(mats, palm_col)

    # Preserve PalmCrown pivot at trunk apex for Three.js wind animation compatibility
    crown = bpy.data.objects.new("PalmCrown", None)
    crown.empty_display_type = "PLAIN_AXES"
    crown.empty_display_size = 0.45
    crown.location = top_pos
    palm_col.objects.link(crown)

    build_crownshaft_and_coconuts(mats, palm_col, crown)
    build_pinnate_fronds(mats, palm_col, crown)

    setup_studio_and_viewport(studio_col)

    total_verts = sum(len(o.data.vertices) for o in palm_col.objects if o.type == "MESH")
    total_polys = sum(len(o.data.polygons) for o in palm_col.objects if o.type == "MESH")
    print(f"[PalmTree geometry] objects={len(palm_col.objects)}, verts={total_verts}, polys={total_polys}")

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[Saved] {BLEND_PATH}")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 1200
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True)
    print(f"[Rendered preview] {PREVIEW_PATH}")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in palm_col.objects:
        obj.select_set(True)

    bpy.ops.export_scene.gltf(
        filepath=GLB_PATH,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_vertex_color="ACTIVE",
    )
    print(f"[Exported] {GLB_PATH}")


if __name__ == "__main__":
    main()
