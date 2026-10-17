# In-game graphics settings

On Title Update 4, open **Graphics Settings** from the original pause menu. The
screen uses the original difficulty screen's spinner list, font, selection
highlight and controller input. No replacement game assets are installed.

Use Up/Down to select a setting and Left/Right to change it. VSync, texture
filtering and HUD placement preview immediately. **A / Save** keeps live changes
and persists all displayed choices. **B / Back** restores unsaved live changes.
Closing the settings screen through another path also restores unsaved changes.

Starred rows (resolution, reconstruction/anti-aliasing, native render scale and
frame limit) apply on the next launch. They allocate resources or configure
timing at startup; the menu does not modify their runtime flags. The native
description panel explains when each setting applies. HUD edge placement takes
effect in gameplay when ultrawide or custom HUD layout is enabled.

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

Live-preview testing changed filtering from 16x to 8x, disabled VSync and moved
the HUD anchors. Each runtime setter accepted the change in the same process.
Back restored all three original values. A second run saved 8x filtering;
leaving the screen kept it active and the pending launcher request contained
the matching value. Renderer sampler parameters are regenerated per draw,
while VSync and the HUD-layout calculation read their flags during execution.

After rebasing onto `82b282e`, the full launcher suite ran 179 tests with 10
failures, 5 errors and 23 skips. A separate checkout of that exact main revision
ran 171 tests with the same 15 failing test names and 23 skips; all eight added
tests passed. Existing failures concern environment cleanup, DLC links, tool
discovery, updater expectations and an open file in relaunch-test cleanup.

The Windows TU4 build and disc-mode syntax checks of the new hook and app
integration pass. The disc executable has not been built or run locally because
its generated code is not present; these syntax checks do not replace a full
disc build. One earlier DLSS run lost the Vulkan device before the pause menu
opened; native rendering was used for final layout validation. This feature
does not resolve that separate renderer stability issue.
