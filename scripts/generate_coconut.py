"""Generate a realistic fallen coastal coconut cluster asset (coconut.blend & coconut.glb) in Blender 5.2."""

import math
import os
import bpy
import bmesh
from mathutils import Color, Euler, Matrix, Vector

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


def create_mesh_with_vcol(name, bm, vert_colors, material, collection, flat=False):
    """Finalize BMesh with active CoconutColor BYTE_COLOR attribute."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    for poly in mesh.polygons:
        poly.use_smooth = not flat

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


def build_coconut_material(name, roughness=0.64, bump_scale=32.0, bump_str=0.35):
    """Build procedural PBR material driven by CoconutColor with fibrous noise bump."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (660, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (340, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    vcol = nt.nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "CoconutColor"
    vcol.location = (-440, 180)
    nt.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])

    if bump_str > 0.0:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-860, -140)
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.location = (-580, -120)
        noise.inputs["Scale"].default_value = bump_scale
        noise.inputs["Detail"].default_value = 10.0
        noise.inputs["Roughness"].default_value = 0.78
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


def build_sand_and_husks(mats, col):
    """Build low sand impact depression mound, 5 shredded coir husks, and fallen dried palm stalk."""
    bm = bmesh.new()
    vcols = []

    c_sand_rim = hex_to_rgba("#d9b982")
    c_sand_hollow = hex_to_rgba("#c2a16b")
    c_husk_light = hex_to_rgba("#7a5230")
    c_husk_dark = hex_to_rgba("#5c3b20")
    c_stem = hex_to_rgba("#6e4c2e")

    # 1. Sand impact depression ring & nested base (radius = 0.42m, flat inner hollow at z=0.0)
    segs = 28
    rings_spec = [
        (0.42, -0.06, c_sand_rim),
        (0.37, 0.010, c_sand_rim),
        (0.30, 0.004, lerp_color(c_sand_rim, c_sand_hollow, 0.45)),
        (0.18, 0.000, c_sand_hollow),
    ]
    mound_rings = []
    for rad, z_val, col_r in rings_spec:
        ring = []
        for s in range(segs):
            ang = (s / segs) * math.pi * 2.0
            undul = 0.012 * math.sin(s * 3.0 + rad * 5.0)
            ring.append(bm.verts.new((math.cos(ang) * (rad + undul), math.sin(ang) * (rad + undul), z_val + undul * 0.4)))
            vcols.append(col_r)
        mound_rings.append(ring)

    for ri in range(len(mound_rings) - 1):
        r0, r1 = mound_rings[ri], mound_rings[ri + 1]
        for s in range(segs):
            sn = (s + 1) % segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))
    center_bot = bm.verts.new((0.0, 0.0, 0.002))
    vcols.append(c_sand_hollow)
    for s in range(segs):
        sn = (s + 1) % segs
        bm.faces.new((mound_rings[-1][s], mound_rings[-1][sn], center_bot))

    # 2. Five shredded fibrous coir husk strips resting beside the coconuts
    husk_specs = [
        ((-0.26, -0.22, 0.032), (0.04, 0.06, 0.55), 0.19),
        ((0.28, -0.02, 0.028), (-0.05, 0.04, -1.15), 0.17),
        ((0.03, 0.31, 0.028), (0.03, -0.05, 0.25), 0.21),
        ((-0.22, 0.14, 0.025), (0.05, 0.03, 2.20), 0.16),
        ((0.21, -0.27, 0.026), (-0.04, -0.04, -2.55), 0.15),
    ]
    for hi, (h_pos, h_rot, h_len) in enumerate(husk_specs):
        rot_m = Euler(h_rot, "XYZ").to_matrix()
        c_h = c_husk_light if hi % 2 == 0 else c_husk_dark
        h_segs = 5
        strip_l = []
        strip_m = []
        strip_r = []
        for k in range(h_segs):
            u = k / (h_segs - 1)
            lx = (u - 0.5) * h_len
            w_strip = 0.028 * (0.4 + 0.6 * math.sin(u * math.pi))
            arch_z = math.sin(u * math.pi) * 0.022
            p_c = Vector(h_pos) + rot_m @ Vector((lx, 0.0, arch_z))
            p_l = Vector(h_pos) + rot_m @ Vector((lx, -w_strip, arch_z * 0.6))
            p_r = Vector(h_pos) + rot_m @ Vector((lx, w_strip, arch_z * 0.6))
            strip_l.append(bm.verts.new(p_l))
            strip_m.append(bm.verts.new(p_c))
            strip_r.append(bm.verts.new(p_r))
            vcols.extend([c_h, lerp_color(c_h, c_husk_dark, 0.3), c_h])
        for k in range(h_segs - 1):
            bm.faces.new((strip_l[k], strip_m[k], strip_m[k + 1], strip_l[k + 1]))
            bm.faces.new((strip_m[k], strip_r[k], strip_r[k + 1], strip_m[k + 1]))

    # 3. Fallen dried brown palm fruiting stem (length = 0.65m) beside the coconuts
    stem_pts = [
        Vector((-0.34, 0.25, 0.025)),
        Vector((-0.18, 0.34, 0.038)),
        Vector((0.02, 0.37, 0.032)),
        Vector((0.20, 0.32, 0.025)),
        Vector((0.29, 0.23, 0.020)),
    ]
    stem_rings = []
    for si, pt in enumerate(stem_pts):
        tang = (stem_pts[min(len(stem_pts) - 1, si + 1)] - stem_pts[max(0, si - 1)]).normalized()
        up_r = Vector((0.0, 0.0, 1.0))
        side_r = tang.cross(up_r).normalized()
        rad_s = 0.022 * (1.0 - 0.35 * (si / (len(stem_pts) - 1)))
        ring = []
        for rs in range(6):
            ang = (rs / 6.0) * math.pi * 2.0
            ring.append(bm.verts.new(pt + (side_r * math.cos(ang) + up_r * math.sin(ang)) * rad_s))
            vcols.append(c_stem)
        stem_rings.append(ring)
    for si in range(len(stem_rings) - 1):
        r0, r1 = stem_rings[si], stem_rings[si + 1]
        for rs in range(6):
            rsn = (rs + 1) % 6
            bm.faces.new((r0[rs], r0[rsn], r1[rsn], r1[rs]))
    bm.faces.new(list(reversed(stem_rings[0])))
    bm.faces.new(stem_rings[-1])

    create_mesh_with_vcol("CoconutSandAndHusks", bm, vcols, mats["husk"], col, flat=True)


def append_trigonal_coconut(bm, vcols, center, radii_xyz, rot_euler, col_base, col_tip, col_calyx):
    """Append a realistic 3-lobed trigonal coconut with tapered tip and 5-pointed calyx cap."""
    xf = Matrix.Translation(Vector(center)) @ Euler(rot_euler, "XYZ").to_matrix().to_4x4()
    rx, ry, rz = radii_xyz
    ang_segs = 18
    lat_rings = 14

    rings = []
    pole_base = bm.verts.new(xf @ Vector((0.0, -ry, 0.0)))
    vcols.append(col_calyx)
    pole_tip = bm.verts.new(xf @ Vector((0.0, ry * 1.05, 0.0)))
    vcols.append(col_tip)

    for il in range(1, lat_rings):
        vf = il / lat_rings
        theta = vf * math.pi
        sin_t = math.sin(theta)
        # Asymmetric oval silhouette: broad belly near basal end (vf~0.35), tapered tip (vf>0.7)
        y_local = -ry * math.cos(theta) * (1.0 + 0.08 * vf)
        rad_profile = (sin_t ** 0.88) * (1.0 - 0.14 * max(0.0, vf - 0.55))

        col_ring = col_calyx if vf < 0.12 else lerp_color(col_base, col_tip, max(0.0, (vf - 0.12) / 0.88))
        ring = []
        for s in range(ang_segs):
            ang = (s / ang_segs) * math.pi * 2.0
            trigonal = 1.0 + 0.085 * math.cos(3.0 * ang)
            # 5-pointed calyx sepal petal ridge around vf < 0.16
            calyx_ridge = 0.07 * max(0.0, math.cos(5.0 * ang)) if vf < 0.16 else 0.0
            ca, sa = math.cos(ang), math.sin(ang)
            px = ca * rx * rad_profile * (trigonal + calyx_ridge)
            pz = sa * rz * rad_profile * (trigonal + calyx_ridge)
            ring.append(bm.verts.new(xf @ Vector((px, y_local, pz))))
            vcols.append(col_ring)
        rings.append(ring)

    # Connect poles and rings
    for s in range(ang_segs):
        sn = (s + 1) % ang_segs
        bm.faces.new((pole_base, rings[0][sn], rings[0][s]))
        bm.faces.new((rings[-1][s], rings[-1][sn], pole_tip))
    for il in range(len(rings) - 1):
        r0, r1 = rings[il], rings[il + 1]
        for s in range(ang_segs):
            sn = (s + 1) % ang_segs
            bm.faces.new((r0[s], r0[sn], r1[sn], r1[s]))


def build_whole_coconuts(mats, col):
    """Build 3 whole trigonal coconuts (fresh green-gold, sun-ripened amber, and fibrous brown)."""
    bm = bmesh.new()
    vcols = []

    c_calyx = hex_to_rgba("#4a3520")
    whole_specs = [
        # (center, radii_xyz, rot_euler, col_base, col_tip)
        ((-0.16, -0.06, 0.115), (0.135, 0.175, 0.135), (0.14, 0.22, -0.45), hex_to_rgba("#4e8032"), hex_to_rgba("#9c9436")),
        ((0.15, 0.14, 0.110), (0.132, 0.168, 0.130), (-0.12, -0.18, 1.35), hex_to_rgba("#b57a32"), hex_to_rgba("#8c5622")),
        ((-0.05, 0.20, 0.112), (0.130, 0.165, 0.128), (0.18, -0.24, 2.60), hex_to_rgba("#5e3c22"), hex_to_rgba("#422815")),
    ]
    for pos, radii, rot, c_a, c_b in whole_specs:
        append_trigonal_coconut(bm, vcols, pos, radii, rot, c_a, c_b, c_calyx)

    create_mesh_with_vcol("WholeCoconuts", bm, vcols, mats["whole"], col)


def append_cracked_coconut_half(bm, vcols, center, rot_euler, scale=1.0):
    """Append a thick-walled cracked coconut cup half showing coir shell, dark endocarp rim, and white flesh."""
    xf = Matrix.Translation(Vector(center)) @ Euler(rot_euler, "XYZ").to_matrix().to_4x4()

    c_husk_out = hex_to_rgba("#5c3a20")
    c_shell_rim = hex_to_rgba("#362012")
    c_meat_rim = hex_to_rgba("#f7f4eb")
    c_meat_inner = hex_to_rgba("#e3dccb")

    segs = 28
    r_outer = 0.132 * scale
    r_shell = 0.114 * scale
    r_meat = 0.090 * scale
    h_depth = 0.132 * scale
    h_inner = 0.102 * scale

    # Outer coir cup bottom pole -> mid -> jagged equatorial rim -> endocarp rim -> meat rim -> inner meat bowl
    pole_out = bm.verts.new(xf @ Vector((0.0, 0.0, -h_depth)))
    vcols.append(c_husk_out)
    pole_in = bm.verts.new(xf @ Vector((0.0, 0.0, -h_inner)))
    vcols.append(c_meat_inner)

    rings_out_low = []
    rings_out_rim = []
    rings_shell_rim = []
    rings_meat_rim = []
    rings_meat_low = []

    for s in range(segs):
        ang = (s / segs) * math.pi * 2.0
        ca, sa = math.cos(ang), math.sin(ang)
        trig = 1.0 + 0.060 * math.cos(3.0 * ang)
        jag = 0.007 * math.sin(ang * 4.0 + 0.7) + 0.004 * math.cos(ang * 7.0)

        rings_out_low.append(bm.verts.new(xf @ Vector((ca * r_outer * 0.78 * trig, sa * r_outer * 0.78 * trig, -h_depth * 0.68))))
        vcols.append(c_husk_out)

        rings_out_rim.append(bm.verts.new(xf @ Vector((ca * r_outer * trig, sa * r_outer * trig, jag))))
        vcols.append(lerp_color(c_husk_out, c_shell_rim, 0.45))

        rings_shell_rim.append(bm.verts.new(xf @ Vector((ca * r_shell * trig, sa * r_shell * trig, jag + 0.003))))
        vcols.append(c_shell_rim)

        rings_meat_rim.append(bm.verts.new(xf @ Vector((ca * r_meat, sa * r_meat, jag * 0.7 + 0.002))))
        vcols.append(c_meat_rim)

        rings_meat_low.append(bm.verts.new(xf @ Vector((ca * r_meat * 0.65, sa * r_meat * 0.65, -h_inner * 0.68))))
        vcols.append(lerp_color(c_meat_rim, c_meat_inner, 0.6))

    for s in range(segs):
        sn = (s + 1) % segs
        bm.faces.new((pole_out, rings_out_low[s], rings_out_low[sn]))
        bm.faces.new((rings_out_low[s], rings_out_rim[s], rings_out_rim[sn], rings_out_low[sn]))
        bm.faces.new((rings_out_rim[s], rings_shell_rim[s], rings_shell_rim[sn], rings_out_rim[sn]))
        bm.faces.new((rings_shell_rim[s], rings_meat_rim[s], rings_meat_rim[sn], rings_shell_rim[sn]))
        bm.faces.new((rings_meat_rim[s], rings_meat_low[s], rings_meat_low[sn], rings_meat_rim[sn]))
        bm.faces.new((rings_meat_low[s], rings_meat_low[sn], pole_in))


def build_split_coconut_halves(mats, col):
    """Build 2 cracked-open coconut cup halves revealing thick creamy-white meat inside dark shell rims."""
    bm = bmesh.new()
    vcols = []

    append_cracked_coconut_half(bm, vcols, center=(0.15, -0.15, 0.122), rot_euler=(-0.50, -0.18, 0.55), scale=1.02)
    append_cracked_coconut_half(bm, vcols, center=(-0.02, -0.24, 0.114), rot_euler=(-0.38, 0.34, -0.95), scale=0.92)

    create_mesh_with_vcol("SplitCoconutHalves", bm, vcols, mats["split"], col)


def setup_studio_and_viewport(studio_col):
    """Set up natural sunlit harbor lighting and close-up framing for coconut_preview.png and coconut.blend."""
    world = bpy.data.worlds.new("CoconutStudioWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = hex_to_rgba("#cde6f7")
        bg.inputs["Strength"].default_value = 0.78

    key_data = bpy.data.lights.new("KeySun", type="SUN")
    key_data.energy = 3.2
    key_data.color = (1.0, 0.96, 0.88)
    key_obj = bpy.data.objects.new("KeySun", key_data)
    key_obj.rotation_euler = (math.radians(48), math.radians(16), math.radians(-38))
    studio_col.objects.link(key_obj)

    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_data.energy = 60.0
    fill_data.size = 3.0
    fill_data.color = (0.86, 0.94, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    fill_obj.location = (-1.8, -1.8, 1.6)
    fill_dir = Vector((0.0, 0.0, 0.08)) - fill_obj.location
    fill_obj.rotation_mode = "QUATERNION"
    fill_obj.rotation_quaternion = fill_dir.to_track_quat("-Z", "Y")
    studio_col.objects.link(fill_obj)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = 45.0
    cam_obj = bpy.data.objects.new("PreviewCamera", cam_data)
    cam_obj.location = (0.72, -1.18, 0.78)
    cam_dir = Vector((0.0, 0.0, 0.08)) - cam_obj.location
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
                    space.region_3d.view_location = Vector((0.0, 0.0, 0.08))
                    space.region_3d.view_rotation = Euler((math.radians(56.0), 0.0, math.radians(28.0)), "XYZ").to_quaternion()
                    space.region_3d.view_distance = 1.45


def main():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    c_col = bpy.data.collections.new("CoconutCluster")
    studio_col = bpy.data.collections.new("Studio")
    bpy.context.scene.collection.children.link(c_col)
    bpy.context.scene.collection.children.link(studio_col)

    mats = {
        "husk": build_coconut_material("CoconutSandHuskMat", roughness=0.86, bump_scale=42.0, bump_str=0.45),
        "whole": build_coconut_material("WholeCoconutMat", roughness=0.64, bump_scale=30.0, bump_str=0.35),
        "split": build_coconut_material("SplitCoconutMat", roughness=0.42, bump_scale=34.0, bump_str=0.22),
    }

    build_sand_and_husks(mats, c_col)
    build_whole_coconuts(mats, c_col)
    build_split_coconut_halves(mats, c_col)
    setup_studio_and_viewport(studio_col)

    total_verts = sum(len(o.data.vertices) for o in c_col.objects if o.type == "MESH")
    total_polys = sum(len(o.data.polygons) for o in c_col.objects if o.type == "MESH")
    print(f"[Coconut geometry] objects={len(c_col.objects)}, verts={total_verts}, polys={total_polys}")

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[Saved] {BLEND_PATH}")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 750
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
