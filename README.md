# Beat Flipper Driver

A Blender addon that adds BPM-driven custom-property animation layers to selected objects or object data. It supports both scripted drivers and baked keyed custom properties for music-synced animation, procedural beat effects, and rhythmic switching.

Manual zip installation supports **Blender 3.0 or later**.

The extension-repository installation path uses the bundled Blender extension manifest, which currently targets **Blender 4.2 or later**.

---

## Installation

### From Add-on Repository (Blender feature)

Repository URL for Blender:

https://blender-addon.hidekisaito.com/index.json

Catalog website (human-browsable):

https://blender-addon.hidekisaito.com/

1. In Blender, open **Edit > Preferences > Get Extensions**.
2. Open the repositories/settings area and add a custom repository URL.
3. Use `https://blender-addon.hidekisaito.com/index.json` as the repository URL.
4. Refresh repositories, find **Beat Flipper Driver**, then install/enable it.

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

Each add creates a custom-property layer on the selected target block:

- First layer: `beat_flipper_value`
- Additional layers: `beat_flipper_value.001`, `beat_flipper_value.002`, and so on

The layer is created either on the object itself or on its object-data block, depending on the selected Target mode.

---

## Panel Reference

### Target

| Control | Description |
|---------|-------------|
| **Object** | Store the beat-flipper properties on the object. |
| **Object Data** | Store the beat-flipper properties on the object's data block (mesh, curve, etc.). Objects without data are skipped. |

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
| **Synchronized** | All selected objects change at the same time. You can offset the pattern with **Phase Offset**. |
| **Randomized Between Objects** | Each object receives a random phase offset so changes are staggered. |

### Phase Offset *(visible in non-keyed mode)*

| Control | Description |
|---------|-------------|
| **Phase Offset** | Offsets the beat pattern start by a number of frames. Only used for non-keyed synchronized mode. |

### Keyed Mode

When **Bake As Keyed Property** is enabled, the addon bakes values as keyframes on the custom property instead of adding a scripted driver.

Behavior in keyed mode:

- The animation starts from **Start Frame**.
- **Transition Mode** and **Phase Offset** are hidden and not used.
- The add-on keys only beat-change points rather than every frame.

### Frame Range *(visible in keyed mode)*

| Control | Description |
|---------|-------------|
| **Start Frame** | First frame used for keyed baking. |
| **End Frame** | Last frame used for keyed baking. Must be greater than or equal to Start Frame. |

### Keyed Interpolation *(visible in keyed mode)*

| Control | Description |
|---------|-------------|
| **Use Interpolation** | Enables interpolation between keyed beat-change points. |
| **Lerp (Linear)** | Uses linear interpolation between keyed values. |
| **Smoothstep** | Uses smooth Bezier interpolation between keyed values. |

When **Use Interpolation** is disabled, keyed values use constant interpolation for hard steps.

---

## Buttons

| Button | Description |
|--------|-------------|
| **Add Driver** | Adds a new beat-flipper layer to each selected target. In non-keyed mode this is a scripted driver; in keyed mode this is baked keyframes. Repeated presses add Blender-style suffixed layers such as `.001`, `.002`, etc. Disabled when the keyed frame range is invalid. |
| **Remove Latest Driver** | Removes only the highest-numbered driver layer from each selected object. |
| **Clear Beat-Flipper Drivers** | Removes all beat-flipper drivers and their custom properties from each selected object. |

---

## Driver Properties

Each layer creates two custom properties on the target block:

| Property | Description |
|----------|-------------|
| `beat_flipper_value` / `beat_flipper_value.001` / ... | The output value, either driver-controlled or keyed. |
| `beat_flipper_phase` / `beat_flipper_phase.001` / ... | The stored phase value used when the layer is created. |

---

## CI / Packaging

The included GitHub Actions workflow (`.github/workflows/package.yml`) automatically:

1. Reads the version from `bl_info` in `beat_flipper_driver/__init__.py`.
2. Zips the `beat_flipper_driver/` directory into `beat_flipper_driver-<version>.zip`.
3. Uploads the zip as a workflow artifact (retained 90 days).
4. On a version tag push (`v*`), creates a GitHub Release and attaches the zip.

To publish a new release, push a tag:

```bash
git tag v1.2.0
git push origin v1.2.0
```

---

## License

This project is provided as-is. See [COPYING](COPYING) if present.
