"""Generate smooth organic 3D assets in Blender 5.2 and export .blend + .glb files."""

import math
import os
import bpy
import bmesh
from mathutils import Euler, Matrix, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_DIR = os.path.join(BASE_DIR, "assets", "blend")
MODEL_DIR = os.path.join(BASE_DIR, "assets", "models")

os.makedirs(BLEND_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)


def reset_scene():
    """Reset Blender to a clean empty scene."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def hex_to_rgba(hex_str, alpha=1.0):
    """Convert hex color string (#RRGGBB) to linear RGBA tuple for Blender."""
    s = hex_str.lstrip("#")
    r, g, b = (int(s[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

    def srgb_to_linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), alpha)


def make_material(
    name,
    base_color,
    roughness=0.6,
    metallic=0.0,
    emission_color=None,
    emission_strength=0.0,
    coat=0.0,
    alpha=1.0,
    use_vertex_color=False,
    double_sided=False,
):
    """Create a Principled BSDF material compatible with glTF 2.0 export."""
    mat = bpy.data.materials.new(name=name)
    if double_sided and hasattr(mat, "use_backface_culling"):
        mat.use_backface_culling = False
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")

    if use_vertex_color:
        vcol = nt.nodes.new("ShaderNodeVertexColor")
        vcol.layer_name = "Col"
        nt.links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        rgba = hex_to_rgba(base_color, alpha) if isinstance(base_color, str) else base_color
        bsdf.inputs["Base Color"].default_value = rgba

    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = "BLEND" if hasattr(mat, "blend_method") else "OPAQUE"

    if emission_strength > 0.0 and emission_color is not None:
        ergba = hex_to_rgba(emission_color, 1.0) if isinstance(emission_color, str) else emission_color
        bsdf.inputs["Emission Color"].default_value = ergba
        bsdf.inputs["Emission Strength"].default_value = emission_strength

    return mat


def link_object(obj, parent=None):
    """Link an object to the active scene collection and optionally parent it."""
    bpy.context.scene.collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def set_smooth(obj):
    """Enable smooth shading across all faces of a mesh object."""
    if obj.type == "MESH" and obj.data is not None:
        for poly in obj.data.polygons:
            poly.use_smooth = True


def add_subsurf(obj, levels=2, render_levels=2):
    """Attach a Catmull-Clark Subdivision Surface modifier."""
    mod = obj.modifiers.new(name="Subsurf", type="SUBSURF")
    mod.levels = levels
    mod.render_levels = render_levels
    set_smooth(obj)
    return mod


def add_bevel(obj, width=0.03, segments=3):
    """Attach a Bevel modifier for rounded edges."""
    mod = obj.modifiers.new(name="Bevel", type="BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(30)
    set_smooth(obj)
    return mod


def create_mesh_object(name, bm, material=None, parent=None):
    """Finalize a BMesh into a Blender object linked to the scene."""
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    if material is not None:
        obj.data.materials.append(material)
    link_object(obj, parent=parent)
    set_smooth(obj)
    return obj


def make_grid_surface(name, nx, ny, vertex_fn, material, parent=None):
    """Build a subdivided rectangular grid displaced by vertex_fn(u, v) -> Vector."""
    bm = bmesh.new()
    grid = [[None] * (nx + 1) for _ in range(ny + 1)]
    for iy in range(ny + 1):
        v = iy / ny
        for ix in range(nx + 1):
            u = ix / nx
            grid[iy][ix] = bm.verts.new(vertex_fn(u, v))
    for iy in range(ny):
        for ix in range(nx):
            bm.faces.new((grid[iy][ix], grid[iy][ix + 1], grid[iy + 1][ix + 1], grid[iy + 1][ix]))
    return create_mesh_object(name, bm, material=material, parent=parent)


def make_cylinder_along(name, p0, p1, r0, r1, segments=16, material=None, parent=None, cap=True):
    """Create a smooth tapered cylinder oriented from p0 to p1."""
    v0 = Vector(p0)
    v1 = Vector(p1)
    vec = v1 - v0
    length = vec.length
    mid = (v0 + v1) * 0.5

    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=cap,
        cap_tris=False,
        segments=segments,
        radius1=r0,
        radius2=r1,
        depth=length,
    )
    obj = create_mesh_object(name, bm, material=material, parent=parent)
    obj.location = mid
    if length > 1e-6:
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = vec.normalized().to_track_quat("Z", "Y")
    return obj


def save_and_export(name):
    """Save editable .blend file and export web-ready .glb file."""
    blend_path = os.path.join(BLEND_DIR, f"{name}.blend")
    glb_path = os.path.join(MODEL_DIR, f"{name}.glb")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    bpy.ops.export_scene.gltf(
        filepath=glb_path,
        export_format="GLB",
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_attributes=True,
        export_vertex_color="ACTIVE",
        export_all_vertex_colors=True,
    )
    print(f"[Generated] {name}: {blend_path} & {glb_path}")


# ---------------------------------------------------------------------------
# 1. SAILBOAT (bow +Y in Blender -> -Z forward in Three.js)
# ---------------------------------------------------------------------------
def build_sailboat():
    reset_scene()

    mat_hull = make_material("HullNavy", "#16375b", roughness=0.28, coat=0.4)
    mat_keel = make_material("KeelCopper", "#8c2d25", roughness=0.48)
    mat_trim = make_material("GunwaleAmber", "#e08214", roughness=0.38, coat=0.2)
    mat_deck = make_material("TeakDeck", "#c88a51", roughness=0.72)
    mat_wood = make_material("MahoganyWood", "#6b3e21", roughness=0.68)
    mat_sail = make_material("SailCanvas", "#fbf6ec", roughness=0.58, double_sided=True)
    mat_brass = make_material("BrassMetal", "#d4a448", roughness=0.28, metallic=0.85)
    mat_buoy = make_material("LifeRingCoral", "#e8533f", roughness=0.45)
    mat_bulb = make_material("BowBulb", "#ffd584", roughness=0.2, emission_color="#ff9d2e", emission_strength=2.2)

    # Lofted organic hull (stations from stern y=-3.0 to bow y=+3.5)
    # Each station defines cross-section from port gunwale -> keel -> starboard gunwale
    stations = [
        (-3.00, 0.88, 0.72, 0.22, -0.18),
        (-2.10, 1.12, 0.68, 0.25, -0.35),
        (-0.80, 1.24, 0.66, 0.26, -0.44),
        (0.60, 1.15, 0.68, 0.24, -0.42),
        (1.90, 0.84, 0.74, 0.16, -0.30),
        (2.85, 0.42, 0.86, 0.07, -0.12),
        (3.55, 0.04, 1.02, 0.00, 0.28),
    ]

    bm = bmesh.new()
    rings = []
    n_arc = 12  # half-profile samples per side -> 2*n_arc + 1 verts per station
    for y_pos, half_beam, sheer_z, chine_x, keel_z in stations:
        ring = []
        for idx in range(n_arc * 2 + 1):
            t = (idx / n_arc) - 1.0  # -1 (port gunwale) .. 0 (keel) .. +1 (starboard gunwale)
            u = abs(t)
            # Smooth U/V hull cross section
            x = math.copysign(half_beam * math.sin(u * math.pi * 0.5), t)
            # Blend keel to sheer smoothly
            z = keel_z + (sheer_z - keel_z) * (u ** 1.65)
            # Subtle flare near gunwale
            if u > 0.7:
                x *= 1.0 + 0.05 * (u - 0.7)
            ring.append(bm.verts.new((x, y_pos, z)))
        rings.append(ring)

    for s in range(len(rings) - 1):
        r0, r1 = rings[s], rings[s + 1]
        for j in range(len(r0) - 1):
            bm.faces.new((r0[j], r1[j], r1[j + 1], r0[j + 1]))

    # Transom stern closure
    stern_ring = rings[0]
    stern_top = bm.verts.new((0.0, -3.00, 0.66))
    for j in range(len(stern_ring) - 1):
        bm.faces.new((stern_ring[j + 1], stern_ring[j], stern_top))

    # Solidify slightly for hull wall thickness & bevel
    hull_obj = create_mesh_object("BoatHull", bm, material=mat_hull)
    sol = hull_obj.modifiers.new("Solidify", "SOLIDIFY")
    sol.thickness = 0.08
    sol.offset = -1.0
    add_subsurf(hull_obj, levels=2, render_levels=2)

    # Lower copper anti-fouling keel fin
    bm_keel = bmesh.new()
    bmesh.ops.create_cube(bm_keel, size=1.0)
    for v in bm_keel.verts:
        v.co.x *= 0.16
        v.co.y *= 2.2
        v.co.z = (v.co.z - 0.5) * 0.75 - 0.35
        if v.co.z < -0.7:
            v.co.y *= 0.72
    keel_obj = create_mesh_object("BoatKeel", bm_keel, material=mat_keel)
    keel_obj.location = (0, -0.25, 0)
    add_subsurf(keel_obj, levels=2, render_levels=2)

    # Gunwale rubrail curve along both sides
    for side in (-1, 1):
        curve_data = bpy.data.curves.new(f"Rubrail_{side}", type="CURVE")
        curve_data.dimensions = "3D"
        curve_data.bevel_depth = 0.055
        curve_data.bevel_resolution = 4
        spline = curve_data.splines.new("NURBS")
        pts = [(side * hb * 1.02, yp, sz + 0.02) for (yp, hb, sz, _, _) in stations]
        spline.points.add(len(pts) - 1)
        for idx, (px, py, pz) in enumerate(pts):
            spline.points[idx].co = (px, py, pz, 1.0)
        spline.use_endpoint_u = True
        rub_obj = bpy.data.objects.new(f"GunwaleTrim_{side}", curve_data)
        rub_obj.data.materials.append(mat_trim)
        link_object(rub_obj)

    # Recessed teak deck matching stations
    bm_deck = bmesh.new()
    deck_rows = []
    for y_pos, half_beam, sheer_z, _, _ in stations:
        row = []
        for ix in range(9):
            t = (ix / 4.0) - 1.0
            row.append(bm_deck.verts.new((t * half_beam * 0.90, y_pos * 0.98, sheer_z - 0.14 + (1 - t * t) * 0.05)))
        deck_rows.append(row)
    for s in range(len(deck_rows) - 1):
        for j in range(len(deck_rows[s]) - 1):
            bm_deck.faces.new((deck_rows[s][j], deck_rows[s + 1][j], deck_rows[s + 1][j + 1], deck_rows[s][j + 1]))
    deck_obj = create_mesh_object("BoatDeck", bm_deck, material=mat_deck)
    add_subsurf(deck_obj, levels=1, render_levels=1)

    # Contoured cockpit benches
    for name, by, bw, bd in [("BenchFront", -0.65, 1.65, 0.54), ("BenchRear", -2.15, 1.38, 0.56)]:
        bm_b = bmesh.new()
        bmesh.ops.create_cube(bm_b, size=1.0)
        for v in bm_b.verts:
            v.co.x *= bw
            v.co.y *= bd
            v.co.z *= 0.22
        bench = create_mesh_object(name, bm_b, material=mat_wood)
        bench.location = (0, by, 0.72)
        add_bevel(bench, width=0.04, segments=3)

    # Rudder & curved tiller pivoted at (0, -3.15, 0.35) -> (0, 0.35, 3.15) in Three.js
    rudder_pivot = bpy.data.objects.new("Rudder", None)
    rudder_pivot.location = (0.0, -3.15, 0.35)
    link_object(rudder_pivot)

    bm_rud = bmesh.new()
    bmesh.ops.create_cube(bm_rud, size=1.0)
    for v in bm_rud.verts:
        v.co.x *= 0.09
        v.co.y = (v.co.y - 0.5) * 0.62
        v.co.z = v.co.z * 0.95 - 0.12
    rud_blade = create_mesh_object("RudderBlade", bm_rud, material=mat_wood, parent=rudder_pivot)
    add_bevel(rud_blade, width=0.02, segments=2)

    tiller = make_cylinder_along(
        "RudderTiller", (0, 0.0, 0.52), (0, 1.05, 0.68), 0.045, 0.032, segments=16, material=mat_wood, parent=rudder_pivot
    )
    add_bevel(tiller, width=0.01, segments=2)

    # Mast, Boom & Bowsprit
    make_cylinder_along("Mast", (0, 0.55, 0.55), (0, 0.55, 7.15), 0.11, 0.06, segments=14, material=mat_wood)
    make_cylinder_along("Boom", (0, 0.52, 1.85), (0, -2.55, 1.98), 0.065, 0.05, segments=12, material=mat_wood)
    make_cylinder_along("Bowsprit", (0, 2.75, 0.92), (0, 4.15, 1.28), 0.065, 0.042, segments=10, material=mat_wood)

    # Smooth wind-bellied Mainsail
    def main_sail_fn(u, v):
        # u: 0 (mast luff) -> 1 (leech), v: 0 (foot) -> 1 (head)
        foot_len = 2.95 * (1.0 - v ** 1.18)
        y = 0.48 - u * foot_len
        z = 1.92 + v * 4.85 + (1 - v) * 0.12 * u
        billow = math.sin(u * math.pi) * math.sin(v * math.pi * 0.92 + 0.15) * 0.34
        return Vector((billow, y, z))

    main_sail = make_grid_surface("MainSail", 16, 20, main_sail_fn, mat_sail)
    add_subsurf(main_sail, levels=1, render_levels=1)

    # Smooth wind-bellied Jib Sail
    def jib_sail_fn(u, v):
        # u: 0 (forestay) -> 1 (clew/leech), v: 0 (foot) -> 1 (head)
        y_stay = 3.85 + (0.62 - 3.85) * v
        z_stay = 1.25 + (6.35 - 1.25) * v
        y_back = 0.72 + (0.62 - 0.72) * v
        z_back = 1.55 + (6.35 - 1.55) * v
        y = y_stay + (y_back - y_stay) * u
        z = z_stay + (z_back - z_stay) * u
        billow = math.sin(u * math.pi) * math.sin(v * math.pi * 0.9 + 0.15) * 0.25 * (1.0 - v * 0.6)
        return Vector((billow, y, z))

    jib_sail = make_grid_surface("JibSail", 14, 18, jib_sail_fn, mat_sail)
    add_subsurf(jib_sail, levels=1, render_levels=1)

    # Bow lantern & stern life buoy
    make_cylinder_along("BowLanternPost", (0, 3.05, 0.90), (0, 3.05, 1.32), 0.04, 0.035, segments=10, material=mat_brass)
    bm_bulb = bmesh.new()
    bmesh.ops.create_uvsphere(bm_bulb, u_segments=14, v_segments=10, radius=0.13)
    bulb = create_mesh_object("BowLanternBulb", bm_bulb, material=mat_bulb)
    bulb.location = (0, 3.05, 1.42)

    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.28, minor_radius=0.075, major_segments=24, minor_segments=12, location=(0.95, -1.85, 0.85)
    )
    buoy = bpy.context.active_object
    buoy.name = "LifeBuoy"
    buoy.rotation_euler = (0.2, 1.15, 0.0)
    buoy.data.materials.append(mat_buoy)
    set_smooth(buoy)

    save_and_export("sailboat")


# ---------------------------------------------------------------------------
# 2. ISLAND (with smooth vertex-colored sandy beach cove facing -Y -> +Z)
# ---------------------------------------------------------------------------
def island_elevation(bx, by):
    """Smooth island terrain height matching scene.js cove facing -Y (Three.js +Z)."""
    lz = -by
    cove_factor = max(0.0, (lz - 4.0) * 0.25) if lz > 4.0 else 0.0
    eff_dist = math.hypot(bx * 0.95, lz * 1.05 + cove_factor)
    base = max(0.0, 1.0 - eff_dist / 22.5)
    hill = (base ** 1.55) * 5.2
    ridge = math.sin(bx * 0.22) * math.cos(lz * 0.19) * 0.35 * base
    return hill + ridge - 1.15


def build_island():
    reset_scene()
    mat_island = make_material("IslandTerrain", "#ebd19b", roughness=0.88, use_vertex_color=True)

    size = 66.0
    segs = 72
    bm = bmesh.new()
    verts = [[None] * (segs + 1) for _ in range(segs + 1)]
    for iy in range(segs + 1):
        by = (iy / segs - 0.5) * size
        for ix in range(segs + 1):
            bx = (ix / segs - 0.5) * size
            bz = island_elevation(bx, by)
            verts[iy][ix] = bm.verts.new((bx, by, bz))
    for iy in range(segs):
        for ix in range(segs):
            bm.faces.new((verts[iy][ix], verts[iy][ix + 1], verts[iy + 1][ix + 1], verts[iy + 1][ix]))

    island_obj = create_mesh_object("IslandTerrain", bm, material=mat_island)
    mesh = island_obj.data
    col_attr = mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")

    wet_sand = hex_to_rgba("#c4a06e")
    dry_sand = hex_to_rgba("#ebd19b")
    grass = hex_to_rgba("#4d8740")

    def lerp_c(c1, c2, t):
        t = max(0.0, min(1.0, t))
        return tuple(c1[k] + (c2[k] - c1[k]) * t for k in range(4))

    for idx, v in enumerate(mesh.vertices):
        elev = v.co.z
        if elev < 0.35:
            c = wet_sand
        elif elev < 2.25:
            c = lerp_c(wet_sand, dry_sand, (elev - 0.35) / 1.9)
        else:
            c = lerp_c(dry_sand, grass, (elev - 2.25) / 0.85)
        col_attr.data[idx].color = c

    add_subsurf(island_obj, levels=1, render_levels=1)
    save_and_export("island")


# ---------------------------------------------------------------------------
# 3. PALM TREE (with PalmCrown pivot for smooth wind swaying)
# ---------------------------------------------------------------------------
def build_palm_tree():
    reset_scene()
    mat_trunk = make_material("PalmTrunk", "#6d4c33", roughness=0.90)
    mat_frond_a = make_material("PalmFrondDark", "#398537", roughness=0.68, double_sided=True)
    mat_frond_b = make_material("PalmFrondLight", "#4c9c43", roughness=0.65, double_sided=True)
    mat_coconut = make_material("Coconut", "#54351e", roughness=0.82)

    # Organic curved segmented palm trunk using ring lofting
    bm_trunk = bmesh.new()
    rings = []
    n_rings = 18
    n_sides = 14
    top_pos = Vector((0.0, 0.0, 0.0))

    for i in range(n_rings + 1):
        t = i / n_rings
        cx = math.sin(t * math.pi * 0.65) * 0.45
        cy = math.sin(t * math.pi * 0.4) * 0.18
        cz = t * 5.8
        # Slight ring ridges for authentic palm bark silhouette
        bark_ridge = 1.0 + 0.06 * math.sin(t * 28.0)
        radius = (0.31 - t * 0.16) * bark_ridge
        center = Vector((cx, cy, cz))
        top_pos = center

        ring = []
        for s in range(n_sides):
            ang = (s / n_sides) * math.PI * 2 if hasattr(math, "PI") else (s / n_sides) * math.pi * 2
            ring.append(bm_trunk.verts.new(center + Vector((math.cos(ang) * radius, math.sin(ang) * radius, 0.0))))
        rings.append(ring)

    for i in range(n_rings):
        r0, r1 = rings[i], rings[i + 1]
        for s in range(n_sides):
            sn = (s + 1) % n_sides
            bm_trunk.faces.new((r0[s], r0[sn], r1[sn], r1[s]))

    trunk_obj = create_mesh_object("PalmTrunk", bm_trunk, material=mat_trunk)
    add_subsurf(trunk_obj, levels=1, render_levels=1)

    crown = bpy.data.objects.new("PalmCrown", None)
    crown.location = top_pos
    link_object(crown)

    # 4 coconuts nestled under crown
    for c in range(4):
        ang = (c / 4.0) * math.pi * 2 + 0.35
        bm_coco = bmesh.new()
        bmesh.ops.create_uvsphere(bm_coco, u_segments=12, v_segments=10, radius=0.19)
        coco = create_mesh_object(f"Coconut_{c}", bm_coco, material=mat_coconut, parent=crown)
        coco.location = (math.cos(ang) * 0.25, math.sin(ang) * 0.25, -0.18)
        coco.scale = (1.0, 1.0, 1.15)
        add_subsurf(coco, levels=1, render_levels=1)

    # 9 gracefully arched pinnate fronds
    frond_count = 9
    for f in range(frond_count):
        yaw = (f / frond_count) * math.pi * 2 + (0.18 if f % 2 else 0.0)
        pitch_lift = 0.28 + (f % 3) * 0.14
        frond_len = 2.85 + (f % 2) * 0.25
        mat = mat_frond_a if f % 2 == 0 else mat_frond_b

        def frond_fn(u, v, fl=frond_len, lift=pitch_lift):
            # u: 0..1 width across frond, v: 0..1 along frond length
            spread = (u - 0.5) * 0.92 * math.sin(v * math.pi)
            # Rib arches up first then droops gracefully
            y = v * fl
            z = math.sin(v * math.pi * 0.75) * lift * 1.4 - (v ** 2.15) * 1.25
            # V-trough fold along central rib
            z -= abs(u - 0.5) * 0.22 * math.sin(v * math.pi)
            return Vector((spread, y, z))

        frond_obj = make_grid_surface(f"PalmFrond_{f}", 6, 14, frond_fn, mat, parent=crown)
        frond_obj.rotation_euler = (0.0, 0.0, yaw)
        add_subsurf(frond_obj, levels=1, render_levels=1)

    save_and_export("palm_tree")


# ---------------------------------------------------------------------------
# 4. PIER (y = -4 to +19.5 in Blender -> z = -19.5 to +4 in Three.js, connected to beach)
# ---------------------------------------------------------------------------
def build_pier():
    reset_scene()
    mat_plank = make_material("PierPlankWood", "#875938", roughness=0.84)
    mat_post = make_material("PierPostWood", "#593923", roughness=0.88)
    mat_rope = make_material("MooringRope", "#c5a97c", roughness=0.92)
    mat_metal = make_material("LanternIron", "#1e293b", roughness=0.45, metallic=0.6)
    mat_glass = make_material("PierLanternGlass", "#ffdf9e", roughness=0.2, emission_color="#ff9d2e", emission_strength=2.0)

    # Main level pier planks spanning y = -4.0 (bay head) to y = +15.60 (shoreline)
    y_vals = [-4.0 + i * 0.56 for i in range(36)]
    for idx, yp in enumerate(y_vals):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 3.15
            v.co.y *= 0.48
            v.co.z *= 0.13
        plank = create_mesh_object(f"PierPlank_{idx}", bm, material=mat_plank)
        jitter_z = math.sin(idx * 2.1) * 0.012
        plank.location = (0.0, yp, 1.15 + jitter_z)
        add_bevel(plank, width=0.025, segments=2)

    # Sloped wooden ramp planks descending smoothly into the rising dry beach sand
    for r_idx in range(7):
        yp = 16.16 + r_idx * 0.56
        zp = 1.11 - (r_idx + 1) * 0.055
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 3.15
            v.co.y *= 0.49
            v.co.z *= 0.13
        plank = create_mesh_object(f"PierRampPlank_{r_idx}", bm, material=mat_plank)
        plank.location = (0.0, yp, zp)
        plank.rotation_euler = (-0.098, 0.0, 0.0)
        add_bevel(plank, width=0.025, segments=2)

    # Longitudinal stringer beams for main deck and sloped ramp
    for sx in (-1.15, 1.15):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 0.22
            v.co.y *= 19.9
            v.co.z *= 0.24
        beam = create_mesh_object(f"PierBeam_{sx}", bm, material=mat_post)
        beam.location = (sx, 5.75, 0.96)
        add_bevel(beam, width=0.025, segments=2)

        ramp_beam = make_cylinder_along(
            f"PierRampBeam_{sx}", (sx, 15.6, 0.96), (sx, 19.6, 0.62), 0.11, 0.11, segments=10, material=mat_post
        )
        add_bevel(ramp_beam, width=0.02, segments=2)

    # Pilings, bollards, rope wraps & pier-head lanterns
    post_y_list = [-3.6, 0.2, 4.0, 7.8, 11.6, 15.4, 19.0]
    for p_idx, py in enumerate(post_y_list):
        is_head = p_idx == 0
        is_shore = p_idx == len(post_y_list) - 1
        top_z = 2.65 if is_head else (1.65 if is_shore else 1.85)
        for side_idx, px in enumerate((-1.42, 1.42)):
            post = make_cylinder_along(
                f"PierPost_{p_idx}_{side_idx}", (px, py, -1.5), (px, py, top_z), 0.16, 0.13, segments=14, material=mat_post
            )
            add_bevel(post, width=0.02, segments=2)

            # Rope collar around piling
            rope_z = 1.38 if is_shore else 1.55
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.16, minor_radius=0.032, major_segments=16, minor_segments=8, location=(px, py, rope_z)
            )
            rope = bpy.context.active_object
            rope.name = f"PierRope_{p_idx}_{side_idx}"
            rope.data.materials.append(mat_rope)
            set_smooth(rope)

            if is_head:
                inward_x = px - 0.34 if px > 0 else px + 0.34
                make_cylinder_along(
                    f"LanternArm_{side_idx}", (px, py, 2.55), (inward_x, py, 2.55), 0.04, 0.035, segments=10, material=mat_metal
                )
                bm_cap = bmesh.new()
                bmesh.ops.create_cone(bm_cap, cap_ends=True, segments=12, radius1=0.22, radius2=0.04, depth=0.14)
                cap = create_mesh_object(f"LanternCap_{side_idx}", bm_cap, material=mat_metal)
                cap.location = (inward_x, py, 2.52)

                bm_bulb = bmesh.new()
                bmesh.ops.create_uvsphere(bm_bulb, u_segments=14, v_segments=10, radius=0.15)
                bulb_name = "PierLantern_L" if px < 0 else "PierLantern_R"
                bulb = create_mesh_object(bulb_name, bm_bulb, material=mat_glass)
                bulb.location = (inward_x, py, 2.34)

    save_and_export("pier")


# ---------------------------------------------------------------------------
# 5. LIGHTHOUSE
# ---------------------------------------------------------------------------
def build_lighthouse():
    reset_scene()
    mat_white = make_material("LighthouseWhite", "#f3f6fa", roughness=0.65)
    mat_red = make_material("LighthouseRed", "#cf3f33", roughness=0.62)
    mat_stone = make_material("LighthouseBase", "#707882", roughness=0.88)
    mat_iron = make_material("LighthouseIron", "#1e293b", roughness=0.45, metallic=0.65)
    mat_glass = make_material("LighthouseGlassMat", "#ffe8a3", roughness=0.15, emission_color="#ffc14d", emission_strength=2.2)

    # Stone plinth
    plinth = make_cylinder_along("LHBase", (0, 0, -0.3), (0, 0, 1.0), 2.05, 1.82, segments=24, material=mat_stone)
    add_bevel(plinth, width=0.04, segments=2)

    # Smooth tapered tower sections
    sec1 = make_cylinder_along("LHTowerLow", (0, 0, 1.0), (0, 0, 4.7), 1.72, 1.32, segments=36, material=mat_white)
    sec2 = make_cylinder_along("LHTowerMid", (0, 0, 4.7), (0, 0, 7.6), 1.32, 1.06, segments=36, material=mat_red)
    sec3 = make_cylinder_along("LHTowerTop", (0, 0, 7.6), (0, 0, 9.7), 1.06, 0.90, segments=36, material=mat_white)
    for obj in (sec1, sec2, sec3):
        add_bevel(obj, width=0.03, segments=2)

    # Arched doorway facing +Y/-Y bay side
    door = make_cylinder_along("LHDoor", (0, -1.62, 1.0), (0, -1.62, 2.35), 0.42, 0.42, segments=16, material=mat_iron)
    door.scale = (1.0, 0.45, 1.0)
    add_bevel(door, width=0.03, segments=2)

    # Corbeled gallery deck & railing
    deck = make_cylinder_along("LHGallery", (0, 0, 9.65), (0, 0, 10.0), 1.02, 1.38, segments=28, material=mat_iron)
    add_bevel(deck, width=0.03, segments=2)

    bpy.ops.mesh.primitive_torus_add(
        major_radius=1.32, minor_radius=0.045, major_segments=28, minor_segments=8, location=(0, 0, 10.55)
    )
    rail = bpy.context.active_object
    rail.name = "LHRailRing"
    rail.data.materials.append(mat_iron)
    set_smooth(rail)

    for p in range(12):
        a = (p / 12.0) * math.pi * 2
        make_cylinder_along(
            f"LHRailPost_{p}",
            (math.cos(a) * 1.32, math.sin(a) * 1.32, 10.0),
            (math.cos(a) * 1.32, math.sin(a) * 1.32, 10.55),
            0.03,
            0.03,
            segments=6,
            material=mat_iron,
        )

    # Glass lantern room
    lantern = make_cylinder_along("LighthouseGlass", (0, 0, 10.0), (0, 0, 11.2), 0.72, 0.72, segments=20, material=mat_glass)
    set_smooth(lantern)

    # Conical dome roof + spire
    roof = make_cylinder_along("LHRoof", (0, 0, 11.2), (0, 0, 12.25), 0.98, 0.04, segments=36, material=mat_red)
    add_bevel(roof, width=0.025, segments=2)
    make_cylinder_along("LHSpire", (0, 0, 12.2), (0, 0, 12.85), 0.05, 0.015, segments=8, material=mat_iron)

    save_and_export("lighthouse")


# ---------------------------------------------------------------------------
# 6. ROCK CLUSTER (smooth organic coastal boulders)
# ---------------------------------------------------------------------------
def build_rock_cluster():
    reset_scene()
    mat_rock = make_material("CoastalRock", "#646d78", roughness=0.88)

    boulders = [
        ("BoulderMain", (0.0, 0.0, 0.38), 1.05, (1.15, 0.95, 0.74), 0.0),
        ("BoulderSideA", (-1.05, 0.42, 0.22), 0.68, (1.10, 0.90, 0.72), 1.4),
        ("BoulderSideB", (0.85, -0.58, 0.18), 0.54, (0.95, 1.12, 0.68), 2.6),
    ]

    for b_name, loc, radius, scl, seed in boulders:
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=3, radius=radius)
        for v in bm.verts:
            p = v.co
            n1 = math.sin(p.x * 2.1 + seed) * math.cos(p.y * 1.9 - seed) * 0.16
            n2 = math.sin(p.z * 2.8 + p.x * 1.3 + seed) * 0.10
            disp = 1.0 + n1 + n2
            v.co = Vector((p.x * scl[0] * disp, p.y * scl[1] * disp, p.z * scl[2] * disp))
            if v.co.z < -0.22:
                v.co.z = -0.22 + (v.co.z + 0.22) * 0.25
        obj = create_mesh_object(b_name, bm, material=mat_rock)
        obj.location = loc
        add_subsurf(obj, levels=1, render_levels=1)

    save_and_export("rock_cluster")


# ---------------------------------------------------------------------------
# 7. BEACH SET (scalloped umbrella + ergonomic curved lounger)
# ---------------------------------------------------------------------------
def build_beach_set():
    reset_scene()
    mat_pole = make_material("BeachWood", "#875a36", roughness=0.78)
    mat_coral = make_material("UmbrellaCoral", "#e85842", roughness=0.72, double_sided=True)
    mat_cream = make_material("UmbrellaCream", "#f9f3e6", roughness=0.72, double_sided=True)
    mat_cushion = make_material("LoungerCushion", "#f2ede2", roughness=0.80)
    mat_pillow = make_material("LoungerPillow", "#1d7fa3", roughness=0.75)

    # Umbrella pole
    make_cylinder_along("UmbrellaPole", (0, 0, 0), (0, 0, 2.55), 0.045, 0.04, segments=12, material=mat_pole)

    # 8-panel scalloped umbrella canopy
    panels = 8
    r_outer = 1.55
    for p in range(panels):
        a0 = (p / panels) * math.pi * 2
        a1 = ((p + 1) / panels) * math.pi * 2
        mat = mat_coral if p % 2 == 0 else mat_cream

        def canopy_fn(u, v, ang0=a0, ang1=a1):
            ang = ang0 + (ang1 - ang0) * u
            rad = v * r_outer
            # Parabolic dome + scalloped edge droop
            scallop = math.sin(u * math.pi) * 0.08 * (v ** 2)
            z = 2.65 - (v ** 1.55) * 0.56 + scallop
            return Vector((math.cos(ang) * rad, math.sin(ang) * rad, z))

        panel_obj = make_grid_surface(f"UmbrellaPanel_{p}", 6, 8, canopy_fn, mat)
        add_subsurf(panel_obj, levels=1, render_levels=1)

    # Ergonomic wooden lounger beside umbrella
    lounger_x = 1.15
    lounger_y = -0.25

    def lounger_cushion_fn(u, v):
        x = lounger_x + (u - 0.5) * 0.78
        y = lounger_y + (v - 0.5) * 1.95
        # Curve up into backrest at v > 0.55 and subtle knee dip
        if v > 0.58:
            t = (v - 0.58) / 0.42
            z = 0.28 + (t ** 1.35) * 0.62
        else:
            z = 0.28 + math.sin(v * math.pi * 1.6) * 0.04
        return Vector((x, y, z))

    cushion = make_grid_surface("LoungerCushion", 8, 16, lounger_cushion_fn, mat_cushion)
    sol = cushion.modifiers.new("Solidify", "SOLIDIFY")
    sol.thickness = 0.09
    add_subsurf(cushion, levels=1, render_levels=1)

    # Lounger legs
    for lx in (-0.34, 0.34):
        for ly in (-0.75, 0.55):
            make_cylinder_along(
                f"LoungerLeg_{lx}_{ly}",
                (lounger_x + lx, lounger_y + ly, 0.0),
                (lounger_x + lx, lounger_y + ly, 0.26),
                0.04,
                0.035,
                segments=8,
                material=mat_pole,
            )

    # Headrest pillow cylinder
    pillow = make_cylinder_along(
        "LoungerPillow",
        (lounger_x - 0.30, lounger_y + 0.78, 0.80),
        (lounger_x + 0.30, lounger_y + 0.78, 0.80),
        0.10,
        0.10,
        segments=20,
        material=mat_pillow,
    )
    add_bevel(pillow, width=0.03, segments=3)

    save_and_export("beach_set")


# ---------------------------------------------------------------------------
# 8. CAMPFIRE (with CampfireFlame mesh)
# ---------------------------------------------------------------------------
def build_campfire():
    reset_scene()
    mat_stone = make_material("FireStone", "#5f6670", roughness=0.90)
    mat_wood = make_material("Driftwood", "#4d3221", roughness=0.88)
    mat_ember = make_material("EmberGlow", "#ff4d00", roughness=0.5, emission_color="#ff5500", emission_strength=2.5)
    mat_flame = make_material("FlameGlow", "#ff8b24", roughness=0.25, emission_color="#ff7714", emission_strength=3.6)

    # Ring of 10 rounded river/beach stones
    for s in range(10):
        a = (s / 10.0) * math.pi * 2
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.21)
        for v in bm.verts:
            v.co.x *= 1.15
            v.co.y *= 0.92
            v.co.z *= 0.68
        stone = create_mesh_object(f"FireStone_{s}", bm, material=mat_stone)
        stone.location = (math.cos(a) * 0.72, math.sin(a) * 0.72, 0.12)
        stone.rotation_euler = (0, 0, a)
        add_subsurf(stone, levels=1, render_levels=1)

    # Crossed driftwood logs
    for l in range(4):
        a = (l / 4.0) * math.pi * 2 + 0.3
        p0 = (math.cos(a) * 0.62, math.sin(a) * 0.62, 0.08)
        p1 = (-math.cos(a) * 0.18, -math.sin(a) * 0.18, 0.44)
        log = make_cylinder_along(f"FireLog_{l}", p0, p1, 0.095, 0.075, segments=10, material=mat_wood)
        add_bevel(log, width=0.015, segments=2)

    # Glowing ember mound
    bm_emb = bmesh.new()
    bmesh.ops.create_uvsphere(bm_emb, u_segments=14, v_segments=10, radius=0.45)
    for v in bm_emb.verts:
        v.co.z *= 0.32
    ember = create_mesh_object("EmberBed", bm_emb, material=mat_ember)
    ember.location = (0, 0, 0.08)

    # Smooth swirling flame mesh
    bm_fl = bmesh.new()
    bmesh.ops.create_uvsphere(bm_fl, u_segments=16, v_segments=14, radius=0.35)
    for v in bm_fl.verts:
        t = max(0.0, (v.co.z + 0.35) / 0.70)
        taper = (1.0 - t) ** 0.75
        swirl_x = math.sin(t * 4.5) * 0.08 * t
        swirl_y = math.cos(t * 3.8) * 0.08 * t
        v.co.x = v.co.x * taper * 0.95 + swirl_x
        v.co.y = v.co.y * taper * 0.95 + swirl_y
        v.co.z = t * 1.15 + 0.14
    flame = create_mesh_object("CampfireFlame", bm_fl, material=mat_flame)
    add_subsurf(flame, levels=1, render_levels=1)

    save_and_export("campfire")


# ---------------------------------------------------------------------------
# 9. SEAGULL (with WingLeft & WingRight pivots)
# ---------------------------------------------------------------------------
def build_seagull():
    reset_scene()
    mat_white = make_material("GullWhite", "#f8fafc", roughness=0.58)
    mat_wingtip = make_material("GullGray", "#cbd5e1", roughness=0.62)
    mat_beak = make_material("GullBeak", "#f59e0b", roughness=0.42)

    # Sculpted aerodynamic body facing +Y (which maps to -Z in Three.js)
    bm_body = bmesh.new()
    bmesh.ops.create_uvsphere(bm_body, u_segments=16, v_segments=14, radius=0.18)
    for v in bm_body.verts:
        # Elongate forward/backward along Y
        y = v.co.y * 2.55
        taper = 1.0 - min(0.75, abs(v.co.y / 0.18) * 0.55)
        v.co.x *= 0.88 * taper
        v.co.z *= 0.78 * taper
        v.co.y = y
        if y > 0.25:
            # Slight upward neck curve toward head
            v.co.z += (y - 0.25) * 0.28
        elif y < -0.25:
            # Flatten tail fan
            v.co.x *= 1.45
            v.co.z *= 0.35
    body = create_mesh_object("GullBody", bm_body, material=mat_white)
    add_subsurf(body, levels=1, render_levels=1)

    # Head
    bm_head = bmesh.new()
    bmesh.ops.create_uvsphere(bm_head, u_segments=12, v_segments=10, radius=0.11)
    head = create_mesh_object("GullHead", bm_head, material=mat_white)
    head.location = (0, 0.48, 0.12)
    head.scale = (0.9, 1.15, 0.92)
    add_subsurf(head, levels=1, render_levels=1)

    # Beak pointing +Y
    make_cylinder_along("GullBeak", (0, 0.58, 0.11), (0, 0.78, 0.08), 0.042, 0.008, segments=16, material=mat_beak)

    # Cambered left and right wings with separate pivot empties
    for side_name, sign in [("WingLeft", -1.0), ("WingRight", 1.0)]:
        pivot = bpy.data.objects.new(side_name, None)
        pivot.location = (sign * 0.09, 0.05, 0.03)
        link_object(pivot)

        def wing_fn(u, v, sgn=sign):
            # u: 0 (root) -> 1 (tip), v: 0 (trailing edge) -> 1 (leading edge)
            span = sgn * u * 0.85
            chord = (0.28 * (1.0 - 0.65 * (u ** 1.4))) * (v - 0.45)
            # Swept gull wing curve + dihedral arch
            sweep_y = chord - (u ** 1.35) * 0.22
            camber_z = math.sin(v * math.pi) * 0.045 * (1.0 - u * 0.5)
            arch_z = math.sin(u * math.pi * 0.8) * 0.09 - (u ** 2) * 0.05
            return Vector((span, sweep_y, camber_z + arch_z))

        wing_mesh = make_grid_surface(f"{side_name}Mesh", 10, 6, wing_fn, mat_wingtip, parent=pivot)
        sol = wing_mesh.modifiers.new("Solidify", "SOLIDIFY")
        sol.thickness = 0.018
        add_subsurf(wing_mesh, levels=1, render_levels=1)

    save_and_export("seagull")


def main():
    builders = [
        build_sailboat,
        build_island,
        build_palm_tree,
        build_pier,
        build_lighthouse,
        build_rock_cluster,
        build_beach_set,
        build_campfire,
        build_seagull,
    ]
    for fn in builders:
        fn()
    print("All 9 Blender assets generated and exported successfully.")


if __name__ == "__main__":
    main()
