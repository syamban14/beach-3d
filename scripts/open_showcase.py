"""Set MATERIAL viewport shading on all 9 .blend assets and build beach_showcase.blend."""

import math
import os
import bpy
from mathutils import Euler, Vector

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_DIR = os.path.join(BASE_DIR, "assets", "blend")

ASSET_NAMES = [
    "sailboat",
    "island",
    "palm_tree",
    "pier",
    "lighthouse",
    "rock_cluster",
    "beach_set",
    "campfire",
    "seagull",
]


def set_all_viewports_material_mode(frame_target=None, view_rot_euler=None, view_dist=None):
    """Switch every VIEW_3D area across all screens to MATERIAL shading mode."""
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.shading.type = "MATERIAL"
                space.shading.use_scene_lights = True
                space.shading.use_scene_world = False
                if hasattr(space, "clip_end"):
                    space.clip_end = 1000.0
                if frame_target is not None and space.region_3d is not None:
                    space.region_3d.view_perspective = "PERSP"
                    space.region_3d.view_location = Vector(frame_target)
                    if view_rot_euler is not None:
                        space.region_3d.view_rotation = Euler(view_rot_euler, "XYZ").to_quaternion()
                    if view_dist is not None:
                        space.region_3d.view_distance = view_dist


def upgrade_individual_blend_files():
    """Update all 9 individual .blend files to open directly in Material Preview mode."""
    for name in ASSET_NAMES:
        path = os.path.join(BLEND_DIR, f"{name}.blend")
        if not os.path.exists(path):
            continue
        bpy.ops.wm.open_mainfile(filepath=path)
        set_all_viewports_material_mode()
        bpy.ops.wm.save_as_mainfile(filepath=path)
        print(f"[Updated shading] {path}")


def island_elevation(bx, by):
    """Match island elevation formula (Blender coords relative to island center)."""
    lz = -by
    cove_factor = max(0.0, (lz - 4.0) * 0.25) if lz > 4.0 else 0.0
    eff_dist = math.hypot(bx * 0.95, lz * 1.05 + cove_factor)
    base = max(0.0, 1.0 - eff_dist / 22.5)
    hill = (base ** 1.55) * 5.2
    ridge = math.sin(bx * 0.22) * math.cos(lz * 0.19) * 0.35 * base
    return hill + ridge - 1.15


def get_or_create_collection(name):
    """Return a collection linked directly under the active scene collection."""
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def append_asset_objects(asset_name):
    """Load objects from an asset .blend file and return its top-level root objects."""
    blend_path = os.path.join(BLEND_DIR, f"{asset_name}.blend")
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
    loaded = [obj for obj in data_to.objects if obj is not None]
    roots = [obj for obj in loaded if obj.parent is None]
    return roots, loaded


def place_asset_group(asset_name, instance_name, collection, location=(0, 0, 0), rotation_z=0.0, scale=1.0, tilt_x=0.0, tilt_y=0.0):
    """Append an asset and parent all its root objects under a clean Empty container."""
    roots, all_objs = append_asset_objects(asset_name)
    container = bpy.data.objects.new(instance_name, None)
    container.empty_display_type = "PLAIN_AXES"
    container.empty_display_size = 0.5
    collection.objects.link(container)

    def link_tree(obj):
        if obj.name not in collection.objects:
            collection.objects.link(obj)
        for ch in obj.children:
            link_tree(ch)

    for r in roots:
        link_tree(r)
        r.parent = container

    container.location = location
    container.rotation_euler = (tilt_x, tilt_y, rotation_z)
    container.scale = (scale, scale, scale)
    return container


def build_ocean_and_environment(env_col):
    """Create a sculpted ocean plane, Sun light, and overview camera."""
    # Ocean plane
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=96, y_subdivisions=96, size=240.0, location=(0, 0, 0))
    ocean = bpy.context.active_object
    ocean.name = "OceanSurface"
    for col in list(ocean.users_collection):
        col.objects.unlink(ocean)
    env_col.objects.link(ocean)

    for v in ocean.data.vertices:
        dist = math.hypot(v.co.x, v.co.y - 28.0)
        amp = 0.15 + 0.65 * min(1.0, max(0.0, (dist - 14.0) / 14.0))
        v.co.z = (
            math.sin(v.co.x * 0.08 + v.co.y * 0.05) * 0.30
            + math.cos(v.co.x * 0.045 - v.co.y * 0.09) * 0.22
        ) * amp
    for poly in ocean.data.polygons:
        poly.use_smooth = True

    mat_ocean = bpy.data.materials.new("OceanWater")
    if hasattr(mat_ocean, "use_nodes") and not mat_ocean.use_nodes:
        mat_ocean.use_nodes = True
    bsdf = mat_ocean.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.015, 0.14, 0.28, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.18
    bsdf.inputs["Metallic"].default_value = 0.1
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.45
    ocean.data.materials.append(mat_ocean)

    # Sun light
    light_data = bpy.data.lights.new(name="TropicalSun", type="SUN")
    light_data.energy = 3.2
    light_data.color = (1.0, 0.96, 0.88)
    sun_obj = bpy.data.objects.new(name="TropicalSun", object_data=light_data)
    sun_obj.location = (25.0, 35.0, 40.0)
    sun_obj.rotation_euler = (math.radians(48), math.radians(15), math.radians(-35))
    env_col.objects.link(sun_obj)

    # Camera framed on sailboat + pier + island
    cam_data = bpy.data.cameras.new(name="ShowcaseCamera")
    cam_data.lens = 34.0
    cam_obj = bpy.data.objects.new(name="ShowcaseCamera", object_data=cam_data)
    cam_obj.location = (-18.0, -43.0, 15.0)
    direction = Vector((0.0, 5.0, 1.5)) - cam_obj.location
    cam_obj.rotation_mode = "QUATERNION"
    cam_obj.rotation_quaternion = direction.to_track_quat("-Z", "Y")
    env_col.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj


def build_showcase():
    """Assemble all 9 assets into beach_showcase.blend."""
    bpy.ops.wm.read_factory_settings(use_empty=False)
    # Remove default Cube / Camera / Light from factory scene
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    col_env = get_or_create_collection("Environment")
    col_island = get_or_create_collection("Island")
    col_boat = get_or_create_collection("Sailboat")
    col_pier = get_or_create_collection("Pier")
    col_lighthouse = get_or_create_collection("Lighthouse")
    col_palms = get_or_create_collection("PalmTrees")
    col_rocks = get_or_create_collection("Rocks")
    col_beach = get_or_create_collection("BeachSets")
    col_fire = get_or_create_collection("Campfire")
    col_gulls = get_or_create_collection("Seagulls")

    build_ocean_and_environment(col_env)

    # Island at Three.js (0, 0, -28) -> Blender (0, 28, 0)
    place_asset_group("island", "Island_Main", col_island, location=(0.0, 28.0, 0.0))

    # Sailboat at Three.js (0, 0.14, 18) -> Blender (0, -18, 0.14)
    place_asset_group("sailboat", "Sailboat_Main", col_boat, location=(0.0, -18.0, 0.14))

    # Pier at origin
    place_asset_group("pier", "Pier_Main", col_pier, location=(0.0, 0.0, 0.0))

    # Lighthouse at Three.js (-10.5, y, -31) -> Blender (-10.5, 31, y)
    lh_y = island_elevation(-10.5, 31.0 - 28.0) - 0.1
    place_asset_group("lighthouse", "Lighthouse_Main", col_lighthouse, location=(-10.5, 31.0, lh_y))

    # Rock clusters
    rocks = [
        (-13.5, 15.5, 1.35, 0.4),
        (13.8, 17.5, 1.25, 2.1),
        (-16.8, 34.0, 1.60, 1.1),
        (16.5, 33.5, 1.45, 3.7),
    ]
    for idx, (rx, ry, scl, rot) in enumerate(rocks):
        rz = max(-0.3, island_elevation(rx, ry - 28.0))
        place_asset_group("rock_cluster", f"RockCluster_{idx}", col_rocks, location=(rx, ry, rz), rotation_z=rot, scale=scl)

    # Beach umbrella & lounger sets
    beach_spots = [
        (-6.2, 15.5, 0.25),
        (5.5, 14.8, -0.45),
    ]
    for idx, (bx, by, rot) in enumerate(beach_spots):
        bz = island_elevation(bx, by - 28.0) - 0.05
        place_asset_group("beach_set", f"BeachSet_{idx}", col_beach, location=(bx, by, bz), rotation_z=rot)

    # Campfire
    fz = island_elevation(7.5, 19.2 - 28.0)
    place_asset_group("campfire", "Campfire_Main", col_fire, location=(7.5, 19.2, fz))

    # Palm trees
    palms = [
        (-5.5, 23.5, 1.05, 0.26, 0.6),
        (-11.5, 22.0, 0.92, 0.30, 2.3),
        (-1.5, 28.0, 1.18, 0.18, -0.4),
        (4.5, 25.5, 1.00, 0.28, -1.2),
        (10.5, 22.5, 0.95, 0.32, -0.6),
        (12.2, 29.0, 1.10, 0.24, 0.9),
        (2.5, 34.5, 1.08, 0.22, 1.5),
        (-6.8, 36.5, 0.96, 0.26, 2.8),
        (8.5, 36.0, 0.88, 0.30, -2.1),
    ]
    for idx, (px, py, scl, lean, yaw) in enumerate(palms):
        pz = island_elevation(px, py - 28.0) - 0.15
        place_asset_group(
            "palm_tree",
            f"PalmTree_{idx}",
            col_palms,
            location=(px, py, pz),
            rotation_z=yaw,
            scale=scl,
            tilt_y=lean * 0.25,
        )

    # Seagulls circling above the island
    gulls = [
        (12.0, 18.0, 12.5, 1.1),
        (-11.0, 24.0, 14.0, -0.6),
        (6.0, 35.0, 11.8, 2.5),
        (-14.0, 33.0, 13.4, 0.4),
        (14.5, 29.0, 15.0, -1.9),
    ]
    for idx, (gx, gy, gz, rot) in enumerate(gulls):
        place_asset_group("seagull", f"Seagull_{idx}", col_gulls, location=(gx, gy, gz), rotation_z=rot)

    set_all_viewports_material_mode(
        frame_target=(0.0, 8.0, 1.5),
        view_rot_euler=(math.radians(72.0), 0.0, math.radians(-22.0)),
        view_dist=52.0,
    )

    showcase_path = os.path.join(BLEND_DIR, "beach_showcase.blend")
    bpy.ops.wm.save_as_mainfile(filepath=showcase_path)
    print(f"[Saved showcase] {showcase_path}")


if __name__ == "__main__":
    upgrade_individual_blend_files()
    build_showcase()
