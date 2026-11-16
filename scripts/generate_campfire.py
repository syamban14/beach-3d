"""Generate a realistic coastal stone-ring campfire with ash mound, log benches, charred logs, glowing embers, and multi-tongue flames."""

import math
import os
import bpy
import bmesh
from mathutils import Color, Euler, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(BASE_DIR, "assets", "blend", "campfire.blend")
GLB_PATH = os.path.join(BASE_DIR, "assets", "models", "campfire.glb")
PREVIEW_PATH = "/Users/syamban/.gemini/antigravity-cli/brain/a2810c20-f453-4255-9182-bae8a0819dcc/scratch/campfire_preview.png"

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


def create_mesh_with_vcol(name, bm, vert_colors, material, collection, flat=False):
    """Finalize BMesh with active CampfireColor BYTE_COLOR attribute."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    for poly in mesh.polygons:
        poly.use_smooth = not flat

    color_attr = mesh.color_attributes.new(name="CampfireColor", type="BYTE_COLOR", domain="POINT")
    mesh.color_attributes.active_color = color_attr
    for idx, rgba in enumerate(vert_colors):
        if idx < len(color_attr.data):
            color_attr.data[idx].color = rgba

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    return obj


def add_cylinder_to_bm(bm, vcols, p0, p1, r0, r1, segs, color, cap_ends=True):
    """Append a cylinder between p0 and p1 with uniform vertex color."""
    v0 = Vector(p0)
    v1 = Vector(p1)
    axis = v1 - v0
    if axis.length < 1e-6:
        return
    z_dir = axis.normalized()
    ref = Vector((1.0, 0.0, 0.0)) if abs(z_dir.dot(Vector((1.0, 0.0, 0.0)))) < 0.9 else Vector((0.0, 1.0, 0.0))
    x_dir = (ref - z_dir * ref.dot(z_dir)).normalized()
    y_dir = z_dir.cross(x_dir).normalized()

    ring0, ring1 = [], []
    for s in range(segs):
        ang = (s / segs) * math.pi * 2.0
        ca, sa = math.cos(ang), math.sin(ang)
        ring0.append(bm.verts.new(v0 + (x_dir * ca + y_dir * sa) * r0))
        vcols.append(color)
        ring1.append(bm.verts.new(v1 + (x_dir * ca + y_dir * sa) * r1))
        vcols.append(color)

    for s in range(segs):
        sn = (s + 1) % segs
        bm.faces.new((ring0[s], ring0[sn], ring1[sn], ring1[s]))
    if cap_ends:
        bm.faces.new(list(reversed(ring0)))
        bm.faces.new(ring1)


def build_fire_material(name, roughness=0.88, bump_scale=24.0, bump_str=0.45, emission_strength=0.0):
    """Build procedural PBR material driven by CampfireColor with optional emission."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (640, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (320, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "CampfireColor"
    vcol.location = (-360, 140)
    nt.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])

    if emission_strength > 0.0 and "Emission Color" in bsdf.inputs:
        nt.links.new(vcol.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission_strength

    if bump_str > 0.0:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-620, -140)
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.location = (-380, -140)
        noise.inputs["Scale"].default_value = bump_scale
        noise.inputs["Detail"].default_value = 9.0
        nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])

        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (60, -160)
        bump.inputs["Strength"].default_value = bump_str
        bump.inputs["Distance"].default_value = 0.015
        nt.links.new(noise.outputs["Factor"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_ash_stones_and_benches(mats, col):
    """Build ash mound, 14 soot-gradient coastal river stones, and 2 split-log seating benches."""
    bm = bmesh.new()
    vcols = []

    c_ash_center = hex_to_rgba("#292522")
    c_ash_mid = hex_to_rgba("#4d4640")
    c_ash_rim = hex_to_rgba("#7a6b58")
    c_soot = hex_to_rgba("#2b2724")
    c_granite = hex_to_rgba("#6e737b")
    c_granite_light = hex_to_rgba("#8a9099")
    c_log_bark = hex_to_rgba("#593a23")
    c_log_split = hex_to_rgba("#9c6d42")

    # 1. Soot-and-ash fire pit mound (radius = 1.05m, skirt down to z = -0.16m)
    segs = 28
    rings_spec = [
        (1.05, -0.16, c_ash_rim),
        (0.95, 0.01, c_ash_rim),
        (0.68, 0.06, c_ash_mid),
        (0.36, 0.09, c_ash_center),
    ]
    mound_rings = []
    for rad, z_val, col_r in rings_spec:
        ring = []
        for s in range(segs):
            ang = (s / segs) * math.pi * 2.0
            ripple = 0.015 * math.sin(s * 3.0 + rad * 4.0)
            ring.append(bm.verts.new((math.cos(ang) * (rad + ripple), math.sin(ang) * (rad + ripple), z_val + ripple * 0.4)))
            vcols.append(col_r)
        mound_rings.append(ring)

    for ri in range(len(mound_rings) - 1):
        r0, r1 = mound_rings[ri], mound_rings[ri + 1]
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))
    center_top = bm.verts.new((0.0, 0.0, 0.11))
    vcols.append(c_ash_center)
    for s in range(segs):
        sn = (s + 1) % segs
        bm.faces.new((mound_rings[-1][s], mound_rings[-1][sn], center_top))

    # 2. Ring of 14 sculpted coastal river stones around radius = 0.78m
    stones = 14
    for i in range(stones):
        ang = (i / stones) * math.pi * 2.0
        r_ring = 0.78 + 0.03 * math.sin(i * 2.3)
        center = Vector((math.cos(ang) * r_ring, math.sin(ang) * r_ring, 0.08 + (i % 2) * 0.015))
        radial_out = Vector((math.cos(ang), math.sin(ang), 0.0))

        tmp = bmesh.new()
        bmesh.ops.create_icosphere(tmp, subdivisions=2, radius=0.19)
        rot_m = Euler((0.12 * math.sin(i * 1.7), 0.10 * math.cos(i * 2.1), ang + 0.4), "XYZ").to_matrix()
        vmap = {}
        for v in tmp.verts:
            p = Vector((v.co.x * (1.05 + 0.15 * (i % 3)), v.co.y * 0.88, v.co.z * 0.72))
            p += p.normalized() * (0.025 * math.sin(v.co.x * 9.0 + i) * math.cos(v.co.y * 8.0))
            wp = center + rot_m @ p
            vmap[v] = bm.verts.new(wp)
            # Inner stone faces darken with soot, outer faces lighter granite
            facing = (wp - center).normalized().dot(radial_out) * 0.5 + 0.5
            stone_col = lerp_color(c_soot, c_granite_light if i % 3 == 0 else c_granite, facing)
            vcols.append(stone_col)
        for f in tmp.faces:
            bm.faces.new([vmap[v] for v in f.verts])
        tmp.free()

    # 3. Two rustic split-log benches outside the stone ring (y = -1.48 and x = -1.48)
    bench_configs = [
        ((0.0, -1.48), (1.42, 0.0, 0.0), 0.0),
        ((-1.48, 0.0), (0.0, 1.42, math.pi * 0.5), math.pi * 0.5),
    ]
    for (bx, by), _, yaw in bench_configs:
        b_dir = Vector((math.cos(yaw), math.sin(yaw), 0.0))
        b_perp = Vector((-math.sin(yaw), math.cos(yaw), 0.0))
        p_center = Vector((bx, by, 0.25))

        # Two vertical support stump blocks grounded down to z = -0.16
        for end_s in (-0.48, 0.48):
            st_c = p_center + b_dir * end_s
            add_cylinder_to_bm(bm, vcols, (st_c.x, st_c.y, -0.16), (st_c.x, st_c.y, 0.24), 0.125, 0.115, 10, c_log_bark)

        # Half-round split bench log resting at z = 0.23..0.34
        log_segs_u = 10
        log_segs_l = 9
        rings_b = []
        for il in range(log_segs_l):
            f_len = (il / (log_segs_l - 1)) * 1.46 - 0.73
            spine = p_center + b_dir * f_len
            ring = []
            for iu in range(log_segs_u):
                # Half-cylinder profile: flat split seat at top (z = +0.08), curved bark belly underneath
                ang_b = math.pi + (iu / (log_segs_u - 1)) * math.pi
                rad_b = 0.135 + 0.008 * math.sin(f_len * 5.0 + iu)
                off = b_perp * (math.cos(ang_b) * rad_b) + Vector((0.0, 0.0, math.sin(ang_b) * rad_b * 0.8 + 0.09))
                ring.append(bm.verts.new(spine + off))
                is_seat = iu == 0 or iu == log_segs_u - 1
                vcols.append(c_log_split if is_seat else c_log_bark)
            rings_b.append(ring)

        for il in range(log_segs_l - 1):
            r0, r1 = rings_b[il], rings_b[il + 1]
            for iu in range(log_segs_u):
                iun = (iu + 1) % log_segs_u
                bm.faces.new((r0[iu], r0[iun], r1[iun], r1[iu]))
        bm.faces.new(list(reversed(rings_b[0])))
        bm.faces.new(rings_b[-1])

    create_mesh_with_vcol("CampfireAshAndStones", bm, vcols, mats["stone"], col, flat=True)


def build_campfire_logs(mats, col):
    """Build 7 crisscrossed/teepee split firewood logs grading from oak outer ends to charred glowing center."""
    bm = bmesh.new()
    vcols = []

    c_oak = hex_to_rgba("#6e492d")
    c_char = hex_to_rgba("#1c1816")
    c_ember = hex_to_rgba("#ff5a14")

    logs = 7
    for l_idx in range(logs):
        ang = (l_idx / logs) * math.pi * 2.0 + 0.25 * math.sin(l_idx * 1.9)
        r_outer = 0.56 + (l_idx % 2) * 0.08
        z_top = 0.38 + (l_idx % 3) * 0.07
        p_out = Vector((math.cos(ang) * r_outer, math.sin(ang) * r_outer, 0.06))
        p_in = Vector((-math.cos(ang + 0.22) * 0.16, -math.sin(ang + 0.22) * 0.16, z_top))
        axis = (p_in - p_out).normalized()
        ref = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.9 else Vector((1.0, 0.0, 0.0))
        x_dir = (ref - axis * ref.dot(axis)).normalized()
        y_dir = axis.cross(x_dir).normalized()

        steps = 8
        rad_segs = 8
        rings = []
        for s_i in range(steps):
            t = s_i / (steps - 1)
            pt = p_out.lerp(p_in, t)
            base_r = 0.085 - t * 0.018
            # Outer oak -> charred transition -> glowing orange underside cracks near center
            if t < 0.45:
                col_base = lerp_color(c_oak, c_char, t / 0.45)
            else:
                col_base = lerp_color(c_char, c_ember, ((t - 0.45) / 0.55) * 0.55)

            ring = []
            for rs in range(rad_segs):
                a_r = (rs / rad_segs) * math.pi * 2.0
                knot = 1.0 + 0.14 * math.sin(a_r * 3.0 + l_idx + t * 5.0)
                v_pos = pt + (x_dir * math.cos(a_r) + y_dir * math.sin(a_r)) * (base_r * knot)
                ring.append(bm.verts.new(v_pos))
                # Highlight underside inner glow cracks facing embers
                crack_glow = max(0.0, -x_dir.z * math.cos(a_r)) if t > 0.48 else 0.0
                vcols.append(lerp_color(col_base, c_ember, min(1.0, crack_glow * 0.85)))
            rings.append(ring)

        for s_i in range(steps - 1):
            r0, r1 = rings[s_i], rings[s_i + 1]
            for rs in range(rad_segs):
                rsn = (rs + 1) % rad_segs
                bm.faces.new((r0[rs], r0[rsn], r1[rsn], r1[rs]))
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])

    create_mesh_with_vcol("CampfireLogs", bm, vcols, mats["wood"], col)


def build_ember_bed(mats, col):
    """Build glowing irregular coal and ember mound at center of fire ring."""
    bm = bmesh.new()
    vcols = []

    c_ember_deep = hex_to_rgba("#ff3d00")
    c_ember_bright = hex_to_rgba("#ffb733")
    c_char_coal = hex_to_rgba("#2b1912")

    # Main glowing ember dome (z = 0.04..0.22m)
    tmp = bmesh.new()
    bmesh.ops.create_icosphere(tmp, subdivisions=2, radius=0.48)
    vmap = {}
    for v in tmp.verts:
        p = Vector((v.co.x, v.co.y, max(-0.08, v.co.z * 0.30)))
        noise_coal = 0.5 + 0.5 * math.sin(p.x * 18.0 + 0.5) * math.cos(p.y * 17.0 - 0.3)
        lum = max(0.0, min(1.0, (p.z + 0.03) / 0.16 * noise_coal))
        p.z += 0.08 + 0.025 * math.sin(p.x * 14.0 + p.y * 11.0)
        vmap[v] = bm.verts.new(p)
        col_e = lerp_color(c_char_coal, lerp_color(c_ember_deep, c_ember_bright, lum), 0.20 + 0.72 * lum)
        vcols.append(col_e)
    for f in tmp.faces:
        bm.faces.new([vmap[v] for v in f.verts])
    tmp.free()

    # Scattered dark-charred & hot coal chunks resting across ember bed
    for c_i in range(12):
        ang = (c_i / 12.0) * math.pi * 2.0 + 0.3
        cr = 0.14 + (c_i % 3) * 0.11
        coal_c = Vector((math.cos(ang) * cr, math.sin(ang) * cr, 0.12))
        tmp_c = bmesh.new()
        bmesh.ops.create_icosphere(tmp_c, subdivisions=1, radius=0.068)
        cmap = {}
        for v in tmp_c.verts:
            wp = coal_c + Vector((v.co.x * 1.25, v.co.y * 0.9, v.co.z * 0.7))
            cmap[v] = bm.verts.new(wp)
            is_hot = (wp.z - coal_c.z) < 0.0 or (c_i % 3 == 0)
            vcols.append(c_ember_deep if is_hot else c_char_coal)
        for f in tmp_c.faces:
            bm.faces.new([cmap[v] for v in f.verts])
        tmp_c.free()

    create_mesh_with_vcol("EmberBed", bm, vcols, mats["ember"], col, flat=True)


def add_flame_tongue(bm, vcols, base_xy, height, base_rad, phase, tilt_vec):
    """Append a swirling tapered flame tongue from z=0.14 up to z=0.14+height."""
    c_core = hex_to_rgba("#fff3a1")
    c_mid = hex_to_rgba("#ff7b14")
    c_tip = hex_to_rgba("#d92b08")

    layers = 12
    segs = 12
    rings = []
    for iz in range(layers):
        t = iz / (layers - 1)
        envelope = math.sin(min(1.0, t * 0.85 + 0.15) * math.pi) ** 0.75 * (1.0 - t * 0.82)
        rad = max(0.012, base_rad * envelope)
        swirl_x = math.sin(t * 5.2 + phase) * 0.08 * t + tilt_vec[0] * t
        swirl_y = math.cos(t * 4.4 + phase) * 0.08 * t + tilt_vec[1] * t
        center = Vector((base_xy[0] + swirl_x, base_xy[1] + swirl_y, 0.14 + t * height))

        if t < 0.42:
            col_t = lerp_color(c_core, c_mid, t / 0.42)
        else:
            col_t = lerp_color(c_mid, c_tip, (t - 0.42) / 0.58)

        ring = []
        for s in range(segs):
            ang = (s / segs) * math.pi * 2.0 + t * 1.6
            lobe = 1.0 + 0.18 * math.sin(ang * 3.0 + t * 4.0 + phase)
            px = center.x + math.cos(ang) * rad * lobe
            py = center.y + math.sin(ang) * rad * lobe
            ring.append(bm.verts.new((px, py, center.z)))
            vcols.append(col_t)
        rings.append(ring)

    for iz in range(layers - 1):
        r0, r1 = rings[iz], rings[iz + 1]
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))
    tip_top = bm.verts.new((
        base_xy[0] + math.sin(5.2 + phase) * 0.08 + tilt_vec[0],
        base_xy[1] + math.cos(4.4 + phase) * 0.08 + tilt_vec[1],
        0.14 + height + 0.03,
    ))
    vcols.append(c_tip)
    for s in range(segs):
        sn = (s + 1) % segs
        bm.faces.new((rings[-1][s], rings[-1][sn], tip_top))


def build_flames(mats, col):
    """Build CampfireFlame mesh with central tall swirling tongue + 4 side licks (origin at 0,0,0)."""
    bm = bmesh.new()
    vcols = []

    # Central tall tongue (height ~1.10 -> z=1.24) + 4 flanking licks
    add_flame_tongue(bm, vcols, (0.0, 0.0), height=1.10, base_rad=0.28, phase=0.2, tilt_vec=(0.02, -0.01))
    add_flame_tongue(bm, vcols, (0.15, 0.08), height=0.72, base_rad=0.17, phase=1.4, tilt_vec=(0.09, 0.05))
    add_flame_tongue(bm, vcols, (-0.14, 0.11), height=0.66, base_rad=0.16, phase=2.7, tilt_vec=(-0.08, 0.07))
    add_flame_tongue(bm, vcols, (-0.09, -0.15), height=0.76, base_rad=0.18, phase=4.1, tilt_vec=(-0.05, -0.09))
    add_flame_tongue(bm, vcols, (0.12, -0.13), height=0.58, base_rad=0.15, phase=5.3, tilt_vec=(0.08, -0.06))

    create_mesh_with_vcol("CampfireFlame", bm, vcols, mats["flame"], col)


def setup_studio_and_viewport(studio_col):
    """Set up warm evening studio lighting to inspect glow, soot contrast, and flame layers."""
    world = bpy.data.worlds.new("CampfireStudioWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_rgba("#182230")
        bg.inputs["Strength"].default_value = 0.55

    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 1.6
    key_data.color = (0.85, 0.90, 1.0)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(48), math.radians(15), math.radians(-35))
    studio_col.objects.link(key_obj)

    fire_pt_data = bpy.data.lights.new("FireGlow", type="POINT")
    fire_pt_data.energy = 160.0
    fire_pt_data.color = (1.0, 0.52, 0.14)
    fire_pt_obj = bpy.data.objects.new("FireGlow", fire_pt_data)
    fire_pt_obj.location = (0.0, 0.0, 0.72)
    studio_col.objects.link(fire_pt_obj)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 35.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (2.8, -3.4, 2.0)
    cam_dir = Vector((-0.15, -0.15, 0.45)) - cam_obj.location
    cam_obj.rotation_mode = "QUATERNION"
    cam_obj.rotation_quaternion = cam_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    c_col = bpy.data.collections.new("Campfire")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(c_col)
    bpy.context.scene.collection.children.link(studio_col)

    mats = {
        "stone": build_fire_material("FireStoneAshMat", roughness=0.90, bump_scale=24.0, bump_str=0.55),
        "wood": build_fire_material("FireWoodMat", roughness=0.86, bump_scale=30.0, bump_str=0.50),
        "ember": build_fire_material("FireEmberMat", roughness=0.55, bump_scale=28.0, bump_str=0.35, emission_strength=2.6),
        "flame": build_fire_material("FireFlameMat", roughness=0.25, bump_scale=12.0, bump_str=0.0, emission_strength=4.2),
    }

    build_ash_stones_and_benches(mats, c_col)
    build_campfire_logs(mats, c_col)
    build_ember_bed(mats, c_col)
    build_flames(mats, c_col)
    setup_studio_and_viewport(studio_col)

    total_verts = sum(len(o.data.vertices) for o in c_col.objects if o.type == "MESH")
    total_polys = sum(len(o.data.polygons) for o in c_col.objects if o.type == "MESH")
    print(f"[Campfire geometry] objects={len(c_col.objects)}, verts={total_verts}, polys={total_polys}")

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[Saved] {BLEND_PATH}")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 800
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True)
    print(f"[Rendered preview] {PREVIEW_PATH}")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in c_col.objects:
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
