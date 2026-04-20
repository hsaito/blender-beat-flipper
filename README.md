# Beat Flipper Driver

A Blender addon that adds BPM-driven custom-property drivers to selected objects. Useful for music-synced animations, procedural beat effects, and anything that should pulse or flip on a rhythmic interval.

Requires **Blender 3.0 or later**.

---

## Installation

### From a release zip (recommended)

1. Download `beat_flipper_driver-<version>.zip` from the [Releases](../../releases) page.
2. In Blender, open **Edit > Preferences > Add-ons**.
3. Click **Install…**, select the downloaded `.zip`, and confirm.
4. Enable **Beat Flipper Driver** in the add-ons list.

### From source

1. Clone or download this repository.
2. Zip only the `beat_flipper_driver/` folder:
   ```
   zip -r beat_flipper_driver.zip beat_flipper_driver/
   ```
3. Install the zip via **Edit > Preferences > Add-ons > Install…**.

---

## Usage

1. Select one or more objects in the 3D Viewport.
2. Open the **N-panel** (press `N`) and go to the **Beat Flip** tab.
3. Configure the settings, then click **Add Driver**.

The addon adds a custom property `beat_flipper_value` (and `_1`, `_2`, … for subsequent layers) to each selected object, driven by a scripted expression that advances at the configured BPM.

---

## Panel Reference

### Range

| Control | Description |
|---------|-------------|
| **Min** | Lower bound of the output value (0.0 – 1.0). |
| **Max** | Upper bound of the output value (0.0 – 1.0). |
| **BPM** | Beats per minute. Determines how often the value changes. Interval is computed from BPM and the scene's FPS. |

### Value Mode

| Option | Description |
|--------|-------------|
| **Randomized** | Picks a value in the Min–Max range on each beat. See sub-options below. |
| **Static (Min/Max)** | Alternates strictly between Min and Max each beat. |

#### Randomization Type *(visible when Value Mode = Randomized)*

| Option | Description |
|--------|-------------|
| **Per Phase** | Generates a fresh pseudo-random value on every BPM phase step. Uses a deterministic hash so scrubbing the timeline is stable. |
| **Per Object Constant** | Picks two random values at driver-creation time and alternates between them. Values are baked into the expression and stay fixed. |

#### Value Scope *(visible when Value Mode = Randomized)*

| Option | Description |
|--------|-------------|
| **Per Object** | Each selected object gets its own independent random values / sequence. |
| **Shared Across Objects** | All selected objects share the same random values / sequence. |

### Transition Mode

| Option | Description |
|--------|-------------|
| **Synchronized** | All selected objects change at the same time (phase offset = 0). |
| **Randomized Between Objects** | Each object receives a random phase offset so changes are staggered. |

### Frame Range *(optional)*

Check **Limit Start** and/or **Limit End** to restrict when the driver is active. Outside the range, the driven property evaluates to `0.0`.

| Control | Description |
|---------|-------------|
| **Limit Start** | Enable a start-frame boundary. |
| **Start Frame** | First frame where the driver is active. |
| **Limit End** | Enable an end-frame boundary. |
| **End Frame** | Last frame where the driver is active. End Frame must be ≥ Start Frame when both are enabled. |

---

## Buttons

| Button | Description |
|--------|-------------|
| **Add Driver** | Adds a new beat-flipper driver layer to each selected object. Repeated presses add additional layers suffixed `_1`, `_2`, etc. Disabled when the frame range is invalid. |
| **Remove Latest Driver** | Removes only the highest-numbered driver layer from each selected object. |
| **Clear Beat-Flipper Drivers** | Removes all beat-flipper drivers and their custom properties from each selected object. |

---

## Driver Properties

Each driver layer creates two custom properties on the object:

| Property | Description |
|----------|-------------|
| `beat_flipper_value` / `beat_flipper_value_N` | The driven output value. |
| `beat_flipper_phase` / `beat_flipper_phase_N` | The phase offset (frames) baked at creation time. |

---

## CI / Packaging

The included GitHub Actions workflow (`.github/workflows/package.yml`) automatically:

1. Reads the version from `bl_info` in `beat_flipper_driver/__init__.py`.
2. Zips the `beat_flipper_driver/` directory into `beat_flipper_driver-<version>.zip`.
3. Uploads the zip as a workflow artifact (retained 90 days).
4. On a version tag push (`v*`), creates a GitHub Release and attaches the zip.

To publish a new release, push a tag:

```bash
git tag v1.3.0
git push origin v1.3.0
```

---

## License

This project is provided as-is. See [LICENSE](LICENSE) if present.
