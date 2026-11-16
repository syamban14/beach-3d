"""Generate a realistic fractured coastal rock cluster asset (rock_cluster.blend & rock_cluster.glb) in Blender 5.2."""

import math
import os
import random
import bpy
import bmesh
from mathutils import Color, Euler, Matrix, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(BASE_DIR, "assets", "blend", "rock_cluster.blend")
GLB_PATH = os.path.join(BASE_DIR, "assets", "models", "rock_cluster.glb")
PREVIEW_PATH = "/Users/syamban/.gemini/antigravity-cli/brain/a2810c20-f453-4255-9182-bae8a0819dcc/scratch/rock_cluster_preview.png"

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


def create_mesh_with_vcol(name, bm, vert_colors, material, collection, split_angle_deg=24.0):
    """Finalize BMesh with RockColor active attribute and optional sharp facet edge split."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    for poly in mesh.polygons:
        poly.use_smooth = True

    color_attr = mesh.color_attributes.new(name="RockColor", type="BYTE_COLOR", domain="POINT")
    mesh.color_attributes.active_color = color_attr
    for idx, rgba in enumerate(vert_colors):
        if idx < len(color_attr.data):
            color_attr.data[idx].color = rgba

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    if split_angle_deg is not None:
        es = obj.modifiers.new("CrispFacets", "EDGE_SPLIT")
        es.split_angle = math.radians(split_angle_deg)
    return obj


def build_rock_material():
    """Build CoastalRockMat reading RockColor + Voronoi/Noise/Wave bump + wet-base roughness gradient."""
    mat = bpy.data.materials.new("CoastalRockMat")
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out_node = nt.nodes.new("ShaderNodeOutputMaterial")
    out_node.location = (960, 0)

    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (660, 0)
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.55
    nt.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "RockColor"
    vcol.location = (-620, 260)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-960, -140)

    noise_med = nt.nodes.new("ShaderNodeTexNoise")
    noise_med.location = (-680, -340)
    noise_med.inputs["Scale"].default_value = 9.0
    noise_med.inputs["Detail"].default_value = 14.0
    noise_med.inputs["Roughness"].default_value = 0.82
    noise_med.inputs["Distortion"].default_value = 0.65
    nt.links.new(tc.outputs["Object"], noise_med.inputs["Vector"])

    # Domain-warp Voronoi coordinates using noise_med.Color so cracks twist organically instead of polygon cells
    warp_scale = nt.nodes.new("ShaderNodeVectorMath")
    warp_scale.operation = "SCALE"
    warp_scale.location = (-840, -180)
    warp_scale.inputs["Scale"].default_value = 0.42
    nt.links.new(noise_med.outputs["Color"], warp_scale.inputs[0])

    warp_add = nt.nodes.new("ShaderNodeVectorMath")
    warp_add.operation = "ADD"
    warp_add.location = (-740, -140)
    nt.links.new(tc.outputs["Object"], warp_add.inputs[0])
    nt.links.new(warp_scale.outputs["Vector"], warp_add.inputs[1])

    voronoi = nt.nodes.new("ShaderNodeTexVoronoi")
    voronoi.location = (-560, -40)
    voronoi.feature = "F1"
    voronoi.inputs["Scale"].default_value = 16.0
    nt.links.new(warp_add.outputs["Vector"], voronoi.inputs["Vector"])

    vor_cracks = nt.nodes.new("ShaderNodeTexVoronoi")
    vor_cracks.location = (-560, -180)
    vor_cracks.feature = "DISTANCE_TO_EDGE"
    vor_cracks.inputs["Scale"].default_value = 3.2
    nt.links.new(warp_add.outputs["Vector"], vor_cracks.inputs["Vector"])

    noise_fine = nt.nodes.new("ShaderNodeTexNoise")
    noise_fine.location = (-680, -520)
    noise_fine.inputs["Scale"].default_value = 46.0
    noise_fine.inputs["Detail"].default_value = 15.0
    noise_fine.inputs["Roughness"].default_value = 0.86
    nt.links.new(tc.outputs["Object"], noise_fine.inputs["Vector"])

    wave_strata = nt.nodes.new("ShaderNodeTexWave")
    wave_strata.location = (-680, -700)
    wave_strata.wave_type = "BANDS"
    wave_strata.bands_direction = "DIAGONAL"
    wave_strata.wave_profile = "SAW"
    wave_strata.inputs["Scale"].default_value = 5.2
    wave_strata.inputs["Distortion"].default_value = 5.8
    wave_strata.inputs["Detail"].default_value = 10.0
    nt.links.new(tc.outputs["Object"], wave_strata.inputs["Vector"])

    # Sharpen warped Voronoi fracture crack seams into natural irregular hairline cracks
    crack_ramp = nt.nodes.new("ShaderNodeValToRGB")
    crack_ramp.location = (-360, -160)
    crack_ramp.color_ramp.elements[0].position = 0.0
    crack_ramp.color_ramp.elements[0].color = (0.25, 0.25, 0.25, 1.0)
    crack_ramp.color_ramp.elements[1].position = 0.09
    crack_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(vor_cracks.outputs["Distance"], crack_ramp.inputs["Factor"])

    # Modulate vertex color with granite speckles + subtle crack darkening
    mix_noise_col = nt.nodes.new("ShaderNodeMix")
    mix_noise_col.data_type = "FLOAT"
    mix_noise_col.location = (-400, 20)
    mix_noise_col.inputs[0].default_value = 0.40
    nt.links.new(noise_med.outputs["Factor"], mix_noise_col.inputs[2])
    nt.links.new(voronoi.outputs["Distance"], mix_noise_col.inputs[3])

    speckle_ramp = nt.nodes.new("ShaderNodeValToRGB")
    speckle_ramp.location = (-180, 60)
    speckle_ramp.color_ramp.elements[0].position = 0.22
    speckle_ramp.color_ramp.elements[0].color = (0.58, 0.56, 0.54, 1.0)
    speckle_ramp.color_ramp.elements[1].position = 0.80
    speckle_ramp.color_ramp.elements[1].color = (1.14, 1.12, 1.08, 1.0)
    nt.links.new(mix_noise_col.outputs[0], speckle_ramp.inputs["Factor"])

    mix_cracks = nt.nodes.new("ShaderNodeMix")
    mix_cracks.data_type = "RGBA"
    mix_cracks.blend_type = "MULTIPLY"
    mix_cracks.location = (20, 140)
    mix_cracks.inputs["Factor"].default_value = 0.32
    nt.links.new(speckle_ramp.outputs["Color"], mix_cracks.inputs[6])
    nt.links.new(crack_ramp.outputs["Color"], mix_cracks.inputs[7])

    mix_base = nt.nodes.new("ShaderNodeMix")
    mix_base.data_type = "RGBA"
    mix_base.blend_type = "MULTIPLY"
    mix_base.location = (220, 220)
    mix_base.inputs["Factor"].default_value = 0.85
    nt.links.new(vcol.outputs["Color"], mix_base.inputs[6])
    nt.links.new(mix_cracks.outputs[2], mix_base.inputs[7])
    nt.links.new(mix_base.outputs[2], bsdf.inputs["Base Color"])

    # Combine Voronoi fractures + Noise + Strata Wave -> strong crisp rock Bump Normal
    mul_v = nt.nodes.new("ShaderNodeMath")
    mul_v.operation = "MULTIPLY"
    mul_v.location = (-420, -280)
    mul_v.inputs[1].default_value = 0.22
    nt.links.new(crack_ramp.outputs["Color"], mul_v.inputs[0])

    mul_m = nt.nodes.new("ShaderNodeMath")
    mul_m.operation = "MULTIPLY"
    mul_m.location = (-420, -400)
    mul_m.inputs[1].default_value = 0.45
    nt.links.new(noise_med.outputs["Factor"], mul_m.inputs[0])

    mul_f = nt.nodes.new("ShaderNodeMath")
    mul_f.operation = "MULTIPLY"
    mul_f.location = (-420, -520)
    mul_f.inputs[1].default_value = 0.38
    nt.links.new(noise_fine.outputs["Factor"], mul_f.inputs[0])

    mul_w = nt.nodes.new("ShaderNodeMath")
    mul_w.operation = "MULTIPLY"
    mul_w.location = (-420, -640)
    mul_w.inputs[1].default_value = 0.28
    wave_out = wave_strata.outputs["Fac"] if "Fac" in wave_strata.outputs else wave_strata.outputs[0]
    nt.links.new(wave_out, mul_w.inputs[0])

    add_1 = nt.nodes.new("ShaderNodeMath")
    add_1.operation = "ADD"
    add_1.location = (-200, -340)
    nt.links.new(mul_v.outputs["Value"], add_1.inputs[0])
    nt.links.new(mul_m.outputs["Value"], add_1.inputs[1])

    add_2 = nt.nodes.new("ShaderNodeMath")
    add_2.operation = "ADD"
    add_2.location = (-200, -580)
    nt.links.new(mul_f.outputs["Value"], add_2.inputs[0])
    nt.links.new(mul_w.outputs["Value"], add_2.inputs[1])

    add_all = nt.nodes.new("ShaderNodeMath")
    add_all.operation = "ADD"
    add_all.location = (10, -460)
    nt.links.new(add_1.outputs["Value"], add_all.inputs[0])
    nt.links.new(add_2.outputs["Value"], add_all.inputs[1])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (280, -340)
    bump.inputs["Strength"].default_value = 0.92
    bump.inputs["Distance"].default_value = 0.085
    nt.links.new(add_all.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    # Height-driven Roughness: glossy wet base (0.16 below z=0.14m) -> dry matte rock (0.88 above z=0.28m)
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    geom.location = (-680, 460)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-460, 460)
    nt.links.new(geom.outputs["Position"], sep.inputs["Vector"])

    z_sub = nt.nodes.new("ShaderNodeMath")
    z_sub.operation = "SUBTRACT"
    z_sub.location = (-260, 460)
    z_sub.inputs[1].default_value = 0.04
    nt.links.new(sep.outputs["Z"], z_sub.inputs[0])

    z_scale = nt.nodes.new("ShaderNodeMath")
    z_scale.operation = "MULTIPLY"
    z_scale.use_clamp = True
    z_scale.location = (-60, 460)
    z_scale.inputs[1].default_value = 4.15
    nt.links.new(z_sub.outputs["Value"], z_scale.inputs[0])

    rough_ramp = nt.nodes.new("ShaderNodeValToRGB")
    rough_ramp.location = (180, 460)
    rough_ramp.color_ramp.elements[0].position = 0.0
    rough_ramp.color_ramp.elements[0].color = (0.16, 0.16, 0.16, 1.0)
    rough_ramp.color_ramp.elements[1].position = 1.0
    rough_ramp.color_ramp.elements[1].color = (0.88, 0.88, 0.88, 1.0)
    nt.links.new(z_scale.outputs["Value"], rough_ramp.inputs["Factor"])
    nt.links.new(rough_ramp.outputs["Color"], bsdf.inputs["Roughness"])

    return mat


def build_barnacle_material():
    """Build chalky calcareous barnacle shell material reading RockColor."""
    mat = bpy.data.materials.new("CoastalBarnacleMat")
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out_node = nt.nodes.new("ShaderNodeOutputMaterial")
    out_node.location = (520, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (220, 0)
    bsdf.inputs["Roughness"].default_value = 0.78
    nt.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "RockColor"
    vcol.location = (-260, 120)
    nt.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-520, -140)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-280, -140)
    noise.inputs["Scale"].default_value = 45.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-20, -140)
    bump.inputs["Strength"].default_value = 0.55
    bump.inputs["Distance"].default_value = 0.015
    nt.links.new(noise.outputs["Factor"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def sculpt_faceted_rock_bmesh(bm, center, radius, scale_xyz, rot_euler, subdivisions, seed, is_pebble=False):
    """Sculpt a faceted rocky crag with fracture planes, strata ledges, V-fissures, and multi-zone vertex colors."""
    rng = random.Random(seed)
    local_bm = bmesh.new()
    bmesh.ops.create_icosphere(local_bm, subdivisions=subdivisions, radius=1.0)

    # Generate 16 fracture cut planes for crisp rocky facets instead of smooth ellipsoids
    n_planes = 12 if is_pebble else 16
    planes = []
    for i in range(n_planes):
        ang_z = (i / n_planes) * math.pi * 2.0 + rng.uniform(-0.35, 0.35)
        tilt = rng.uniform(-0.85, 0.85)
        nx = math.cos(ang_z) * math.cos(tilt)
        ny = math.sin(ang_z) * math.cos(tilt)
        nz = math.sin(tilt)
        n_vec = Vector((nx, ny, nz)).normalized()
        dist = rng.uniform(0.70, 0.94)
        planes.append((n_vec, dist))

    # Add 2 bottom/top fracture planes for flat/angular cliff silhouette
    planes.append((Vector((0.0, 0.0, 1.0)), rng.uniform(0.76, 0.90)))
    planes.append((Vector((0.15, -0.1, -1.0)).normalized(), 0.72))

    # Tilted sedimentary strata axis
    strata_axis = Vector((rng.uniform(-0.32, 0.32), rng.uniform(-0.32, 0.32), 1.0)).normalized()
    strata_freq = rng.uniform(5.5, 8.2) if not is_pebble else 4.0

    # 2-3 deep V-fissure crack planes
    fissures = []
    for _ in range(1 if is_pebble else 3):
        fn = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.45, 0.45))).normalized()
        foff = rng.uniform(-0.28, 0.28)
        fwidth = rng.uniform(0.055, 0.095)
        fdepth = rng.uniform(0.14, 0.24)
        fissures.append((fn, foff, fwidth, fdepth))

    rot_m = Euler(rot_euler, "XYZ").to_matrix()

    # Palette colors in scene-linear space
    c_wet_dark = hex_to_rgba("#1c2226")
    c_wet_mid = hex_to_rgba("#2b333a")
    c_moss_dark = hex_to_rgba("#2b4a1f")
    c_moss_light = hex_to_rgba("#466327")
    c_rock_a = hex_to_rgba("#4c5258")
    c_rock_b = hex_to_rgba("#635c53")
    c_rock_c = hex_to_rgba("#756c60")
    c_fissure_dark = hex_to_rgba("#25282c")
    c_ridge_light = hex_to_rgba("#8d867c")
    c_sun_peak = hex_to_rgba("#a49d92")

    out_colors = []
    tidal_samples = []  # store (world_pos, outward_normal) for barnacle placement

    for v in local_bm.verts:
        d = v.co.normalized()

        # Find two tightest intersecting fracture planes -> creates planar faces & sharp edges
        r1 = 1.6
        r2 = 1.6
        for p_n, p_d in planes:
            dot = d.dot(p_n)
            if dot > 0.12:
                r_hit = p_d / dot
                if r_hit < r1:
                    r2 = r1
                    r1 = r_hit
                elif r_hit < r2:
                    r2 = r_hit

        r_base = min(1.08, r1)
        ridge_factor = max(0.0, min(1.0, 1.0 - (r2 - r1) / 0.14))

        # Sawtooth strata ledges & sharper rock fracture displacement
        s_coord = d.dot(strata_axis) * strata_freq + 0.45 * math.sin(d.x * 3.6 + seed)
        s_phase = s_coord - math.floor(s_coord)
        strata_step = (0.088 if not is_pebble else 0.035) * (s_phase - 0.5)

        # Carve V-fissure cracks
        crevice_factor = 0.0
        for fn, foff, fwidth, fdepth in fissures:
            dist_f = abs(d.dot(fn) - foff)
            if dist_f < fwidth:
                c_amt = (1.0 - dist_f / fwidth) ** 1.25
                crevice_factor = max(crevice_factor, c_amt)
        crack_drop = crevice_factor * (0.26 if not is_pebble else 0.11)

        # Coarse + fine surface fracture roughness
        micro_rock = (
            math.sin(d.x * 9.5 + seed) * math.cos(d.y * 8.4 - seed) * 0.055
            + math.cos(d.z * 14.5 + d.x * 7.2 + seed * 1.7) * 0.036
            + math.sin(d.y * 22.0 - d.z * 19.0) * 0.022
        )

        r_eff = radius * max(0.38, r_base + strata_step - crack_drop + micro_rock)
        local_p = Vector((
            d.x * r_eff * scale_xyz[0],
            d.y * r_eff * scale_xyz[1],
            d.z * r_eff * scale_xyz[2],
        ))

        world_p = center + (rot_m @ local_p)
        # Flatten & embed base cleanly below sand line
        if world_p.z < -0.10:
            world_p.z = -0.10 + (world_p.z + 0.10) * 0.22
            world_p.x += (world_p.x - center.x) * 0.08
            world_p.y += (world_p.y - center.y) * 0.08

        v.co = world_p

        # Compute multi-zone vertex coloration based on height, crevices, ridges, and moss
        z = world_p.z
        slope_up = d.dot(Vector((0.0, 0.0, 1.0)))
        rock_tone = 0.5 + 0.5 * math.sin(world_p.x * 2.3 - world_p.y * 1.9 + world_p.z * 3.4 + seed)
        base_col = lerp_color(c_rock_a, c_rock_b, rock_tone)
        if z > 0.45:
            base_col = lerp_color(base_col, c_rock_c, min(1.0, (z - 0.45) / 0.55))

        # Highlight bleached sharp cliff ridges & peaks
        base_col = lerp_color(base_col, c_ridge_light, ridge_factor * 0.55)
        if z > 0.72:
            base_col = lerp_color(base_col, c_sun_peak, min(1.0, (z - 0.72) / 0.45) * 0.65)

        # Darken fissure crevices deeply
        base_col = lerp_color(base_col, c_fissure_dark, crevice_factor * 0.85)

        # Tidal moss belt on upward/ledge faces & crevices (z in 0.04 .. 0.42m)
        if not is_pebble and 0.03 < z < 0.44:
            moss_band = math.sin(((z - 0.03) / 0.41) * math.pi)
            moss_patch = 0.5 + 0.5 * math.sin(world_p.x * 4.8 + world_p.y * 5.2 + seed)
            moss_weight = max(0.0, min(1.0, moss_band * (0.45 * crevice_factor + 0.55 * max(0.0, slope_up + 0.25)) * (0.55 + 0.7 * moss_patch)))
            moss_col = lerp_color(c_moss_dark, c_moss_light, moss_patch)
            base_col = lerp_color(base_col, moss_col, min(0.88, moss_weight * 0.95))

        # Wet basalt darkening near tidal base (z < 0.20m)
        if z < 0.22:
            wet_t = max(0.0, min(1.0, (0.22 - z) / 0.24))
            wet_col = lerp_color(c_wet_mid, c_wet_dark, max(0.0, min(1.0, (0.12 - z) / 0.16)))
            base_col = lerp_color(base_col, wet_col, wet_t * 0.90)

        out_colors.append(base_col)

        if not is_pebble and 0.05 <= z <= 0.26 and crevice_factor < 0.45 and slope_up > -0.25:
            out_dir = (rot_m @ d).normalized()
            tidal_samples.append((world_p.copy(), out_dir))

    # Transfer local_bm geometry into destination bm
    vert_map = {}
    for v in local_bm.verts:
        nv = bm.verts.new(v.co)
        vert_map[v] = nv
    for f in local_bm.faces:
        bm.faces.new([vert_map[v] for v in f.verts])
    local_bm.free()

    return out_colors, tidal_samples


def build_barnacle_mesh(mats, rock_col, sample_sites):
    """Build tiny dense muted calcareous barnacle encrustations seated flush on lower tidal rock faces."""
    rng = random.Random(303)
    bm = bmesh.new()
    vcols = []

    c_shell_outer = hex_to_rgba("#6c695f")
    c_shell_rim = hex_to_rgba("#8a8579")
    c_aperture = hex_to_rgba("#24221d")

    rng.shuffle(sample_sites)
    # Tightly clustered colonies strictly near wet lower waterline
    centers = []
    for pos, normal in sample_sites:
        if pos.z > 0.19:
            continue
        if len(centers) >= 16:
            break
        if all((pos - c[0]).length > 0.22 for c in centers):
            centers.append((pos, normal))

    for c_pos, c_norm in centers:
        up_q = c_norm.to_track_quat("Z", "Y").to_matrix()
        tangent_u = up_q @ Vector((1.0, 0.0, 0.0))
        tangent_v = up_q @ Vector((0.0, 1.0, 0.0))

        # 7-11 tiny tight-packed shells seated deep onto local facet without overhanging corners
        for k in range(rng.randint(7, 11)):
            off_u = rng.uniform(-0.028, 0.028)
            off_v = rng.uniform(-0.028, 0.028)
            b_pos = c_pos + tangent_u * off_u + tangent_v * off_v - c_norm * 0.014
            r_base = rng.uniform(0.009, 0.017)
            r_top = r_base * rng.uniform(0.45, 0.56)
            r_hole = r_top * 0.52
            h = rng.uniform(0.007, 0.014)

            segs = 7
            ring_bot = []
            ring_top = []
            ring_in = []
            for s in range(segs):
                ang = (s / segs) * math.pi * 2.0
                flute = 1.0 + 0.14 * math.cos(ang * 5.0)
                ca, sa = math.cos(ang), math.sin(ang)
                radial = tangent_u * ca + tangent_v * sa

                ring_bot.append(bm.verts.new(b_pos + radial * (r_base * flute)))
                vcols.append(c_shell_outer)

                ring_top.append(bm.verts.new(b_pos + c_norm * h + radial * (r_top * flute)))
                vcols.append(c_shell_rim)

                ring_in.append(bm.verts.new(b_pos + c_norm * (h * 0.55) + radial * r_hole))
                vcols.append(c_aperture)

            center_hole = bm.verts.new(b_pos + c_norm * (h * 0.45))
            vcols.append(c_aperture)

            for s in range(segs):
                sn = (s + 1) % segs
                bm.faces.new((ring_bot[s], ring_bot[sn], ring_top[sn], ring_top[s]))
                bm.faces.new((ring_top[s], ring_top[sn], ring_in[sn], ring_in[s]))
                bm.faces.new((ring_in[s], ring_in[sn], center_hole))

    return create_mesh_with_vcol("BarnacleClusters", bm, vcols, mats["barnacle"], rock_col, split_angle_deg=None)


def build_rock_cluster_meshes(mats, rock_col):
    """Build 3 major crags, 4 interlocking outcrops, 18 coastal pebbles, and tidal barnacles."""
    tidal_samples_all = []

    # 3 Principal Crags matching cohesive natural cliff outcrop silhouette
    crags = [
        ("RockCrag_Main", Vector((0.0, 0.0, 0.44)), 1.08, (1.22, 0.96, 0.92), (0.08, -0.12, 0.25), 4, 11),
        ("RockCrag_West", Vector((-1.05, 0.42, 0.26)), 0.74, (1.14, 0.88, 0.78), (-0.14, 0.18, 1.42), 4, 23),
        ("RockCrag_East", Vector((0.86, -0.56, 0.22)), 0.62, (0.98, 1.16, 0.74), (0.16, 0.10, 2.58), 4, 37),
    ]
    for name, loc, rad, scl, rot, subdiv, seed in crags:
        bm = bmesh.new()
        vcols, samples = sculpt_faceted_rock_bmesh(bm, Vector((0, 0, 0)), rad, scl, rot, subdiv, seed, is_pebble=False)
        # Shift verts cleanly to final cluster world position so vertex color heights align with z=0 waterline
        shift = loc
        for v in bm.verts:
            v.co += shift
            if v.co.z < -0.14:
                v.co.z = -0.14 + (v.co.z + 0.14) * 0.20
        # Re-evaluate world-height wet zone cleanly after world offset
        c_wet_dark = hex_to_rgba("#1c2226")
        c_wet_mid = hex_to_rgba("#2b333a")
        c_moss = hex_to_rgba("#385823")
        for idx, v in enumerate(bm.verts):
            wz = v.co.z
            col = vcols[idx]
            if 0.04 < wz < 0.36 and v.co.z < loc.z:
                m_amt = math.sin(((wz - 0.04) / 0.32) * math.pi) * 0.35
                col = lerp_color(col, c_moss, m_amt)
            if wz < 0.20:
                wet_t = max(0.0, min(1.0, (0.20 - wz) / 0.22))
                w_col = lerp_color(c_wet_mid, c_wet_dark, max(0.0, min(1.0, (0.10 - wz) / 0.15)))
                col = lerp_color(col, w_col, wet_t * 0.85)
            vcols[idx] = col

        for s_pos, s_norm in samples:
            w_pos = s_pos + shift
            if 0.04 <= w_pos.z <= 0.26:
                tidal_samples_all.append((w_pos, s_norm))

        create_mesh_with_vcol(name, bm, vcols, mats["rock"], rock_col)

    # 4 Medium Outcrops wedged at crag junctions
    outcrops = [
        ("RockOutcrop_0", Vector((-0.56, -0.78, 0.12)), 0.44, (1.12, 0.90, 0.68), (0.2, -0.1, 0.8), 51),
        ("RockOutcrop_1", Vector((0.62, 0.68, 0.14)), 0.46, (0.95, 1.15, 0.72), (-0.15, 0.22, 1.9), 67),
        ("RockOutcrop_2", Vector((-1.42, -0.24, 0.08)), 0.36, (1.08, 0.86, 0.65), (0.1, 0.2, 3.1), 83),
        ("RockOutcrop_3", Vector((1.22, 0.08, 0.10)), 0.38, (1.15, 0.92, 0.64), (-0.2, -0.1, 4.4), 97),
    ]
    for name, loc, rad, scl, rot, seed in outcrops:
        bm = bmesh.new()
        vcols, samples = sculpt_faceted_rock_bmesh(bm, loc, rad, scl, rot, subdivisions=3, seed=seed, is_pebble=False)
        tidal_samples_all.extend(samples)
        create_mesh_with_vcol(name, bm, vcols, mats["rock"], rock_col)

    # 18 Coastal Pebbles & Broken Shards nestled close around crag & outcrop bases
    rng = random.Random(512)
    bm_peb = bmesh.new()
    peb_vcols = []
    for p_idx in range(18):
        ang = (p_idx / 18.0) * math.pi * 2.0 + rng.uniform(-0.28, 0.28)
        dist = rng.uniform(0.75, 1.48)
        px = math.cos(ang) * dist
        py = math.sin(ang) * dist * 0.85
        pz = rng.uniform(-0.02, 0.02)
        prad = rng.uniform(0.065, 0.165)
        pscl = (rng.uniform(0.95, 1.42), rng.uniform(0.75, 1.15), rng.uniform(0.42, 0.72))
        prot = (rng.uniform(-0.35, 0.35), rng.uniform(-0.35, 0.35), rng.uniform(0, 6.28))

        cols, _ = sculpt_faceted_rock_bmesh(
            bm_peb,
            Vector((px, py, pz)),
            prad,
            pscl,
            prot,
            subdivisions=2,
            seed=200 + p_idx,
            is_pebble=True,
        )
        peb_vcols.extend(cols)

    create_mesh_with_vcol("CoastalPebbles", bm_peb, peb_vcols, mats["rock"], rock_col)

    # Barnacles clinging onto tidal zone rocks
    if tidal_samples_all:
        build_barnacle_mesh(mats, rock_col, tidal_samples_all)


def setup_studio_and_viewport(studio_col):
    """Set up natural sunlit sky, fill/rim lights, close preview camera, and Material Preview viewport."""
    world = bpy.data.worlds.new("RockStudioWorld")
    bpy.context.scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_rgba("#cde2f2")
        bg.inputs["Strength"].default_value = 0.65

    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 3.4
    key_data.color = (1.0, 0.96, 0.88)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(46), math.radians(18), math.radians(-42))
    studio_col.objects.link(key_obj)

    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_data.energy = 85.0
    fill_data.size = 4.5
    fill_data.color = (0.82, 0.92, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    fill_obj.location = (3.2, -3.5, 2.5)
    fill_dir = Vector((0.0, 0.0, 0.35)) - fill_obj.location
    fill_obj.rotation_mode = "QUATERNION"
    fill_obj.rotation_quaternion = fill_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(fill_obj)

    rim_data = bpy.data.lights.new("RimLight", type="AREA")
    rim_data.energy = 115.0
    rim_data.size = 4.0
    rim_data.color = (1.0, 0.92, 0.80)
    rim_obj = bpy.data.objects.new("RimLight", rim_data)
    rim_obj.location = (-2.8, 3.5, 3.0)
    rim_dir = Vector((0.0, 0.0, 0.4)) - rim_obj.location
    rim_obj.rotation_mode = "QUATERNION"
    rim_obj.rotation_quaternion = rim_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(rim_obj)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 42.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (-2.15, -3.65, 1.95)
    cam_dir = Vector((-0.05, 0.0, 0.36)) - cam_obj.location
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
                    space.region_3d.view_location = Vector((-0.05, 0.0, 0.35))
                    space.region_3d.view_rotation = Euler((math.radians(66.0), 0.0, math.radians(-30.0)), "XYZ").to_quaternion()
                    space.region_3d.view_distance = 4.6


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    rock_col = bpy.data.collections.new("RockCluster")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(rock_col)
    bpy.context.scene.collection.children.link(studio_col)

    mats = {
        "rock": build_rock_material(),
        "barnacle": build_barnacle_material(),
    }

    build_rock_cluster_meshes(mats, rock_col)
    setup_studio_and_viewport(studio_col)

    total_verts = sum(len(o.data.vertices) for o in rock_col.objects if o.type == "MESH")
    total_polys = sum(len(o.data.polygons) for o in rock_col.objects if o.type == "MESH")
    print(f"[RockCluster geometry] objects={len(rock_col.objects)}, verts={total_verts}, polys={total_polys}")

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
    for obj in rock_col.objects:
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
