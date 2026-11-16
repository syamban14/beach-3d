"""Generate a realistic beach island terrain asset (island.blend & island.glb) in Blender 5.2.

Features rippled wet/dry beach sand, organic brown coastal soil transition zones,
lush multi-tone turf, 3D grass tufts & spinifex dune grass, and coastal shells/pebbles.
"""

import math
import os
import random
import bpy
import bmesh
from mathutils import Color, Euler, Matrix, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(BASE_DIR, "assets", "blend", "island.blend")
GLB_PATH = os.path.join(BASE_DIR, "assets", "models", "island.glb")
PREVIEW_PATH = "/Users/syamban/.gemini/antigravity-cli/brain/a2810c20-f453-4255-9182-bae8a0819dcc/scratch/island_preview.png"

os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(PREVIEW_PATH), exist_ok=True)

# Palm tree local positions (bx, by) relative to island center (0, 28, 0) in Blender
PALM_SITES = [
    (-5.5, -4.5),
    (-11.5, -6.0),
    (-1.5, 0.0),
    (4.5, -2.5),
    (10.5, -5.5),
    (12.2, 1.0),
    (2.5, 6.5),
    (-6.8, 8.5),
    (8.5, 8.0),
]

LIGHTHOUSE_SITE = (-10.5, 3.0)
CAMPFIRE_SITE = (7.5, -8.8)


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


def smoothstep(edge0, edge1, x):
    """Smooth Hermite interpolation between 0 and 1."""
    if abs(edge1 - edge0) < 1e-6:
        return 1.0 if x >= edge1 else 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def island_elevation(bx, by):
    """Macro island elevation matching scene.js (cove facing -Y Blender -> +Z Three.js)."""
    lz = -by
    cove_factor = max(0.0, (lz - 4.0) * 0.25) if lz > 4.0 else 0.0
    eff_dist = math.hypot(bx * 0.95, lz * 1.05 + cove_factor)
    base = max(0.0, 1.0 - eff_dist / 22.5)
    hill = (base ** 1.55) * 5.2
    ridge = math.sin(bx * 0.22) * math.cos(lz * 0.19) * 0.35 * base
    return hill + ridge - 1.15


def organic_warp(x, y):
    """Multi-octave domain warp noise in roughly [-1.0, 1.0] for natural jagged biome edges."""
    return (
        math.sin(x * 0.42 + y * 0.35) * 0.45
        + math.cos(x * 0.85 - y * 0.72 + 1.4) * 0.32
        + math.sin(x * 1.65 + y * 1.45 - 0.8) * 0.23
    )


def pier_ramp_damp(bx, by):
    """Attenuate micro-relief strictly along the pier ramp shoreline path."""
    if abs(bx) < 2.4 and -13.5 < by < -7.0:
        dx = smoothstep(1.2, 2.4, abs(bx))
        dy_low = 1.0 - smoothstep(-13.5, -12.0, by)
        dy_high = smoothstep(-8.5, -7.0, by)
        return max(dx, dy_low, dy_high)
    return 1.0


def detailed_elevation(bx, by):
    """Return macro elevation + subtle sand ripples, soil hummocks, and turf mounds."""
    macro = island_elevation(bx, by)
    damp = pier_ramp_damp(bx, by)

    # Subtle physical sand undulations while shader normal wave handles fine wind ripples
    sand_mask = smoothstep(0.15, 0.55, macro) * (1.0 - smoothstep(1.45, 1.95, macro))
    ripple_wave = math.sin(bx * 3.8 - by * 4.4 + 0.9 * math.sin(bx * 0.7 + by * 0.6))
    ripples = ripple_wave * 0.012 * sand_mask

    # Organic soil & tree root hummocks (1.35m < elev < 2.45m or near palm roots)
    soil_mask = smoothstep(1.25, 1.65, macro) * (1.0 - smoothstep(2.15, 2.55, macro))
    hummocks = (
        math.sin(bx * 1.35 + by * 1.15) * math.cos(bx * 0.9 - by * 1.45) * 0.036 * soil_mask
    )
    for px, py in PALM_SITES:
        dp = math.hypot(bx - px, by - py)
        if dp < 1.8:
            hummocks += (1.0 - smoothstep(0.2, 1.8, dp)) * 0.055

    # Hill turf micro-mounds (elev >= 2.05m)
    turf_mask = smoothstep(1.95, 2.35, macro)
    mounds = (
        math.sin(bx * 1.8 - by * 1.6) * 0.020
        + math.cos(bx * 2.9 + by * 2.4) * 0.014
    ) * turf_mask

    return macro + (ripples + hummocks + mounds) * damp, macro, ripple_wave


def create_mesh_with_vcol(name, bm, vert_colors, material, collection):
    """Finalize BMesh with active IslandColor byte attribute and smooth shading."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    for poly in mesh.polygons:
        poly.use_smooth = True

    color_attr = mesh.color_attributes.new(name="IslandColor", type="BYTE_COLOR", domain="POINT")
    mesh.color_attributes.active_color = color_attr
    for idx, rgba in enumerate(vert_colors):
        if idx < len(color_attr.data):
            color_attr.data[idx].color = rgba

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    return obj


def build_terrain_material():
    """Build procedural IslandTerrainMat combining IslandColor, fine sand/soil/wave bump, and wet roughness."""
    mat = bpy.data.materials.new("IslandTerrainMat")
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out_node = nt.nodes.new("ShaderNodeOutputMaterial")
    out_node.location = (920, 0)

    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (620, 0)
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.42
    nt.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "IslandColor"
    vcol.location = (-580, 260)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-920, -140)

    noise_sand = nt.nodes.new("ShaderNodeTexNoise")
    noise_sand.location = (-640, -40)
    noise_sand.inputs["Scale"].default_value = 120.0
    noise_sand.inputs["Detail"].default_value = 12.0
    noise_sand.inputs["Roughness"].default_value = 0.82
    nt.links.new(tc.outputs["Object"], noise_sand.inputs["Vector"])

    noise_clump = nt.nodes.new("ShaderNodeTexNoise")
    noise_clump.location = (-640, -240)
    noise_clump.inputs["Scale"].default_value = 24.0
    noise_clump.inputs["Detail"].default_value = 14.0
    noise_clump.inputs["Roughness"].default_value = 0.78
    noise_clump.inputs["Distortion"].default_value = 0.55
    nt.links.new(tc.outputs["Object"], noise_clump.inputs["Vector"])

    wave_ripple = nt.nodes.new("ShaderNodeTexWave")
    wave_ripple.location = (-640, -460)
    wave_ripple.wave_type = "BANDS"
    wave_ripple.bands_direction = "DIAGONAL"
    wave_ripple.wave_profile = "SIN"
    wave_ripple.inputs["Scale"].default_value = 14.0
    wave_ripple.inputs["Distortion"].default_value = 3.6
    wave_ripple.inputs["Detail"].default_value = 5.0
    nt.links.new(tc.outputs["Object"], wave_ripple.inputs["Vector"])

    # Modulate vertex color slightly with clumped soil/sand grain noise
    speckle_ramp = nt.nodes.new("ShaderNodeValToRGB")
    speckle_ramp.location = (-280, 80)
    speckle_ramp.color_ramp.elements[0].position = 0.25
    speckle_ramp.color_ramp.elements[0].color = (0.76, 0.75, 0.72, 1.0)
    speckle_ramp.color_ramp.elements[1].position = 0.80
    speckle_ramp.color_ramp.elements[1].color = (1.12, 1.10, 1.06, 1.0)
    nt.links.new(noise_clump.outputs["Factor"], speckle_ramp.inputs["Factor"])

    mix_col = nt.nodes.new("ShaderNodeMix")
    mix_col.data_type = "RGBA"
    mix_col.blend_type = "MULTIPLY"
    mix_col.location = (120, 220)
    mix_col.inputs["Factor"].default_value = 0.72
    nt.links.new(vcol.outputs["Color"], mix_col.inputs[6])
    nt.links.new(speckle_ramp.outputs["Color"], mix_col.inputs[7])
    nt.links.new(mix_col.outputs[2], bsdf.inputs["Base Color"])

    # Combine fine sand grain + clump noise + diagonal wind wave -> crisp Bump
    mul_s = nt.nodes.new("ShaderNodeMath")
    mul_s.operation = "MULTIPLY"
    mul_s.location = (-360, -80)
    mul_s.inputs[1].default_value = 0.38
    nt.links.new(noise_sand.outputs["Factor"], mul_s.inputs[0])

    mul_c = nt.nodes.new("ShaderNodeMath")
    mul_c.operation = "MULTIPLY"
    mul_c.location = (-360, -240)
    mul_c.inputs[1].default_value = 0.45
    nt.links.new(noise_clump.outputs["Factor"], mul_c.inputs[0])

    mul_w = nt.nodes.new("ShaderNodeMath")
    mul_w.operation = "MULTIPLY"
    mul_w.location = (-360, -400)
    mul_w.inputs[1].default_value = 0.30
    wave_out = wave_ripple.outputs["Fac"] if "Fac" in wave_ripple.outputs else wave_ripple.outputs[0]
    nt.links.new(wave_out, mul_w.inputs[0])

    add_1 = nt.nodes.new("ShaderNodeMath")
    add_1.operation = "ADD"
    add_1.location = (-140, -180)
    nt.links.new(mul_s.outputs["Value"], add_1.inputs[0])
    nt.links.new(mul_c.outputs["Value"], add_1.inputs[1])

    add_all = nt.nodes.new("ShaderNodeMath")
    add_all.operation = "ADD"
    add_all.location = (40, -280)
    nt.links.new(add_1.outputs["Value"], add_all.inputs[0])
    nt.links.new(mul_w.outputs["Value"], add_all.inputs[1])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (280, -280)
    bump.inputs["Strength"].default_value = 0.80
    bump.inputs["Distance"].default_value = 0.055
    nt.links.new(add_all.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    # Height-driven Roughness: glossy wet shoreline sand (0.22 below z=0.25m) -> dry matte sand/soil (0.86)
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    geom.location = (-640, 480)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-440, 480)
    nt.links.new(geom.outputs["Position"], sep.inputs["Vector"])

    z_sub = nt.nodes.new("ShaderNodeMath")
    z_sub.operation = "SUBTRACT"
    z_sub.location = (-240, 480)
    z_sub.inputs[1].default_value = 0.16
    nt.links.new(sep.outputs["Z"], z_sub.inputs[0])

    z_scale = nt.nodes.new("ShaderNodeMath")
    z_scale.operation = "MULTIPLY"
    z_scale.use_clamp = True
    z_scale.location = (-40, 480)
    z_scale.inputs[1].default_value = 2.0  # map [0.16..0.66] -> [0..1]
    nt.links.new(z_sub.outputs["Value"], z_scale.inputs[0])

    rough_ramp = nt.nodes.new("ShaderNodeValToRGB")
    rough_ramp.location = (180, 480)
    rough_ramp.color_ramp.elements[0].position = 0.0
    rough_ramp.color_ramp.elements[0].color = (0.22, 0.22, 0.22, 1.0)
    rough_ramp.color_ramp.elements[1].position = 1.0
    rough_ramp.color_ramp.elements[1].color = (0.86, 0.86, 0.86, 1.0)
    nt.links.new(z_scale.outputs["Value"], rough_ramp.inputs["Factor"])
    nt.links.new(rough_ramp.outputs["Color"], bsdf.inputs["Roughness"])

    return mat


def build_grass_material():
    """Build lush double-sided IslandGrassMat reading IslandColor with leaf vein bump & SSS."""
    mat = bpy.data.materials.new("IslandGrassMat")
    if mat.node_tree is None:
        mat.use_nodes = True
    mat.use_backface_culling = False
    nt = mat.node_tree
    nt.nodes.clear()

    out_node = nt.nodes.new("ShaderNodeOutputMaterial")
    out_node.location = (620, 0)

    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (320, 0)
    bsdf.inputs["Roughness"].default_value = 0.48
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.06
        if "Subsurface Scale" in bsdf.inputs:
            bsdf.inputs["Subsurface Scale"].default_value = 0.015
        if "Subsurface Radius" in bsdf.inputs:
            bsdf.inputs["Subsurface Radius"].default_value = (0.35, 1.0, 0.25)
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.25
        if "Coat Roughness" in bsdf.inputs:
            bsdf.inputs["Coat Roughness"].default_value = 0.22
    nt.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "IslandColor"
    vcol.location = (-220, 140)
    nt.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-580, -140)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-340, -140)
    noise.inputs["Scale"].default_value = 28.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-40, -140)
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.015
    nt.links.new(noise.outputs["Factor"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    return mat


def build_island_terrain(mats, island_col):
    """Build 160x160 sculpted IslandTerrain mesh with 5-zone linear vertex colors."""
    size = 66.0
    segs = 160
    bm = bmesh.new()
    vcols = []

    # 5-zone color palette in scene-linear space
    c_seabed_deep = hex_to_rgba("#4a3926")
    c_seabed_mid = hex_to_rgba("#6b5338")
    c_wet_dark = hex_to_rgba("#7a5f3e")
    c_wet_light = hex_to_rgba("#9e7e55")
    c_sand_low = hex_to_rgba("#c8a66e")
    c_sand_mid = hex_to_rgba("#ddc18b")
    c_sand_high = hex_to_rgba("#ebd5a7")
    c_soil_dark = hex_to_rgba("#5b3f26")
    c_soil_mid = hex_to_rgba("#755333")
    c_soil_sandy = hex_to_rgba("#8c6943")
    c_grass_deep = hex_to_rgba("#214d19")
    c_grass_mid = hex_to_rgba("#356b23")
    c_grass_bright = hex_to_rgba("#548730")
    c_humus_patch = hex_to_rgba("#5a4028")

    grid_verts = [[None] * (segs + 1) for _ in range(segs + 1)]
    for iy in range(segs + 1):
        by = (iy / segs - 0.5) * size
        for ix in range(segs + 1):
            bx = (ix / segs - 0.5) * size
            bz, macro, ripple = detailed_elevation(bx, by)
            grid_verts[iy][ix] = bm.verts.new((bx, by, bz))

            # Estimate local slope magnitude quickly from central diff of macro elevation
            eps = 0.45
            slope_x = (island_elevation(bx + eps, by) - island_elevation(bx - eps, by)) / (2.0 * eps)
            slope_y = (island_elevation(bx, by + eps) - island_elevation(bx, by - eps)) / (2.0 * eps)
            slope = math.hypot(slope_x, slope_y)

            warp = organic_warp(bx, by)
            micro_var = 0.5 + 0.5 * math.sin(bx * 1.9 - by * 1.7 + 0.6 * warp)

            # Palm tree base soil boost (rich brown soil ring under tree roots)
            palm_soil = 0.0
            for px, py in PALM_SITES:
                dp = math.hypot(bx - px, by - py)
                if dp < 2.2:
                    palm_soil = max(palm_soil, 1.0 - smoothstep(0.3, 2.2, dp))

            # Campfire ash/soil ring boost
            cf_dist = math.hypot(bx - CAMPFIRE_SITE[0], by - CAMPFIRE_SITE[1])
            campfire_soil = 1.0 - smoothstep(0.5, 2.4, cf_dist) if cf_dist < 2.4 else 0.0

            # Compute clean multi-zone blend across seabed -> wet sand -> dry sand -> soil -> turf
            e_wet_top = 0.34 + 0.12 * warp
            e_sand_top = 1.48 + 0.26 * warp
            e_grass_start = 2.05 + 0.25 * warp

            if macro < -0.20:
                col = lerp_color(c_seabed_deep, c_seabed_mid, smoothstep(-1.15, -0.20, macro))
            elif macro < e_wet_top:
                col = lerp_color(c_wet_dark, c_wet_light, smoothstep(-0.20, e_wet_top, macro))
            else:
                # Dry sand base with organic wind-drift mottling (avoid artificial stripes)
                sand_drift = 0.5 + 0.35 * organic_warp(bx * 0.65, by * 0.65) + 0.15 * (micro_var - 0.5)
                dry_sand_col = lerp_color(c_sand_low, c_sand_mid, smoothstep(0.15, 0.72, sand_drift))
                dry_sand_col = lerp_color(dry_sand_col, c_sand_high, smoothstep(0.65, 1.0, sand_drift))

                # Rich soil layer (belt 1.42..2.28m + steep embankment exposure + tree bases)
                soil_col = lerp_color(c_soil_dark, c_soil_mid, micro_var)
                soil_col = lerp_color(soil_col, c_soil_sandy, smoothstep(0.25, 0.85, warp * 0.5 + 0.5) * 0.65)

                # Multi-tone tropical turf with subtle dark humus patches in low pockets
                grass_col = lerp_color(c_grass_deep, c_grass_mid, smoothstep(0.15, 0.75, micro_var))
                grass_col = lerp_color(grass_col, c_grass_bright, smoothstep(0.65, 1.0, micro_var + 0.2 * warp))
                humus_spot = smoothstep(0.60, 0.94, math.sin(bx * 1.45 + by * 1.65 + warp))
                grass_col = lerp_color(grass_col, c_humus_patch, humus_spot * 0.26)

                # Blend dry sand -> coastal soil belt -> hill turf
                soil_in = smoothstep(e_sand_top - 0.32, e_sand_top + 0.24, macro)
                grass_in = smoothstep(e_grass_start - 0.22, e_grass_start + 0.38, macro)

                col = lerp_color(dry_sand_col, soil_col, soil_in)
                col = lerp_color(col, grass_col, grass_in)

                # Steep slope soil exposure + palm root / campfire soil overlay
                slope_soil = smoothstep(0.32, 0.58, slope) * 0.55
                extra_soil = max(slope_soil * grass_in, palm_soil * 0.78, campfire_soil * 0.85)
                col = lerp_color(col, soil_col, min(0.92, extra_soil))

                # Wet shoreline transition edge softly darkening lower edge of dry sand
                wet_blend = 1.0 - smoothstep(e_wet_top, e_wet_top + 0.28, macro)
                if wet_blend > 0.0:
                    col = lerp_color(col, c_wet_light, wet_blend)

            vcols.append(col)

    for iy in range(segs):
        for ix in range(segs):
            bm.faces.new((
                grid_verts[iy][ix],
                grid_verts[iy][ix + 1],
                grid_verts[iy + 1][ix + 1],
                grid_verts[iy + 1][ix],
            ))

    return create_mesh_with_vcol("IslandTerrain", bm, vcols, mats["terrain"], island_col)


def add_grass_blade_to_bmesh(bm, vcols, root_pos, yaw, pitch, length, width, c_base, c_mid, c_tip):
    """Add 1 curved 3D V-folded grass blade (10 verts, 5 faces) directly into bm."""
    cos_y = math.cos(yaw)
    sin_y = math.sin(yaw)
    fwd_xy = Vector((cos_y, sin_y, 0.0))
    lat_xy = Vector((-sin_y, cos_y, 0.0))

    # 3 stations along curved arching blade + sharp 1-vert tip = 10 verts total
    stations = [
        (0.00, 1.00, c_base),
        (0.42, 0.82, lerp_color(c_base, c_mid, 0.75)),
        (0.76, 0.45, c_mid),
    ]
    rows = []
    for u, w_scale, col_u in stations:
        reach = math.sin(u * math.pi * 0.52) * pitch * length
        z_lift = u * length - (u ** 2.1) * (pitch * length * 0.42)
        center = root_pos + fwd_xy * reach + Vector((0.0, 0.0, z_lift))
        w = width * w_scale
        fold = w * 0.45

        vl = bm.verts.new(center - lat_xy * w + fwd_xy * fold)
        vc = bm.verts.new(center - fwd_xy * fold * 0.4)
        vr = bm.verts.new(center + lat_xy * w + fwd_xy * fold)
        vcols.extend([col_u, col_u, col_u])
        rows.append((vl, vc, vr))

    tip_reach = pitch * length * 1.15
    tip_z = length - (pitch * length * 0.46)
    v_tip = bm.verts.new(root_pos + fwd_xy * tip_reach + Vector((0.0, 0.0, tip_z)))
    vcols.append(c_tip)

    for i in range(len(rows) - 1):
        r0, r1 = rows[i], rows[i + 1]
        bm.faces.new((r0[0], r0[1], r1[1], r1[0]))
        bm.faces.new((r0[1], r0[2], r1[2], r1[1]))

    top_row = rows[-1]
    bm.faces.new((top_row[0], top_row[1], v_tip))
    bm.faces.new((top_row[1], top_row[2], v_tip))


def is_excluded_for_grass(bx, by):
    """Avoid placing grass tufts inside lighthouse floor, campfire pit, or pier ramp."""
    if math.hypot(bx - LIGHTHOUSE_SITE[0], by - LIGHTHOUSE_SITE[1]) < 3.4:
        return True
    if math.hypot(bx - CAMPFIRE_SITE[0], by - CAMPFIRE_SITE[1]) < 2.1:
        return True
    if abs(bx) < 2.6 and -14.0 < by < -6.5:
        return True
    return False


def build_grass_and_shells(mats, island_col):
    """Build 3D IslandGrassTufts, CoastalDuneGrass spinifex clumps, and BeachPebblesAndShells."""
    rng = random.Random(777)

    # 1. Hill & Palm-Base Grass Tufts (~250 clumps)
    bm_tufts = bmesh.new()
    tuft_vcols = []

    c_t_base = hex_to_rgba("#383318")
    c_t_mid_a = hex_to_rgba("#2d681e")
    c_t_mid_b = hex_to_rgba("#428027")
    c_t_tip = hex_to_rgba("#7ba136")

    placed_tufts = 0
    attempts = 0
    while placed_tufts < 380 and attempts < 3600:
        attempts += 1
        bx = rng.uniform(-16.0, 16.0)
        by = rng.uniform(-14.0, 16.0)
        if is_excluded_for_grass(bx, by):
            continue

        bz, macro, _ = detailed_elevation(bx, by)
        near_palm = any(math.hypot(bx - px, by - py) < 2.1 for px, py in PALM_SITES)
        if macro < 1.85 and not (near_palm and macro > 1.35):
            continue

        placed_tufts += 1
        n_blades = rng.randint(5, 7)
        clump_base_z = bz - 0.025
        for b in range(n_blades):
            ang = (b / n_blades) * math.pi * 2.0 + rng.uniform(-0.35, 0.35)
            rad_off = rng.uniform(0.02, 0.14)
            rx = bx + math.cos(ang) * rad_off
            ry = by + math.sin(ang) * rad_off
            rz, _, _ = detailed_elevation(rx, ry)
            h_blade = rng.uniform(0.16, 0.38)
            w_blade = rng.uniform(0.018, 0.032)
            lean_pitch = rng.uniform(0.32, 0.72)
            c_mid = lerp_color(c_t_mid_a, c_t_mid_b, rng.uniform(0.0, 1.0))

            add_grass_blade_to_bmesh(
                bm_tufts,
                tuft_vcols,
                Vector((rx, ry, min(clump_base_z, rz) - 0.01)),
                ang + rng.uniform(-0.25, 0.25),
                lean_pitch,
                h_blade,
                w_blade,
                c_t_base,
                c_mid,
                c_t_tip,
            )

    create_mesh_with_vcol("IslandGrassTufts", bm_tufts, tuft_vcols, mats["grass"], island_col)

    # 2. Coastal Spinifex Dune Grass (~85 clumps in sandy-soil border belt 1.15..2.05m)
    bm_dune = bmesh.new()
    dune_vcols = []

    c_d_base = hex_to_rgba("#5a5228")
    c_d_mid = hex_to_rgba("#567330")
    c_d_tip = hex_to_rgba("#989c49")

    placed_dune = 0
    attempts = 0
    while placed_dune < 105 and attempts < 2500:
        attempts += 1
        bx = rng.uniform(-18.0, 18.0)
        by = rng.uniform(-15.5, 17.5)
        if is_excluded_for_grass(bx, by):
            continue

        bz, macro, _ = detailed_elevation(bx, by)
        if not (1.15 <= macro <= 2.05):
            continue

        placed_dune += 1
        n_blades = rng.randint(5, 7)
        for b in range(n_blades):
            ang = (b / n_blades) * math.pi * 2.0 + rng.uniform(-0.4, 0.4)
            rad_off = rng.uniform(0.02, 0.16)
            rx = bx + math.cos(ang) * rad_off
            ry = by + math.sin(ang) * rad_off
            rz, _, _ = detailed_elevation(rx, ry)
            add_grass_blade_to_bmesh(
                bm_dune,
                dune_vcols,
                Vector((rx, ry, rz - 0.015)),
                ang,
                rng.uniform(0.45, 0.85),
                rng.uniform(0.22, 0.46),
                rng.uniform(0.012, 0.022),
                c_d_base,
                c_d_mid,
                c_d_tip,
            )

    create_mesh_with_vcol("CoastalDuneGrass", bm_dune, dune_vcols, mats["grass"], island_col)

    # 3. Beach Pebbles & Shells along shoreline wash (0.15m <= elev <= 0.95m)
    bm_peb = bmesh.new()
    peb_vcols = []

    c_shell_cream = hex_to_rgba("#e8dcc2")
    c_shell_coral = hex_to_rgba("#c97e63")
    c_peb_grey = hex_to_rgba("#6f7378")
    c_peb_tan = hex_to_rgba("#947c5d")
    shell_palette = [c_shell_cream, c_shell_coral, c_peb_grey, c_peb_tan]

    placed_peb = 0
    attempts = 0
    while placed_peb < 90 and attempts < 2200:
        attempts += 1
        bx = rng.uniform(-20.0, 20.0)
        by = rng.uniform(-17.5, 19.5)
        if abs(bx) < 2.6 and -14.0 < by < -6.5:
            continue
        bz, macro, _ = detailed_elevation(bx, by)
        if not (0.15 <= macro <= 0.95):
            continue

        placed_peb += 1
        col_choice = shell_palette[placed_peb % len(shell_palette)]
        prad = rng.uniform(0.035, 0.09)
        scl = (rng.uniform(0.85, 1.35), rng.uniform(0.7, 1.15), rng.uniform(0.32, 0.55))
        rot_m = Euler((rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), rng.uniform(0, 6.28)), "XYZ").to_matrix()

        tmp_bm = bmesh.new()
        bmesh.ops.create_icosphere(tmp_bm, subdivisions=1, radius=prad)
        vmap = {}
        for v in tmp_bm.verts:
            p = Vector((v.co.x * scl[0], v.co.y * scl[1], v.co.z * scl[2]))
            nv = bm_peb.verts.new(Vector((bx, by, bz - 0.006)) + rot_m @ p)
            vmap[v] = nv
            peb_vcols.append(col_choice)
        for f in tmp_bm.faces:
            bm_peb.faces.new([vmap[v] for v in f.verts])
        tmp_bm.free()

    create_mesh_with_vcol("BeachPebblesAndShells", bm_peb, peb_vcols, mats["terrain"], island_col)


def setup_studio_and_viewport(studio_col):
    """Set up bright tropical sky, sunlight, overview camera framing sand/soil/grass, and Material Preview."""
    world = bpy.data.worlds.new("IslandStudioWorld")
    bpy.context.scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_rgba("#b7dff5")
        bg.inputs["Strength"].default_value = 0.65

    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 3.2
    key_data.color = (1.0, 0.96, 0.88)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(48), math.radians(16), math.radians(-42))
    studio_col.objects.link(key_obj)

    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_data.energy = 420.0
    fill_data.size = 24.0
    fill_data.color = (0.82, 0.92, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    fill_obj.location = (18.0, -22.0, 16.0)
    fill_dir = Vector((0.0, 0.0, 1.2)) - fill_obj.location
    fill_obj.rotation_mode = "QUATERNION"
    fill_obj.rotation_quaternion = fill_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(fill_obj)

    rim_data = bpy.data.lights.new("RimLight", type="AREA")
    rim_data.energy = 500.0
    rim_data.size = 22.0
    rim_data.color = (1.0, 0.92, 0.78)
    rim_obj = bpy.data.objects.new("RimLight", rim_data)
    rim_obj.location = (-16.0, 22.0, 18.0)
    rim_dir = Vector((0.0, 0.0, 1.5)) - rim_obj.location
    rim_obj.rotation_mode = "QUATERNION"
    rim_obj.rotation_quaternion = rim_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(rim_obj)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 36.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (-14.5, -24.0, 9.8)
    cam_dir = Vector((0.0, -1.5, 1.35)) - cam_obj.location
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
                    space.region_3d.view_location = Vector((0.0, -1.5, 1.35))
                    space.region_3d.view_rotation = Euler((math.radians(70.0), 0.0, math.radians(-28.0)), "XYZ").to_quaternion()
                    space.region_3d.view_distance = 28.0


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    island_col = bpy.data.collections.new("Island")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(island_col)
    bpy.context.scene.collection.children.link(studio_col)

    mats = {
        "terrain": build_terrain_material(),
        "grass": build_grass_material(),
    }

    build_island_terrain(mats, island_col)
    build_grass_and_shells(mats, island_col)
    setup_studio_and_viewport(studio_col)

    total_verts = sum(len(o.data.vertices) for o in island_col.objects if o.type == "MESH")
    total_polys = sum(len(o.data.polygons) for o in island_col.objects if o.type == "MESH")
    print(f"[Island geometry] objects={len(island_col.objects)}, verts={total_verts}, polys={total_polys}")

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
    for obj in island_col.objects:
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
