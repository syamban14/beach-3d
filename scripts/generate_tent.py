"""Generate a realistic A-frame glamping canvas tent on a raised teak deck (tent.blend & tent.glb) in Blender 5.2."""

import math
import os
import bpy
import bmesh
from mathutils import Color, Euler, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(BASE_DIR, "assets", "blend", "tent.blend")
GLB_PATH = os.path.join(BASE_DIR, "assets", "models", "tent.glb")
PREVIEW_PATH = "/Users/syamban/.gemini/antigravity-cli/brain/a2810c20-f453-4255-9182-bae8a0819dcc/scratch/tent_preview.png"

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
    """Finalize BMesh with active TentColor BYTE_COLOR attribute."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    for poly in mesh.polygons:
        poly.use_smooth = not flat

    color_attr = mesh.color_attributes.new(name="TentColor", type="BYTE_COLOR", domain="POINT")
    mesh.color_attributes.active_color = color_attr
    for idx, rgba in enumerate(vert_colors):
        if idx < len(color_attr.data):
            color_attr.data[idx].color = rgba

    obj = bpy.data.objects.new(name, mesh)
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
    """Append a tapered cylinder between p0 and p1 with uniform vertex color."""
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


def add_uv_sphere_to_bm(bm, vcols, center, radius, scale_xyz, segs, rings, color):
    """Append a scaled UV sphere/ellipsoid into bm."""
    tmp = bmesh.new()
    bmesh.ops.create_uvsphere(tmp, u_segments=segs, v_segments=rings, radius=radius)
    vmap = {}
    c_vec = Vector(center)
    for v in tmp.verts:
        p = Vector((v.co.x * scale_xyz[0], v.co.y * scale_xyz[1], v.co.z * scale_xyz[2]))
        vmap[v] = bm.verts.new(c_vec + p)
        vcols.append(color)
    for f in tmp.faces:
        bm.faces.new([vmap[v] for v in f.verts])
    tmp.free()


def build_tent_material(name, roughness=0.72, metallic=0.0, bump_scale=28.0, bump_str=0.35, double_sided=False, emission_strength=0.0):
    """Build procedural PBR material driven by TentColor with optional emission and surface bump."""
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
    vcol.layer_name = "TentColor"
    vcol.location = (-440, 180)
    nt.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])

    if emission_strength > 0.0 and "Emission Color" in bsdf.inputs:
        nt.links.new(vcol.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission_strength

    if bump_str > 0.0:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-860, -140)
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.location = (-580, -120)
        noise.inputs["Scale"].default_value = bump_scale
        noise.inputs["Detail"].default_value = 9.0
        nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])

        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.location = (-320, 40)
        ramp.color_ramp.elements[0].position = 0.24
        ramp.color_ramp.elements[0].color = (0.86, 0.85, 0.84, 1.0)
        ramp.color_ramp.elements[1].position = 0.80
        ramp.color_ramp.elements[1].color = (1.06, 1.05, 1.03, 1.0)
        nt.links.new(noise.outputs["Factor"], ramp.inputs["Factor"])

        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.location = (40, 160)
        mix.inputs["Factor"].default_value = 0.42
        nt.links.new(vcol.outputs["Color"], mix.inputs[6])
        nt.links.new(ramp.outputs["Color"], mix.inputs[7])
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])

        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (60, -180)
        bump.inputs["Strength"].default_value = bump_str
        bump.inputs["Distance"].default_value = 0.014
        nt.links.new(noise.outputs["Factor"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    return mat


def build_deck_platform(mats, col):
    """Build raised slatted teak glamping deck (2.75m x 3.35m) with foundation posts and front step."""
    bm = bmesh.new()
    vcols = []

    c_teak_a = hex_to_rgba("#9c6538")
    c_teak_b = hex_to_rgba("#824f29")
    c_joist = hex_to_rgba("#59351c")

    # 9 foundation posts down to z=-0.32m so deck never floats on sloped sand
    for px in (-1.20, 0.0, 1.20):
        for py in (-1.50, 0.0, 1.50):
            add_box_to_bm(bm, vcols, (px, py, -0.10), (0.14, 0.14, 0.44), (0.0, 0.0, 0.0), c_joist)

    # Outer skirt frame rim & 3 longitudinal stringers
    for px in (-1.31, 0.0, 1.31):
        add_box_to_bm(bm, vcols, (px, 0.0, 0.09), (0.11, 3.35, 0.12), (0.0, 0.0, 0.0), c_joist)
    for py in (-1.62, 1.62):
        add_box_to_bm(bm, vcols, (0.0, py, 0.09), (2.75, 0.11, 0.12), (0.0, 0.0, 0.0), c_joist)

    # 26 transverse slatted teak deck planks (top surface z=0.18m)
    planks = 26
    for i in range(planks):
        py = -1.60 + (i + 0.5) * (3.20 / planks)
        add_box_to_bm(
            bm, vcols,
            (0.0, py, 0.165),
            (2.74, 0.105, 0.032),
            (0.0, 0.0, 0.0),
            c_teak_a if i % 2 == 0 else c_teak_b,
        )

    # Front wooden entry step on the -Y side (y=-1.68..-1.96)
    for sx in (-0.65, 0.65):
        add_box_to_bm(bm, vcols, (sx, -1.82, -0.09), (0.12, 0.24, 0.34), (0.0, 0.0, 0.0), c_joist)
    add_box_to_bm(bm, vcols, (0.0, -1.78, 0.075), (1.52, 0.125, 0.032), (0.0, 0.0, 0.0), c_teak_a)
    add_box_to_bm(bm, vcols, (0.0, -1.91, 0.075), (1.52, 0.115, 0.032), (0.0, 0.0, 0.0), c_teak_b)

    create_mesh_with_vcol("TentDeckPlatform", bm, vcols, mats["wood"], col, flat=True)


def build_timber_frame_and_stakes(mats, col):
    """Build front & rear crossed A-frame poles, ridge beam, perimeter wooden stakes, and guy ropes."""
    bm = bmesh.new()
    vcols = []

    c_pole = hex_to_rgba("#6e4322")
    c_pole_dark = hex_to_rgba("#4c2d17")
    c_brass = hex_to_rgba("#c99c3c")
    c_rope = hex_to_rgba("#d1bc94")

    # Front (y=-1.18) and rear (y=+1.30) A-frame crossed poles meeting near (0, y, 2.12) & crossing to 2.28
    for ay in (-1.18, 1.30):
        add_cylinder_to_bm(bm, vcols, (-1.18, ay, 0.17), (0.10, ay, 2.28), 0.044, 0.034, 10, c_pole)
        add_cylinder_to_bm(bm, vcols, (1.18, ay, 0.17), (-0.10, ay, 2.28), 0.044, 0.034, 10, c_pole)
        # Brass hinge collar at ridge crossing
        add_cylinder_to_bm(bm, vcols, (0.0, ay - 0.06, 2.10), (0.0, ay + 0.06, 2.10), 0.056, 0.056, 10, c_brass)

    # Ridge beam running y=-1.50..+1.44 at z=2.10 extending over front porch
    add_cylinder_to_bm(bm, vcols, (0.0, -1.50, 2.10), (0.0, 1.44, 2.10), 0.042, 0.042, 10, c_pole_dark)
    add_cylinder_to_bm(bm, vcols, (0.0, -1.52, 2.10), (0.0, -1.46, 2.10), 0.052, 0.052, 10, c_brass)

    # 6 wooden stakes driven into sand beside the deck + taut hemp guy lines to rainfly eaves
    for side in (-1.0, 1.0):
        for sy in (-0.95, 0.15, 1.15):
            st_bot = Vector((side * 1.66, sy, -0.22))
            st_top = Vector((side * 1.56, sy, 0.18))
            add_cylinder_to_bm(bm, vcols, st_bot, st_top, 0.025, 0.032, 8, c_pole_dark)
            eave_pt = Vector((side * 1.12, sy, 0.65))
            add_cylinder_to_bm(bm, vcols, eave_pt, st_top - Vector((0.0, 0.0, 0.02)), 0.008, 0.008, 6, c_rope)

    create_mesh_with_vcol("TentTimberFrame", bm, vcols, mats["wood"], col)


def eval_tent_slope_pt(side_sign, u_y, v_h, y0=-1.16, y1=1.28, half_w=1.14, ridge_z=2.08, eave_z=0.18, sag=0.055):
    """Evaluate point on A-frame canvas roof slope from eave (v=0) to ridge (v=1) with gentle catenary sag."""
    y_val = y0 + (y1 - y0) * u_y
    x_val = side_sign * half_w * (1.0 - v_h)
    sag_drop = sag * math.sin(v_h * math.pi) * (0.4 + 0.6 * math.sin(u_y * math.pi))
    z_val = eave_z + (ridge_z - eave_z) * v_h - sag_drop
    return Vector((x_val, y_val, z_val))


def build_canvas_body_and_rainfly(mats, col):
    """Build warm cream canvas A-frame body with side windows, tied open front flaps, and terracotta rainfly."""
    bm = bmesh.new()
    vcols = []

    c_canvas = hex_to_rgba("#efe5d0")
    c_canvas_seam = hex_to_rgba("#d9cbb0")
    c_rainfly = hex_to_rgba("#b85838")
    c_rainfly_trim = hex_to_rgba("#943f24")
    c_window_mesh = hex_to_rgba("#2f2a24")
    c_flap_tie = hex_to_rgba("#8a4626")

    # 1. Cream-sand canvas inner tent walls (-X and +X slopes from y=-1.16 to y=+1.28)
    nu, nv = 12, 10
    for side in (-1.0, 1.0):
        grid = [[None] * (nv + 1) for _ in range(nu + 1)]
        for iu in range(nu + 1):
            uy = iu / nu
            for iv in range(nv + 1):
                vh = iv / nv
                pt = eval_tent_slope_pt(side, uy, vh)
                grid[iu][iv] = bm.verts.new(pt)
                col_c = lerp_color(c_canvas_seam, c_canvas, vh * 0.65 + 0.35)
                vcols.append(col_c)
        for iu in range(nu):
            for iv in range(nv):
                bm.faces.new((grid[iu][iv], grid[iu + 1][iv], grid[iu + 1][iv + 1], grid[iu][iv + 1]))

        # Side roll-up window patch + dark mesh opening + rolled blind cylinder above window
        w_y0, w_y1 = 0.30, 0.68
        p_bl = eval_tent_slope_pt(side, w_y0, 0.24) + Vector((side * 0.012, 0.0, 0.0))
        p_br = eval_tent_slope_pt(side, w_y1, 0.24) + Vector((side * 0.012, 0.0, 0.0))
        p_tr = eval_tent_slope_pt(side, w_y1, 0.56) + Vector((side * 0.012, 0.0, 0.0))
        p_tl = eval_tent_slope_pt(side, w_y0, 0.56) + Vector((side * 0.012, 0.0, 0.0))
        verts_w = [bm.verts.new(p) for p in (p_bl, p_br, p_tr, p_tl)]
        vcols.extend([c_window_mesh] * 4)
        bm.faces.new(verts_w)
        # Rolled canvas shade cylinder sitting cleanly along top edge of window
        add_cylinder_to_bm(bm, vcols, p_tl + Vector((side * 0.03, -0.02, 0.01)), p_tr + Vector((side * 0.03, 0.02, 0.01)), 0.052, 0.052, 10, c_canvas_seam)

    # 2. Rear enclosed gable wall (y = +1.28)
    g_l = bm.verts.new((-1.14, 1.28, 0.18))
    g_r = bm.verts.new((1.14, 1.28, 0.18))
    g_top = bm.verts.new((0.0, 1.28, 2.08))
    vcols.extend([c_canvas_seam, c_canvas_seam, c_canvas])
    bm.faces.new((g_l, g_r, g_top))

    # 3. Tied-back open front door flaps on the -Y entrance (y = -1.16)
    for side in (-1.0, 1.0):
        flap_pts = [
            Vector((side * 1.14, -1.16, 0.18)),
            Vector((side * 0.72, -1.24, 0.22)),
            Vector((side * 0.54, -1.25, 0.92)),
            Vector((side * 0.02, -1.16, 2.08)),
            Vector((side * 0.58, -1.20, 1.05)),
        ]
        # Construct smooth draped open-curtain flap panel
        fv0 = bm.verts.new(flap_pts[0])
        fv1 = bm.verts.new(flap_pts[1])
        fv2 = bm.verts.new(flap_pts[2])
        fv3 = bm.verts.new(flap_pts[3])
        fv4 = bm.verts.new(flap_pts[4])
        vcols.extend([c_canvas_seam, c_canvas, c_canvas, c_canvas, c_canvas_seam])
        bm.faces.new((fv0, fv1, fv2, fv4))
        bm.faces.new((fv4, fv2, fv3))
        # Tie-back leather/canvas strap cinching flap at mid-height
        add_cylinder_to_bm(bm, vcols, (side * 0.52, -1.26, 0.92), (side * 0.72, -1.14, 0.92), 0.026, 0.026, 8, c_flap_tie)

    # 4. Overarching terracotta-rust outer rainfly with front porch canopy overhang (y=-1.44..+1.36)
    fly_y0, fly_y1 = -1.44, 1.36
    for side in (-1.0, 1.0):
        f_grid = [[None] * (nv + 1) for _ in range(nu + 1)]
        for iu in range(nu + 1):
            uy = iu / nu
            for iv in range(nv + 1):
                vh = iv / nv
                # Rainfly flares cleanly above lower side window (eave at z=0.64, x=+-1.12) & wraps smoothly around ridge
                y_f = fly_y0 + (fly_y1 - fly_y0) * uy
                eave_scallop = (1.0 - vh) * (1.0 - abs(math.cos(uy * math.pi * 2.0))) * 0.045
                x_f = side * (1.13 - 0.035 * (1.0 - vh) * math.sin(uy * math.pi * 2.0) ** 2) * (1.0 - vh)
                sag_f = 0.045 * math.sin(vh * math.pi) * (0.45 + 0.55 * math.sin(uy * math.pi))
                z_f = 0.64 + (2.11 - 0.64) * vh - sag_f + eave_scallop
                f_grid[iu][iv] = bm.verts.new((x_f, y_f, z_f))
                vcols.append(c_rainfly_trim if iv == 0 or iu in (0, nu) else c_rainfly)
        for iu in range(nu):
            for iv in range(nv):
                bm.faces.new((f_grid[iu][iv], f_grid[iu + 1][iv], f_grid[iu + 1][iv + 1], f_grid[iu][iv + 1]))

    create_mesh_with_vcol("TentCanvasBody", bm, vcols, mats["fabric"], col)


def build_interior_bedding(mats, col):
    """Build quilted interior mattress, folded blanket, coastal pillows, striped porch rug, and camp crate."""
    bm = bmesh.new()
    vcols = []

    c_mattress = hex_to_rgba("#f4efe4")
    c_mattress_tuft = hex_to_rgba("#ded5c3")
    c_blanket = hex_to_rgba("#bf4f36")
    c_blanket_fold = hex_to_rgba("#9c3c26")
    c_pillow_blue = hex_to_rgba("#246a87")
    c_pillow_cream = hex_to_rgba("#f5ebd6")
    c_rug_a = hex_to_rgba("#c97b54")
    c_rug_b = hex_to_rgba("#e8dcc6")
    c_rug_c = hex_to_rgba("#3e6d7a")
    c_crate_a = hex_to_rgba("#7a4d28")
    c_crate_b = hex_to_rgba("#613b1c")

    # 1. Quilted interior mattress (x=0.10, y=0.22, width=1.25m, length=1.88m, z=0.18..0.38)
    mx, my = 0.10, 0.22
    add_box_to_bm(bm, vcols, (mx, my, 0.27), (1.25, 1.88, 0.18), (0.0, 0.0, 0.0), c_mattress)
    # Diamond/quilted surface seam pads
    for qi in range(4):
        qy = my - 0.65 + qi * 0.44
        add_box_to_bm(bm, vcols, (mx, qy, 0.365), (1.20, 0.38, 0.024), (0.0, 0.0, 0.0), c_mattress if qi % 2 == 0 else c_mattress_tuft)

    # Terracotta folded blanket over front/foot half of mattress
    add_box_to_bm(bm, vcols, (mx, my - 0.38, 0.382), (1.28, 1.06, 0.036), (0.0, 0.0, 0.0), c_blanket)
    add_box_to_bm(bm, vcols, (mx, my + 0.14, 0.398), (1.28, 0.14, 0.024), (0.0, 0.0, 0.0), c_blanket_fold)

    # 2 coastal sleeping pillows near rear head of mattress (y = my + 0.72)
    add_uv_sphere_to_bm(bm, vcols, (mx - 0.28, my + 0.72, 0.43), 0.22, (1.15, 0.78, 0.38), 12, 8, c_pillow_blue)
    add_uv_sphere_to_bm(bm, vcols, (mx + 0.28, my + 0.72, 0.43), 0.22, (1.15, 0.78, 0.38), 12, 8, c_pillow_cream)

    # 2. Woven striped porch rug spanning interior threshold & front porch deck (y = -1.42..-0.65)
    rug_palette = [c_rug_a, c_rug_b, c_rug_c, c_rug_b, c_rug_a, c_rug_b, c_rug_c]
    n_stripes = len(rug_palette)
    for ri, rcol in enumerate(rug_palette):
        ry = -1.42 + (ri + 0.5) * (0.78 / n_stripes)
        add_box_to_bm(bm, vcols, (0.0, ry, 0.188), (1.36, 0.78 / n_stripes + 0.002, 0.016), (0.0, 0.0, 0.0), rcol)

    # 3. Slatted wooden camp crate beside interior/porch entrance (-0.78, -0.78) + rolled blanket
    cx, cy = -0.78, -0.78
    add_box_to_bm(bm, vcols, (cx, cy, 0.34), (0.44, 0.36, 0.32), (0.0, 0.0, 0.18), c_crate_b)
    for si in range(3):
        sz = 0.24 + si * 0.10
        add_box_to_bm(bm, vcols, (cx, cy, sz), (0.46, 0.38, 0.045), (0.0, 0.0, 0.18), c_crate_a)
    add_cylinder_to_bm(bm, vcols, (cx - 0.15, cy - 0.03, 0.54), (cx + 0.15, cy + 0.03, 0.54), 0.068, 0.068, 12, c_rug_c)

    create_mesh_with_vcol("TentInteriorBedding", bm, vcols, mats["fabric"], col, flat=True)


def build_porch_lantern(mats, col):
    """Build brass hurricane porch lantern at (0, -1.32, 1.80) and emissive TentLanternBulb."""
    lx, ly, lz = 0.0, -1.32, 1.80
    c_brass = hex_to_rgba("#d2a13e")
    c_brass_dark = hex_to_rgba("#8a6422")
    c_bulb = hex_to_rgba("#ffd984")

    # 1. TentLanternFrame (hanging hook + base reservoir + vented cap + 4 guard wires)
    bm_f = bmesh.new()
    f_vcols = []

    add_cylinder_to_bm(bm_f, f_vcols, (lx, ly, 2.08), (lx, ly, lz + 0.14), 0.009, 0.009, 6, c_brass_dark)
    add_cylinder_to_bm(bm_f, f_vcols, (lx, ly, lz - 0.13), (lx, ly, lz - 0.08), 0.095, 0.085, 12, c_brass)
    add_cylinder_to_bm(bm_f, f_vcols, (lx, ly, lz + 0.07), (lx, ly, lz + 0.13), 0.092, 0.045, 12, c_brass_dark)
    add_cylinder_to_bm(bm_f, f_vcols, (lx, ly, lz + 0.13), (lx, ly, lz + 0.16), 0.035, 0.025, 10, c_brass)
    for gi in range(4):
        ang = (gi / 4.0) * math.pi * 2.0 + 0.4
        gx = lx + math.cos(ang) * 0.078
        gy = ly + math.sin(ang) * 0.078
        add_cylinder_to_bm(bm_f, f_vcols, (gx, gy, lz - 0.09), (gx, gy, lz + 0.08), 0.007, 0.007, 6, c_brass_dark)

    create_mesh_with_vcol("TentLanternFrame", bm_f, f_vcols, mats["brass"], col)

    # 2. TentLanternBulb (centered at (0, -1.32, 1.80))
    bm_b = bmesh.new()
    b_vcols = []
    add_uv_sphere_to_bm(bm_b, b_vcols, (lx, ly, lz), 0.062, (1.0, 1.0, 1.25), 14, 10, c_bulb)
    create_mesh_with_vcol("TentLanternBulb", bm_b, b_vcols, mats["bulb"], col)


def setup_studio_and_viewport(studio_col):
    """Set up sunlit harbor studio lighting and framing for tent_preview.png and tent.blend."""
    world = bpy.data.worlds.new("TentStudioWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_rgba("#b9dcf2")
        bg.inputs["Strength"].default_value = 0.72

    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 3.0
    key_data.color = (1.0, 0.96, 0.88)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(48), math.radians(18), math.radians(-38))
    studio_col.objects.link(key_obj)

    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_data.energy = 240.0
    fill_data.size = 10.0
    fill_data.color = (0.86, 0.94, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    fill_obj.location = (-5.5, -5.5, 3.8)
    fill_dir = Vector((0.0, 0.0, 0.95)) - fill_obj.location
    fill_obj.rotation_mode = "QUATERNION"
    fill_obj.rotation_quaternion = fill_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(fill_obj)

    lantern_pt = bpy.data.lights.new("PorchLanternPoint", type="POINT")
    lantern_pt.energy = 45.0
    lantern_pt.color = (1.0, 0.72, 0.30)
    lantern_obj = bpy.data.objects.new("PorchLanternPoint", lantern_pt)
    lantern_obj.location = (0.0, -1.32, 1.80)
    studio_col.objects.link(lantern_obj)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 35.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (-3.6, -4.6, 2.35)
    cam_dir = Vector((0.0, -0.05, 0.95)) - cam_obj.location
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
                    space.region_3d.view_location = Vector((0.0, -0.05, 0.95))
                    space.region_3d.view_rotation = Euler((math.radians(72.0), 0.0, math.radians(-38.0)), "XYZ").to_quaternion()
                    space.region_3d.view_distance = 5.8


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    t_col = bpy.data.collections.new("Tent")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(t_col)
    bpy.context.scene.collection.children.link(studio_col)

    mats = {
        "wood": build_tent_material("TentTeakMat", roughness=0.62, bump_scale=24.0, bump_str=0.35),
        "fabric": build_tent_material("TentCanvasMat", roughness=0.80, bump_scale=38.0, bump_str=0.25, double_sided=True),
        "brass": build_tent_material("TentBrassMat", roughness=0.28, metallic=0.86, bump_scale=30.0, bump_str=0.12),
        "bulb": build_tent_material("TentBulbMat", roughness=0.20, bump_str=0.0, emission_strength=3.0),
    }

    build_deck_platform(mats, t_col)
    build_timber_frame_and_stakes(mats, t_col)
    build_canvas_body_and_rainfly(mats, t_col)
    build_interior_bedding(mats, t_col)
    build_porch_lantern(mats, t_col)
    setup_studio_and_viewport(studio_col)

    total_verts = sum(len(o.data.vertices) for o in t_col.objects if o.type == "MESH")
    total_polys = sum(len(o.data.polygons) for o in t_col.objects if o.type == "MESH")
    print(f"[Tent geometry] objects={len(t_col.objects)}, verts={total_verts}, polys={total_polys}")

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
    for obj in t_col.objects:
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
