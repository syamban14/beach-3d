"""Generate high-detail individual young and mature fallen whole coconut models (coconut.blend & coconut.glb)."""

import math
import os
import bpy
import bmesh
from mathutils import Color, Euler, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(BASE_DIR, "assets", "blend", "coconut.blend")
GLB_PATH = os.path.join(BASE_DIR, "assets", "models", "coconut.glb")
PREVIEW_PATH = "/Users/syamban/.gemini/antigravity-cli/brain/a2810c20-f453-4255-9182-bae8a0819dcc/scratch/coconut_preview.png"

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


def create_mesh_with_vcol(name, bm, vert_colors, material, collection):
    """Finalize BMesh with active CoconutColor BYTE_COLOR attribute centered at local origin."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    for poly in mesh.polygons:
        poly.use_smooth = True

    color_attr = mesh.color_attributes.new(name="CoconutColor", type="BYTE_COLOR", domain="POINT")
    mesh.color_attributes.active_color = color_attr
    for idx, rgba in enumerate(vert_colors):
        if idx < len(color_attr.data):
            color_attr.data[idx].color = rgba

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    return obj


def build_coconut_shader(name, roughness=0.45, bump_scale=30.0, bump_str=0.25, coat=0.18, stretch_y=0.25):
    """Create procedural shader driven by CoconutColor with stretched longitudinal striations."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (740, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (440, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Coat Weight" in bsdf.inputs and coat > 0.0:
        bsdf.inputs["Coat Weight"].default_value = coat
        if "Coat Roughness" in bsdf.inputs:
            bsdf.inputs["Coat Roughness"].default_value = 0.22
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "CoconutColor"
    vcol.location = (-460, 180)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-980, -140)
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.location = (-780, -140)
    mapping.inputs["Scale"].default_value = (1.0, stretch_y, 1.0)
    nt.links.new(tc.outputs["Object"], mapping.inputs["Vector"])

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-560, -120)
    noise.inputs["Scale"].default_value = bump_scale
    noise.inputs["Detail"].default_value = 12.0
    noise.inputs["Roughness"].default_value = 0.78
    nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-300, 40)
    ramp.color_ramp.elements[0].position = 0.24
    ramp.color_ramp.elements[0].color = (0.84, 0.83, 0.80, 1.0)
    ramp.color_ramp.elements[1].position = 0.80
    ramp.color_ramp.elements[1].color = (1.08, 1.06, 1.02, 1.0)
    nt.links.new(noise.outputs["Factor"], ramp.inputs["Factor"])

    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.location = (60, 160)
    mix.inputs["Factor"].default_value = 0.45
    nt.links.new(vcol.outputs["Color"], mix.inputs[6])
    nt.links.new(ramp.outputs["Color"], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (120, -180)
    bump.inputs["Strength"].default_value = bump_str
    bump.inputs["Distance"].default_value = 0.012
    nt.links.new(noise.outputs["Factor"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    return mat


def append_stem_cylinder(bm, vcols, pts_r, segs, color):
    """Loft a smooth curved stem stub along (Vector, radius) points."""
    rings = []
    n_pts = len(pts_r)
    for i, (p, rad) in enumerate(pts_r):
        t = (pts_r[min(n_pts - 1, i + 1)][0] - pts_r[max(0, i - 1)][0]).normalized()
        ref = Vector((0.0, 0.0, 1.0)) if abs(t.z) < 0.9 else Vector((1.0, 0.0, 0.0))
        x_dir = (ref - t * ref.dot(t)).normalized()
        y_dir = t.cross(x_dir).normalized()
        ring = []
        for s in range(segs):
            ang = (s / segs) * math.pi * 2.0
            ring.append(bm.verts.new(p + (x_dir * math.cos(ang) + y_dir * math.sin(ang)) * rad))
            vcols.append(color)
        rings.append(ring)

    for i in range(n_pts - 1):
        r0, r1 = rings[i], rings[i + 1]
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def build_young_coconut(mat, col):
    """Build CoconutYoung: detailed fresh green-gold 3-lobed coconut with 6-petal calyx cap & stem stub."""
    bm = bmesh.new()
    vcols = []

    rx, ry, rz = 0.145, 0.185, 0.140
    ang_segs = 36
    lat_rings = 24

    c_green_rich = hex_to_rgba("#4d842f")
    c_green_deep = hex_to_rgba("#386622")
    c_yellow_tip = hex_to_rgba("#8fa339")
    c_calyx_dark = hex_to_rgba("#574126")
    c_calyx_light = hex_to_rgba("#705634")
    c_stem = hex_to_rgba("#47341d")

    pole_base = bm.verts.new((0.0, -ry * 0.94, 0.0))
    vcols.append(c_calyx_dark)
    pole_tip = bm.verts.new((0.0, ry * 1.07, 0.0))
    vcols.append(c_yellow_tip)

    rings = []
    for il in range(1, lat_rings):
        vf = il / lat_rings
        theta = vf * math.pi
        sin_t = math.sin(theta)
        y_val = -ry * math.cos(theta) * (1.0 + 0.09 * vf)
        # Broader rounded shoulder at basal half, tapering gently toward pointed tip
        rad_prof = (sin_t ** 0.85) * (1.0 - 0.16 * max(0.0, vf - 0.52))
        ring = []
        for s in range(ang_segs):
            ang = (s / ang_segs) * math.pi * 2.0
            trigonal = 1.0 + 0.075 * math.cos(3.0 * ang)
            ca, sa = math.cos(ang), math.sin(ang)
            px = ca * rx * rad_prof * trigonal
            pz = sa * rz * rad_prof * trigonal
            ring.append(bm.verts.new((px, y_val, pz)))

            sun_kiss = 0.5 + 0.5 * math.cos(ang - 0.6)
            col_body = lerp_color(c_green_deep, c_green_rich, 0.35 + 0.65 * sin_t)
            col_v = lerp_color(col_body, c_yellow_tip, max(0.0, (vf - 0.45) / 0.55) * 0.55 + sun_kiss * 0.25)
            if vf < 0.08:
                col_v = lerp_color(c_calyx_dark, col_v, vf / 0.08)
            vcols.append(col_v)
        rings.append(ring)

    for s in range(ang_segs):
        sn = (s + 1) % ang_segs
        bm.faces.new((pole_base, rings[0][sn], rings[0][s]))
        bm.faces.new((rings[-1][s], rings[-1][sn], pole_tip))
    for il in range(len(rings) - 1):
        r0, r1 = rings[il], rings[il + 1]
        for s in range(ang_segs):
            sn = (s + 1) % ang_segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))

    # Multi-layered woody calyx cap (tampuk kelapa): 6 bracts hugging the basal coconut dome flush
    for layer_idx, (num_petals, ang_off, vf_start, vf_end, lift_h) in enumerate([
        (3, 0.15, 0.03, 0.19, 0.009),
        (3, 1.20, 0.06, 0.24, 0.006),
    ]):
        for pi in range(num_petals):
            a_center = ang_off + (pi / num_petals) * math.pi * 2.0
            c_petal = c_calyx_dark if layer_idx == 0 else c_calyx_light
            p_rows = 5
            p_cols = 5
            p_grid = [[None] * p_cols for _ in range(p_rows)]
            for ir in range(p_rows):
                u = ir / (p_rows - 1)
                vf = vf_start + (vf_end - vf_start) * u
                theta = vf * math.pi
                sin_t = math.sin(theta)
                y_shell = -ry * math.cos(theta) * (1.0 + 0.09 * vf)
                rad_prof = (sin_t ** 0.85) * (1.0 - 0.16 * max(0.0, vf - 0.52))
                span = 0.85 * (1.0 - 0.65 * (u ** 1.3))
                # Stand cleanly proud of basal shell (2..7mm) so petals overlap cleanly without z-fighting
                scale_lift = 1.0 + lift_h * (1.0 - u * 0.65) * 6.5
                for ic in range(p_cols):
                    v = (ic / (p_cols - 1)) * 2.0 - 1.0
                    a_v = a_center + v * span
                    trigonal = 1.0 + 0.075 * math.cos(3.0 * a_v)
                    edge_tuck = 0.28 + 0.72 * (1.0 - v * v)
                    r_x = rx * rad_prof * trigonal * (1.0 + (scale_lift - 1.0) * edge_tuck)
                    r_z = rz * rad_prof * trigonal * (1.0 + (scale_lift - 1.0) * edge_tuck)
                    y_p = y_shell - lift_h * 0.85 * (1.0 - u * 0.6) * edge_tuck
                    p_grid[ir][ic] = bm.verts.new((math.cos(a_v) * r_x, y_p, math.sin(a_v) * r_z))
                    vcols.append(lerp_color(c_calyx_dark, c_petal, u))
            for ir in range(p_rows - 1):
                for ic in range(p_cols - 1):
                    bm.faces.new((p_grid[ir][ic], p_grid[ir + 1][ic], p_grid[ir + 1][ic + 1], p_grid[ir][ic + 1]))

    # Short curved pedicel stem stub at stem end (-Y)
    stem_pts = [
        (Vector((0.0, -ry * 0.90, 0.0)), 0.024),
        (Vector((0.006, -ry * 1.00, 0.004)), 0.018),
        (Vector((0.014, -ry * 1.10, 0.010)), 0.014),
    ]
    append_stem_cylinder(bm, vcols, stem_pts, 8, c_stem)

    return create_mesh_with_vcol("CoconutYoung", bm, vcols, mat, col)


def build_old_coconut(mat, col):
    """Build CoconutOld: mature trigonal brown coir coconut with sharper seam ridges, striations & stem scar."""
    bm = bmesh.new()
    vcols = []

    rx, ry, rz = 0.138, 0.180, 0.134
    ang_segs = 36
    lat_rings = 24

    c_coir_light = hex_to_rgba("#6b4426")
    c_coir_mid = hex_to_rgba("#523219")
    c_coir_dark = hex_to_rgba("#3d2411")
    c_scar = hex_to_rgba("#362112")

    pole_base = bm.verts.new((0.0, -ry * 0.93, 0.0))
    vcols.append(c_scar)
    pole_tip = bm.verts.new((0.0, ry * 1.08, 0.0))
    vcols.append(c_coir_dark)

    rings = []
    for il in range(1, lat_rings):
        vf = il / lat_rings
        theta = vf * math.pi
        sin_t = math.sin(theta)
        y_val = -ry * math.cos(theta) * (1.0 + 0.08 * vf)
        rad_prof = (sin_t ** 0.86) * (1.0 - 0.18 * max(0.0, vf - 0.50))

        ring = []
        for s in range(ang_segs):
            ang = (s / ang_segs) * math.pi * 2.0
            trigonal = 1.0 + 0.095 * math.cos(3.0 * ang)
            # Fine longitudinal dried coir fiber striations
            fiber = 0.005 * math.sin(24.0 * ang + vf * 4.0)
            ca, sa = math.cos(ang), math.sin(ang)
            r_x = rx * rad_prof * trigonal + fiber
            r_z = rz * rad_prof * trigonal + fiber
            ring.append(bm.verts.new((ca * r_x, y_val, sa * r_z)))

            ridge_tone = 0.5 + 0.5 * math.cos(3.0 * ang)
            fiber_tone = 0.5 + 0.5 * math.sin(24.0 * ang + vf * 5.0)
            col_c = lerp_color(c_coir_dark, c_coir_mid, ridge_tone * 0.65 + sin_t * 0.35)
            col_c = lerp_color(col_c, c_coir_light, fiber_tone * 0.45 * sin_t)
            if vf < 0.14:
                col_c = lerp_color(c_scar, col_c, vf / 0.14)
            vcols.append(col_c)
        rings.append(ring)

    for s in range(ang_segs):
        sn = (s + 1) % ang_segs
        bm.faces.new((pole_base, rings[0][sn], rings[0][s]))
        bm.faces.new((rings[-1][s], rings[-1][sn], pole_tip))
    for il in range(len(rings) - 1):
        r0, r1 = rings[il], rings[il + 1]
        for s in range(ang_segs):
            sn = (s + 1) % ang_segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))

    # Weathered dark-brown calyx/stem scar torus around -Y end
    scar_segs = 14
    scar_r = 0.036
    scar_tube = 0.011
    scar_rings = []
    for i in range(scar_segs):
        a0 = (i / scar_segs) * math.pi * 2.0
        cx, cz = math.cos(a0) * scar_r, math.sin(a0) * scar_r
        s_ring = []
        for j in range(6):
            a1 = (j / 6.0) * math.pi * 2.0
            rad_off = scar_tube * math.cos(a1)
            y_off = -ry * 0.94 + math.sin(a1) * scar_tube
            px = math.cos(a0) * (scar_r + rad_off)
            pz = math.sin(a0) * (scar_r + rad_off)
            s_ring.append(bm.verts.new((px, y_off, pz)))
            vcols.append(c_scar)
        scar_rings.append(s_ring)
    for i in range(scar_segs):
        inext = (i + 1) % scar_segs
        r0, r1 = scar_rings[i], scar_rings[inext]
        for j in range(6):
            jn = (j + 1) % 6
            bm.faces.new((r0[j], r1[j], r1[jn], r0[jn]))

    return create_mesh_with_vcol("CoconutOld", bm, vcols, mat, col)


def setup_studio_and_viewport(studio_col):
    """Set up natural daylight harbor lighting framing both individual coconuts side-by-side."""
    world = bpy.data.worlds.new("CoconutStudioWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_rgba("#cde6f7")
        bg.inputs["Strength"].default_value = 0.80

    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 3.2
    key_data.color = (1.0, 0.96, 0.88)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(48), math.radians(16), math.radians(-38))
    studio_col.objects.link(key_obj)

    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_data.energy = 55.0
    fill_data.size = 3.0
    fill_data.color = (0.86, 0.94, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    fill_obj.location = (-1.6, -1.6, 1.4)
    fill_dir = Vector((0.0, 0.0, 0.13)) - fill_obj.location
    fill_obj.rotation_mode = "QUATERNION"
    fill_obj.rotation_quaternion = fill_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(fill_obj)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 48.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (0.18, -1.05, 0.56)
    cam_dir = Vector((0.0, 0.0, 0.12)) - cam_obj.location
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
                    space.region_3d.view_location = Vector((0.0, 0.0, 0.12))
                    space.region_3d.view_rotation = Euler((math.radians(60.0), 0.0, math.radians(12.0)), "XYZ").to_quaternion()
                    space.region_3d.view_distance = 1.15


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    c_col = bpy.data.collections.new("Coconuts")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(c_col)
    bpy.context.scene.collection.children.link(studio_col)

    mat_young = build_coconut_shader("CoconutYoungMat", roughness=0.42, bump_scale=28.0, bump_str=0.18, coat=0.28, stretch_y=0.35)
    mat_old = build_coconut_shader("CoconutOldMat", roughness=0.84, bump_scale=38.0, bump_str=0.48, coat=0.0, stretch_y=0.15)

    young_obj = build_young_coconut(mat_young, c_col)
    old_obj = build_old_coconut(mat_old, c_col)

    # Side-by-side placement for coconut.blend and preview render
    young_obj.location = (-0.20, 0.0, 0.135)
    young_obj.rotation_euler = (0.06, 0.15, -0.35)
    old_obj.location = (0.20, 0.0, 0.130)
    old_obj.rotation_euler = (-0.08, -0.22, 0.55)

    setup_studio_and_viewport(studio_col)

    total_verts = sum(len(o.data.vertices) for o in c_col.objects if o.type == "MESH")
    total_polys = sum(len(o.data.polygons) for o in c_col.objects if o.type == "MESH")
    print(f"[Coconut geometry] objects={len(c_col.objects)}, verts={total_verts}, polys={total_polys}")

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[Saved] {BLEND_PATH}")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 640
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True)
    print(f"[Rendered preview] {PREVIEW_PATH}")

    # Center both meshes strictly at local (0, 0, 0) before GLB export so Three.js clones each at exact origin
    young_obj.location = (0.0, 0.0, 0.0)
    young_obj.rotation_euler = (0.0, 0.0, 0.0)
    old_obj.location = (0.0, 0.0, 0.0)
    old_obj.rotation_euler = (0.0, 0.0, 0.0)

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
