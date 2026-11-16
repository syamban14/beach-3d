"""Generate a standalone realistic ocean asset (ocean.blend & ocean.glb) in Blender 5.2."""

import math
import os
import bpy
import bmesh
from mathutils import Color, Euler, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(BASE_DIR, "assets", "blend", "ocean.blend")
GLB_PATH = os.path.join(BASE_DIR, "assets", "models", "ocean.glb")
PREVIEW_PATH = "/Users/syamban/.gemini/antigravity-cli/brain/a2810c20-f453-4255-9182-bae8a0819dcc/scratch/ocean_preview.png"

os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(PREVIEW_PATH), exist_ok=True)

# 9 directional Gerstner waves: (dir_x, dir_y, amplitude, wavelength, steepness, phase)
GERSTNER_WAVES = [
    # 3 primary swells
    (0.84, 0.54, 0.50, 25.0, 0.72, 0.35),
    (0.38, 0.92, 0.39, 18.5, 0.66, 1.85),
    (-0.56, 0.83, 0.32, 14.8, 0.58, 3.10),
    # 3 cross wind waves
    (0.95, -0.30, 0.21, 9.4, 0.62, 0.95),
    (0.16, 0.98, 0.17, 7.1, 0.56, 2.40),
    (-0.84, 0.54, 0.14, 5.4, 0.52, 4.15),
    # 3 short choppy waves
    (0.68, 0.73, 0.088, 3.6, 0.52, 1.25),
    (-0.64, -0.77, 0.065, 2.35, 0.48, 2.95),
    (0.92, 0.39, 0.044, 1.65, 0.44, 0.55),
]

NUM_WAVES = len(GERSTNER_WAVES)


def hex_to_rgba(hex_str, alpha=1.0):
    """Convert #rrggbb hex string to linear RGBA tuple."""
    h = hex_str.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    c = Color((r, g, b))
    return (c.r, c.g, c.b, alpha)


def evaluate_gerstner_field(x, y):
    """Evaluate layered Gerstner swells, cross chops, and high-frequency ripples at (x, y)."""
    px = x
    py = y
    pz = 0.0
    compression = 0.0

    for dx_raw, dy_raw, amp, wavelength, steepness, phase in GERSTNER_WAVES:
        length = math.hypot(dx_raw, dy_raw) or 1.0
        dx = dx_raw / length
        dy = dy_raw / length
        k = (2.0 * math.pi) / wavelength
        # Sharper crest pinching without folding columns inside out
        q = steepness / (k * amp * 4.6)
        theta = k * (dx * x + dy * y) + phase
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        px += q * amp * dx * cos_t
        py += q * amp * dy * cos_t
        pz += amp * sin_t
        compression += (steepness / NUM_WAVES) * sin_t

    # Physical surface chop ripples so geometry silhouette itself isn't overly smooth
    ripple = (
        math.sin(x * 2.45 + y * 1.65) * math.cos(x * 0.85 - y * 2.15) * 0.048
        + math.sin(x * 4.20 - y * 3.10) * 0.028
        + math.cos(x * 6.10 + y * 5.20) * 0.018
    )
    pz += ripple

    # Compute lacy crest foam score in [0, 1] restricted to steep peaks
    foam_height = max(0.0, min(1.0, (pz - 0.62) / 0.65))
    foam_pinch = max(0.0, min(1.0, (compression - 0.16) / 0.24))
    cellular = (0.5 + 0.5 * math.sin(x * 2.2 - y * 1.8 + pz * 3.1)) * (0.5 + 0.5 * math.cos(x * 3.9 + y * 4.4))
    raw_foam = (0.62 * foam_height + 0.38 * foam_pinch) * (0.40 + 0.90 * cellular)
    foam_crest = max(0.0, min(1.0, (raw_foam - 0.32) / 0.55))

    return px, py, pz, foam_crest


def build_ocean_material():
    """Create procedural OceanWater shader with multi-octave bump ripples, deep water ramp, and lacy crest foam."""
    mat = bpy.data.materials.new("OceanWater")
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out_node = nt.nodes.new("ShaderNodeOutputMaterial")
    out_node.location = (1180, 0)

    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (880, 0)
    bsdf.inputs["IOR"].default_value = 1.333
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.68
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.58
    if "Coat Roughness" in bsdf.inputs:
        bsdf.inputs["Coat Roughness"].default_value = 0.04
    nt.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])

    # Object coordinates for multi-scale wind & capillary ripples
    tex_coord = nt.nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-1080, -280)

    noise_chop = nt.nodes.new("ShaderNodeTexNoise")
    noise_chop.location = (-800, -100)
    noise_chop.inputs["Scale"].default_value = 1.35
    noise_chop.inputs["Detail"].default_value = 10.0
    noise_chop.inputs["Roughness"].default_value = 0.66
    noise_chop.inputs["Distortion"].default_value = 0.55
    nt.links.new(tex_coord.outputs["Object"], noise_chop.inputs["Vector"])

    noise_cap = nt.nodes.new("ShaderNodeTexNoise")
    noise_cap.location = (-800, -340)
    noise_cap.inputs["Scale"].default_value = 3.8
    noise_cap.inputs["Detail"].default_value = 10.0
    noise_cap.inputs["Roughness"].default_value = 0.66
    nt.links.new(tex_coord.outputs["Object"], noise_cap.inputs["Vector"])

    voronoi_facets = nt.nodes.new("ShaderNodeTexVoronoi")
    voronoi_facets.location = (-800, -580)
    voronoi_facets.inputs["Scale"].default_value = 6.2
    nt.links.new(tex_coord.outputs["Object"], voronoi_facets.inputs["Vector"])

    # Combine ripple layers -> Bump Normal
    mul_chop = nt.nodes.new("ShaderNodeMath")
    mul_chop.operation = "MULTIPLY"
    mul_chop.location = (-520, -120)
    mul_chop.inputs[1].default_value = 0.58
    nt.links.new(noise_chop.outputs["Factor"], mul_chop.inputs[0])

    mul_cap = nt.nodes.new("ShaderNodeMath")
    mul_cap.operation = "MULTIPLY"
    mul_cap.location = (-520, -320)
    mul_cap.inputs[1].default_value = 0.34
    nt.links.new(noise_cap.outputs["Factor"], mul_cap.inputs[0])

    mul_vor = nt.nodes.new("ShaderNodeMath")
    mul_vor.operation = "MULTIPLY"
    mul_vor.location = (-520, -520)
    mul_vor.inputs[1].default_value = 0.12
    nt.links.new(voronoi_facets.outputs["Distance"], mul_vor.inputs[0])

    add_b1 = nt.nodes.new("ShaderNodeMath")
    add_b1.operation = "ADD"
    add_b1.location = (-300, -220)
    nt.links.new(mul_chop.outputs["Value"], add_b1.inputs[0])
    nt.links.new(mul_cap.outputs["Value"], add_b1.inputs[1])

    add_b2 = nt.nodes.new("ShaderNodeMath")
    add_b2.operation = "ADD"
    add_b2.location = (-100, -320)
    nt.links.new(add_b1.outputs["Value"], add_b2.inputs[0])
    nt.links.new(mul_vor.outputs["Value"], add_b2.inputs[1])

    bump_node = nt.nodes.new("ShaderNodeBump")
    bump_node.location = (180, -320)
    bump_node.inputs["Strength"].default_value = 0.56
    bump_node.inputs["Distance"].default_value = 0.16
    nt.links.new(add_b2.outputs["Value"], bump_node.inputs["Height"])
    nt.links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])

    # Height depth gradient (from -1.1m..+1.5m into [0..1])
    geom_node = nt.nodes.new("ShaderNodeNewGeometry")
    geom_node.location = (-1080, 300)

    sep_xyz = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep_xyz.location = (-860, 300)
    nt.links.new(geom_node.outputs["Position"], sep_xyz.inputs["Vector"])

    z_shift = nt.nodes.new("ShaderNodeMath")
    z_shift.operation = "ADD"
    z_shift.location = (-640, 300)
    z_shift.inputs[1].default_value = 1.10
    nt.links.new(sep_xyz.outputs["Z"], z_shift.inputs[0])

    z_norm = nt.nodes.new("ShaderNodeMath")
    z_norm.operation = "MULTIPLY"
    z_norm.use_clamp = True
    z_norm.location = (-440, 300)
    z_norm.inputs[1].default_value = 0.38
    nt.links.new(z_shift.outputs["Value"], z_norm.inputs[0])

    # Deep Water ColorRamp (abyssal navy -> deep ocean blue -> deep teal -> translucent crest tint)
    water_ramp = nt.nodes.new("ShaderNodeValToRGB")
    water_ramp.location = (-160, 340)
    w_elts = water_ramp.color_ramp.elements
    w_elts[0].position = 0.00
    w_elts[0].color = hex_to_rgba("#02101e")
    w_elts[1].position = 0.94
    w_elts[1].color = hex_to_rgba("#127c8c")
    w_mid = water_ramp.color_ramp.elements.new(0.45)
    w_mid.color = hex_to_rgba("#042a42")
    w_high = water_ramp.color_ramp.elements.new(0.76)
    w_high.color = hex_to_rgba("#095266")
    nt.links.new(z_norm.outputs["Value"], water_ramp.inputs["Factor"])

    # Reference OceanColor attribute gently in deep shadow blend so glTF exports vertex colors cleanly
    vcol_node = nt.nodes.new("ShaderNodeVertexColor")
    vcol_node.layer_name = "OceanColor"
    vcol_node.location = (-160, 560)

    mix_vcol = nt.nodes.new("ShaderNodeMix")
    mix_vcol.data_type = "RGBA"
    mix_vcol.location = (180, 420)
    mix_vcol.inputs["Factor"].default_value = 0.14
    nt.links.new(water_ramp.outputs["Color"], mix_vcol.inputs[6])
    nt.links.new(vcol_node.outputs["Color"], mix_vcol.inputs[7])

    # Lacy Cellular Foam Mask restricted to sharp breaking crests
    noise_foam = nt.nodes.new("ShaderNodeTexNoise")
    noise_foam.location = (-800, 100)
    noise_foam.inputs["Scale"].default_value = 2.8
    noise_foam.inputs["Detail"].default_value = 12.0
    noise_foam.inputs["Roughness"].default_value = 0.78
    noise_foam.inputs["Distortion"].default_value = 0.45
    nt.links.new(tex_coord.outputs["Object"], noise_foam.inputs["Vector"])

    foam_noise_w = nt.nodes.new("ShaderNodeMath")
    foam_noise_w.operation = "MULTIPLY"
    foam_noise_w.location = (-440, 100)
    foam_noise_w.inputs[1].default_value = 0.52
    nt.links.new(noise_foam.outputs["Factor"], foam_noise_w.inputs[0])

    foam_z_w = nt.nodes.new("ShaderNodeMath")
    foam_z_w.operation = "MULTIPLY"
    foam_z_w.location = (-440, 190)
    foam_z_w.inputs[1].default_value = 0.85
    nt.links.new(z_norm.outputs["Value"], foam_z_w.inputs[0])

    foam_combine = nt.nodes.new("ShaderNodeMath")
    foam_combine.operation = "ADD"
    foam_combine.use_clamp = True
    foam_combine.location = (-240, 120)
    nt.links.new(foam_z_w.outputs["Value"], foam_combine.inputs[0])
    nt.links.new(foam_noise_w.outputs["Value"], foam_combine.inputs[1])

    foam_mask_ramp = nt.nodes.new("ShaderNodeValToRGB")
    foam_mask_ramp.location = (0, 120)
    fm_elts = foam_mask_ramp.color_ramp.elements
    fm_elts[0].position = 0.86
    fm_elts[0].color = (0.0, 0.0, 0.0, 1.0)
    fm_elts[1].position = 0.96
    fm_elts[1].color = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(foam_combine.outputs["Value"], foam_mask_ramp.inputs["Factor"])

    # Mix frothy whitecap onto high broken crests only
    mix_foam_col = nt.nodes.new("ShaderNodeMix")
    mix_foam_col.data_type = "RGBA"
    mix_foam_col.location = (520, 260)
    mix_foam_col.inputs[7].default_value = hex_to_rgba("#e8f6ff")
    nt.links.new(foam_mask_ramp.outputs["Color"], mix_foam_col.inputs["Factor"])
    nt.links.new(mix_vcol.outputs[2], mix_foam_col.inputs[6])
    nt.links.new(mix_foam_col.outputs[2], bsdf.inputs["Base Color"])

    # Roughness: glossy ocean (0.08) -> matte sea-foam (0.62)
    mix_rough = nt.nodes.new("ShaderNodeMix")
    mix_rough.data_type = "FLOAT"
    mix_rough.location = (520, 20)
    mix_rough.inputs[2].default_value = 0.08
    mix_rough.inputs[3].default_value = 0.62
    nt.links.new(foam_mask_ramp.outputs["Color"], mix_rough.inputs[0])
    nt.links.new(mix_rough.outputs[0], bsdf.inputs["Roughness"])

    return mat


def build_seabed_material():
    """Create dark textured SeabedSand material beneath the ocean surface."""
    mat = bpy.data.materials.new("SeabedSand")
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = hex_to_rgba("#0c2c3d")
    bsdf.inputs["Roughness"].default_value = 0.88
    return mat


def create_ocean_meshes(ocean_col):
    """Create high-res Gerstner-deformed OceanSurface with OceanColor + OceanSeabed."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=240, y_segments=240, size=45.0)

    vertex_foam = []
    min_z = 999.0
    max_z = -999.0
    for v in bm.verts:
        px, py, pz, foam = evaluate_gerstner_field(v.co.x, v.co.y)
        v.co = Vector((px, py, pz))
        vertex_foam.append((pz, foam))
        if pz < min_z:
            min_z = pz
        if pz > max_z:
            max_z = pz

    mesh = bpy.data.meshes.new("OceanSurface")
    bm.to_mesh(mesh)
    bm.free()

    for poly in mesh.polygons:
        poly.use_smooth = True

    # Populate byte color attribute for glTF export fidelity
    color_attr = mesh.color_attributes.new(name="OceanColor", type="BYTE_COLOR", domain="POINT")
    mesh.color_attributes.active_color = color_attr
    c_deep = Vector(hex_to_rgba("#02101e"))
    c_mid = Vector(hex_to_rgba("#042a42"))
    c_turq = Vector(hex_to_rgba("#095266"))
    c_crest = Vector(hex_to_rgba("#127c8c"))
    c_foam = Vector(hex_to_rgba("#e8f6ff"))

    z_span = max(0.01, max_z - min_z)
    for idx, (pz, foam) in enumerate(vertex_foam):
        t = (pz - min_z) / z_span
        if t < 0.45:
            col_vec = c_deep.lerp(c_mid, t / 0.45)
        elif t < 0.78:
            col_vec = c_mid.lerp(c_turq, (t - 0.45) / 0.33)
        else:
            col_vec = c_turq.lerp(c_crest, min(1.0, (t - 0.78) / 0.22))
        col_vec = col_vec.lerp(c_foam, foam * 0.85)
        color_attr.data[idx].color = (col_vec[0], col_vec[1], col_vec[2], 1.0)

    ocean_obj = bpy.data.objects.new("OceanSurface", mesh)
    ocean_col.objects.link(ocean_obj)
    ocean_obj.data.materials.append(build_ocean_material())

    # Seabed mesh at z ~ -4.2m
    bm_bed = bmesh.new()
    bmesh.ops.create_grid(bm_bed, x_segments=80, y_segments=80, size=45.0)
    for v in bm_bed.verts:
        dune = math.sin(v.co.x * 0.14 + v.co.y * 0.09) * 0.45 + math.cos(v.co.x * 0.28 - v.co.y * 0.21) * 0.22
        v.co.z = -4.2 + dune

    bed_mesh = bpy.data.meshes.new("OceanSeabed")
    bm_bed.to_mesh(bed_mesh)
    bm_bed.free()
    for poly in bed_mesh.polygons:
        poly.use_smooth = True

    bed_obj = bpy.data.objects.new("OceanSeabed", bed_mesh)
    ocean_col.objects.link(bed_obj)
    bed_obj.data.materials.append(build_seabed_material())

    print(f"[Ocean geometry] verts={len(mesh.vertices)}, z_range=({min_z:.3f}, {max_z:.3f})")
    return ocean_obj, bed_obj


def setup_studio_and_viewport(studio_col):
    """Set up gradient sky world, grazing sun glitter light, camera, and Material Preview."""
    world = bpy.data.worlds.new("OceanSkyWorld")
    bpy.context.scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    w_nt = world.node_tree
    w_nt.nodes.clear()

    w_out = w_nt.nodes.new("ShaderNodeOutputWorld")
    w_out.location = (520, 0)
    bg = w_nt.nodes.new("ShaderNodeBackground")
    bg.location = (280, 0)
    bg.inputs["Strength"].default_value = 0.85
    w_nt.links.new(bg.outputs["Background"], w_out.inputs["Surface"])

    w_tc = w_nt.nodes.new("ShaderNodeTexCoord")
    w_tc.location = (-460, 0)
    w_sep = w_nt.nodes.new("ShaderNodeSeparateXYZ")
    w_sep.location = (-260, 0)
    w_nt.links.new(w_tc.outputs["Generated"], w_sep.inputs["Vector"])

    sky_ramp = w_nt.nodes.new("ShaderNodeValToRGB")
    sky_ramp.location = (-20, 0)
    s_elts = sky_ramp.color_ramp.elements
    s_elts[0].position = 0.48
    s_elts[0].color = hex_to_rgba("#b7dcf2")
    s_elts[1].position = 0.78
    s_elts[1].color = hex_to_rgba("#3878ad")
    w_nt.links.new(w_sep.outputs["Z"], sky_ramp.inputs["Factor"])
    w_nt.links.new(sky_ramp.outputs["Color"], bg.inputs["Color"])

    # Grazing warm sun angled toward the waves for realistic specular glitter & troughs
    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 4.6
    key_data.color = (1.0, 0.94, 0.84)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(68), math.radians(8), math.radians(-162))
    studio_col.objects.link(key_obj)

    fill_data = bpy.data.lights.new("SkyFillLight", type="SUN")
    fill_data.energy = 0.85
    fill_data.color = (0.58, 0.80, 1.0)
    fill_obj = bpy.data.objects.new("SkyFillLight", fill_data)
    fill_obj.rotation_euler = (math.radians(35), math.radians(-18), math.radians(35))
    studio_col.objects.link(fill_obj)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 42.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (0.0, -34.0, 6.2)
    cam_dir = Vector((0.0, 6.0, 0.0)) - cam_obj.location
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
                    space.region_3d.view_location = Vector((0.0, 0.0, 0.0))
                    space.region_3d.view_rotation = Euler((math.radians(74.0), 0.0, 0.0), "XYZ").to_quaternion()
                    space.region_3d.view_distance = 30.0


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    ocean_col = bpy.data.collections.new("Ocean")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(ocean_col)
    bpy.context.scene.collection.children.link(studio_col)

    create_ocean_meshes(ocean_col)
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
    for obj in ocean_col.objects:
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
