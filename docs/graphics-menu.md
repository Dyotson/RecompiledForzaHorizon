# In-game graphics settings

On Title Update 4, open **Graphics** above **Quit** in the original pause menu,
or below **Horizon Rally** on the main menu before gameplay.
The screen uses the original difficulty screen's spinner list, font, selection
highlight and controller input. No replacement game assets are installed.

Use Up/Down to select a setting and Left/Right to change it. VSync, texture
filtering and HUD placement preview immediately. **A / Save** applies resolution,
DLSS/DLAA/FSR 3 mode, native scene scale and frame limit in the running game, and
persists the choices. No game relaunch is needed. **B / Back** restores unsaved
previews; it does not undo settings that were already applied and saved.

**Performance overlay** offers Off, FPS, and FPS + frame-time graph. It previews
immediately and Back restores the previous choice. The counter measures guest
VdSwap frames, not simulation ticks or UI redraws. FPS uses a rolling second of
elapsed frame intervals; the graph keeps the last 240 intervals and auto-ranges
to retain long stalls. It draws over the native output without taking input.
The passive dialog does not request continuous presenter redraws (SDK patch
0076); interactive dialogs retain their existing repaint behavior.

**Quality preset** offers Custom, Auto, Low, Medium, and High. These are bundles
of reconstruction and texture filtering; they do not change the game's model,
shadow, or reflection quality. Output resolution, HUD placement, FPS cap, VSync,
and the monitoring overlay remain unchanged. Manual reconstruction, scene-scale,
or filtering edits return the selector to Custom. The preset selector itself
is an action; the resulting individual settings are persisted.

| Preset | Reconstruction when available | Filtering | Native fallback scale |
| --- | --- | --- | --- |
| Low | DLSS / FSR 3 Performance | 2x | 1x |
| Medium | DLSS / FSR 3 Balanced | 8x | output scale |
| High | DLSS / FSR 3 Quality | 16x | output scale |
| Auto | Native at 1080p; Quality above 1080p | 16x | output scale |

DLSS is offered only when its Windows/Vulkan runtime is available; otherwise
Vulkan presets use FSR 3. Auto chooses from supported features and the selected
output size. It does not benchmark or guarantee a target frame rate. At 4K,
the native fallback scale is 3x, which remains experimental.

The GPU receives one complete request, finishes its current frame and waits for
outstanding submissions before replacing scale-dependent render targets,
textures, reconstruction and pipeline caches. Active shader microcode is copied
before the old cache is destroyed. Shader storage is separated by output and
scene scale. An initialization failure restores the previous caches and flags;
the menu displays the error and does not persist the failed request.

The native scene scale is independent of the output/HUD resolution. For example,
Native 1x can render the scene at 1280x720 with a 2560x1440 HUD. Reconstruction
selects its own input size. Frame limit changes update the guest vblank timer
and reset the frame-time/render timing history. The game process and save remain
loaded throughout these changes.

On Windows/NVIDIA/Vulkan, the launcher prepares its pinned NVIDIA runtime in
the existing background worker even when starting with Native selected, so the
in-game menu can enable DLSS later. A setup failure still permits playing a
native session; selecting an unavailable reconstruction mode shows an error.
The renderer receives only the verified private runtime folder.

After successful application, the host atomically writes
`graphics-settings.json` in the launcher's data directory. The launcher validates
all fields before saving its configuration and removing the request. Both
launcher startup and launching from an already-open launcher import changes.

## Scope

Live resource changes currently require Vulkan, host render targets and a
standard 16:9 output (1080p, 1440p or 4K). Changing custom/ultrawide dimensions or
a D3D12 resource configuration live is not implemented; the menu reports an
error instead of partially applying it. HUD anchors still preview when
ultrawide/custom HUD layout is enabled. The TU4-only native scene hooks remain
guarded by `FORZA_TU4`; the disc executable keeps its existing menu.

## Validation

Windows TU4 host, GPU library and runtime builds pass. The complete 64-patch SDK
series applies to the pinned SDK. A separate SDK checkout built using only the
public branch's patches also passes; Native -> DLSS Quality -> DLSS Performance
was exercised in one process on that clean build, returning to gameplay with
1280x720 scene input and native 2560x1440 HUD output.

Copied-save tests on the RTX 5060 Ti / driver 617.14 exercised Native, DLSS
Quality, DLAA, FSR 3 Quality and DLSS Performance; 1080p, 1440p and 4K outputs;
native scene scales 1x and 3x; and frame limit changes from 120 to 30 and back.
The 30 FPS limit measured 30.0 FPS after switching. The 1080p test caught and
fixed a scene-transfer crop: blits now use actual raster dimensions rather than
the larger integer backing size. Captures retain the output's aspect ratio.

A session deliberately launched without its NVIDIA runtime rejected DLSS,
restored native rendering, displayed the failure and wrote no settings request.
Save/Back preview behavior and import/persistence tests remain covered.

All 11 added launcher tests pass. The full suite ran 182 tests: 10 failures,
5 errors and 23 skips, with exactly the same failing test names as a separate
current-main baseline (171 tests). Existing failures concern environment cleanup,
DLC links, tool discovery, updater expectations and relaunch cleanup.

Disc-mode syntax checks of the hook and app integration pass. The complete disc
build and AMD/D3D12 runtime testing were not available locally. These checks
do not establish general DLSS driver stability or cover every gameplay/event
transition.

The monitoring/preset extension was checked on the same clean public SDK build:
main-menu entry -> Graphics -> Auto -> Save -> Back -> Single Player -> free roam,
then Low / Medium / High and overlay FPS / graph / Off from the pause menu. Back
restored the saved graph mode and filtering. Auto saved DLSS Quality at 1440p in
the same process. The overlay read approximately 67-68 FPS in the garage exterior
while the independent FPS log read 68.1; this is an observed test scene, not a
benchmark of each preset. The monitoring/preset version displayed nine rows; the separate AA selector now makes ten.

The standalone `forza-recomp/tests/graphics_monitor_test.cpp` exercises steady
30/60 FPS, long hitches, stale samples, ring wraparound, and preset fallbacks.
It builds without the SDK using a C++17 compiler. The monitoring/preset version
passed its 12 menu launcher tests; the current AA extension is validated below.

## Anti-aliasing and upscaling

**Upscaling** selects Off, DLSS Quality/Balanced/Performance, or FSR 3
Quality/Balanced/Performance. Reconstruction includes temporal anti-aliasing;
the separate **Anti-aliasing** row then has one locked choice, Included
(upscaler). With upscaling Off it offers:

- **Game default (MSAA):** preserves the sample count requested by each guest
  render pass. No sample-count register override is made.
- **SMAA 1x:** the official high-preset spatial algorithm, running as three compute
  passes (edge detection, blend weights, neighborhood blending) on scene color
  before native HUD composition. It uses no history, jitter, or NVIDIA runtime.
- **NVIDIA DLAA:** output-sized temporal reconstruction on RTX, using the existing
  verified automatic runtime setup.
- **FSR Native AA (TAA):** output-sized FidelityFX temporal AA using the existing
  depth, motion-vector and jitter bridge. This is FSR's native AA implementation,
  not a newly written generic TAA algorithm.

These methods keep the game's own MSAA on intermediate targets. SMAA is an
additional spatial pass, not a substitute for a guest multisample resolve.
The launcher separates these choices too, migrates former DLAA / FSR Native
selections, and disables incompatible combinations. Final-image FXAA is disabled
when scene AA/reconstruction is active so it cannot filter the native HUD.
`forza_antialiasing` is launcher configuration; launch arguments translate it to
the renderer's existing scene-mode setting. The native menu saves the independent
`anti_aliasing` field alongside `upscaler` in its version-1 request.

### MSAA investigation

With `FORZA_AA_DIAGNOSTICS=1`, the TU4 run observed guest-requested 4x targets at
pitch 640, single-sample targets at pitch 1280, and 2x targets at pitch 1280.
This is a mixed per-pass layout. A global 2x/4x override would also need to change
EDRAM tile addressing, depth/color target layouts and guest resolves together.
The existing `native_2x_msaa` flag chooses the implementation of a guest 2x target;
it does not enable 2x AA globally. Its launcher label now states that distinction.
Forced MSAA counts remain unimplemented rather than offering unsafe overrides.

### Validation of the AA extension

The Windows public SDK and TU4 host built successfully, and all 66 SDK patches
apply. The separate DLAA launcher setting prepared its pinned runtime and reached
free roam with output-sized 2560x1440 input; DLAA -> SMAA then applied live.
A separate SMAA launch had no NVIDIA runtime folder, no `FORZA_DLSS_RUNTIME`,
and no loaded NGX modules. It reached free roam at 2560x1440,
and passed a short driving check. The same process switched SMAA -> FSR Native AA
-> FSR Quality -> SMAA without restart. Missing-runtime DLSS selection restored
the preceding FSR Native AA configuration and left the saved request unchanged.
The native AA row locked while upscaling was enabled and unlocked when disabled.
Captures show native HUD/menu text and no rainbow car in these tested scenes;
this is not a claim of complete temporal-artifact coverage.

The focused launcher/AA/vendor tests passed (47). The full root launcher suite
ran 187 tests with the same 15 existing baseline failures tracked by #121.
SMAA shader and lookup-table sources are pinned and SHA-256 checked against
[the official SMAA project](https://github.com/iryoku/smaa/tree/71c806a838bdd7d517df19192a20f0c61b3ca29d);
its MIT license is packaged with the SDK.
