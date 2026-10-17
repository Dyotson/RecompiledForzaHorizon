# ReXGlue SDK patches we carry

`patches/rexglue-sdk/` holds this project's patches to the ReXGlue SDK (nightly 0.10.0.24,
commit `bd833a2`); `tools/build_rexglue_sdk.sh` applies them to the clone
`~/rexglue-sdk-src-forza` and installs the patched GPU plugin, runtime and codegen tool into
the overlay `~/rexglue-sdk-patched-forza`. Patches 0001-0035 came from RecompiledHaloReach,
whose `docs/sdk_patches.md` describes each one (the numbers match; this repo leaves out
0010, 0012, 0014, 0024, 0026 and 0027). Patches written here (0036, 0038 and 0039 for both
projects, measured in this game's races; RecompiledHaloReach `docs/perf.md` has the profile; 0040, 0042, 0043, 0048, 0049 and 0050 are this
project's alone):

| Patch | Area | What changes | Why |
| --- | --- | --- | --- |
| 0036 | Vulkan shared memory uploads | An upload of vertex or index data the CPU rewrote no longer ends the current render pass when no draw in it has read the uploaded pages: it is recorded before the render pass, and the uploads hoisted there share one barrier pair (`vulkan_hoist_shared_memory_uploads`) | Races at 144 ran 52,000 render pass instances and 133,000 barriers a second, nearly all for these uploads (10,600 and 27,000 with the patch) |
| 0037 | Video mode (runtime) | The guest refresh rate (`video_mode_refresh_rate`, its range and `VdQueryVideoMode`'s clamp) may go up to 480 Hz instead of 240 | 144 fps (and other rates above 120) can keep the game's divider of two: a 288 Hz guest vblank. With a 144 Hz vblank and no divider, the emulated GPU's swap waits (which end on a vblank, patch 0030) turn every frame that misses 6.9 ms into a 13.9 ms one: free roam made 72 fps at a 144 fps target. `docs/framerate.md` |
| 0038 | Vulkan submission | The deferred command buffer is replayed into Vulkan and submitted on a "Vulkan Submission" thread instead of the GPU command processor thread (`vulkan_threaded_submission`) | The replay took 11% of the command processor thread, which bounds the races above 60 fps |
| 0039 | Shared memory | `clear_memory_page_state` off by default, as in Xenia (`--clear_memory_page_state=true` restores the SDK's default) | On, every page the CPU wrote and the GPU read was uploaded again after every frame: 74,000 uploads (2 GB) a second in a race at 144, 1,800 without |
| 0040 | Keyboard and mouse (runtime) | The left stick's keys ramp (`mnk_stick_ramp`, default 0.2 s: 60 % at once, full lock over the ramp, released in half of it); the mouse drives the right stick by its speed, low-passed over the game's polls (1000 px/s is half the stick at sensitivity 1, five times the SDK's old scale); `Shift`, `Control` and `Alt` work as bindings on their own | Steering with keys was full lock at once; a mouse moved at normal speeds stayed inside the game's dead zone of the look stick; a key bound to a modifier never fired. `docs/playing.md` |
| 0042 | Vulkan render targets (debug) | `vulkan_render_target_initial_fill` (default 0, unchanged behaviour): 1 clears a new host color render target to zero before its first use, 2 fills it with magenta (64, 0, 64, 1); each fill is logged | A render target the guest never wrote holds whatever the driver's memory had; filling it shows whether the game reads such memory (driver-dependent flicker, #34; `docs/rendering.md` > "Screening for driver-dependent bugs") |
| 0043 | Presenter (runtime) | `present_effect` accepts `cas` and `fsr` (AMD FSR 1: EASU upscaling, repeated up to 4x, then RCAS) on Linux and Windows, Vulkan and Direct3D 12: `REX_HAS_FIDELITYFX_SDK` is defined for the whole SDK build, no FidelityFX library needed. `fsr2` / `fsr3` stay out unless the SDK is built with the FidelityFX runtime | The nightly SDK is built without the `REXGLUE_ENABLE_FIDELITYFX` option, so `present_effect` allowed only `bilinear` and the launcher's cas / fsr / fsr2 / fsr3 entries did nothing. The CAS and FSR 1 shaders are precompiled in the SDK source (`src/ui/shaders`); only the temporal path (FSR 2/3) needs the FidelityFX library (#44; `docs/rendering.md` > "Upscaling") |
| 0048 | Resolve readback | The readback buffers of a resolve are keyed by the written range plus the copy's source (depth or color) and destination format (format, number format, endian, swap, array/slice), not the range alone. Exponent bias, EDRAM base and size stay out of the key | Photo mode (#54): the saved photo is a 1280x720 color resolve into the range a depth resolve fills every frame. With the range as key, `some` treated it as an old key and never copied it back (the CPU encoded whatever an earlier copy left there), and `fast` handed the CPU the previous resolve of that range, the depth buffer. With the copy's kind in the key it is a first-seen key: copied back after a GPU wait. A key is first-seen whenever the range alone was, so everything `some` copied before (car thumbnails) is still copied; race fps at 144 unchanged (`docs/perf.md`) |
| 0049 | Draws (Vulkan, Direct3D 12) | The memexport readback check after a draw looks at the draw's memexport ranges first, and only then at the setting | The setting check looks the legacy setting up by name (the registry lock, two `std::string`s and a hash lookup) and ran on every draw, memexport or not: in a race 8-15% of the command processor thread, most of its `malloc` and `memcpy` (#45, `docs/perf.md`) |
| 0050 | Timer queue (runtime) | On Linux and macOS the timer thread blocks on a condition variable until the next timer is due or a new one comes (disruptorplus' blocking wait strategy, whose two timed waits passed their arguments in the wrong order and did not compile); its timer slack is 1 us. Windows keeps the spin strategy (whole-tick deadlines there) | The spin strategy polled between timers (pause loops, `sched_yield` 19 times in 20, then a 1 ms sleep): with the 1 ms timestamp timer, 5-7% of a core in a race, and up to 1 ms late in its sleep phase (#45) |
| 0051 | Pipelines (Vulkan) | New setting `sync_pipeline_creation` (default off): while set, a draw whose pipeline is a placeholder waits for the creation thread's real pipeline (up to 10 s) instead of being skipped, and new pipelines are created at once, whatever `async_shader_compilation` says. Direct3D 12 not covered | A render made once and read back loses every draw skipped for a placeholder for good: with an empty pipeline cache the car's picture saved at a purchase had no car (#74). The game sets it around the picture and the livery renders of a car load (`src/hooks/thumbnail_sync.cpp`, #77); nothing else uses it |
| 0052 | Textures (Vulkan, Direct3D 12) | New setting `scaled_resolve_min_coverage_percent` (default 50; 0 = old behaviour): with a resolution scale above 1, a texture is loaded from the scaled resolve buffer only if resolves wrote at least that share of its guest memory range, not on any overlap of one page | A resolve that overlapped only the last mip pages of a 1024x1024 DXT5 texture made the whole texture a "scaled resolve" texture, read from a buffer that is zero where nothing was resolved: black (#77). Resolve targets are covered by their own resolve and stay scaled |

0037 is in `librexruntime.so`, so the overlay carries a patched runtime (as for 0028).
Without it the game falls back on its own: `src/hooks/frame_time.cpp` reads the setting's
range and uses a divider of one when twice the frame rate does not fit.

0044 fixes native clang-cl SDK builds on Windows. 0045 records the Vulkan
presenter's output-pipeline format so an unchanged swapchain does not rebuild
that pipeline every paint.

0047 uses hardware implicit LOD for ordinary automatic cubemap samples on NVIDIA,
preserving mip bias and filtering. The captured traffic-car reflection shader
produced a checker pattern with manually emitted coarse gradients; implicit LOD
matched the reference result. Explicit guest gradients and LOD, and other GPU
vendors, retain their existing path. See [Rendering issues](rendering.md#nvidia-car-reflection-sampling-2026-10-15).

0064 flushes pending Vulkan shader/pipeline storage writes before sleeping and drains queued records on shutdown. See [Performance](perf.md#flush-pending-vulkan-shader-cache-writes-before-waiting-49).

0065 skips repeated Vulkan GPU-to-host resolve work after a successful CPU copy in `some` mode, preserving the first copy and cache eviction. Other modes are unchanged. See [Performance](perf.md#nvidia-vulkan-resolve-readback-overhead-49-2026-10-15).

0063 adds native ultrawide rasterization, proportional HUD layout/edge anchors and square reflection cube faces. It applies independently of DLSS; see [Ultrawide](ultrawide.md).

0053 refreshes known reused car-thumbnail readback surfaces on Vulkan; see
[Rendering issues](rendering.md#reused-car-thumbnail-readbacks-vulkan).

0067 enables the SDK's existing direct clock-conversion fallback on Linux libc++
when C++20 clock conversions are unavailable, using the standard-library feature
macro rather than an Apple-only platform check. Native libstdc++ and MSVC
conversions remain unchanged.


0055 preserves the source stencil value when copying depth/stencil ownership
without shader stencil export. Previously the stencil-only shader skipped its
bit test and filled the destination with 255, rejecting dynamic shadows (#75).
See [Rendering issues](rendering.md#missing-dynamic-shadows-in-the-stencil-copy-fallback-75).

0068 binds a window of the scaled resolve buffer, not the whole buffer, for the readback downscale
compute pass when the buffer (512 MB x scale^2) is larger than `maxStorageBufferRange`. At render
scale 3 on AMD the whole-buffer binding was invalid and the car thumbnail was saved black (#102).
Smaller buffers (scale 1 and 2 on AMD) are unchanged. See
[Rendering issues](rendering.md#black-thumbnail-at-render-scale-3-102).

0069 limits the default Vulkan frame queue to two frames on NVIDIA, retaining
three on other vendors. This shortens blocking resolve-readback waits without
skipping CPU copies or changing readback-cache eviction. The three-slot resource
ring and fence-based retirement remain in place. Set
`vulkan_max_frames_in_flight=3` to restore the previous queue depth; nonpositive
values select the vendor default, and positive values are limited to 1-3.
See [Performance](perf.md#nvidia-readback-cache-miss-stalls-49-2026-10-16).

0070 adds FIFO_LATEST_READY (`VK_EXT_present_mode_fifo_latest_ready`, or its KHR promotion) to the
Vulkan presenter: enabled with the `presentModeFifoLatestReady` feature when the device has it, and
chosen over plain FIFO when the surface offers it (after mailbox, immediate and relaxed FIFO, which
keep their cvars). New cvar `vulkan_allow_present_mode_fifo_latest_ready` (default true); false or an
unsupported driver gives plain FIFO exactly as before. The chosen mode is logged once. It evens out
the frame pacing of FIFO at high frame rates on drivers without MAILBOX (#80). See
[Frame rate](framerate.md).

0066 averages supersampled RGBA8 car-thumbnail pixels during readback, keeping other formats and resolves unchanged. Requires the known-thumbnail refresh rule already on main (0053); see [Rendering issues](rendering.md#filter-supersampled-car-thumbnails-50).

0072 adds the AMD FidelityFX FSR 3.1 upscaler (no frame generation) as a second backend of
0046's scene/UI split: `fh1_upscaler=fsr3_quality|fsr3_balanced|fsr3_performance|fsr3_native`
on any Vulkan GPU. CMake fetches the FidelityFX SDK v1.1.4 GLSL passes and headers (MIT; pinned
commit and per-file SHA-256; `REXGLUE_FSR3_SDK`, `REXGLUE_USE_FSR3`) and embeds them; the
renderer compiles them with its glslang at start-up (`CompileFh1ComputeReflected`, with an
include handler and reflection for the bindings) and `fh1_fsr3.cpp` dispatches the SDK's pass
sequence. The DLSS state (inputs, depth/motion pass, jitter, status file) is no longer NGX-only;
jitter uses FSR's phase count in FSR modes. The MIT notice is installed under
`share/licenses/amd-fidelityfx-fsr3` and copied beside the GPU library. See
[Rendering issues](rendering.md#temporal-upscaling-with-amd-fsr-3-51-2026-10-16).

0073 raises the FSR 3 and DLSS scene input to at least the game's native 1280x720 (never above the
output), logged once: FSR 3 Performance at a 1080p output (960x540) crashed a player's game (#110).
See [Rendering issues](rendering.md#temporal-upscaling-with-amd-fsr-3-51-2026-10-16).

0046 adds native Windows Vulkan DLSS/DLAA with separate scene/UI rendering.
See [Native DLSS](native_dlss.md) for runtime setup, licensing and validation limits.

0057/0058 keep DLSS viewport jitter consistent across EDRAM tiles and rotate
depth, motion vectors and NGX jitter into the final color orientation. 0062
synchronizes unscaled scene resolves into the scaled native HUD cache (1440p
Performance uses a 1x scene and 2x HUD). All three belong to the DLSS integration
and apply without the ultrawide patch series.

0071 loads eligible scaled, tiled 32-bit textures directly from the scaled resolve
buffer into an R32_UINT storage view on NVIDIA. The shader preserves the original
texel bits and endian conversion, while removing the intermediate untile buffer
and buffer-to-image copy. It handles single-layer 2D base levels only; other
formats, mip chains, arrays, 3D layouts, unsupported storage formats, and other
vendors retain the original path. Image allocation/view failures also fall back.
`vulkan_direct_scaled_texture_upload=false` restores the original uploads. The
storage descriptors use the existing frame retirement rules, and image writes
are ordered before subsequent sampling or uploads. See [Performance](perf.md#scaled-texture-upload-cost-101).

0074 adds a racing wheel input driver (`src/input/wheel/`, issue #4). An SDL joystick that is a wheel (SDL
type, a wheel-like name, or any controller without a gamepad mapping with `wheel_mode = on`) is presented as
the Xbox 360 Wireless Racing Wheel: SubType 2 with the force feedback and wireless flags (FH1 checks exactly
that when it reads the capabilities), steering on thumb LX, pedals on the triggers, buttons and hat on the pad
buttons. Axes are detected from their resting values, with overrides and curves (`wheel_*` cvars). The
motors' vibration drives SDL haptic effects (a spring and a sine): approximate, untested on hardware. The
patch also turns on SDL's haptic subsystem in `thirdparty/CMakeLists.txt` (it was off) and the SDL gamepad
driver ignores wheels the wheel driver takes. Local builds need `libudev.h` (Homebrew `systemd`, added to
`tools/build_rexglue_sdk.sh`), otherwise SDL is built without udev and sees no joystick at all.
Test: a uinput virtual wheel; see [Playing](playing.md#racing-wheels-issue-4).

0075 adds the native graphics menu's Vulkan Apply transaction. A complete request
is consumed at a closed frame, after pending submissions finish. Scale-dependent
render targets, textures, reconstruction and pipelines are replaced together;
the previous configuration is restored if initialization fails. Active shader
microcode is transferred before releasing the old cache, and shader storage is
partitioned by output and scene scale. Native scene scaling is independent of
the HUD's output size. Scene-to-HUD blits use the actual raster sizes, including
fractional 1080p output within 2x backing storage. NVIDIA device extensions are
requested when the device is created so Native sessions can enable DLSS later.
The vblank worker observes refresh-rate changes without restarting. See
[In-game graphics settings](graphics-menu.md) for validation and current limits.

0076 lets passive ImGui dialogs opt out of continuous UI repaints. The performance
overlay draws with game frames; interactive dialogs continue to request redraws
for input and animations. This prevents the FPS display itself from driving the
presenter at a higher rate than the game.

0077 adds SMAA 1x to the FH1 scene/native-HUD bridge. It fetches pinned, hash-checked
MIT sources and lookup tables from iryoku/smaa, packages the license, and compiles
three Vulkan compute passes. SMAA bypasses NGX and temporal jitter/history. The
live graphics transaction accepts the new scene mode and suppresses final-image
FXAA while scene AA is active. Optional diagnostics log guest MSAA sample counts
without changing the guest registers or render-target layout.
