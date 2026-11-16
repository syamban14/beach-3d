"""Generate a realistic detailed wooden sloop sailboat (sailboat.blend & sailboat.glb) in Blender 5.2."""

import math
import os
import bpy
import bmesh
from mathutils import Color, Euler, Matrix, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(BASE_DIR, "assets", "blend", "sailboat.blend")
GLB_PATH = os.path.join(BASE_DIR, "assets", "models", "sailboat.glb")
PREVIEW_PATH = "/Users/syamban/.gemini/antigravity-cli/brain/a2810c20-f453-4255-9182-bae8a0819dcc/scratch/sailboat_preview.png"

os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(PREVIEW_PATH), exist_ok=True)

# Hull cross-section control stations: (y_pos, half_beam, sheer_z, chine_x, keel_z)
HULL_STATIONS = [
    (-3.05, 0.90, 0.74, 0.22, -0.16),
    (-2.10, 1.14, 0.69, 0.26, -0.35),
    (-0.80, 1.26, 0.67, 0.28, -0.44),
    (0.60, 1.17, 0.69, 0.24, -0.42),
    (1.90, 0.86, 0.75, 0.16, -0.30),
    (2.85, 0.44, 0.88, 0.07, -0.10),
    (3.58, 0.04, 1.04, 0.00, 0.30),
]

MAST_XY = (0.0, 0.62)
MAST_BASE_Z = 0.15
MAST_TOP_Z = 7.20


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


def eval_hull_station(v_t):
    """Smoothly interpolate hull parameters for v_t in [0, 1] from stern to bow."""
    scaled = max(0.0, min(1.0, v_t)) * (len(HULL_STATIONS) - 1)
    idx = min(len(HULL_STATIONS) - 2, int(math.floor(scaled)))
    frac = scaled - idx
    frac_s = frac * frac * (3.0 - 2.0 * frac)
    a = HULL_STATIONS[idx]
    b = HULL_STATIONS[idx + 1]
    return tuple(a[k] + (b[k] - a[k]) * frac_s for k in range(5))


def hull_section_point(y_pos, half_beam, sheer_z, keel_z, t_param):
    """Evaluate 3D point on hull shell at t_param in [-1 (port), 0 (keel), +1 (starboard)]."""
    u = abs(t_param)
    x = math.copysign(half_beam * math.sin(u * math.pi * 0.5), t_param)
    z = keel_z + (sheer_z - keel_z) * (u ** 1.65)
    if u > 0.7:
        x *= 1.0 + 0.055 * (u - 0.7)
    return Vector((x, y_pos, z))


def create_mesh_with_vcol(name, bm, vert_colors, material, collection, parent=None, flat=False):
    """Finalize BMesh with active BoatColor BYTE_COLOR attribute."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    for poly in mesh.polygons:
        poly.use_smooth = not flat

    color_attr = mesh.color_attributes.new(name="BoatColor", type="BYTE_COLOR", domain="POINT")
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


def parallel_transport_tube(bm, vcols, points, radii, color, segs=10, cap_ends=True):
    """Loft a continuous twist-free tube along a 3D point list into bm."""
    rings = []
    n_pts = len(points)
    prev_tangent = None
    x_axis = None

    for i, p in enumerate(points):
        p_vec = Vector(p)
        if i == 0:
            tangent = (Vector(points[1]) - p_vec).normalized()
        elif i == n_pts - 1:
            tangent = (p_vec - Vector(points[i - 1])).normalized()
        else:
            tangent = (Vector(points[i + 1]) - Vector(points[i - 1])).normalized()

        if x_axis is None:
            ref = Vector((1.0, 0.0, 0.0)) if abs(tangent.dot(Vector((1.0, 0.0, 0.0)))) < 0.9 else Vector((0.0, 1.0, 0.0))
            x_axis = (ref - tangent * ref.dot(tangent)).normalized()
        else:
            rot_q = prev_tangent.rotation_difference(tangent)
            x_axis = rot_q @ x_axis
            x_axis = (x_axis - tangent * x_axis.dot(tangent)).normalized()
        y_axis = tangent.cross(x_axis).normalized()
        prev_tangent = tangent

        rad = radii[i] if isinstance(radii, (list, tuple)) else radii
        ring = []
        for s in range(segs):
            ang = (s / segs) * math.pi * 2.0
            offset = x_axis * (math.cos(ang) * rad) + y_axis * (math.sin(ang) * rad)
            ring.append(bm.verts.new(p_vec + offset))
            vcols.append(color)
        rings.append(ring)

    for i in range(n_pts - 1):
        r0, r1 = rings[i], rings[i + 1]
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))

    if cap_ends and n_pts >= 2:
        t0 = (Vector(points[1]) - Vector(points[0])).normalized()
        r0_val = radii[0] if isinstance(radii, (list, tuple)) else radii
        c0 = bm.verts.new(Vector(points[0]) - t0 * (r0_val * 0.25))
        vcols.append(color)
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((rings[0][sn], rings[0][s], c0))

        t1 = (Vector(points[-1]) - Vector(points[-2])).normalized()
        r1_val = radii[-1] if isinstance(radii, (list, tuple)) else radii
        c1 = bm.verts.new(Vector(points[-1]) + t1 * (r1_val * 0.25))
        vcols.append(color)
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((rings[-1][s], rings[-1][sn], c1))

    return rings


def add_box_to_bm(bm, vcols, center, size_xyz, rot_euler, color):
    """Add an oriented box with uniform vertex color into bm."""
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


def build_wood_material(name, roughness=0.55, coat=0.25, wave_dir="Y", wave_scale=12.0, bump_str=0.45):
    """Create procedural marine wood shader reading BoatColor + stretched longitudinal grain."""
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (820, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (520, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Coat Weight" in bsdf.inputs and coat > 0.0:
        bsdf.inputs["Coat Weight"].default_value = coat
        if "Coat Roughness" in bsdf.inputs:
            bsdf.inputs["Coat Roughness"].default_value = 0.14
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "BoatColor"
    vcol.location = (-520, 220)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-1040, -120)

    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.location = (-840, -120)
    # Stretch grain cleanly along hull/deck length (Y) or mast height (Z)
    mapping.inputs["Scale"].default_value = (1.0, 0.15, 1.0)
    nt.links.new(tc.outputs["Object"], mapping.inputs["Vector"])

    noise_grain = nt.nodes.new("ShaderNodeTexNoise")
    noise_grain.location = (-600, -80)
    noise_grain.inputs["Scale"].default_value = wave_scale * 2.2
    noise_grain.inputs["Detail"].default_value = 12.0
    noise_grain.inputs["Roughness"].default_value = 0.68
    noise_grain.inputs["Distortion"].default_value = 0.85
    nt.links.new(mapping.outputs["Vector"], noise_grain.inputs["Vector"])

    noise_fine = nt.nodes.new("ShaderNodeTexNoise")
    noise_fine.location = (-600, -320)
    noise_fine.inputs["Scale"].default_value = 44.0
    noise_fine.inputs["Detail"].default_value = 10.0
    noise_fine.inputs["Roughness"].default_value = 0.72
    nt.links.new(mapping.outputs["Vector"], noise_fine.inputs["Vector"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-260, 40)
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (0.76, 0.74, 0.71, 1.0)
    ramp.color_ramp.elements[1].position = 0.82
    ramp.color_ramp.elements[1].color = (1.12, 1.10, 1.06, 1.0)
    nt.links.new(noise_grain.outputs["Factor"], ramp.inputs["Factor"])

    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.location = (80, 180)
    mix.inputs["Factor"].default_value = 0.65
    nt.links.new(vcol.outputs["Color"], mix.inputs[6])
    nt.links.new(ramp.outputs["Color"], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])

    add_h = nt.nodes.new("ShaderNodeMath")
    add_h.operation = "ADD"
    add_h.location = (-220, -220)
    nt.links.new(noise_grain.outputs["Factor"], add_h.inputs[0])
    nt.links.new(noise_fine.outputs["Factor"], add_h.inputs[1])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (180, -220)
    bump.inputs["Strength"].default_value = bump_str
    bump.inputs["Distance"].default_value = 0.015
    nt.links.new(add_h.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_sail_material():
    """Build cross-woven canvas sail shader reading BoatColor with subtle SSS translucency."""
    mat = bpy.data.materials.new("SailCanvasMat")
    if mat.node_tree is None:
        mat.use_nodes = True
    mat.use_backface_culling = False
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (760, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (460, 0)
    bsdf.inputs["Roughness"].default_value = 0.62
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.08
        if "Subsurface Scale" in bsdf.inputs:
            bsdf.inputs["Subsurface Scale"].default_value = 0.02
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "BoatColor"
    vcol.location = (-240, 200)
    nt.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-860, -160)

    w_u = nt.nodes.new("ShaderNodeTexWave")
    w_u.location = (-560, -80)
    w_u.wave_type = "BANDS"
    w_u.bands_direction = "Z"
    w_u.inputs["Scale"].default_value = 46.0
    nt.links.new(tc.outputs["Object"], w_u.inputs["Vector"])

    w_v = nt.nodes.new("ShaderNodeTexWave")
    w_v.location = (-560, -300)
    w_v.wave_type = "BANDS"
    w_v.bands_direction = "Y"
    w_v.inputs["Scale"].default_value = 46.0
    nt.links.new(tc.outputs["Object"], w_v.inputs["Vector"])

    add_w = nt.nodes.new("ShaderNodeMath")
    add_w.operation = "ADD"
    add_w.location = (-240, -180)
    wu_out = w_u.outputs["Fac"] if "Fac" in w_u.outputs else w_u.outputs[0]
    wv_out = w_v.outputs["Fac"] if "Fac" in w_v.outputs else w_v.outputs[0]
    nt.links.new(wu_out, add_w.inputs[0])
    nt.links.new(wv_out, add_w.inputs[1])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (120, -180)
    bump.inputs["Strength"].default_value = 0.42
    bump.inputs["Distance"].default_value = 0.008
    nt.links.new(add_w.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_simple_vcol_material(name, roughness=0.5, metallic=0.0, bump_scale=35.0, bump_str=0.3, emission_hex=None, emission_str=0.0, double_sided=False):
    """Build compact PBR shader reading BoatColor with subtle procedural micro-texture bump."""
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    mat.use_backface_culling = not double_sided
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (560, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (260, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission_hex and "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = hex_to_rgba(emission_hex)
        bsdf.inputs["Emission Strength"].default_value = emission_str
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "BoatColor"
    vcol.location = (-220, 140)
    nt.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])

    if bump_str > 0.0:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-580, -140)
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.location = (-340, -140)
        noise.inputs["Scale"].default_value = bump_scale
        noise.inputs["Detail"].default_value = 8.0
        nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])

        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (-20, -140)
        bump.inputs["Strength"].default_value = bump_str
        bump.inputs["Distance"].default_value = 0.012
        nt.links.new(noise.outputs["Factor"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    return mat


def build_hull_and_ribs(mats, col):
    """Build planked BoatHull, BoatKeel, StemAndTransom, interior HullRibs, and GunwaleTrim."""
    # 1. Planked BoatHull (36 lengthwise stations x 33 profile vertices across strakes)
    bm_hull = bmesh.new()
    hull_vcols = []
    n_len = 36
    n_arc = 16  # 16 segments per side -> 33 verts per cross-section

    c_copper = hex_to_rgba("#7a261f")
    c_stripe = hex_to_rgba("#efe9dc")
    c_navy_a = hex_to_rgba("#122d4d")
    c_navy_b = hex_to_rgba("#193b63")
    c_mahogany = hex_to_rgba("#5e3219")

    rings = []
    for iy in range(n_len + 1):
        v_t = iy / n_len
        y_pos, half_beam, sheer_z, _, keel_z = eval_hull_station(v_t)
        ring = []
        for idx in range(n_arc * 2 + 1):
            t_p = (idx / n_arc) - 1.0
            u = abs(t_p)
            pt = hull_section_point(y_pos, half_beam, sheer_z, keel_z, t_p)

            # Carvel plank strake seam indents (8 strakes per side)
            strake_coord = u * 8.0
            strake_idx = int(math.floor(strake_coord))
            seam_dist = abs((strake_coord - strake_idx) - 0.5)
            seam_groove = math.exp(-((0.5 - seam_dist) * 18.0) ** 2) * 0.008
            if abs(pt.x) > 0.05:
                pt.x -= math.copysign(seam_groove, pt.x)

            ring.append(bm_hull.verts.new(pt))

            # Color hull by waterline height + sheer strake accent
            z = pt.z
            if z < 0.07:
                vcol = c_copper
            elif z < 0.14:
                vcol = c_stripe
            elif u > 0.87:
                vcol = c_mahogany
            else:
                vcol = c_navy_a if strake_idx % 2 == 0 else c_navy_b
            hull_vcols.append(vcol)
        rings.append(ring)

    for iy in range(n_len):
        r0, r1 = rings[iy], rings[iy + 1]
        for j in range(len(r0) - 1):
            bm_hull.faces.new((r0[j], r1[j], r1[j + 1], r0[j + 1]))

    hull_obj = create_mesh_with_vcol("BoatHull", bm_hull, hull_vcols, mats["hull"], col)
    sol = hull_obj.modifiers.new("Solidify", "SOLIDIFY")
    sol.thickness = 0.065
    sol.offset = -1.0

    # 2. Stempost & Framed Transom Stern (Mahogany)
    bm_stem = bmesh.new()
    stem_vcols = []
    # Transom stern bulkhead closing y = -3.05 cleanly
    t_ring_pts = []
    for idx in range(n_arc * 2 + 1):
        t_p = (idx / n_arc) - 1.0
        t_ring_pts.append(hull_section_point(-3.05, 0.90, 0.74, -0.16, t_p))
    stern_verts = []
    for p in t_ring_pts:
        stern_verts.append(bm_stem.verts.new(p))
        stem_vcols.append(c_mahogany if p.z > 0.14 else c_copper)
    stern_top = bm_stem.verts.new((0.0, -3.05, 0.73))
    stem_vcols.append(c_mahogany)
    for j in range(len(stern_verts) - 1):
        bm_stem.faces.new((stern_verts[j + 1], stern_verts[j], stern_top))

    # Curved bow stempost timber rising at bow
    stem_pts = [
        hull_section_point(2.75, 0.49, 0.86, -0.12, 0.0) + Vector((0, -0.02, -0.02)),
        hull_section_point(3.18, 0.25, 0.95, 0.08, 0.0),
        hull_section_point(3.58, 0.04, 1.04, 0.30, 0.0),
        Vector((0.0, 3.63, 1.09)),
    ]
    parallel_transport_tube(bm_stem, stem_vcols, stem_pts, [0.075, 0.068, 0.062, 0.052], c_mahogany, segs=8)
    create_mesh_with_vcol("StemAndTransom", bm_stem, stem_vcols, mats["mahogany"], col)

    # 3. Hydrodynamic Tapered Copper Keel Fin
    bm_keel = bmesh.new()
    keel_vcols = []
    bmesh.ops.create_cube(bm_keel, size=1.0)
    for v in bm_keel.verts:
        # Taper cleanly toward trailing edge (-Y) and bottom tip
        vy = v.co.y
        vx = v.co.x * (0.14 if vy > 0 else 0.08)
        vz = (v.co.z - 0.5) * 0.72 - 0.34
        if vz < -0.68:
            vy *= 0.74
        v.co = Vector((vx, -0.25 + vy * 2.25, vz))
        keel_vcols.append(c_copper)
    keel_obj = create_mesh_with_vcol("BoatKeel", bm_keel, keel_vcols, mats["hull"], col)
    bevel_k = keel_obj.modifiers.new("Bevel", "BEVEL")
    bevel_k.width = 0.03
    bevel_k.segments = 2

    # 4. Interior Curved Oak Hull Ribs (11 frames) + Keelson Spine
    bm_ribs = bmesh.new()
    rib_vcols = []
    c_oak = hex_to_rgba("#6e4427")

    for r_i in range(11):
        v_t = 0.08 + (r_i / 10.0) * 0.78
        y_pos, half_beam, sheer_z, _, keel_z = eval_hull_station(v_t)
        rib_pts = []
        for s_j in range(13):
            t_p = -0.96 + (s_j / 12.0) * 1.92
            pt = hull_section_point(y_pos, half_beam, sheer_z, keel_z, t_p)
            pt.x *= 0.93
            pt.z += 0.038
            rib_pts.append(pt)
        parallel_transport_tube(bm_ribs, rib_vcols, rib_pts, 0.032, c_oak, segs=6, cap_ends=False)

    # Centerline keelson spine timber inside bottom of hull
    keelson_pts = []
    for k_i in range(10):
        v_t = 0.06 + (k_i / 9.0) * 0.82
        y_pos, _, _, _, keel_z = eval_hull_station(v_t)
        keelson_pts.append(Vector((0.0, y_pos, keel_z + 0.06)))
    parallel_transport_tube(bm_ribs, rib_vcols, keelson_pts, 0.065, c_oak, segs=6)
    create_mesh_with_vcol("HullRibs", bm_ribs, rib_vcols, mats["mahogany"], col)

    # 5. Varnished Mahogany Gunwale Cap Rails
    bm_gun = bmesh.new()
    gun_vcols = []
    for side in (-1.0, 1.0):
        g_pts = []
        for iy in range(25):
            v_t = iy / 24.0
            y_pos, half_beam, sheer_z, _, keel_z = eval_hull_station(v_t)
            pt = hull_section_point(y_pos, half_beam, sheer_z, keel_z, side * 1.0)
            pt.x *= 1.01
            pt.z += 0.025
            g_pts.append(pt)
        parallel_transport_tube(bm_gun, gun_vcols, g_pts, 0.052, c_mahogany, segs=8)
    create_mesh_with_vcol("GunwaleTrim", bm_gun, gun_vcols, mats["mahogany"], col)


def build_deck_and_cockpit(mats, col):
    """Build planked Teak Foredeck/Sideways/Stern, Cockpit Coaming, Grating Floor, and Slatted Benches."""
    c_teak_a = hex_to_rgba("#ba8046")
    c_teak_b = hex_to_rgba("#cfa76e")
    c_caulk = hex_to_rgba("#241a12")
    c_mahogany = hex_to_rgba("#5e3219")

    # 1. Planked Teak Foredeck (y = +0.42..+3.55), Side Waterways, & Stern Deck
    bm_deck = bmesh.new()
    deck_vcols = []

    def add_planked_strip(bm, vcols, y0, y1, nx=14, ny=12, cut_inner_cockpit=False):
        verts = [[None] * (nx + 1) for _ in range(ny + 1)]
        for iy in range(ny + 1):
            y_cur = y0 + (y1 - y0) * (iy / ny)
            # Map y_cur to hull parameter t
            v_t = (y_cur - (-3.05)) / (3.58 - (-3.05))
            _, hb, sz, _, _ = eval_hull_station(v_t)
            for ix in range(nx + 1):
                tx = (ix / nx) * 2.0 - 1.0
                if cut_inner_cockpit:
                    # Extend flush to inner hull sheer wall (0.74..0.995*hb)
                    u_s = ix / nx
                    x_cur = cut_inner_cockpit * hb * (0.74 + u_s * 0.255)
                else:
                    x_cur = tx * hb * 0.995
                crown = 0.045 * (1.0 - (x_cur / max(0.05, hb)) ** 2)
                z_cur = sz - 0.052 + crown
                verts[iy][ix] = bm.verts.new((x_cur, y_cur, z_cur))

                # Plank color alternating with dark caulking line every ~0.11m in X
                plank_coord = (x_cur + 2.0) / 0.11
                plank_idx = int(math.floor(plank_coord))
                in_caulk = abs((plank_coord - plank_idx) - 0.5) > 0.43
                col_p = c_caulk if in_caulk else (c_teak_a if plank_idx % 2 == 0 else c_teak_b)
                vcols.append(col_p)

        for iy in range(ny):
            for ix in range(nx):
                bm.faces.new((
                    verts[iy][ix],
                    verts[iy + 1][ix],
                    verts[iy + 1][ix + 1],
                    verts[iy][ix + 1],
                ))

    add_planked_strip(bm_deck, deck_vcols, 0.40, 3.50, nx=24, ny=18, cut_inner_cockpit=False)
    add_planked_strip(bm_deck, deck_vcols, -2.76, 0.42, nx=5, ny=14, cut_inner_cockpit=-1.0)
    add_planked_strip(bm_deck, deck_vcols, -2.76, 0.42, nx=5, ny=14, cut_inner_cockpit=1.0)
    add_planked_strip(bm_deck, deck_vcols, -3.02, -2.74, nx=18, ny=4, cut_inner_cockpit=False)

    create_mesh_with_vcol("BoatDeck", bm_deck, deck_vcols, mats["teak"], col)

    # 2. Cockpit Coaming Framing the Open Cockpit Well
    bm_coam = bmesh.new()
    coam_vcols = []
    coam_pts = []
    # Forward bulkhead y = 0.40, port -> starboard -> stern -2.75 -> port
    n_c = 8
    for i in range(n_c + 1):
        u = -0.75 + (i / n_c) * 1.50
        _, hb, sz, _, _ = eval_hull_station((0.40 + 3.05) / 6.63)
        coam_pts.append((u * hb, 0.40, sz + 0.04))
    for i in range(1, 9):
        yc = 0.40 - (i / 8.0) * 3.15
        _, hb, sz, _, _ = eval_hull_station((yc + 3.05) / 6.63)
        coam_pts.append((0.75 * hb, yc, sz + 0.04))
    for i in range(1, n_c + 1):
        u = 0.75 - (i / n_c) * 1.50
        _, hb, sz, _, _ = eval_hull_station((-2.75 + 3.05) / 6.63)
        coam_pts.append((u * hb, -2.75, sz + 0.04))
    for i in range(1, 8):
        yc = -2.75 + (i / 8.0) * 3.15
        _, hb, sz, _, _ = eval_hull_station((yc + 3.05) / 6.63)
        coam_pts.append((-0.75 * hb, yc, sz + 0.04))

    for idx_c in range(len(coam_pts)):
        p0 = Vector(coam_pts[idx_c])
        p1 = Vector(coam_pts[(idx_c + 1) % len(coam_pts)])
        v0 = bm_coam.verts.new(p0 + Vector((0, 0, -0.14)))
        v1 = bm_coam.verts.new(p1 + Vector((0, 0, -0.14)))
        v2 = bm_coam.verts.new(p1 + Vector((0, 0, 0.09)))
        v3 = bm_coam.verts.new(p0 + Vector((0, 0, 0.09)))
        coam_vcols.extend([c_mahogany] * 4)
        bm_coam.faces.new((v0, v1, v2, v3))

    coam_obj = create_mesh_with_vcol("CockpitCoaming", bm_coam, coam_vcols, mats["mahogany"], col, flat=True)
    sol_c = coam_obj.modifiers.new("Solidify", "SOLIDIFY")
    sol_c.thickness = 0.045

    bm_coam_cap = bmesh.new()
    cap_vcols = []
    cap_loop = [Vector(p) + Vector((0, 0, 0.095)) for p in coam_pts] + [Vector(coam_pts[0]) + Vector((0, 0, 0.095))]
    parallel_transport_tube(bm_coam_cap, cap_vcols, cap_loop, 0.030, c_mahogany, segs=8, cap_ends=False)
    create_mesh_with_vcol("CockpitCoamingRail", bm_coam_cap, cap_vcols, mats["mahogany"], col)

    # 3. Slatted Teak Cockpit Floor Grating + Side/Cross Benches
    bm_floor = bmesh.new()
    floor_vcols = []
    for k in range(12):
        xp = -0.62 + k * 0.112
        add_box_to_bm(bm_floor, floor_vcols, (xp, -1.18, 0.14), (0.075, 2.85, 0.032), (0, 0, 0), c_teak_a if k % 2 == 0 else c_teak_b)
    for m in range(7):
        yp = -2.45 + m * 0.42
        add_box_to_bm(bm_floor, floor_vcols, (0.0, yp, 0.11), (1.28, 0.06, 0.03), (0, 0, 0), c_mahogany)
    create_mesh_with_vcol("CockpitFloor", bm_floor, floor_vcols, mats["teak"], col)

    bm_bench = bmesh.new()
    bench_vcols = []
    # Side benches with slatted planks + cross aft & fore thwarts
    for side in (-1.0, 1.0):
        for s_k in range(3):
            bx = side * (0.54 + s_k * 0.105)
            add_box_to_bm(bm_bench, bench_vcols, (bx, -1.20, 0.46), (0.088, 2.55, 0.035), (0, 0, 0), c_teak_a if s_k % 2 == 0 else c_teak_b)
        for sup_y in (-2.1, -1.2, -0.3):
            add_box_to_bm(bm_bench, bench_vcols, (side * 0.65, sup_y, 0.30), (0.06, 0.06, 0.32), (0, 0, 0), c_mahogany)

    # Stern & Fore Thwart Benches
    for yp, bw in [(-2.42, 1.38), (0.05, 1.56)]:
        for s_b in range(3):
            by_p = yp + (s_b - 1) * 0.105
            add_box_to_bm(bm_bench, bench_vcols, (0.0, by_p, 0.48), (bw, 0.088, 0.038), (0, 0, 0), c_teak_b if s_b % 2 == 0 else c_teak_a)
    create_mesh_with_vcol("CockpitBenches", bm_bench, bench_vcols, mats["mahogany"], col)


def build_mast_and_rigging(mats, col):
    """Build tapered Mast with Spreaders & Hoops, Boom, Bowsprit, Pulley Blocks, and Standing/Running Rigging."""
    c_spruce = hex_to_rgba("#9c6838")
    c_mahogany = hex_to_rgba("#5e3219")
    c_brass = hex_to_rgba("#d4a448")
    c_rope = hex_to_rgba("#c9b086")
    c_cable = hex_to_rgba("#4e5660")
    c_pennant = hex_to_rgba("#d44234")

    # 1. Mast, Spreaders (Crosstrees), Boom & Bowsprit
    bm_spars = bmesh.new()
    spar_vcols = []

    mast_pts = [Vector((MAST_XY[0], MAST_XY[1], MAST_BASE_Z + (MAST_TOP_Z - MAST_BASE_Z) * (i / 10.0))) for i in range(11)]
    mast_rads = [0.105 - 0.052 * (i / 10.0) for i in range(11)]
    parallel_transport_tube(bm_spars, spar_vcols, mast_pts, mast_rads, c_spruce, segs=14)

    # Mast deck boot collar + Crosstree spreaders at z = 4.65m
    parallel_transport_tube(
        bm_spars,
        spar_vcols,
        [Vector((0.0, 0.62, 0.66)), Vector((0.0, 0.62, 0.80))],
        [0.14, 0.125],
        c_mahogany,
        segs=14,
    )
    add_box_to_bm(bm_spars, spar_vcols, (0.0, 0.62, 4.65), (1.18, 0.075, 0.055), (0, 0, 0), c_spruce)

    # Boom from gooseneck z=1.78 to stern y=-2.60
    boom_pts = [Vector((0.0, 0.56 - (i / 8.0) * 3.16, 1.78 + (i / 8.0) * 0.12)) for i in range(9)]
    boom_rads = [0.062 - 0.016 * (i / 8.0) for i in range(9)]
    parallel_transport_tube(bm_spars, spar_vcols, boom_pts, boom_rads, c_spruce, segs=12)

    # Bowsprit extending past stem
    bow_pts = [Vector((0.0, 2.55 + (i / 6.0) * 1.68, 0.87 + (i / 6.0) * 0.44)) for i in range(7)]
    bow_rads = [0.066 - 0.026 * (i / 6.0) for i in range(7)]
    parallel_transport_tube(bm_spars, spar_vcols, bow_pts, bow_rads, c_spruce, segs=12)

    # Wind pennant flag at masthead
    add_box_to_bm(bm_spars, spar_vcols, (0.0, 0.40, 7.12), (0.012, 0.42, 0.10), (0, 0, 0), c_pennant)
    create_mesh_with_vcol("SparsAndMast", bm_spars, spar_vcols, mats["mahogany"], col)

    # 2. Mast Hoops (11 sail luff rings along mast) + Brass Gooseneck + Masthead Finial
    bm_hoops = bmesh.new()
    hoop_vcols = []
    for h_i in range(11):
        hz = 1.98 + (h_i / 10.0) * 4.42
        m_r = 0.095 - (hz - MAST_BASE_Z) / (MAST_TOP_Z - MAST_BASE_Z) * 0.045 + 0.022
        ring_pts = []
        for s_k in range(17):
            a = (s_k / 16.0) * math.pi * 2.0
            ring_pts.append(Vector((math.cos(a) * m_r, 0.62 + math.sin(a) * m_r, hz)))
        parallel_transport_tube(bm_hoops, hoop_vcols, ring_pts, 0.013, c_mahogany, segs=6, cap_ends=False)

    # Gooseneck fitting & bowsprit iron band
    add_box_to_bm(bm_hoops, hoop_vcols, (0.0, 0.56, 1.78), (0.09, 0.11, 0.08), (0, 0, 0), c_brass)
    add_box_to_bm(bm_hoops, hoop_vcols, (0.0, 3.55, 1.12), (0.14, 0.09, 0.10), (0, 0, 0), c_brass)
    create_mesh_with_vcol("MastHoops", bm_hoops, hoop_vcols, mats["brass"], col)

    # 3. Pulley Blocks (wooden shells + brass sheaves)
    bm_blocks = bmesh.new()
    block_vcols = []
    block_locs = [
        (0.0, -2.35, 1.80),    # boom mainsheet upper block
        (0.0, -2.85, 0.72),    # stern traveler block
        (-1.02, -0.35, 0.72),  # port jib sheet block
        (1.02, -0.35, 0.72),   # starboard jib sheet block
    ]
    for bx, by, bz in block_locs:
        add_box_to_bm(bm_blocks, block_vcols, (bx, by, bz), (0.055, 0.085, 0.11), (0, 0, 0), c_mahogany)
        add_box_to_bm(bm_blocks, block_vcols, (bx, by, bz), (0.064, 0.04, 0.06), (0, 0, 0), c_brass)
    create_mesh_with_vcol("PulleyBlocks", bm_blocks, block_vcols, mats["mahogany"], col)

    # 4. Standing & Running Rigging + Deck Rope Coils
    bm_rig = bmesh.new()
    rig_vcols = []

    # Forestay, Bobstay, Backstay, Upper & Lower Shrouds
    stays = [
        ([(0.0, 0.62, 6.72), (0.0, 4.18, 1.30)], 0.014, c_cable),
        ([(0.0, 4.18, 1.26), (0.0, 3.25, 0.18)], 0.013, c_cable),
        ([(0.0, 0.62, 7.05), (0.0, -3.14, 0.72)], 0.012, c_cable),
        # Port & Starboard Upper Shrouds routed cleanly over spreaders
        ([(0.0, 0.62, 6.80), (-0.58, 0.62, 4.65), (-1.14, 0.35, 0.68)], 0.012, c_cable),
        ([(0.0, 0.62, 6.80), (0.58, 0.62, 4.65), (1.14, 0.35, 0.68)], 0.012, c_cable),
        # Lower Shrouds
        ([(0.0, 0.62, 4.60), (-1.16, 0.05, 0.68)], 0.010, c_cable),
        ([(0.0, 0.62, 4.60), (1.16, 0.05, 0.68)], 0.010, c_cable),
    ]
    for pts, rad, col_r in stays:
        parallel_transport_tube(bm_rig, rig_vcols, pts, rad, col_r, segs=6)

    # Running Rigging: Mainsheet tackle + Jib sheets + Main Halyard
    parallel_transport_tube(
        bm_rig,
        rig_vcols,
        [(0.0, -2.35, 1.80), (-0.02, -2.85, 0.72), (0.02, -2.32, 1.80), (0.0, -2.85, 0.72), (0.18, -2.50, 0.56)],
        0.012,
        c_rope,
        segs=6,
    )
    # Jib sheets back to deck blocks & cleats
    for side in (-1.0, 1.0):
        parallel_transport_tube(
            bm_rig,
            rig_vcols,
            [(0.18, 0.90, 1.56), (side * 1.02, -0.35, 0.74), (side * 0.85, -0.95, 0.65)],
            0.011,
            c_rope,
            segs=6,
        )
    # Halyard running alongside mast to deck cleat
    parallel_transport_tube(
        bm_rig,
        rig_vcols,
        [(0.04, 0.55, 6.85), (0.07, 0.56, 0.78), (0.28, 0.52, 0.68)],
        0.010,
        c_rope,
        segs=6,
    )

    # Two neat hemp RopeCoils resting on deck
    for cx, cy, cz in [(0.35, 0.95, 0.65), (-0.42, -2.65, 0.69)]:
        coil_pts = []
        for s_i in range(36):
            u = s_i / 35.0
            a = u * math.pi * 6.5
            r_c = 0.08 + u * 0.14
            coil_pts.append(Vector((cx + math.cos(a) * r_c, cy + math.sin(a) * r_c, cz + (1.0 - u) * 0.02)))
        parallel_transport_tube(bm_rig, rig_vcols, coil_pts, 0.016, c_rope, segs=6)

    create_mesh_with_vcol("RiggingLines", bm_rig, rig_vcols, mats["rope"], col)


def build_sails(mats, col):
    """Build MainSail & JibSail with horizontal stitched panel seams, batten pockets, and corner patches."""
    c_canvas = hex_to_rgba("#f4ecda")
    c_canvas_warm = hex_to_rgba("#e8ddc6")
    c_seam = hex_to_rgba("#c4b69c")
    c_patch = hex_to_rgba("#d6c6a8")
    c_boltrope = hex_to_rgba("#a89572")

    # 1. MainSail (28 u-segs x 36 v-segs)
    bm_main = bmesh.new()
    main_vcols = []
    nu, nv = 26, 36
    grid_m = [[None] * (nu + 1) for _ in range(nv + 1)]

    for iv in range(nv + 1):
        v = iv / nv
        for iu in range(nu + 1):
            u = iu / nu
            foot_len = 2.82 * (1.0 - v ** 1.15)
            # Subtle graceful roach curve along leech while clearing backstay cleanly
            if 0.08 < v < 0.95:
                foot_len += math.sin(v * math.pi) * 0.08
            y = 0.54 - u * foot_len
            z = 1.88 + v * 4.92 + (1.0 - v) * 0.12 * u

            # Wind billow peaking around u=0.38
            billow = math.sin((u ** 0.78) * math.pi) * math.sin(v * math.pi * 0.92 + 0.12) * 0.36
            # Subtle horizontal panel seam ridges (9 panels) + 3 batten pockets near trailing edge
            panel_coord = v * 9.0
            panel_idx = int(math.floor(panel_coord))
            seam_prox = math.exp(-((abs(panel_coord - panel_idx - 0.5) - 0.5) * 18.0) ** 2)
            batten_bump = 0.0
            if u > 0.65:
                for bv in (0.28, 0.52, 0.76):
                    if abs(v - bv) < 0.025:
                        batten_bump = 0.015 * (1.0 - abs(v - bv) / 0.025)

            x = billow + seam_prox * 0.008 + batten_bump
            grid_m[iv][iu] = bm_main.verts.new((x, y, z))

            # Color canvas panel, stitched seam, corner reinforcement patches, & bolt rope
            col_s = c_canvas if panel_idx % 2 == 0 else c_canvas_warm
            col_s = lerp_color(col_s, c_seam, seam_prox * 0.75)
            if (u < 0.12 and v < 0.12) or (u > 0.85 and v < 0.12) or (v > 0.90):
                col_s = lerp_color(col_s, c_patch, 0.75)
            if u < 0.03 or v < 0.03:
                col_s = lerp_color(col_s, c_boltrope, 0.65)
            main_vcols.append(col_s)

    for iv in range(nv):
        for iu in range(nu):
            bm_main.faces.new((grid_m[iv][iu], grid_m[iv][iu + 1], grid_m[iv + 1][iu + 1], grid_m[iv + 1][iu]))

    create_mesh_with_vcol("MainSail", bm_main, main_vcols, mats["sail"], col)

    # 2. JibSail attached cleanly along exact Forestay line (0,4.18,1.30) -> (0,0.62,6.72)
    bm_jib = bmesh.new()
    jib_vcols = []
    ju, jv = 20, 28
    grid_j = [[None] * (ju + 1) for _ in range(jv + 1)]

    stay_bot = Vector((0.0, 4.10, 1.32))
    stay_top = Vector((0.0, 0.62, 6.68))
    clew_pt = Vector((0.0, 0.90, 1.56))

    for iv in range(jv + 1):
        v = iv / jv
        p_stay = stay_bot.lerp(stay_top, v)
        p_leech = clew_pt.lerp(stay_top, v)
        for iu in range(ju + 1):
            u = iu / ju
            pt = p_stay.lerp(p_leech, u)
            billow = math.sin((u ** 0.82) * math.pi) * math.sin(v * math.pi * 0.90 + 0.12) * 0.28 * (1.0 - v * 0.55)
            panel_coord = v * 7.0
            panel_idx = int(math.floor(panel_coord))
            seam_prox = math.exp(-((abs(panel_coord - panel_idx - 0.5) - 0.5) * 18.0) ** 2)

            grid_j[iv][iu] = bm_jib.verts.new((pt.x + billow + seam_prox * 0.006, pt.y, pt.z))

            col_s = c_canvas if panel_idx % 2 == 0 else c_canvas_warm
            col_s = lerp_color(col_s, c_seam, seam_prox * 0.75)
            if (u < 0.12 and v < 0.12) or (u > 0.82 and v < 0.14) or (v > 0.88):
                col_s = lerp_color(col_s, c_patch, 0.75)
            jib_vcols.append(col_s)

    for iv in range(jv):
        for iu in range(ju):
            bm_jib.faces.new((grid_j[iv][iu], grid_j[iv][iu + 1], grid_j[iv + 1][iu + 1], grid_j[iv + 1][iu]))

    create_mesh_with_vcol("JibSail", bm_jib, jib_vcols, mats["sail"], col)


def build_rudder_and_fittings(mats, col):
    """Build hinged Rudder (Empty at (0,-3.15,0.35)), Caged Bow Lantern, Bow Anchor, Deck Cleats, & Life Buoy."""
    c_mahogany = hex_to_rgba("#5e3219")
    c_oak = hex_to_rgba("#7a4a2a")
    c_brass = hex_to_rgba("#d4a448")
    c_iron = hex_to_rgba("#2b3038")
    c_bulb = hex_to_rgba("#ffd584")
    c_buoy_red = hex_to_rgba("#cf3b2c")
    c_buoy_white = hex_to_rgba("#f4f1ea")

    # 1. Rudder Pivot (matches scene.js getObjectByName('Rudder'))
    rudder_pivot = bpy.data.objects.new("Rudder", None)
    rudder_pivot.location = (0.0, -3.15, 0.35)
    col.objects.link(rudder_pivot)

    bm_rud = bmesh.new()
    rud_vcols = []
    # Tapered hydrofoil wooden rudder blade + S-curved tiller
    bmesh.ops.create_cube(bm_rud, size=1.0)
    for v in bm_rud.verts:
        taper_y = 0.75 if v.co.z < 0.0 else 1.0
        vx = v.co.x * (0.09 if v.co.y > 0 else 0.03)
        vy = (v.co.y - 0.5) * 0.58 * taper_y
        vz = v.co.z * 0.96 - 0.10
        v.co = Vector((vx, vy, vz))
        rud_vcols.append(c_oak if abs(vz) < 0.3 else c_mahogany)

    # S-curved tiller handle reaching over transom into cockpit
    tiller_pts = [
        Vector((0.0, 0.02, 0.42)),
        Vector((0.0, 0.35, 0.48)),
        Vector((0.0, 0.78, 0.56)),
        Vector((0.0, 1.18, 0.64)),
    ]
    parallel_transport_tube(bm_rud, rud_vcols, tiller_pts, [0.044, 0.036, 0.030, 0.038], c_mahogany, segs=10)
    create_mesh_with_vcol("RudderBladeAndTiller", bm_rud, rud_vcols, mats["mahogany"], col, parent=rudder_pivot)

    # Brass rudder pintle/gudgeon hinge straps + tiller end cap
    bm_rh = bmesh.new()
    rh_vcols = []
    for hz in (-0.18, 0.24):
        add_box_to_bm(bm_rh, rh_vcols, (0.0, -0.14, hz), (0.11, 0.34, 0.055), (0, 0, 0), c_brass)
    add_box_to_bm(bm_rh, rh_vcols, (0.0, 1.20, 0.64), (0.06, 0.08, 0.06), (0, 0, 0), c_brass)
    create_mesh_with_vcol("RudderHardware", bm_rh, rh_vcols, mats["brass"], col, parent=rudder_pivot)

    # 2. Caged Brass Bow Lantern wrapping BowLanternBulb (matches scene.js getObjectByName('BowLanternBulb'))
    bm_lframe = bmesh.new()
    lf_vcols = []
    parallel_transport_tube(
        bm_lframe,
        lf_vcols,
        [Vector((0.0, 3.05, 0.90)), Vector((0.0, 3.05, 1.32))],
        [0.042, 0.036],
        c_brass,
        segs=10,
    )
    # Lantern base cup & chimney roof cap
    add_box_to_bm(bm_lframe, lf_vcols, (0.0, 3.05, 1.33), (0.20, 0.20, 0.04), (0, 0, 0), c_brass)
    add_box_to_bm(bm_lframe, lf_vcols, (0.0, 3.05, 1.62), (0.24, 0.24, 0.045), (0, 0, 0), c_brass)
    add_box_to_bm(bm_lframe, lf_vcols, (0.0, 3.05, 1.68), (0.11, 0.11, 0.08), (0, 0, 0), c_brass)
    # 6 brass protective cage bars around glass bulb
    for c_i in range(6):
        ang = (c_i / 6.0) * math.pi * 2.0
        bx = math.cos(ang) * 0.135
        by = 3.05 + math.sin(ang) * 0.135
        parallel_transport_tube(
            bm_lframe,
            lf_vcols,
            [Vector((bx, by, 1.34)), Vector((bx, by, 1.61))],
            0.009,
            c_brass,
            segs=6,
        )
    create_mesh_with_vcol("BowLanternFrame", bm_lframe, lf_vcols, mats["brass"], col)

    bm_bulb = bmesh.new()
    bmesh.ops.create_uvsphere(bm_bulb, u_segments=14, v_segments=10, radius=0.115)
    for v in bm_bulb.verts:
        v.co += Vector((0.0, 3.05, 1.47))
    create_mesh_with_vcol("BowLanternBulb", bm_bulb, [c_bulb] * len(bm_bulb.verts), mats["bulb"], col)

    # 3. Forged Iron Bow Anchor lashed on starboard foredeck + 4 Brass Deck Cleats
    bm_iron = bmesh.new()
    iron_vcols = []
    # Anchor shank + cross stock + curved fluke arms resting at (0.28, 2.15, 0.81) tilted along deck slope
    a_origin = Vector((0.26, 2.25, 0.81))
    a_rot = Euler((0.08, -0.05, 0.35), "XYZ").to_matrix()
    def a_pt(p):
        return a_origin + a_rot @ Vector(p)

    parallel_transport_tube(bm_iron, iron_vcols, [a_pt((0, -0.28, 0)), a_pt((0, 0.34, 0))], 0.024, c_iron, segs=8)
    parallel_transport_tube(bm_iron, iron_vcols, [a_pt((-0.20, 0.28, 0)), a_pt((0.20, 0.28, 0))], 0.018, c_iron, segs=8)
    parallel_transport_tube(
        bm_iron,
        iron_vcols,
        [a_pt((-0.22, -0.14, 0.02)), a_pt((-0.11, -0.26, 0)), a_pt((0, -0.30, 0)), a_pt((0.11, -0.26, 0)), a_pt((0.22, -0.14, 0.02))],
        0.022,
        c_iron,
        segs=8,
    )
    create_mesh_with_vcol("BowAnchor", bm_iron, iron_vcols, mats["iron"], col)

    # 4 Brass Horn Cleats mounted on foredeck and cockpit gunwales
    bm_cleats = bmesh.new()
    cleat_vcols = []
    for cx, cy, cz, cyaw in [
        (-0.24, 2.65, 0.82, 0.3),
        (0.24, 2.65, 0.82, -0.3),
        (-1.12, -1.65, 0.72, 0.0),
        (1.12, -1.65, 0.72, 0.0),
    ]:
        add_box_to_bm(bm_cleats, cleat_vcols, (cx, cy, cz + 0.025), (0.04, 0.22, 0.028), (0, 0, cyaw), c_brass)
        add_box_to_bm(bm_cleats, cleat_vcols, (cx, cy, cz + 0.01), (0.035, 0.08, 0.03), (0, 0, cyaw), c_brass)
    create_mesh_with_vcol("DeckCleats", bm_cleats, cleat_vcols, mats["brass"], col)

    # 4. Red-White Quartered Life Buoy mounted on starboard coaming
    bm_buoy = bmesh.new()
    buoy_vcols = []
    R_maj, r_min = 0.27, 0.072
    segs_u, segs_v = 24, 12
    b_rot = Euler((0.15, 1.22, 0.0), "XYZ").to_matrix()
    b_center = Vector((0.98, -1.85, 0.84))
    b_rings = []
    for iu in range(segs_u):
        ang_u = (iu / segs_u) * math.pi * 2.0
        # 4 painted quadrants: red / white alternating every 90 deg
        quadrant = int((ang_u / (math.pi * 0.5)) % 4)
        col_q = c_buoy_red if quadrant % 2 == 0 else c_buoy_white
        ring = []
        for iv in range(segs_v):
            ang_v = (iv / segs_v) * math.pi * 2.0
            local_p = Vector((
                (R_maj + r_min * math.cos(ang_v)) * math.cos(ang_u),
                (R_maj + r_min * math.cos(ang_v)) * math.sin(ang_u),
                r_min * math.sin(ang_v),
            ))
            ring.append(bm_buoy.verts.new(b_center + b_rot @ local_p))
            buoy_vcols.append(col_q)
        b_rings.append(ring)
    for iu in range(segs_u):
        iun = (iu + 1) % segs_u
        for iv in range(segs_v):
            ivn = (iv + 1) % segs_v
            bm_buoy.faces.new((b_rings[iu][iv], b_rings[iun][iv], b_rings[iun][ivn], b_rings[iu][ivn]))
    create_mesh_with_vcol("LifeBuoy", bm_buoy, buoy_vcols, mats["hull"], col)


def setup_studio_and_viewport(studio_col):
    """Set up natural sunlit harbor lighting, camera framing full boat & rigging, and Material Preview."""
    world = bpy.data.worlds.new("SailboatStudioWorld")
    bpy.context.scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_rgba("#c6e4f7")
        bg.inputs["Strength"].default_value = 0.70

    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 3.2
    key_data.color = (1.0, 0.96, 0.88)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(48), math.radians(16), math.radians(-42))
    studio_col.objects.link(key_obj)

    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_data.energy = 260.0
    fill_data.size = 10.0
    fill_data.color = (0.84, 0.93, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    fill_obj.location = (-7.5, -5.5, 4.5)
    fill_dir = Vector((0.0, 0.3, 2.5)) - fill_obj.location
    fill_obj.rotation_mode = "QUATERNION"
    fill_obj.rotation_quaternion = fill_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(fill_obj)

    rim_data = bpy.data.lights.new("RimLight", type="AREA")
    rim_data.energy = 300.0
    rim_data.size = 8.0
    rim_data.color = (1.0, 0.92, 0.80)
    rim_obj = bpy.data.objects.new("RimLight", rim_data)
    rim_obj.location = (6.5, 6.5, 5.5)
    rim_dir = Vector((0.0, 0.3, 2.8)) - rim_obj.location
    rim_obj.rotation_mode = "QUATERNION"
    rim_obj.rotation_quaternion = rim_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(rim_obj)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 35.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (-7.8, -6.8, 3.6)
    cam_dir = Vector((0.0, 0.15, 2.7)) - cam_obj.location
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
                    space.region_3d.view_location = Vector((0.0, 0.35, 2.4))
                    space.region_3d.view_rotation = Euler((math.radians(72.0), 0.0, math.radians(-42.0)), "XYZ").to_quaternion()
                    space.region_3d.view_distance = 10.5


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    boat_col = bpy.data.collections.new("Sailboat")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(boat_col)
    bpy.context.scene.collection.children.link(studio_col)

    mats = {
        "hull": build_wood_material("HullWoodMat", roughness=0.30, coat=0.45, wave_dir="Y", wave_scale=9.0, bump_str=0.32),
        "teak": build_wood_material("TeakDeckMat", roughness=0.68, coat=0.05, wave_dir="X", wave_scale=18.0, bump_str=0.52),
        "mahogany": build_wood_material("MahoganyMat", roughness=0.38, coat=0.32, wave_dir="Y", wave_scale=14.0, bump_str=0.45),
        "sail": build_sail_material(),
        "rope": build_simple_vcol_material("RopeHempMat", roughness=0.88, bump_scale=55.0, bump_str=0.60),
        "brass": build_simple_vcol_material("BrassMat", roughness=0.26, metallic=0.88, bump_scale=30.0, bump_str=0.15),
        "iron": build_simple_vcol_material("IronMat", roughness=0.52, metallic=0.82, bump_scale=42.0, bump_str=0.45),
        "bulb": build_simple_vcol_material("BowBulbMat", roughness=0.20, bump_str=0.0, emission_hex="#ff9d2e", emission_str=2.4),
    }

    build_hull_and_ribs(mats, boat_col)
    build_deck_and_cockpit(mats, boat_col)
    build_mast_and_rigging(mats, boat_col)
    build_sails(mats, boat_col)
    build_rudder_and_fittings(mats, boat_col)

    setup_studio_and_viewport(studio_col)

    total_verts = sum(len(o.data.vertices) for o in boat_col.objects if o.type == "MESH")
    total_polys = sum(len(o.data.polygons) for o in boat_col.objects if o.type == "MESH")
    print(f"[Sailboat geometry] objects={len(boat_col.objects)}, verts={total_verts}, polys={total_polys}")

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[Saved] {BLEND_PATH}")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 1080
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True)
    print(f"[Rendered preview] {PREVIEW_PATH}")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in boat_col.objects:
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
