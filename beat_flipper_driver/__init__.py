# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Hideki Saito

bl_info = {
    "name": "Beat Flipper Driver",
    "author": "Hideki Saito",
    "version": (1, 2, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Beat Flip",
    "description": "Adds BPM-based custom-property drivers to selected objects",
    "category": "Animation",
    "support": "COMMUNITY"
}

import math
import random

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup


DRIVER_PROP_NAME = "beat_flipper_value"
PHASE_PROP_NAME = "beat_flipper_phase"


def _indexed_driver_property_name(index):
    return f"{DRIVER_PROP_NAME}.{index:03d}"


def _next_driver_property_name(id_block):
    """Return the next available beat flipper property name for an ID block."""
    if DRIVER_PROP_NAME not in id_block:
        return DRIVER_PROP_NAME

    max_index = 0
    for key in id_block.keys():
        dot_prefix = f"{DRIVER_PROP_NAME}."
        underscore_prefix = f"{DRIVER_PROP_NAME}_"

        suffix = None
        if key.startswith(dot_prefix):
            suffix = key[len(dot_prefix):]
        elif key.startswith(underscore_prefix):
            suffix = key[len(underscore_prefix):]

        if suffix and suffix.isdigit():
            max_index = max(max_index, int(suffix))

    return _indexed_driver_property_name(max_index + 1)


def _phase_property_name(driver_prop_name):
    suffix = driver_prop_name[len(DRIVER_PROP_NAME):]
    return f"{PHASE_PROP_NAME}{suffix}"


def _is_beat_flipper_property(prop_name):
    return (
        prop_name == DRIVER_PROP_NAME
        or prop_name.startswith(f"{DRIVER_PROP_NAME}.")
        or prop_name.startswith(f"{DRIVER_PROP_NAME}_")
    )


def _is_beat_flipper_phase_property(prop_name):
    return (
        prop_name == PHASE_PROP_NAME
        or prop_name.startswith(f"{PHASE_PROP_NAME}.")
        or prop_name.startswith(f"{PHASE_PROP_NAME}_")
    )


def _latest_driver_property_name(id_block):
    latest_name = DRIVER_PROP_NAME if DRIVER_PROP_NAME in id_block else None
    latest_index = 0
    for key in id_block.keys():
        dot_prefix = f"{DRIVER_PROP_NAME}."
        underscore_prefix = f"{DRIVER_PROP_NAME}_"

        suffix = None
        if key.startswith(dot_prefix):
            suffix = key[len(dot_prefix):]
        elif key.startswith(underscore_prefix):
            suffix = key[len(underscore_prefix):]

        if suffix and suffix.isdigit():
            idx = int(suffix)
            if idx > latest_index:
                latest_index = idx
                latest_name = key

    return latest_name


def _remove_fcurves_for_property(id_block, property_name):
    """Remove action fcurves bound to a custom property data path."""
    data_path = f'["{property_name}"]'
    removed_count = 0

    for fcurves in _iter_action_fcurve_collections(id_block):
        to_remove = [fcurve for fcurve in fcurves if fcurve.data_path == data_path]
        for fcurve in to_remove:
            try:
                fcurves.remove(fcurve)
                removed_count += 1
            except (AttributeError, RuntimeError, TypeError):
                # Some Blender action containers are read-only for specific data layouts.
                continue

    return removed_count


def _iter_action_fcurve_collections(id_block):
    """Yield fcurve collections for both legacy and layered Blender actions."""
    anim_data = getattr(id_block, "animation_data", None)
    if not anim_data:
        return

    action = getattr(anim_data, "action", None)
    if not action:
        return

    legacy_fcurves = getattr(action, "fcurves", None)
    if legacy_fcurves is not None:
        yield legacy_fcurves
        return

    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            channelbags = getattr(strip, "channelbags", None)
            if channelbags is None:
                continue

            action_slot = getattr(anim_data, "action_slot", None)
            if action_slot and hasattr(channelbags, "for_slot"):
                channelbag = channelbags.for_slot(action_slot)
                if channelbag is not None:
                    bag_fcurves = getattr(channelbag, "fcurves", None)
                    if bag_fcurves is not None:
                        yield bag_fcurves
                continue

            for channelbag in channelbags:
                bag_fcurves = getattr(channelbag, "fcurves", None)
                if bag_fcurves is not None:
                    yield bag_fcurves


def _configure_property_ui(id_block, property_name, min_value, max_value):
    """Register ID-property UI metadata so Blender shows the evaluated value cleanly."""
    ui_data = id_block.id_properties_ui(property_name)
    ui_data.update(
        default=min_value,
        min=min_value,
        max=max_value,
        soft_min=min_value,
        soft_max=max_value,
        description="Beat Flipper output value",
    )


def _prime_keyed_property_visibility(id_block):
    """Work around Blender not refreshing the first keyed ID property until a driver exists once."""
    temp_prop_name = "_beat_flipper_prime"
    suffix = 1
    while temp_prop_name in id_block:
        temp_prop_name = f"_beat_flipper_prime_{suffix}"
        suffix += 1

    id_block[temp_prop_name] = 0.0

    try:
        fcurve = id_block.driver_add(f'["{temp_prop_name}"]')
        driver = fcurve.driver
        driver.type = "SCRIPTED"
        driver.expression = "0.0"
        id_block.driver_remove(f'["{temp_prop_name}"]')
    finally:
        if temp_prop_name in id_block:
            del id_block[temp_prop_name]


def _refresh_blender_ui(context, id_block=None):
    """Force dependency and UI refresh so driven custom property values redraw."""
    if id_block is not None and hasattr(id_block, "update_tag"):
        id_block.update_tag()

    context.view_layer.update()
    for area in context.screen.areas:
        area.tag_redraw()


def _force_driver_evaluation(scene, current_frame):
    """Force driver reevaluation by moving one frame and restoring the current frame."""
    frame_start = scene.frame_start
    frame_end = scene.frame_end

    if frame_end > current_frame:
        temp_frame = current_frame + 1
    elif frame_start < current_frame:
        temp_frame = current_frame - 1
    else:
        temp_frame = None

    if temp_frame is not None:
        scene.frame_set(temp_frame)

    scene.frame_set(current_frame)


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
    time_expr = f"(frame_var + {phase:.1f}) / {interval_frames:.1f}"
    step_expr = f"floor({time_expr})"
    parity_expr = f"(0.5 - 0.5 * cos({step_expr} * 3.141592653589793))"

    if value_mode == "RANDOM":
        if randomization_type == "OBJECT_CONSTANT":
            # Pure arithmetic alternation (no if/else in driver expression).
            return (
                f"{object_random_value_a:.1f}"
                f" + ({(object_random_value_b - object_random_value_a):.1f}) * {parity_expr}"
            )

        # Deterministic pseudo-random number per step for stable playback/scrubbing.
        # object_seed shifts the hash input so each object produces its own sequence
        # when object_value_scope is PER_OBJECT; it is 0.0 for SHARED scope.
        sin_expr = f"(sin({step_expr} * 12.9898 + {object_seed:.1f} + 78.233) * 43758.5453)"
        current_rand = f"{sin_expr} - floor({sin_expr})"
        return f"{min_value:.1f} + ({current_rand}) * {(max_value - min_value):.1f}"

    # Pure arithmetic alternation for static mode.
    return f"{min_value:.1f} + ({(max_value - min_value):.1f}) * {parity_expr}"


def _wrap_frame_range(expr, start_frame, end_frame):
    """Gate a driver expression to 0.0 outside the active frame range."""
    # Use boolean arithmetic instead of a conditional expression because Blender's
    # driver parser can reject nested if/else forms in some builds.
    gate = f"((frame_var >= {start_frame}) * (frame_var <= {end_frame}))"
    return f"({expr}) * {gate}"


def _evaluate_value(
    min_value,
    max_value,
    interval_frames,
    value_mode,
    phase,
    randomization_type,
    object_random_value_a,
    object_random_value_b,
    object_seed,
    frame,
):
    """Evaluate the beat-flipper value numerically for a given frame."""
    time_value = (frame + phase) / interval_frames
    step = int(time_value // 1)
    parity = step % 2

    if value_mode == "RANDOM":
        if randomization_type == "OBJECT_CONSTANT":
            return object_random_value_a if parity == 0 else object_random_value_b

        hash_value = math.sin(step * 12.9898 + object_seed + 78.233) * 43758.5453
        random_value = hash_value - math.floor(hash_value)
        return min_value + random_value * (max_value - min_value)

    return min_value if parity == 0 else max_value


def _step_at_frame(interval_frames, phase, frame):
    """Return the current beat step index for a frame."""
    return int(math.floor((frame + phase) / interval_frames))


def _apply_baked_interpolation(id_block, prop_name, interpolation_mode):
    """Set interpolation style for baked keyframes on an ID custom property."""
    data_path = f'["{prop_name}"]'
    for fcurves in _iter_action_fcurve_collections(id_block):
        for fcurve in fcurves:
            if fcurve.data_path != data_path:
                continue

            for point in fcurve.keyframe_points:
                if interpolation_mode == "STEP":
                    point.interpolation = "CONSTANT"
                elif interpolation_mode == "LERP":
                    point.interpolation = "LINEAR"
                else:
                    point.interpolation = "BEZIER"
                    point.handle_left_type = "AUTO_CLAMPED"
                    point.handle_right_type = "AUTO_CLAMPED"


def _on_bake_toggle(self, _context):
    """Disable interpolation and sync/offset when bake mode is disabled or enabled."""
    if self.bake_as_keyed_property:
        # In keyed mode: disable sync options and offset (animation starts at Start Frame)
        self.sync_mode = "SYNC"
    if not self.bake_as_keyed_property:
        self.bake_use_interpolation = False


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
    bpm_multiplier: FloatProperty(
        name="BPM Multiplier",
        description="Multiplier applied to BPM when calculating beat interval",
        default=1.0,
        min=0.001,
        soft_min=0.25,
        soft_max=4.0,
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
        description="How transitions align across selected objects (disabled in keyed mode)",
        items=[
            ("SYNC", "Synchronized", "All objects change at the same time"),
            ("RANDOMIZED", "Randomized Between Objects", "Each object gets a random phase offset"),
        ],
        default="SYNC",
    )
    phase_offset: FloatProperty(
        name="Phase Offset",
        description="Offset the beat pattern start in frames (disabled in keyed mode)",
        default=0.0,
        soft_min=-240.0,
        soft_max=240.0,
    )
    start_frame: IntProperty(
        name="Start Frame",
        description="First frame where the beat driver is active (required for keyed mode)",
        default=1,
    )
    end_frame: IntProperty(
        name="End Frame",
        description="Last frame where the beat driver is active (required for keyed mode)",
        default=250,
    )
    bake_as_keyed_property: BoolProperty(
        name="Bake As Keyed Property",
        description=(
            "Insert keyframes for the custom property within the enabled frame range "
            "instead of creating a scripted driver"
        ),
        default=False,
        update=_on_bake_toggle,
    )
    bake_use_interpolation: BoolProperty(
        name="Use Interpolation",
        description="Interpolate between baked change points",
        default=False,
    )
    bake_interpolation_mode: EnumProperty(
        name="Interpolation Type",
        description="Interpolation style for baked keyframes",
        items=[
            ("LERP", "Lerp (Linear)", "Use linear interpolation between keys"),
            ("SMOOTHSTEP", "Smoothstep", "Use smooth Bezier interpolation between keys"),
        ],
        default="LERP",
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

        if settings.bpm <= 0.0:
            self.report({"ERROR"}, "BPM must be greater than zero")
            return {"CANCELLED"}

        if settings.bpm_multiplier <= 0.0:
            self.report({"ERROR"}, "BPM Multiplier must be greater than zero")
            return {"CANCELLED"}

        scene = context.scene
        fps = scene.render.fps / scene.render.fps_base
        effective_bpm = settings.bpm * settings.bpm_multiplier

        if effective_bpm <= 0.0:
            self.report({"ERROR"}, "Effective BPM must be greater than zero")
            return {"CANCELLED"}

        # interval_frames = seconds_per_beat * frames_per_second
        # = (60 / effective_bpm) * fps
        interval_frames = (60.0 / effective_bpm) * fps

        if interval_frames <= 0.0:
            self.report({"ERROR"}, "Calculated interval must be greater than zero")
            return {"CANCELLED"}

        if settings.end_frame < settings.start_frame:
            self.report({"ERROR"}, "End Frame must be greater than or equal to Start Frame")
            return {"CANCELLED"}

        is_bake_mode = settings.bake_as_keyed_property
        use_bake_interpolation = is_bake_mode and settings.bake_use_interpolation

        # Pre-sample shared values once when all objects should share the same randoms.
        is_shared = settings.object_value_scope == "SHARED"
        shared_value_a = random.uniform(settings.min_value, settings.max_value)
        shared_value_b = random.uniform(settings.min_value, settings.max_value)
        shared_seed = 0.0

        added_count = 0
        skipped_no_data = 0
        current_frame = scene.frame_current

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
            _configure_property_ui(
                id_block=target_block,
                property_name=driver_prop_name,
                min_value=settings.min_value,
                max_value=settings.max_value,
            )

            if is_shared:
                object_random_value_a = shared_value_a
                object_random_value_b = shared_value_b
                object_seed = shared_seed
            else:
                object_random_value_a = random.uniform(settings.min_value, settings.max_value)
                object_random_value_b = random.uniform(settings.min_value, settings.max_value)
                object_seed = random.uniform(0.0, 1000.0)

            # In keyed mode, start beat pattern at Start frame (phase aligns beat 0 to frame start_frame)
            # In driver mode, use sync_mode and phase_offset settings
            if is_bake_mode:
                phase = float(-settings.start_frame)
                target_block[phase_prop_name] = 0.0
            else:
                if settings.sync_mode == "RANDOMIZED":
                    phase = random.uniform(0.0, interval_frames)
                    target_block[phase_prop_name] = phase
                else:
                    phase = float(settings.phase_offset)
                    target_block[phase_prop_name] = 0.0

            if is_bake_mode:
                if not (target_block.animation_data and target_block.animation_data.drivers):
                    _prime_keyed_property_visibility(target_block)

                previous_step = None
                for frame in range(settings.start_frame, settings.end_frame + 1):
                    current_step = _step_at_frame(interval_frames, phase, frame)
                    if previous_step is None or current_step != previous_step:
                        baked_value = _evaluate_value(
                            min_value=settings.min_value,
                            max_value=settings.max_value,
                            interval_frames=interval_frames,
                            value_mode=settings.value_mode,
                            phase=phase,
                            randomization_type=settings.randomization_type,
                            object_random_value_a=object_random_value_a,
                            object_random_value_b=object_random_value_b,
                            object_seed=object_seed,
                            frame=frame,
                        )
                        target_block[driver_prop_name] = baked_value
                        target_block.keyframe_insert(data_path=f'["{driver_prop_name}"]', frame=frame)
                    previous_step = current_step

                keyed_interp_mode = settings.bake_interpolation_mode if use_bake_interpolation else "STEP"
                _apply_baked_interpolation(
                    id_block=target_block,
                    prop_name=driver_prop_name,
                    interpolation_mode=keyed_interp_mode,
                )
            else:
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
                # Always wrap with frame range for driver mode consistency
                driver.expression = _wrap_frame_range(
                    base_expr,
                    start_frame=settings.start_frame,
                    end_frame=settings.end_frame,
                )
            added_count += 1

        _force_driver_evaluation(scene, current_frame)
        _refresh_blender_ui(context)

        if added_count == 0 and settings.target_mode == "DATA":
            self.report({"ERROR"}, "No selected objects have object data")
            return {"CANCELLED"}

        action_label = "Baked keyed property on" if is_bake_mode else "Added driver on"
        msg = f"{action_label} {added_count} target(s)"
        if skipped_no_data > 0:
            msg += f"; skipped {skipped_no_data} object(s) without data"

        self.report({"INFO"}, msg)

        _refresh_blender_ui(context)

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
        removed_key_curves = 0
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
                    removed_key_curves += _remove_fcurves_for_property(target_block, key)
                    del target_block[key]

        msg = f"Removed {removed_drivers} driver(s) and {removed_key_curves} keyed curve(s)"
        if skipped_no_data > 0:
            msg += f"; skipped {skipped_no_data} object(s) without data"

        self.report({"INFO"}, msg)

        _refresh_blender_ui(context)

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
        removed_key_curves = 0
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
                removed_key_curves += _remove_fcurves_for_property(target_block, latest_prop)
                del target_block[latest_prop]

            phase_prop = _phase_property_name(latest_prop)
            if phase_prop in target_block:
                removed_key_curves += _remove_fcurves_for_property(target_block, phase_prop)
                del target_block[phase_prop]

        msg = (
            f"Removed latest driver on {removed_drivers} target(s)"
            f" and {removed_key_curves} keyed curve(s)"
        )
        if skipped_no_data > 0:
            msg += f"; skipped {skipped_no_data} object(s) without data"

        self.report({"INFO"}, msg)

        _refresh_blender_ui(context)

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
        col.prop(settings, "bpm_multiplier", slider=True)

        layout.separator()

        col = layout.column(align=True)
        col.prop(settings, "value_mode")
        if settings.value_mode == "RANDOM":
            col.prop(settings, "randomization_type")
            col.prop(settings, "object_value_scope")
        
        # Hide sync and offset in keyed mode
        if not settings.bake_as_keyed_property:
            col.prop(settings, "sync_mode")
            col.prop(settings, "phase_offset")

        layout.separator()
        box = layout.box()
        box.label(text="Keyed Mode", icon="KEYFRAME")
        box.prop(settings, "bake_as_keyed_property")

        if settings.bake_as_keyed_property:
            box.label(text="Frame Range (Required)", icon="TIME")
            row = box.row(align=True)
            row.prop(settings, "start_frame", text="Start")
            row.prop(settings, "end_frame", text="End")

            interp_row = box.row(align=True)
            interp_row.prop(settings, "bake_use_interpolation")

            interp_type_row = box.row(align=True)
            interp_type_row.enabled = settings.bake_use_interpolation
            interp_type_row.prop(settings, "bake_interpolation_mode", text="")

            frame_range_invalid = settings.end_frame < settings.start_frame
            if frame_range_invalid:
                row = box.row()
                row.alert = True
                row.label(text="End Frame must be >= Start Frame", icon="ERROR")

        layout.separator()
        # Validate: if keyed mode is on, frame limits must be valid
        frame_range_invalid = settings.end_frame < settings.start_frame
        
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
