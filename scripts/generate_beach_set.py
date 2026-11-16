"""Generate a realistic beach umbrella, slatted teak sunlounger, towel, and side table set (beach_set.blend & beach_set.glb) in Blender 5.2."""

import math
import os
import bpy
import bmesh
from mathutils import Color, Euler, Matrix, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(BASE_DIR, "assets", "blend", "beach_set.blend")
GLB_PATH = os.path.join(BASE_DIR, "assets", "models", "beach_set.glb")
PREVIEW_PATH = "/Users/syamban/.gemini/antigravity-cli/brain/a2810c20-f453-4255-9182-bae8a0819dcc/scratch/beach_set_preview.png"

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
    """Finalize BMesh with active BeachSetColor BYTE_COLOR attribute."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    for poly in mesh.polygons:
        poly.use_smooth = not flat

    color_attr = mesh.color_attributes.new(name="BeachSetColor", type="BYTE_COLOR", domain="POINT")
    mesh.color_attributes.active_color = color_attr
    for idx, rgba in enumerate(vert_colors):
        if idx < len(color_attr.data):
            color_attr.data[idx].color = rgba

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    return obj


def add_box_to_bm(bm, vcols, center, size_xyz, rot_euler, color, xform=None):
    """Append an oriented box with uniform vertex color into bm, optionally transformed by xform."""
    rot_m = Euler(rot_euler, "XYZ").to_matrix()
    tmp = bmesh.new()
    bmesh.ops.create_cube(tmp, size=1.0)
    vmap = {}
    for v in tmp.verts:
        p = Vector((v.co.x * size_xyz[0], v.co.y * size_xyz[1], v.co.z * size_xyz[2]))
        wp = Vector(center) + rot_m @ p
        if xform is not None:
            wp = xform @ wp
        vmap[v] = bm.verts.new(wp)
        vcols.append(color)
    for f in tmp.faces:
        bm.faces.new([vmap[v] for v in f.verts])
    tmp.free()


def add_cylinder_to_bm(bm, vcols, p0, p1, r0, r1, segs, color, cap_ends=True, xform=None):
    """Append a tapered cylinder between p0 and p1 into bm."""
    v0 = Vector(p0)
    v1 = Vector(p1)
    if xform is not None:
        v0 = xform @ v0
        v1 = xform @ v1
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


def build_textured_material(name, roughness=0.72, metallic=0.0, bump_scale=28.0, bump_str=0.35, double_sided=False):
    """Build procedural PBR material driven by BeachSetColor with noise surface bump."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_backface_culling = not double_sided
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (660, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (340, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "BeachSetColor"
    vcol.location = (-440, 180)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-860, -140)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-600, -120)
    noise.inputs["Scale"].default_value = bump_scale
    noise.inputs["Detail"].default_value = 10.0
    noise.inputs["Roughness"].default_value = 0.72
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-320, 40)
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (0.85, 0.84, 0.82, 1.0)
    ramp.color_ramp.elements[1].position = 0.80
    ramp.color_ramp.elements[1].color = (1.06, 1.05, 1.03, 1.0)
    nt.links.new(noise.outputs["Factor"], ramp.inputs["Factor"])

    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.location = (40, 160)
    mix.inputs["Factor"].default_value = 0.45
    nt.links.new(vcol.outputs["Color"], mix.inputs[6])
    nt.links.new(ramp.outputs["Color"], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (60, -180)
    bump.inputs["Strength"].default_value = bump_str
    bump.inputs["Distance"].default_value = 0.012
    nt.links.new(noise.outputs["Factor"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_beach_mat_platform(mats, col):
    """Build woven straw beach mat (2.45m x 2.25m) and weighted timber umbrella base."""
    bm = bmesh.new()
    vcols = []

    c_straw_a = hex_to_rgba("#d9be8b")
    c_straw_b = hex_to_rgba("#cbb07c")
    c_border = hex_to_rgba("#b5935b")
    c_teak_dark = hex_to_rgba("#613b20")
    c_brass = hex_to_rgba("#c99c3c")

    # Woven mat core body + subtle woven slat strips
    add_box_to_bm(bm, vcols, (0.04, -0.05, -0.025), (2.45, 2.25, 0.07), (0.0, 0.0, 0.0), c_straw_a)
    for si in range(18):
        sy = -1.10 + (si / 17.0) * 2.10
        add_box_to_bm(
            bm, vcols,
            (0.04, sy, 0.015),
            (2.38, 0.105, 0.014),
            (0.0, 0.0, 0.0),
            c_straw_a if si % 2 == 0 else c_straw_b,
        )
    # Stitched border edge bands
    for bx, by, sx, sy in [
        (0.04, -1.155, 2.48, 0.06),
        (0.04, 1.055, 2.48, 0.06),
        (-1.165, -0.05, 0.06, 2.28),
        (1.245, -0.05, 0.06, 2.28),
    ]:
        add_box_to_bm(bm, vcols, (bx, by, 0.018), (sx, sy, 0.022), (0.0, 0.0, 0.0), c_border)

    # Weighted cross-timber & octagonal umbrella base at x=-0.58, y=0.0 extending to z=-0.16
    ux, uy = -0.58, 0.0
    add_cylinder_to_bm(bm, vcols, (ux, uy, -0.16), (ux, uy, 0.08), 0.25, 0.22, 8, c_teak_dark)
    add_box_to_bm(bm, vcols, (ux, uy, 0.04), (0.58, 0.14, 0.07), (0.0, 0.0, 0.0), c_teak_dark)
    add_box_to_bm(bm, vcols, (ux, uy, 0.04), (0.14, 0.58, 0.07), (0.0, 0.0, 0.0), c_teak_dark)
    add_cylinder_to_bm(bm, vcols, (ux, uy, 0.08), (ux, uy, 0.18), 0.07, 0.058, 12, c_brass)

    create_mesh_with_vcol("BeachMatPlatform", bm, vcols, mats["straw"], col, flat=True)


def umbrella_xform():
    """Return 4x4 Matrix positioning & tilting umbrella pole 6 deg toward the lounger (+X)."""
    pivot = Vector((-0.58, 0.0, 0.10))
    return (
        Matrix.Translation(pivot)
        @ Euler((0.0, math.radians(6.0), 0.0), "XYZ").to_matrix().to_4x4()
    )


def eval_canopy_z(rad_frac):
    """Evaluate dome canopy local Z relative to runner/hub apex along local pole axis."""
    return 2.48 - (rad_frac ** 1.45) * 0.50


def build_umbrella_frame_and_canopy(mats, col):
    """Build hardwood tilted pole, ribs/stretchers, runner, finial, and scalloped wind-vented canopy."""
    xf = umbrella_xform()

    c_wood = hex_to_rgba("#8a5732")
    c_wood_dark = hex_to_rgba("#5c361c")
    c_brass = hex_to_rgba("#d2a13e")

    # 1. UmbrellaFrame
    bm_frame = bmesh.new()
    frame_vcols = []

    # Main pole from socket (z=0.0) up to z=2.56 + wooden finial z=2.62
    add_cylinder_to_bm(bm_frame, frame_vcols, (0.0, 0.0, 0.0), (0.0, 0.0, 2.52), 0.044, 0.036, 12, c_wood, xform=xf)
    # Brass locking collar & lower sliding runner hub
    add_cylinder_to_bm(bm_frame, frame_vcols, (0.0, 0.0, 1.24), (0.0, 0.0, 1.36), 0.050, 0.050, 12, c_brass, xform=xf)
    add_cylinder_to_bm(bm_frame, frame_vcols, (0.0, 0.0, 1.76), (0.0, 0.0, 1.88), 0.068, 0.068, 12, c_wood_dark, xform=xf)
    # Top hub + turned wooden finial spire
    add_cylinder_to_bm(bm_frame, frame_vcols, (0.0, 0.0, 2.46), (0.0, 0.0, 2.56), 0.065, 0.052, 12, c_brass, xform=xf)
    add_cylinder_to_bm(bm_frame, frame_vcols, (0.0, 0.0, 2.56), (0.0, 0.0, 2.70), 0.048, 0.012, 10, c_wood_dark, xform=xf)

    # 8 radiating wooden ribs + stretchers + brass tip ferrules
    panels = 8
    r_outer = 1.56
    for p in range(panels):
        ang = (p / panels) * math.pi * 2.0
        ca, sa = math.cos(ang), math.sin(ang)
        pts_rib = []
        for k in range(5):
            vf = k / 4.0
            rk = vf * (r_outer + 0.02)
            zk = eval_canopy_z(vf) - 0.02
            pts_rib.append((ca * rk, sa * rk, zk))
        for k in range(4):
            add_cylinder_to_bm(bm_frame, frame_vcols, pts_rib[k], pts_rib[k + 1], 0.016, 0.014, 6, c_wood, xform=xf)
        # Brass rib tip endcap
        add_cylinder_to_bm(bm_frame, frame_vcols, pts_rib[3], pts_rib[4], 0.018, 0.015, 8, c_brass, xform=xf)
        # Stretcher strut from sliding runner (z=1.82) to mid-rib (vf=0.50)
        mid_p = pts_rib[2]
        add_cylinder_to_bm(bm_frame, frame_vcols, (ca * 0.05, sa * 0.05, 1.82), mid_p, 0.013, 0.012, 6, c_wood_dark, xform=xf)

    create_mesh_with_vcol("UmbrellaFrame", bm_frame, frame_vcols, mats["wood"], col)

    # 2. UmbrellaCanopy (8 alternating terracotta/cream panels + upper wind vent tier + scalloped valance)
    bm_canopy = bmesh.new()
    can_vcols = []

    c_terra = hex_to_rgba("#d9533f")
    c_terra_shade = hex_to_rgba("#b8402e")
    c_cream = hex_to_rgba("#f6efe2")
    c_cream_shade = hex_to_rgba("#e2d7c2")

    u_segs = 6
    v_segs = 7
    for p in range(panels):
        a0 = (p / panels) * math.pi * 2.0
        a1 = ((p + 1) / panels) * math.pi * 2.0
        col_main = c_terra if p % 2 == 0 else c_cream
        col_shade = c_terra_shade if p % 2 == 0 else c_cream_shade

        # Main canopy panel from vent inner ring (r=0.34) to outer rim (r=1.56)
        grid = [[None] * (u_segs + 1) for _ in range(v_segs + 1)]
        for iv in range(v_segs + 1):
            vf = 0.22 + (iv / v_segs) * 0.78
            rad = vf * r_outer
            for iu in range(u_segs + 1):
                uf = iu / u_segs
                ang = a0 + (a1 - a0) * uf
                # Soft fabric billow between ribs + slight scoop at outer edge
                billow = math.sin(uf * math.pi) * 0.032 * math.sin(vf * math.pi)
                z_p = eval_canopy_z(vf) + billow
                wp = xf @ Vector((math.cos(ang) * rad, math.sin(ang) * rad, z_p))
                grid[iv][iu] = bm_canopy.verts.new(wp)
                can_vcols.append(lerp_color(col_main, col_shade, vf * 0.4))

        for iv in range(v_segs):
            for iu in range(u_segs):
                bm_canopy.faces.new((grid[iv][iu], grid[iv][iu + 1], grid[iv + 1][iu + 1], grid[iv + 1][iu]))

        # Upper wind-vent canopy cap tier (r=0.04..0.46) raised +0.075m above main canopy gap
        v_cap_segs = 4
        cap_grid = [[None] * (u_segs + 1) for _ in range(v_cap_segs + 1)]
        for iv in range(v_cap_segs + 1):
            vf_c = 0.02 + (iv / v_cap_segs) * 0.30
            rad_c = vf_c * r_outer
            for iu in range(u_segs + 1):
                uf = iu / u_segs
                ang = a0 + (a1 - a0) * uf
                z_c = eval_canopy_z(vf_c) + 0.082
                wp = xf @ Vector((math.cos(ang) * rad_c, math.sin(ang) * rad_c, z_c))
                cap_grid[iv][iu] = bm_canopy.verts.new(wp)
                can_vcols.append(col_main)

        for iv in range(v_cap_segs):
            for iu in range(u_segs):
                bm_canopy.faces.new((cap_grid[iv][iu], cap_grid[iv][iu + 1], cap_grid[iv + 1][iu + 1], cap_grid[iv + 1][iu]))

        # Hanging scalloped valance flap around rim (r=1.56, drop=0.15m) with cream piping trim
        val_rows = 3
        val_grid = [[None] * (u_segs + 1) for _ in range(val_rows + 1)]
        rim_z = eval_canopy_z(1.0)
        for ir in range(val_rows + 1):
            rf = ir / val_rows
            is_piping = ir == val_rows
            for iu in range(u_segs + 1):
                uf = iu / u_segs
                ang = a0 + (a1 - a0) * uf
                scallop_drop = 0.12 + 0.05 * math.sin(uf * math.pi)
                z_v = rim_z - rf * scallop_drop
                rad_v = r_outer + 0.015 * math.sin(rf * math.pi)
                wp = xf @ Vector((math.cos(ang) * rad_v, math.sin(ang) * rad_v, z_v))
                val_grid[ir][iu] = bm_canopy.verts.new(wp)
                can_vcols.append(c_cream if is_piping else lerp_color(col_main, col_shade, 0.35))

        for ir in range(val_rows):
            for iu in range(u_segs):
                bm_canopy.faces.new((val_grid[ir][iu], val_grid[ir + 1][iu], val_grid[ir + 1][iu + 1], val_grid[ir][iu + 1]))

    create_mesh_with_vcol("UmbrellaCanopy", bm_canopy, can_vcols, mats["fabric"], col)


def build_sunlounger_and_cushion(mats, col):
    """Build slatted teak sunlounger with wheels, backrest struts, drink tray, cushion, pillow, and towel."""
    lx, ly = 0.48, -0.05
    back_deg = 32.0
    back_rad = math.radians(back_deg)
    hinge_y = ly + 0.22
    hinge_z = 0.29

    c_teak_a = hex_to_rgba("#9c6538")
    c_teak_b = hex_to_rgba("#824f29")
    c_brass = hex_to_rgba("#d2a13e")

    # 1. TeakSunlounger
    bm_lounger = bmesh.new()
    l_vcols = []

    # 6 sturdy legs down to z=-0.16 so frame never floats on uneven beach sand
    for sx in (-0.36, 0.36):
        for sy in (-0.82, 0.16, 0.72):
            add_box_to_bm(bm_lounger, l_vcols, (lx + sx, ly + sy, 0.06), (0.065, 0.065, 0.44), (0.0, 0.0, 0.0), c_teak_b)
        # Longitudinal side apron rails
        add_box_to_bm(bm_lounger, l_vcols, (lx + sx, ly - 0.02, 0.28), (0.065, 1.98, 0.085), (0.0, 0.0, 0.0), c_teak_a)

    # End frame rails & 18 transverse teak bed slats
    add_box_to_bm(bm_lounger, l_vcols, (lx, ly - 0.98, 0.28), (0.82, 0.06, 0.085), (0.0, 0.0, 0.0), c_teak_b)
    add_box_to_bm(bm_lounger, l_vcols, (lx, ly + 0.94, 0.28), (0.82, 0.06, 0.085), (0.0, 0.0, 0.0), c_teak_b)
    for k in range(18):
        sy = ly - 0.88 + k * 0.105
        add_box_to_bm(bm_lounger, l_vcols, (lx, sy, 0.295), (0.72, 0.072, 0.024), (0.0, 0.0, 0.0), c_teak_a if k % 2 == 0 else c_teak_b)

    # Rear teak wheels with brass hubs at head legs (y = ly + 0.72)
    add_cylinder_to_bm(bm_lounger, l_vcols, (lx - 0.44, ly + 0.72, 0.08), (lx + 0.44, ly + 0.72, 0.08), 0.022, 0.022, 10, c_brass)
    for side in (-1.0, 1.0):
        wx = lx + side * 0.425
        add_cylinder_to_bm(bm_lounger, l_vcols, (wx - 0.025, ly + 0.72, 0.08), (wx + 0.025, ly + 0.72, 0.08), 0.115, 0.115, 16, c_teak_b)
        add_cylinder_to_bm(bm_lounger, l_vcols, (wx - 0.032, ly + 0.72, 0.08), (wx + 0.032, ly + 0.72, 0.08), 0.038, 0.038, 12, c_brass)

    # Slatted inclined backrest frame (+32 deg tilt upward around hinge_y, hinge_z)
    back_xf = (
        Matrix.Translation(Vector((lx, hinge_y, hinge_z)))
        @ Euler((back_rad, 0.0, 0.0), "XYZ").to_matrix().to_4x4()
    )
    for sx in (-0.33, 0.33):
        add_box_to_bm(bm_lounger, l_vcols, (sx, 0.40, 0.02), (0.055, 0.84, 0.065), (0.0, 0.0, 0.0), c_teak_a, xform=back_xf)
    add_box_to_bm(bm_lounger, l_vcols, (0.0, 0.80, 0.02), (0.72, 0.055, 0.065), (0.0, 0.0, 0.0), c_teak_b, xform=back_xf)
    for bs in range(7):
        add_box_to_bm(bm_lounger, l_vcols, (0.0, 0.09 + bs * 0.105, 0.035), (0.64, 0.068, 0.022), (0.0, 0.0, 0.0), c_teak_a if bs % 2 == 0 else c_teak_b, xform=back_xf)

    # Prop support struts connecting angled backrest underside back down to rear frame rail
    for sx in (-0.28, 0.28):
        p_back = back_xf @ Vector((sx, 0.56, 0.0))
        add_cylinder_to_bm(bm_lounger, l_vcols, (lx + sx, ly + 0.62, 0.30), p_back, 0.018, 0.018, 8, c_brass)

    # Pull-out slatted side drink tray on the umbrella (-X) side
    add_box_to_bm(bm_lounger, l_vcols, (lx - 0.48, ly - 0.12, 0.26), (0.28, 0.32, 0.028), (0.0, 0.0, 0.0), c_teak_a)

    create_mesh_with_vcol("TeakSunlounger", bm_lounger, l_vcols, mats["wood"], col, flat=True)

    # 2. LoungerCushionAndTowel (piped segmented mattress + striped bolster pillow + turquoise beach towel)
    bm_soft = bmesh.new()
    s_vcols = []

    c_cush = hex_to_rgba("#f4efe4")
    c_cush_seam = hex_to_rgba("#d8cfbe")
    c_pillow_blue = hex_to_rgba("#246a87")
    c_pillow_white = hex_to_rgba("#f2ede2")
    c_towel_turq = hex_to_rgba("#2fa89c")
    c_towel_white = hex_to_rgba("#f7f4ec")

    # Lower horizontal cushion segments (3 tufted pads along seat)
    for seg_i, (sy_c, slen) in enumerate([(-0.68, 0.38), (-0.28, 0.38), (0.09, 0.32)]):
        add_box_to_bm(bm_soft, s_vcols, (lx, ly + sy_c, 0.345), (0.72, slen, 0.075), (0.0, 0.0, 0.0), c_cush)
        add_box_to_bm(bm_soft, s_vcols, (lx, ly + sy_c + slen * 0.5, 0.352), (0.725, 0.025, 0.072), (0.0, 0.0, 0.0), c_cush_seam)

    # Backrest cushion segments resting atop the tilted slats
    for b_i, (by_c, blen) in enumerate([(0.20, 0.34), (0.58, 0.38)]):
        add_box_to_bm(bm_soft, s_vcols, (0.0, by_c, 0.082), (0.70, blen, 0.075), (0.0, 0.0, 0.0), c_cush, xform=back_xf)
        if b_i == 0:
            add_box_to_bm(bm_soft, s_vcols, (0.0, by_c + blen * 0.5, 0.09), (0.705, 0.025, 0.072), (0.0, 0.0, 0.0), c_cush_seam, xform=back_xf)

    # Striped coastal-blue bolster pillow near top of backrest
    n_p_stripes = 7
    p_w = 0.54
    for pi in range(n_p_stripes):
        px0 = -p_w * 0.5 + (pi / n_p_stripes) * p_w
        px1 = -p_w * 0.5 + ((pi + 1) / n_p_stripes) * p_w
        col_st = c_pillow_blue if pi % 2 == 0 else c_pillow_white
        add_cylinder_to_bm(bm_soft, s_vcols, (px0, 0.66, 0.165), (px1, 0.66, 0.165), 0.082, 0.082, 14, col_st, xform=back_xf)

    # Folded turquoise-and-white striped beach towel draped cleanly over the foot end (-Y) of the lounger
    n_towel_stripes = 8
    t_len = 0.56
    for ti in range(n_towel_stripes):
        ty_c = ly - 0.88 + (ti + 0.5) * (t_len / n_towel_stripes)
        col_tw = c_towel_turq if ti % 2 == 0 else c_towel_white
        add_box_to_bm(bm_soft, s_vcols, (lx, ty_c, 0.392), (0.75, t_len / n_towel_stripes + 0.004, 0.022), (0.0, 0.0, 0.0), col_tw)
    # Rolled overhanging towel drape hanging neatly over foot rail edge
    add_box_to_bm(bm_soft, s_vcols, (lx, ly - 0.92, 0.335), (0.75, 0.04, 0.14), (0.0, 0.0, 0.0), c_towel_turq)

    create_mesh_with_vcol("LoungerCushionAndTowel", bm_soft, s_vcols, mats["fabric"], col)


def build_side_table_and_drinks(mats, col):
    """Build slatted teak octagonal side table with coconut drink + striped straw and sun hat."""
    bm = bmesh.new()
    vcols = []

    tx, ty = -0.25, -0.38
    c_teak_a = hex_to_rgba("#9c6538")
    c_teak_b = hex_to_rgba("#7a4a26")
    c_coconut = hex_to_rgba("#4c7d32")
    c_coconut_inner = hex_to_rgba("#2b1e16")
    c_straw_red = hex_to_rgba("#d93829")
    c_straw_white = hex_to_rgba("#f8f5ec")
    c_hat_straw = hex_to_rgba("#e0c488")
    c_hat_band = hex_to_rgba("#205c78")

    # 4 splayed octagonal table legs down to z=-0.14 + cross brace ring
    for li in range(4):
        ang = (li / 4.0) * math.pi * 2.0 + math.pi * 0.25
        add_cylinder_to_bm(
            bm, vcols,
            (tx + math.cos(ang) * 0.17, ty + math.sin(ang) * 0.17, -0.14),
            (tx + math.cos(ang) * 0.14, ty + math.sin(ang) * 0.14, 0.42),
            0.022, 0.020, 8, c_teak_b,
        )
    add_cylinder_to_bm(bm, vcols, (tx, ty, 0.16), (tx, ty, 0.19), 0.17, 0.17, 8, c_teak_b)
    # Octagonal tabletop rim + slatted surface planks at z=0.43..0.46
    add_cylinder_to_bm(bm, vcols, (tx, ty, 0.415), (tx, ty, 0.445), 0.24, 0.24, 8, c_teak_b)
    for si in range(5):
        sy = ty - 0.16 + si * 0.08
        slen = 0.40 - abs(si - 2) * 0.055
        add_box_to_bm(bm, vcols, (tx, sy, 0.452), (slen, 0.065, 0.018), (0.0, 0.0, 0.0), c_teak_a if si % 2 == 0 else c_teak_b)

    # Fresh green coconut drink + red-and-white striped bendy straw
    cx, cy = tx - 0.07, ty + 0.06
    add_cylinder_to_bm(bm, vcols, (cx, cy, 0.46), (cx, cy, 0.56), 0.052, 0.065, 12, c_coconut)
    add_cylinder_to_bm(bm, vcols, (cx, cy, 0.56), (cx, cy, 0.59), 0.065, 0.048, 12, c_coconut)
    add_cylinder_to_bm(bm, vcols, (cx, cy, 0.585), (cx, cy, 0.595), 0.040, 0.040, 12, c_coconut_inner)
    # Segmented striped straw
    for k in range(5):
        z0 = 0.57 + k * 0.032
        z1 = z0 + 0.032
        sx0 = cx + k * 0.005
        sx1 = cx + (k + 1) * 0.005
        add_cylinder_to_bm(bm, vcols, (sx0, cy, z0), (sx1, cy, z1), 0.007, 0.007, 6, c_straw_red if k % 2 == 0 else c_straw_white)
    add_cylinder_to_bm(bm, vcols, (cx + 0.025, cy, 0.73), (cx + 0.07, cy + 0.02, 0.76), 0.007, 0.007, 6, c_straw_red)

    # Woven straw sun hat resting slightly off-center on table top
    hx, hy = tx + 0.07, ty - 0.07
    add_cylinder_to_bm(bm, vcols, (hx, hy, 0.465), (hx, hy, 0.482), 0.165, 0.135, 16, c_hat_straw)
    add_cylinder_to_bm(bm, vcols, (hx, hy, 0.48), (hx, hy, 0.505), 0.095, 0.092, 14, c_hat_band)
    add_cylinder_to_bm(bm, vcols, (hx, hy, 0.505), (hx, hy, 0.555), 0.090, 0.068, 14, c_hat_straw)

    create_mesh_with_vcol("BeachSideTableAndDrinks", bm, vcols, mats["wood"], col)


def setup_studio_and_viewport(studio_col):
    """Set up sunlit tropical beach studio lighting and camera framing the full set."""
    world = bpy.data.worlds.new("BeachSetStudioWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_rgba("#c8e7f9")
        bg.inputs["Strength"].default_value = 0.75

    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 3.2
    key_data.color = (1.0, 0.96, 0.88)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(46), math.radians(18), math.radians(-42))
    studio_col.objects.link(key_obj)

    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_data.energy = 240.0
    fill_data.size = 10.0
    fill_data.color = (0.85, 0.93, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    fill_obj.location = (-5.5, -5.0, 3.8)
    fill_dir = Vector((0.0, 0.0, 1.1)) - fill_obj.location
    fill_obj.rotation_mode = "QUATERNION"
    fill_obj.rotation_quaternion = fill_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(fill_obj)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 35.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (-3.6, -4.4, 2.35)
    cam_dir = Vector((0.05, -0.05, 1.05)) - cam_obj.location
    cam_obj.rotation_mode = "QUATERNION"
    cam_obj.rotation_quaternion = cam_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    b_col = bpy.data.collections.new("BeachSet")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(b_col)
    bpy.context.scene.collection.children.link(studio_col)

    mats = {
        "straw": build_textured_material("BeachStrawMat", roughness=0.84, bump_scale=38.0, bump_str=0.45),
        "wood": build_textured_material("BeachTeakMat", roughness=0.58, bump_scale=24.0, bump_str=0.35),
        "fabric": build_textured_material("BeachCanvasMat", roughness=0.78, bump_scale=44.0, bump_str=0.25, double_sided=True),
    }

    build_beach_mat_platform(mats, b_col)
    build_umbrella_frame_and_canopy(mats, b_col)
    build_sunlounger_and_cushion(mats, b_col)
    build_side_table_and_drinks(mats, b_col)
    setup_studio_and_viewport(studio_col)

    total_verts = sum(len(o.data.vertices) for o in b_col.objects if o.type == "MESH")
    total_polys = sum(len(o.data.polygons) for o in b_col.objects if o.type == "MESH")
    print(f"[BeachSet geometry] objects={len(b_col.objects)}, verts={total_verts}, polys={total_polys}")

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[Saved] {BLEND_PATH}")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 840
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True)
    print(f"[Rendered preview] {PREVIEW_PATH}")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in b_col.objects:
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
