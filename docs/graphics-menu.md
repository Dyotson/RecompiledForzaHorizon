# In-game graphics settings

On Title Update 4, open **Graphics** above **Quit** in the original pause menu.
The screen uses the original difficulty screen's spinner list, font, selection
highlight and controller input. No replacement game assets are installed.

Use Up/Down to select a setting and Left/Right to change it. VSync, texture
filtering and HUD placement preview immediately. **A / Save** applies resolution,
DLSS/DLAA/FSR 3 mode, native scene scale and frame limit in the running game, and
persists the choices. No game relaunch is needed. **B / Back** restores unsaved
previews; it does not undo settings that were already applied and saved.

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
