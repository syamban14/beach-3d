"""Generate a realistic classic coastal lighthouse (lighthouse.blend & lighthouse.glb) in Blender 5.2."""

import math
import os
import bpy
import bmesh
from mathutils import Color, Euler, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(BASE_DIR, "assets", "blend", "lighthouse.blend")
GLB_PATH = os.path.join(BASE_DIR, "assets", "models", "lighthouse.glb")
PREVIEW_PATH = "/Users/syamban/.gemini/antigravity-cli/brain/a2810c20-f453-4255-9182-bae8a0819dcc/scratch/lighthouse_preview.png"

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


def create_mesh_with_vcol(name, bm, vert_colors, material, collection, location=(0.0, 0.0, 0.0), flat=False):
    """Finalize BMesh with active LighthouseColor BYTE_COLOR attribute."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    for poly in mesh.polygons:
        poly.use_smooth = not flat

    color_attr = mesh.color_attributes.new(name="LighthouseColor", type="BYTE_COLOR", domain="POINT")
    mesh.color_attributes.active_color = color_attr
    for idx, rgba in enumerate(vert_colors):
        if idx < len(color_attr.data):
            color_attr.data[idx].color = rgba

    obj = bpy.data.objects.new(name, mesh)
    obj.location = Vector(location)
    collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    return obj


def add_box_to_bm(bm, vcols, center, size_xyz, rot_euler, color):
    """Append an oriented box with uniform vertex color into bm."""
    rot_m = Euler(rot_euler, "XYZ").to_matrix()
    tmp = bmesh.new()
    bmesh.ops.create_cube(tmp, size=1.0)
    vmap = {}
    for v in tmp.verts:
        p = Vector((v.co.x * size_xyz[0], v.co.y * size_xyz[1], v.co.z * size_xyz[2]))
        vmap[v] = bm.verts.new(Vector(center) + rot_m @ p)
        vcols.append(color)
    for f in tmp.faces:
        bm.faces.new([vmap[v] for v in f.verts])
    tmp.free()


def add_cylinder_to_bm(bm, vcols, p0, p1, r0, r1, segs, color, cap_ends=True):
    """Append a tapered cylinder segment between p0 and p1 into bm."""
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


def add_ring_to_bm(bm, vcols, center_z, r_inner, r_outer, height, segs, color):
    """Append a horizontal architectural molding collar ring around Z."""
    z_bot = center_z - height * 0.5
    z_top = center_z + height * 0.5
    b_in, b_out, t_out, t_in = [], [], [], []
    for s in range(segs):
        ang = (s / segs) * math.pi * 2.0
        ca, sa = math.cos(ang), math.sin(ang)
        b_in.append(bm.verts.new((ca * r_inner, sa * r_inner, z_bot)))
        vcols.append(color)
        b_out.append(bm.verts.new((ca * r_outer, sa * r_outer, z_bot)))
        vcols.append(color)
        t_out.append(bm.verts.new((ca * r_outer, sa * r_outer, z_top)))
        vcols.append(color)
        t_in.append(bm.verts.new((ca * r_inner, sa * r_inner, z_top)))
        vcols.append(color)

    for s in range(segs):
        sn = (s + 1) % segs
        bm.faces.new((b_in[s], b_out[s], b_out[sn], b_in[sn]))
        bm.faces.new((b_out[s], t_out[s], t_out[sn], b_out[sn]))
        bm.faces.new((t_out[s], t_in[s], t_in[sn], t_out[sn]))
        bm.faces.new((t_in[s], b_in[s], b_in[sn], t_in[sn]))


def add_uv_sphere_to_bm(bm, vcols, center, radius, segs, rings, color):
    """Append a UV sphere into bm with uniform vertex color."""
    tmp = bmesh.new()
    bmesh.ops.create_uvsphere(tmp, u_segments=segs, v_segments=rings, radius=radius)
    vmap = {}
    c_vec = Vector(center)
    for v in tmp.verts:
        vmap[v] = bm.verts.new(v.co + c_vec)
        vcols.append(color)
    for f in tmp.faces:
        bm.faces.new([vmap[v] for v in f.verts])
    tmp.free()


def tower_radius_at_z(z_val):
    """Evaluate classical lighthouse tower outer radius with slight convex entasis."""
    t = max(0.0, min(1.0, (z_val - 1.20) / (9.55 - 1.20)))
    r_lin = 1.74 + (0.92 - 1.74) * t
    entasis = 0.048 * math.sin(t * math.pi)
    return r_lin + entasis


def build_masonry_material(name, roughness=0.78, noise_scale=18.0, bump_str=0.45):
    """Build procedural stone/masonry material reading LighthouseColor with surface noise bump."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (760, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (460, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "LighthouseColor"
    vcol.location = (-440, 200)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-920, -100)

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-640, -60)
    noise.inputs["Scale"].default_value = noise_scale
    noise.inputs["Detail"].default_value = 12.0
    noise.inputs["Roughness"].default_value = 0.74
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])

    noise_fine = nt.nodes.new("ShaderNodeTexNoise")
    noise_fine.location = (-640, -320)
    noise_fine.inputs["Scale"].default_value = noise_scale * 3.4
    noise_fine.inputs["Detail"].default_value = 10.0
    noise_fine.inputs["Roughness"].default_value = 0.78
    nt.links.new(tc.outputs["Object"], noise_fine.inputs["Vector"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-340, 40)
    ramp.color_ramp.elements[0].position = 0.24
    ramp.color_ramp.elements[0].color = (0.82, 0.81, 0.80, 1.0)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (1.06, 1.05, 1.04, 1.0)
    nt.links.new(noise.outputs["Factor"], ramp.inputs["Factor"])

    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.location = (60, 180)
    mix.inputs["Factor"].default_value = 0.55
    nt.links.new(vcol.outputs["Color"], mix.inputs[6])
    nt.links.new(ramp.outputs["Color"], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])

    add_h = nt.nodes.new("ShaderNodeMath")
    add_h.operation = "ADD"
    add_h.location = (-220, -200)
    nt.links.new(noise.outputs["Factor"], add_h.inputs[0])
    nt.links.new(noise_fine.outputs["Factor"], add_h.inputs[1])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (180, -200)
    bump.inputs["Strength"].default_value = bump_str
    bump.inputs["Distance"].default_value = 0.015
    nt.links.new(add_h.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_simple_material(name, roughness=0.45, metallic=0.0, bump_scale=28.0, bump_str=0.25, emission_strength=0.0):
    """Build procedural material driven by LighthouseColor with micro-surface bump."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (620, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (320, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "LighthouseColor"
    vcol.location = (-260, 140)
    nt.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])

    if emission_strength > 0.0 and "Emission Color" in bsdf.inputs:
        nt.links.new(vcol.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission_strength

    if bump_str > 0.0:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-560, -140)
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.location = (-340, -140)
        noise.inputs["Scale"].default_value = bump_scale
        noise.inputs["Detail"].default_value = 8.0
        nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])

        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (60, -160)
        bump.inputs["Strength"].default_value = bump_str
        bump.inputs["Distance"].default_value = 0.012
        nt.links.new(noise.outputs["Factor"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    return mat


def build_glass_material():
    """Build translucent lantern glass material showing internal Fresnel optic in Blender preview."""
    mat = bpy.data.materials.new("LighthouseGlassMat")
    mat.use_nodes = True
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (560, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (260, 0)
    bsdf.inputs["Base Color"].default_value = hex_to_rgba("#e8f4fb")
    bsdf.inputs["Roughness"].default_value = 0.08
    bsdf.inputs["IOR"].default_value = 1.48
    bsdf.inputs["Alpha"].default_value = 0.34
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.55
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.85
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = hex_to_rgba("#ffd275")
        bsdf.inputs["Emission Strength"].default_value = 0.35
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def build_foundation(mats, col):
    """Build 16-sided stepped granite foundation plinth, water-table cornice, and entrance steps."""
    bm = bmesh.new()
    vcols = []

    c_moss = hex_to_rgba("#4c5947")
    c_granite_dark = hex_to_rgba("#626973")
    c_granite_mid = hex_to_rgba("#7c848f")
    c_granite_light = hex_to_rgba("#969ea8")

    # Stepped/coursed 16-sided stone plinth from z=-0.45..1.22
    course_levels = [
        (-0.45, 2.20, 0.00),
        (-0.08, 2.12, 0.15),
        (-0.05, 2.04, 0.25),
        (0.32, 1.98, 0.45),
        (0.35, 1.92, 0.55),
        (0.72, 1.88, 0.72),
        (0.75, 1.84, 0.82),
        (1.08, 1.82, 0.92),
    ]
    segs = 16
    rings = []
    for z_val, rad, moss_mix in course_levels:
        base_col = lerp_color(c_moss, c_granite_mid, moss_mix)
        ring = []
        for s in range(segs):
            ang = (s / segs) * math.pi * 2.0
            jitter = 0.015 * math.sin(s * 3.1 + z_val * 5.0)
            col_v = lerp_color(c_granite_dark, base_col, 0.5 + 0.4 * math.cos(s * 2.3 + z_val * 3.0))
            ring.append(bm.verts.new((math.cos(ang) * (rad + jitter), math.sin(ang) * (rad + jitter), z_val)))
            vcols.append(col_v)
        rings.append(ring)

    for r_i in range(len(rings) - 1):
        r0, r1 = rings[r_i], rings[r_i + 1]
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])

    # Projecting granite water-table cornice at z=1.10..1.24
    add_ring_to_bm(bm, vcols, center_z=1.17, r_inner=1.70, r_outer=1.92, height=0.14, segs=24, color=c_granite_light)

    # 4 granite entrance steps on the -Y bay-facing side
    for step_idx in range(4):
        step_z = 0.06 + step_idx * 0.26
        step_y = -2.42 + step_idx * 0.20
        step_w = 1.24 - step_idx * 0.06
        add_box_to_bm(
            bm,
            vcols,
            center=(0.0, step_y, step_z),
            size_xyz=(step_w, 0.34, 0.26),
            rot_euler=(0.0, 0.0, 0.0),
            color=c_granite_light if step_idx % 2 == 0 else c_granite_mid,
        )
    # Side stone cheek walls flanking the steps
    for side in (-1.0, 1.0):
        add_box_to_bm(
            bm,
            vcols,
            center=(side * 0.65, -2.08, 0.56),
            size_xyz=(0.18, 0.92, 0.72),
            rot_euler=(math.radians(-16.0), 0.0, 0.0),
            color=c_granite_dark,
        )

    create_mesh_with_vcol("LHFoundation", bm, vcols, mats["stone"], col, flat=True)


def build_tower_body(mats, col):
    """Build tapered red-and-white masonry lighthouse tower with belt courses and mortar grooves."""
    bm = bmesh.new()
    vcols = []

    c_white_warm = hex_to_rgba("#ebe8df")
    c_white_weath = hex_to_rgba("#d8d3c8")
    c_red_deep = hex_to_rgba("#c2382c")
    c_red_weath = hex_to_rgba("#a82e24")
    c_stone_trim = hex_to_rgba("#9aa2ab")

    segs = 36
    z_rings = 55
    z_min, z_max = 1.20, 9.55
    rings = []

    for iz in range(z_rings):
        frac = iz / (z_rings - 1)
        z_cur = z_min + (z_max - z_min) * frac
        r_base = tower_radius_at_z(z_cur)
        # Subtle recessed horizontal masonry course groove every 3 rings
        groove = -0.008 if (iz % 3 == 0 and 0 < iz < z_rings - 1) else 0.0

        # Horizontal color bands
        if z_cur < 4.15:
            band_a, band_b = c_white_warm, c_white_weath
        elif z_cur < 6.85:
            band_a, band_b = c_red_deep, c_red_weath
        elif z_cur < 8.95:
            band_a, band_b = c_white_warm, c_white_weath
        else:
            band_a, band_b = c_red_deep, c_red_weath

        # Weathering near bottom and under gallery overhang
        weather_bias = 0.35 if z_cur < 2.2 or z_cur > 9.1 else 0.0

        ring = []
        for s in range(segs):
            ang = (s / segs) * math.pi * 2.0
            # Running-bond brick variation across courses & azimuth
            brick_var = 0.5 + 0.5 * math.sin(s * 2.4 + (iz % 2) * 1.57 + iz * 0.7)
            col_v = lerp_color(band_a, band_b, min(1.0, brick_var * 0.48 + weather_bias))
            rad = r_base + groove
            ring.append(bm.verts.new((math.cos(ang) * rad, math.sin(ang) * rad, z_cur)))
            vcols.append(col_v)
        rings.append(ring)

    for iz in range(z_rings - 1):
        r0, r1 = rings[iz], rings[iz + 1]
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])

    # Projecting granite belt-course molding rings at band transitions (z=4.15, z=6.85) and base of neck (z=8.95)
    for belt_z in (4.15, 6.85, 8.95):
        r_belt = tower_radius_at_z(belt_z)
        add_ring_to_bm(bm, vcols, center_z=belt_z, r_inner=r_belt - 0.04, r_outer=r_belt + 0.075, height=0.11, segs=36, color=c_stone_trim)

    create_mesh_with_vcol("LHTowerBody", bm, vcols, mats["masonry"], col)


def build_door_and_windows(mats, col):
    """Build bay-facing stone arched doorway with timber door and 3 recessed lit casement windows."""
    bm = bmesh.new()
    vcols = []

    c_stone_arch = hex_to_rgba("#9098a2")
    c_stone_key = hex_to_rgba("#767d87")
    c_timber = hex_to_rgba("#5a341b")
    c_timber_dark = hex_to_rgba("#3d2211")
    c_iron = hex_to_rgba("#1e252e")
    c_window_lit = hex_to_rgba("#ffd273")

    # 1. Bay-facing (-Y) Arched Doorway at z=1.10..2.58 with projecting stone portal so taper never clips door
    arch_center_z = 2.08
    arch_rad = 0.44
    door_front_y = -1.86
    door_leaf_y = -1.78

    # Projecting granite threshold & jamb pillars
    add_box_to_bm(bm, vcols, (0.0, door_front_y + 0.08, 1.12), (1.16, 0.34, 0.14), (0.0, 0.0, 0.0), c_stone_key)
    for side in (-1.0, 1.0):
        add_box_to_bm(bm, vcols, (side * 0.45, door_front_y + 0.11, 1.62), (0.20, 0.34, 0.98), (0.0, 0.0, 0.0), c_stone_arch)

    # Semicircular bossed stone arch voussoirs + keystone sitting proud of tower curve
    num_voussoirs = 9
    for vi in range(num_voussoirs):
        ang = (vi / (num_voussoirs - 1)) * math.pi
        vx = math.cos(ang) * arch_rad
        vz = arch_center_z + math.sin(ang) * arch_rad
        vy = min(-tower_radius_at_z(vz) - 0.06, door_front_y + 0.06)
        is_key = vi == (num_voussoirs // 2)
        size_v = (0.14, 0.34 if is_key else 0.28, 0.20 if is_key else 0.15)
        add_box_to_bm(bm, vcols, (vx, vy, vz), size_v, (0.0, -(ang - math.pi * 0.5), 0.0), c_stone_key if is_key else c_stone_arch)

    # Recessed vertical-plank timber door leaf + rounded arch transom (strictly proud of lower tower radius 1.74)
    for plank_i in range(5):
        px = -0.28 + plank_i * 0.14
        add_box_to_bm(bm, vcols, (px, door_leaf_y, 1.66), (0.125, 0.10, 1.02), (0.0, 0.0, 0.0), c_timber if plank_i % 2 == 0 else c_timber_dark)
    add_cylinder_to_bm(
        bm, vcols,
        (0.0, door_leaf_y - 0.05, arch_center_z),
        (0.0, door_leaf_y + 0.07, arch_center_z),
        arch_rad - 0.07, arch_rad - 0.07,
        segs=16, color=c_timber_dark,
    )
    # Iron strap hinges & door handle
    for hz in (1.36, 1.94):
        add_box_to_bm(bm, vcols, (-0.18, door_leaf_y - 0.055, hz), (0.34, 0.025, 0.045), (0.0, 0.0, 0.0), c_iron)
    add_box_to_bm(bm, vcols, (0.24, door_leaf_y - 0.065, 1.72), (0.04, 0.04, 0.09), (0.0, 0.0, 0.0), c_iron)

    # 2. Three vertical recessed casement windows aligned to tower slope around front/sides
    window_specs = [
        (3.15, math.radians(-128.0)),  # front-left/bay side (+X/-Y azimuth)
        (5.50, math.radians(-90.0)),   # straight front bay side (-Y)
        (7.85, math.radians(-52.0)),   # front-right/cliff side (-X/-Y)
    ]
    for wz, w_az in window_specs:
        r_w = tower_radius_at_z(wz) + 0.04
        wall_tilt = math.atan2(tower_radius_at_z(wz - 0.4) - tower_radius_at_z(wz + 0.4), 0.8)
        rot_z = w_az + math.pi * 0.5  # align local -Y outward toward azimuth w_az
        rot_e = Euler((-wall_tilt, 0.0, rot_z), "XYZ")
        rot_m = rot_e.to_matrix()

        def place_win(lx, ly, lz, sx, sy, sz, w_col):
            world_p = Vector((math.cos(w_az) * r_w, math.sin(w_az) * r_w, wz)) + rot_m @ Vector((lx, ly, lz))
            add_box_to_bm(bm, vcols, world_p, (sx, sy, sz), rot_e, w_col)

        # Granite window sill & lintel
        place_win(0.0, -0.05, -0.36, 0.60, 0.22, 0.09, c_stone_arch)
        place_win(0.0, -0.04, 0.36, 0.58, 0.20, 0.10, c_stone_key)
        # Side stone jambs
        for sx in (-0.23, 0.23):
            place_win(sx, -0.02, 0.0, 0.09, 0.18, 0.64, c_stone_arch)
        # Recessed warm glowing window pane backing (clear of tower taper)
        place_win(0.0, -0.005, 0.0, 0.38, 0.08, 0.60, c_window_lit)
        # Iron cross mullions
        place_win(0.0, -0.055, 0.0, 0.035, 0.035, 0.60, c_iron)
        place_win(0.0, -0.055, 0.0, 0.38, 0.035, 0.035, c_iron)

    create_mesh_with_vcol("LHDoorAndWindows", bm, vcols, mats["masonry"], col, flat=True)


def build_gallery_and_corbels(mats, col):
    """Build 16 curved corbel brackets, cantilevered gallery deck, and upper lantern cornice."""
    bm = bmesh.new()
    vcols = []

    c_stone_deck = hex_to_rgba("#8a929c")
    c_stone_shade = hex_to_rgba("#6c747e")
    c_iron = hex_to_rgba("#222b36")

    # 16 curved stepped corbel brackets (z=9.05..9.60)
    num_corbels = 16
    for ci in range(num_corbels):
        ang = (ci / num_corbels) * math.pi * 2.0
        for step_k, (z_c, r_in, r_out, h_c) in enumerate([
            (9.14, 0.88, 1.08, 0.18),
            (9.32, 0.88, 1.24, 0.18),
            (9.49, 0.88, 1.38, 0.16),
        ]):
            r_mid = (r_in + r_out) * 0.5
            r_len = r_out - r_in
            add_box_to_bm(
                bm,
                vcols,
                center=(math.cos(ang) * r_mid, math.sin(ang) * r_mid, z_c),
                size_xyz=(r_len, 0.13, h_c),
                rot_euler=(0.0, 0.0, ang),
                color=c_stone_shade if step_k % 2 == 0 else c_stone_deck,
            )

    # Cantilevered circular watch gallery deck (z=9.55..9.95, radius=1.42) + drip lip
    add_cylinder_to_bm(bm, vcols, (0.0, 0.0, 9.55), (0.0, 0.0, 9.76), 1.34, 1.44, 32, c_stone_deck)
    add_cylinder_to_bm(bm, vcols, (0.0, 0.0, 9.76), (0.0, 0.0, 9.95), 1.44, 1.40, 32, c_stone_shade)
    # Dark non-slip iron walkway ring on deck top
    add_ring_to_bm(bm, vcols, center_z=9.96, r_inner=0.84, r_outer=1.35, height=0.03, segs=32, color=c_iron)

    # Upper lantern cornice ring beneath cupola (z=11.12..11.26, radius=1.04)
    add_cylinder_to_bm(bm, vcols, (0.0, 0.0, 11.12), (0.0, 0.0, 11.26), 0.82, 1.04, 32, c_iron)

    create_mesh_with_vcol("LHGalleryAndCorbels", bm, vcols, mats["stone"], col, flat=True)


def build_railing(mats, col):
    """Build wrought-iron gallery balustrade with 16 ball-finial stanchions and X-lattice infill."""
    bm = bmesh.new()
    vcols = []

    c_iron = hex_to_rgba("#1b232d")
    c_iron_brass = hex_to_rgba("#9c7a38")

    rad = 1.34
    z_bot = 9.95
    z_mid = 10.03
    z_top = 10.62
    posts = 16

    for p in range(posts):
        ang0 = (p / posts) * math.pi * 2.0
        ang1 = ((p + 1) / posts) * math.pi * 2.0
        p0 = Vector((math.cos(ang0) * rad, math.sin(ang0) * rad, z_bot))
        p1 = Vector((math.cos(ang1) * rad, math.sin(ang1) * rad, z_bot))

        # Vertical turned stanchion + brass finial ball
        add_cylinder_to_bm(bm, vcols, p0, (p0.x, p0.y, z_top + 0.03), 0.026, 0.022, 8, c_iron)
        add_uv_sphere_to_bm(bm, vcols, (p0.x, p0.y, z_top + 0.055), 0.038, 10, 8, c_iron_brass)

        # Top handrail segment & bottom rail segment
        add_cylinder_to_bm(bm, vcols, (p0.x, p0.y, z_top), (p1.x, p1.y, z_top), 0.026, 0.026, 8, c_iron)
        add_cylinder_to_bm(bm, vcols, (p0.x, p0.y, z_mid), (p1.x, p1.y, z_mid), 0.016, 0.016, 6, c_iron)

        # Diagonal X-lattice infill bars
        add_cylinder_to_bm(bm, vcols, (p0.x, p0.y, z_mid), (p1.x, p1.y, z_top - 0.04), 0.011, 0.011, 6, c_iron)
        add_cylinder_to_bm(bm, vcols, (p1.x, p1.y, z_mid), (p0.x, p0.y, z_top - 0.04), 0.011, 0.011, 6, c_iron)

    create_mesh_with_vcol("LHRailing", bm, vcols, mats["iron"], col)


def build_lantern_room_and_optic(mats, col):
    """Build helical-mullion lantern cage, transparent glass cylinder, and rotatable brass Fresnel optic."""
    c_iron = hex_to_rgba("#1e2733")
    c_brass = hex_to_rgba("#d4a242")
    c_brass_dark = hex_to_rgba("#8e6b27")
    c_lamp_core = hex_to_rgba("#fff2b8")
    c_prism = hex_to_rgba("#ffe48c")

    # 1. LHLanternRoomFrame (lower parapet murette, pedestal, and 12 helical diamond glazing bars)
    bm_frame = bmesh.new()
    frame_vcols = []

    add_cylinder_to_bm(bm_frame, frame_vcols, (0.0, 0.0, 9.95), (0.0, 0.0, 10.24), 0.86, 0.84, 24, c_iron)
    add_ring_to_bm(bm_frame, frame_vcols, center_z=10.24, r_inner=0.76, r_outer=0.87, height=0.05, segs=24, color=c_brass_dark)
    # Internal cast-iron pedestal supporting Fresnel lens
    add_cylinder_to_bm(bm_frame, frame_vcols, (0.0, 0.0, 9.96), (0.0, 0.0, 10.35), 0.42, 0.34, 16, c_iron)

    # 12 helical diagonal brass/iron bars forming diamond lattice around lantern room (z=10.22..11.14)
    rad_glaze = 0.80
    bars = 12
    twist = (2.0 * math.pi) / 6.0
    for b_i in range(bars):
        a_base = (b_i / bars) * math.pi * 2.0
        for direction in (-1.0, 1.0):
            pts = []
            for seg in range(5):
                f = seg / 4.0
                ang = a_base + direction * twist * f
                z_p = 10.22 + (11.14 - 10.22) * f
                pts.append((math.cos(ang) * rad_glaze, math.sin(ang) * rad_glaze, z_p))
            for seg in range(4):
                add_cylinder_to_bm(bm_frame, frame_vcols, pts[seg], pts[seg + 1], 0.020, 0.020, 6, c_iron)

    create_mesh_with_vcol("LHLanternRoomFrame", bm_frame, frame_vcols, mats["iron"], col)

    # 2. LighthouseGlass (smooth translucent glazing cylinder at z=10.22..11.14, radius=0.77)
    bm_glass = bmesh.new()
    glass_vcols = []
    c_glass = hex_to_rgba("#ffe9a8")
    add_cylinder_to_bm(bm_glass, glass_vcols, (0.0, 0.0, 10.22), (0.0, 0.0, 11.14), 0.77, 0.77, 24, c_glass, cap_ends=False)
    create_mesh_with_vcol("LighthouseGlass", bm_glass, glass_vcols, mats["glass"], col)

    # 3. LHFresnelOptic (origin strictly at (0, 0, 10.62) so rotating around Y in Three.js spins on axis)
    bm_optic = bmesh.new()
    optic_vcols = []

    # Upper & lower octagonal brass turret rings
    add_ring_to_bm(bm_optic, optic_vcols, center_z=-0.24, r_inner=0.34, r_outer=0.45, height=0.05, segs=8, color=c_brass)
    add_ring_to_bm(bm_optic, optic_vcols, center_z=0.24, r_inner=0.34, r_outer=0.45, height=0.05, segs=8, color=c_brass)
    for s in range(8):
        ang = (s / 8.0) * math.pi * 2.0
        xp, yp = math.cos(ang) * 0.42, math.sin(ang) * 0.42
        add_cylinder_to_bm(bm_optic, optic_vcols, (xp, yp, -0.24), (xp, yp, 0.24), 0.024, 0.024, 6, c_brass)

    # Central bright lamp core
    add_uv_sphere_to_bm(bm_optic, optic_vcols, (0.0, 0.0, 0.0), 0.16, 16, 12, c_lamp_core)

    # Opposing bullseye Fresnel lens drums facing -Y and +Y (aligning with Three.js +Z and -Z beams)
    for y_sign in (-1.0, 1.0):
        # Brass lens barrel shroud
        add_cylinder_to_bm(
            bm_optic, optic_vcols,
            (0.0, y_sign * 0.24, 0.0), (0.0, y_sign * 0.36, 0.0),
            0.30, 0.26, 18, c_brass, cap_ends=False,
        )
        # Concentric stepped Fresnel prism rings + bright bullseye center
        for r_out, r_in, y_off, col_ring in [
            (0.25, 0.18, 0.35, c_prism),
            (0.18, 0.11, 0.37, c_prism),
            (0.11, 0.00, 0.39, c_lamp_core),
        ]:
            n_seg = 16
            ring_outer = []
            ring_inner = []
            for s in range(n_seg):
                ang = (s / n_seg) * math.pi * 2.0
                ca, sa = math.cos(ang), math.sin(ang)
                ring_outer.append(bm_optic.verts.new((ca * r_out, y_sign * (y_off - 0.015), sa * r_out)))
                optic_vcols.append(col_ring)
                if r_in > 0.0:
                    ring_inner.append(bm_optic.verts.new((ca * r_in, y_sign * y_off, sa * r_in)))
                    optic_vcols.append(col_ring)
            if r_in > 0.0:
                for s in range(n_seg):
                    sn = (s + 1) % n_seg
                    if y_sign > 0:
                        bm_optic.faces.new((ring_outer[s], ring_inner[s], ring_inner[sn], ring_outer[sn]))
                    else:
                        bm_optic.faces.new((ring_outer[s], ring_outer[sn], ring_inner[sn], ring_inner[s]))
            else:
                center_v = bm_optic.verts.new((0.0, y_sign * (y_off + 0.025), 0.0))
                optic_vcols.append(c_lamp_core)
                for s in range(n_seg):
                    sn = (s + 1) % n_seg
                    if y_sign > 0:
                        bm_optic.faces.new((ring_outer[s], center_v, ring_outer[sn]))
                    else:
                        bm_optic.faces.new((ring_outer[sn], center_v, ring_outer[s]))

    create_mesh_with_vcol("LHFresnelOptic", bm_optic, optic_vcols, mats["optic"], col, location=(0.0, 0.0, 10.62))


def build_cupola_and_vane(mats, col):
    """Build ribbed weathered verdigris copper dome cupola, ventilator ball, lightning spire, and weathervane."""
    bm = bmesh.new()
    vcols = []

    c_patina_light = hex_to_rgba("#529688")
    c_patina_dark = hex_to_rgba("#34635a")
    c_bronze = hex_to_rgba("#5c4429")
    c_brass = hex_to_rgba("#c8983b")

    # Ribbed cupola dome from z=11.24..12.28 (radius 0.99 tapering smoothly to 0.16 in ogee curve)
    segs = 24
    dome_steps = 10
    rings = []
    for iz in range(dome_steps):
        f = iz / (dome_steps - 1)
        z_cur = 11.24 + (12.28 - 11.24) * math.sin(f * math.pi * 0.5)
        r_cur = 0.15 + 0.84 * (math.cos(f * math.pi * 0.5) ** 0.78)
        col_d = lerp_color(c_patina_dark, c_patina_light, f * 0.75)
        ring = []
        for s in range(segs):
            ang = (s / segs) * math.pi * 2.0
            # Alternating 12 standing-seam copper ribs slightly raised
            rib_lift = 0.022 if (s % 2 == 0 and iz > 0) else 0.0
            r_eff = r_cur + rib_lift
            ring.append(bm.verts.new((math.cos(ang) * r_eff, math.sin(ang) * r_eff, z_cur)))
            vcols.append(c_bronze if (s % 2 == 0 and iz == 0) else col_d)
        rings.append(ring)

    for iz in range(dome_steps - 1):
        r0, r1 = rings[iz], rings[iz + 1]
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])

    # Brass ventilator ball at z=12.36 + lightning spire z=12.36..13.18
    add_uv_sphere_to_bm(bm, vcols, (0.0, 0.0, 12.36), 0.16, 14, 10, c_brass)
    add_cylinder_to_bm(bm, vcols, (0.0, 0.0, 12.36), (0.0, 0.0, 13.18), 0.032, 0.010, 8, c_brass)

    # Arrow weathervane at z=12.88 aligned slightly obliquely across breeze
    vane_z = 12.88
    add_cylinder_to_bm(bm, vcols, (-0.38, -0.14, vane_z), (0.40, 0.15, vane_z), 0.014, 0.014, 6, c_brass)
    add_box_to_bm(bm, vcols, (-0.34, -0.125, vane_z + 0.03), (0.18, 0.018, 0.11), (0.0, 0.0, math.atan2(0.29, 0.78)), c_brass)
    add_box_to_bm(bm, vcols, (0.40, 0.15, vane_z), (0.12, 0.08, 0.025), (0.0, 0.0, math.atan2(0.29, 0.78)), c_brass)

    create_mesh_with_vcol("LHCupolaAndVane", bm, vcols, mats["copper"], col)


def setup_studio_and_viewport(studio_col):
    """Set up natural twilight coastal studio lighting and camera framing full lighthouse."""
    world = bpy.data.worlds.new("LighthouseStudioWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_rgba("#1e3148")
        bg.inputs["Strength"].default_value = 0.65

    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 2.6
    key_data.color = (1.0, 0.92, 0.82)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(52), math.radians(18), math.radians(-38))
    studio_col.objects.link(key_obj)

    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_data.energy = 320.0
    fill_data.size = 12.0
    fill_data.color = (0.72, 0.86, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    fill_obj.location = (-9.0, -9.0, 7.0)
    fill_dir = Vector((0.0, 0.0, 6.2)) - fill_obj.location
    fill_obj.rotation_mode = "QUATERNION"
    fill_obj.rotation_quaternion = fill_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(fill_obj)

    beacon_data = bpy.data.lights.new("LanternPoint", type="POINT")
    beacon_data.energy = 280.0
    beacon_data.color = (1.0, 0.82, 0.42)
    beacon_obj = bpy.data.objects.new("LanternPoint", beacon_data)
    beacon_obj.location = (0.0, 0.0, 10.62)
    studio_col.objects.link(beacon_obj)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 35.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (-10.2, -13.8, 7.6)
    cam_dir = Vector((0.0, 0.0, 6.2)) - cam_obj.location
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
                    space.region_3d.view_location = Vector((0.0, 0.0, 6.2))
                    space.region_3d.view_rotation = Euler((math.radians(76.0), 0.0, math.radians(-36.0)), "XYZ").to_quaternion()
                    space.region_3d.view_distance = 19.0


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    lh_col = bpy.data.collections.new("Lighthouse")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(lh_col)
    bpy.context.scene.collection.children.link(studio_col)

    mats = {
        "stone": build_masonry_material("LighthouseStoneMat", roughness=0.88, noise_scale=18.0, bump_str=0.52),
        "masonry": build_masonry_material("LighthouseMasonryMat", roughness=0.72, noise_scale=22.0, bump_str=0.38),
        "iron": build_simple_material("LighthouseIronMat", roughness=0.44, metallic=0.72, bump_scale=42.0, bump_str=0.22),
        "copper": build_simple_material("LighthouseCopperMat", roughness=0.42, metallic=0.55, bump_scale=30.0, bump_str=0.28),
        "optic": build_simple_material("LighthouseOpticMat", roughness=0.14, metallic=0.35, bump_scale=24.0, bump_str=0.08, emission_strength=3.2),
        "glass": build_glass_material(),
    }

    build_foundation(mats, lh_col)
    build_tower_body(mats, lh_col)
    build_door_and_windows(mats, lh_col)
    build_gallery_and_corbels(mats, lh_col)
    build_railing(mats, lh_col)
    build_lantern_room_and_optic(mats, lh_col)
    build_cupola_and_vane(mats, lh_col)

    setup_studio_and_viewport(studio_col)

    total_verts = sum(len(o.data.vertices) for o in lh_col.objects if o.type == "MESH")
    total_polys = sum(len(o.data.polygons) for o in lh_col.objects if o.type == "MESH")
    print(f"[Lighthouse geometry] objects={len(lh_col.objects)}, verts={total_verts}, polys={total_polys}")

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[Saved] {BLEND_PATH}")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 800
    scene.render.resolution_y = 1200
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True)
    print(f"[Rendered preview] {PREVIEW_PATH}")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in lh_col.objects:
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
