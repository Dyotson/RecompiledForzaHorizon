# In-game graphics settings

On Title Update 4, open **Graphics Settings** from the original pause menu. The
screen uses the original difficulty screen's spinner list, font, selection
highlight and controller input. No replacement game assets are installed.

Use Up/Down to select a setting and Left/Right to change it. **A / Save** stages
the displayed choices for the next launch. **B / Back** leaves the screen;
unsaved choices are discarded when it is opened again. Renderer settings are
not changed while a frame is being submitted.

The host writes a complete, atomically replaced `graphics-settings.json` request
in the launcher's data directory. The launcher validates all fields before
changing its configuration, saves it atomically, then removes the request. A
failed configuration save keeps the request for retry. Both launcher startup
and launching a game from an already-open launcher import pending changes.
Existing DLSS runtime preparation still handles downloading the runtime.

The menu currently exposes output resolution, reconstruction/anti-aliasing,
native render scale, frame limit, VSync, anisotropic filtering and HUD placement.
DLSS is offered for NVIDIA on the Vulkan backend; FSR 3 is offered on Vulkan.
The HUD continues to use the configured output resolution with reconstruction.

The disc executable does not expose this entry yet. The native scene hooks are
guarded by `FORZA_TU4`; disc address porting and runtime validation are still
required before enabling it there.

## Local validation

The Windows TU4 host builds successfully. A copied profile was used to exercise
the real pause entry, changing a spinner, contextual descriptions, Save, Back,
and restoration of the pause list. Native output captures are 2560 x 1440.
An actual request saved by the guest menu was imported into an isolated
launcher configuration and persisted successfully. Launcher graphics import,
GPU, FSR 3, ultrawide and data-folder tests: 53 run, one platform skip.

The existing relaunch test has a Windows file-handle cleanup failure reproduced
unchanged on main. One DLSS run lost the Vulkan device before the pause menu
opened; native rendering was used for final layout validation. This feature
does not resolve that separate renderer stability issue.
