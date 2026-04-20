# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Hideki Saito

bl_info = {
    "name": "Beat Flipper Driver",
    "author": "Hideki Saito",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Beat Flip",
    "description": "Adds BPM-based custom-property drivers to selected objects",
    "category": "Animation",
    "support": "COMMUNITY"
}

import random

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup


DRIVER_PROP_NAME = "beat_flipper_value"
PHASE_PROP_NAME = "beat_flipper_phase"


def _next_driver_property_name(id_block):
    """Return the next available beat flipper property name for an ID block."""
    if DRIVER_PROP_NAME not in id_block:
        return DRIVER_PROP_NAME

    max_index = 0
    prefix = f"{DRIVER_PROP_NAME}_"
    for key in id_block.keys():
        if not key.startswith(prefix):
            continue

        suffix = key[len(prefix):]
        if suffix.isdigit():
            max_index = max(max_index, int(suffix))

    return f"{DRIVER_PROP_NAME}_{max_index + 1}"


def _phase_property_name(driver_prop_name):
    suffix = driver_prop_name[len(DRIVER_PROP_NAME):]
    return f"{PHASE_PROP_NAME}{suffix}"


def _is_beat_flipper_property(prop_name):
    return prop_name == DRIVER_PROP_NAME or prop_name.startswith(f"{DRIVER_PROP_NAME}_")


def _is_beat_flipper_phase_property(prop_name):
    return prop_name == PHASE_PROP_NAME or prop_name.startswith(f"{PHASE_PROP_NAME}_")


def _latest_driver_property_name(id_block):
    if DRIVER_PROP_NAME not in id_block:
        return None

    latest_name = DRIVER_PROP_NAME
    latest_index = 0
    prefix = f"{DRIVER_PROP_NAME}_"
    for key in id_block.keys():
        if not key.startswith(prefix):
            continue

        suffix = key[len(prefix):]
        if suffix.isdigit():
            idx = int(suffix)
            if idx > latest_index:
                latest_index = idx
                latest_name = key

    return latest_name


def _build_expression(
    min_value,
    max_value,
    interval_frames,
    value_mode,
    phase,
    randomization_type,
    object_random_value_a,
    object_random_value_b,
    object_seed,
):
    time_expr = f"(frame_var + {phase:.6f}) / {interval_frames:.6f}"
    step_expr = f"floor({time_expr})"
    parity_expr = f"(0.5 - 0.5 * cos(({step_expr}) * 3.141592653589793))"

    if value_mode == "RANDOM":
        if randomization_type == "OBJECT_CONSTANT":
            return (
                f"{object_random_value_a:.6f} if ({parity_expr}) == 0"
                f" else {object_random_value_b:.6f}"
            )

        # Deterministic pseudo-random number per step for stable playback/scrubbing.
        # object_seed shifts the hash input so each object produces its own sequence
        # when object_value_scope is PER_OBJECT; it is 0.0 for SHARED scope.
        current_hash = (
            f"(sin(({step_expr}) * 12.9898 + {object_seed:.6f} + 78.233) * 43758.5453)"
        )
        current_rand = f"(({current_hash}) - floor({current_hash}))"
        return f"{min_value:.6f} + ({current_rand}) * ({(max_value - min_value):.6f})"

    return (
        f"{min_value:.6f} if ({parity_expr}) == 0"
        f" else {max_value:.6f}"
    )


def _wrap_frame_range(expr, use_start, start_frame, use_end, end_frame):
    """Wrap a driver expression so it returns 0.0 outside the active frame range."""
    if not use_start and not use_end:
        return expr

    conditions = []
    if use_start:
        conditions.append(f"frame_var >= {start_frame}")
    if use_end:
        conditions.append(f"frame_var <= {end_frame}")

    guard = " and ".join(conditions)
    return f"({expr}) if ({guard}) else 0.0"


class BeatFlipperSettings(PropertyGroup):
    target_mode: EnumProperty(
        name="Target",
        description="Where to add the driver property",
        items=[
            ("OBJECT", "Object", "Add driver property on the object"),
            ("DATA", "Object Data", "Add driver property on object data (mesh, curve, etc.)"),
        ],
        default="OBJECT",
    )
    min_value: FloatProperty(
        name="Min",
        description="Minimum output value",
        default=0.0,
        min=0.0,
        max=1.0,
    )
    max_value: FloatProperty(
        name="Max",
        description="Maximum output value",
        default=1.0,
        min=0.0,
        max=1.0,
    )
    bpm: FloatProperty(
        name="BPM",
        description="Beats per minute used to calculate change interval",
        default=120.0,
        min=1.0,
        soft_max=300.0,
    )
    value_mode: EnumProperty(
        name="Value Mode",
        description="How value is chosen on each beat",
        items=[
            ("RANDOM", "Randomized", "Pick a random value between Min and Max each beat"),
            ("STATIC", "Static (Min/Max)", "Alternate between Min and Max each beat"),
        ],
        default="RANDOM",
    )
    randomization_type: EnumProperty(
        name="Randomization Type",
        description="How randomized mode generates values",
        items=[
            (
                "PER_PHASE",
                "Per Phase",
                "Generate a new value at each BPM phase",
            ),
            (
                "OBJECT_CONSTANT",
                "Per Object Constant",
                "Use two random values per object and alternate between them across phases",
            ),
        ],
        default="PER_PHASE",
    )
    object_value_scope: EnumProperty(
        name="Value Scope",
        description="Whether all objects share the same random values or each gets its own",
        items=[
            (
                "PER_OBJECT",
                "Per Object",
                "Each object receives its own independent random values",
            ),
            (
                "SHARED",
                "Shared Across Objects",
                "All selected objects use the same random values",
            ),
        ],
        default="PER_OBJECT",
    )
    sync_mode: EnumProperty(
        name="Transition Mode",
        description="How transitions align across selected objects",
        items=[
            ("SYNC", "Synchronized", "All objects change at the same time"),
            ("RANDOMIZED", "Randomized Between Objects", "Each object gets a random phase offset"),
        ],
        default="SYNC",
    )
    use_start_frame: BoolProperty(
        name="Limit Start",
        description="Clamp beat output to zero before this frame",
        default=False,
    )
    start_frame: IntProperty(
        name="Start Frame",
        description="First frame where the beat driver is active",
        default=1,
    )
    use_end_frame: BoolProperty(
        name="Limit End",
        description="Clamp beat output to zero after this frame",
        default=False,
    )
    end_frame: IntProperty(
        name="End Frame",
        description="Last frame where the beat driver is active",
        default=250,
    )


class OBJECT_OT_add_beat_flipper_driver(Operator):
    bl_idname = "object.add_beat_flipper_driver"
    bl_label = "Add Driver"
    bl_description = "Add a new beat-flipper driver on selected objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.beat_flipper_settings
        selected_objects = context.selected_objects

        if not selected_objects:
            self.report({"ERROR"}, "No objects selected")
            return {"CANCELLED"}

        if settings.min_value > settings.max_value:
            self.report({"ERROR"}, "Min must be less than or equal to Max")
            return {"CANCELLED"}

        scene = context.scene
        fps = scene.render.fps / scene.render.fps_base
        interval_frames = (60.0 / settings.bpm) * fps

        if interval_frames <= 0.0:
            self.report({"ERROR"}, "Calculated interval must be greater than zero")
            return {"CANCELLED"}

        if (
            settings.use_start_frame
            and settings.use_end_frame
            and settings.end_frame < settings.start_frame
        ):
            self.report({"ERROR"}, "End Frame must be greater than or equal to Start Frame")
            return {"CANCELLED"}

        # Pre-sample shared values once when all objects should share the same randoms.
        is_shared = settings.object_value_scope == "SHARED"
        shared_value_a = random.uniform(settings.min_value, settings.max_value)
        shared_value_b = random.uniform(settings.min_value, settings.max_value)
        shared_seed = 0.0

        added_count = 0
        skipped_no_data = 0

        for obj in selected_objects:
            target_block = obj
            if settings.target_mode == "DATA":
                if obj.data is None:
                    skipped_no_data += 1
                    continue
                target_block = obj.data

            driver_prop_name = _next_driver_property_name(target_block)
            phase_prop_name = _phase_property_name(driver_prop_name)
            target_block[driver_prop_name] = settings.min_value

            if is_shared:
                object_random_value_a = shared_value_a
                object_random_value_b = shared_value_b
                object_seed = shared_seed
            else:
                object_random_value_a = random.uniform(settings.min_value, settings.max_value)
                object_random_value_b = random.uniform(settings.min_value, settings.max_value)
                object_seed = random.uniform(0.0, 1000.0)

            phase = 0.0
            if settings.sync_mode == "RANDOMIZED":
                phase = random.uniform(0.0, interval_frames)
                target_block[phase_prop_name] = phase
            else:
                target_block[phase_prop_name] = 0.0

            fcurve = target_block.driver_add(f'["{driver_prop_name}"]')
            driver = fcurve.driver
            driver.type = "SCRIPTED"

            while driver.variables:
                driver.variables.remove(driver.variables[0])

            frame_var = driver.variables.new()
            frame_var.name = "frame_var"
            frame_var.type = "SINGLE_PROP"
            frame_var.targets[0].id_type = "SCENE"
            frame_var.targets[0].id = scene
            frame_var.targets[0].data_path = "frame_current"

            base_expr = _build_expression(
                min_value=settings.min_value,
                max_value=settings.max_value,
                interval_frames=interval_frames,
                value_mode=settings.value_mode,
                phase=phase,
                randomization_type=settings.randomization_type,
                object_random_value_a=object_random_value_a,
                object_random_value_b=object_random_value_b,
                object_seed=object_seed,
            )
            driver.expression = _wrap_frame_range(
                base_expr,
                use_start=settings.use_start_frame,
                start_frame=settings.start_frame,
                use_end=settings.use_end_frame,
                end_frame=settings.end_frame,
            )
            added_count += 1

        if added_count == 0 and settings.target_mode == "DATA":
            self.report({"ERROR"}, "No selected objects have object data")
            return {"CANCELLED"}

        msg = f"Added driver on {added_count} target(s)"
        if skipped_no_data > 0:
            msg += f"; skipped {skipped_no_data} object(s) without data"

        self.report({"INFO"}, msg)
        return {"FINISHED"}


class OBJECT_OT_clear_beat_flipper_drivers(Operator):
    bl_idname = "object.clear_beat_flipper_drivers"
    bl_label = "Clear Beat-Flipper Drivers"
    bl_description = "Remove all beat-flipper drivers and properties from selected objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.beat_flipper_settings
        selected_objects = context.selected_objects

        if not selected_objects:
            self.report({"ERROR"}, "No objects selected")
            return {"CANCELLED"}

        removed_drivers = 0
        skipped_no_data = 0
        for obj in selected_objects:
            target_block = obj
            if settings.target_mode == "DATA":
                if obj.data is None:
                    skipped_no_data += 1
                    continue
                target_block = obj.data

            if target_block.animation_data and target_block.animation_data.drivers:
                data_paths = [fcurve.data_path for fcurve in target_block.animation_data.drivers]
                for data_path in data_paths:
                    if data_path.startswith(f'["{DRIVER_PROP_NAME}'):
                        try:
                            target_block.driver_remove(data_path)
                            removed_drivers += 1
                        except TypeError:
                            pass

            for key in list(target_block.keys()):
                if _is_beat_flipper_property(key) or _is_beat_flipper_phase_property(key):
                    del target_block[key]

        msg = f"Removed {removed_drivers} driver(s)"
        if skipped_no_data > 0:
            msg += f"; skipped {skipped_no_data} object(s) without data"

        self.report({"INFO"}, msg)
        return {"FINISHED"}


class OBJECT_OT_remove_latest_beat_flipper_driver(Operator):
    bl_idname = "object.remove_latest_beat_flipper_driver"
    bl_label = "Remove Latest Driver"
    bl_description = "Remove only the most recently added beat-flipper driver per selected object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.beat_flipper_settings
        selected_objects = context.selected_objects

        if not selected_objects:
            self.report({"ERROR"}, "No objects selected")
            return {"CANCELLED"}

        removed_drivers = 0
        skipped_no_data = 0
        for obj in selected_objects:
            target_block = obj
            if settings.target_mode == "DATA":
                if obj.data is None:
                    skipped_no_data += 1
                    continue
                target_block = obj.data

            latest_prop = _latest_driver_property_name(target_block)
            if not latest_prop:
                continue

            data_path = f'["{latest_prop}"]'
            try:
                target_block.driver_remove(data_path)
                removed_drivers += 1
            except TypeError:
                pass

            if latest_prop in target_block:
                del target_block[latest_prop]

            phase_prop = _phase_property_name(latest_prop)
            if phase_prop in target_block:
                del target_block[phase_prop]

        msg = f"Removed latest driver on {removed_drivers} target(s)"
        if skipped_no_data > 0:
            msg += f"; skipped {skipped_no_data} object(s) without data"

        self.report({"INFO"}, msg)
        return {"FINISHED"}


class VIEW3D_PT_beat_flipper_panel(Panel):
    bl_label = "Beat Flipper Driver"
    bl_idname = "VIEW3D_PT_beat_flipper_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Beat Flip"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.beat_flipper_settings

        col = layout.column(align=True)
        col.prop(settings, "target_mode")
        col.prop(settings, "min_value")
        col.prop(settings, "max_value")
        col.prop(settings, "bpm")

        layout.separator()

        col = layout.column(align=True)
        col.prop(settings, "value_mode")
        if settings.value_mode == "RANDOM":
            col.prop(settings, "randomization_type")
            col.prop(settings, "object_value_scope")
        col.prop(settings, "sync_mode")

        layout.separator()
        box = layout.box()
        box.label(text="Frame Range", icon="TIME")

        row = box.row(align=True)
        row.prop(settings, "use_start_frame")
        sub = row.row(align=True)
        sub.enabled = settings.use_start_frame
        sub.prop(settings, "start_frame", text="")

        row = box.row(align=True)
        row.prop(settings, "use_end_frame")
        sub = row.row(align=True)
        sub.enabled = settings.use_end_frame
        sub.prop(settings, "end_frame", text="")

        frame_range_invalid = (
            settings.use_start_frame
            and settings.use_end_frame
            and settings.end_frame < settings.start_frame
        )
        if frame_range_invalid:
            row = box.row()
            row.alert = True
            row.label(text="End Frame must be >= Start Frame", icon="ERROR")

        layout.separator()
        add_row = layout.row()
        add_row.enabled = not frame_range_invalid
        add_row.operator(OBJECT_OT_add_beat_flipper_driver.bl_idname, icon="DRIVER")
        layout.operator(OBJECT_OT_remove_latest_beat_flipper_driver.bl_idname, icon="REMOVE")
        layout.operator(OBJECT_OT_clear_beat_flipper_drivers.bl_idname, icon="TRASH")


classes = (
    BeatFlipperSettings,
    OBJECT_OT_add_beat_flipper_driver,
    OBJECT_OT_remove_latest_beat_flipper_driver,
    OBJECT_OT_clear_beat_flipper_drivers,
    VIEW3D_PT_beat_flipper_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.beat_flipper_settings = PointerProperty(type=BeatFlipperSettings)


def unregister():
    del bpy.types.Scene.beat_flipper_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
