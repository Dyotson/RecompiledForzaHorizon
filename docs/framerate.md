# Frame rate above 30 fps

Status: `frame_rate` in `forza.toml` (or `--frame_rate=N`) runs the game at 30 (the
console's, the default) or any rate from 60 to 240: 60, 120 and 144 are tested. The game
times its simulation in real time, so physics, the race clock and the videos keep their
speed at every rate; above 30 its frame time comes from the guest tick clock instead of
the kernel's millisecond tick (`src/hooks/frame_time.cpp`), so motion stays even above 60.
Addresses are in `default.xex` (base version); `docs/perf.md` explains the measurements.

## How Forza paces itself

**Frame limiter: the vblank callback.** The game registers `sub_8257E888` as D3D's vertical
blank callback (`sub_829EF650`, called at `0x8259CB9C`). On every vblank it stores the time
and the vblank data and tail-calls `sub_8247C678`, which counts vblanks (`0x832E126C`) and
sets the main loop's event (handle at `0x832E1260`), clearing the count, when:

- the developer option `mainthread30fps` (options object `0x832E29A0` +0x95B, the static
  object `sub_82479E88` returns; on by default) is set: the count has reached 2;
- it is off: every vblank, unless `frontend30fps` (+0x95A, off by default) is set and the
  flag `0x832E1269` is clear (then every second vblank).

The main loop (`sub_823ED888`) waits on that event once per frame. At the console's 60 Hz
that is 30 fps. Forza Motorsport 4, whose engine this is, ran with `mainthread30fps` off at
60 fps.

**Rendering is decoupled.** The main loop runs the simulation and hands the frame to a
render thread; when the render thread (bound by the GPU emulation) is still busy, the main
loop does not wait for it. In a race at a 144 fps target the main loop ran 144 times a
second while the render thread swapped about 70 frames a second (below). So the frame rate the
player sees is the render thread's, and the simulation keeps its own rate. Since #78 the main loop waits
for the render thread while that falls behind ("Render sync" below).

**Frame time: the kernel's millisecond tick.** After the wait the main loop reads a clock
(the object at `0x832ADD20`: `KeTimeStampBundle->TickCount` plus an offset, `sub_82CEBC40`)
and takes the milliseconds since the last frame (`r30`, 16 if more than 4 s passed):

```
dt = ms * 0.001                                     (f31)
if sub_8247C168() or the clock's +0x50 method:      dt as it is, leftover = 0
else if the frame took 16 or 17 ms:                 dt = 1/59.94, the difference goes into a
                                                    leftover (f30) paid back once it exceeds 1 ms
else:                                               dt = max(ms * 0.001 + leftover, 0.0001), leftover = 0
lockupdatetimeto60fps (+0x956):                     dt = 1/59.94
```

The result is stored at `game+0x1C0` (`stfs f31` at `0x823EDB84`) and handed to the
per-frame updates in `f31`. The 16/17 ms case is the engine's 60 fps path.

**Physics step.** The physics world step (`sub_82D4E2E0`) clamps the dt it is given to
0.2 s and runs `n = min(ceil(dt * CarPhysicsUpdateHz), 2)` substeps of `min(dt / n, 1/30)`
(`CarPhysicsUpdateHz` is 359 in `media/physics.zip:PhysicsSettings.ini`, the physics
settings object `0x834AA248` +0x178; the developer option `forcecarphysicsupdatehz`
overrides it). So every frame longer than 2.8 ms gets two substeps: 16.7 ms each at 30 fps,
8.3 ms at 60, 3.5 ms at 144. The car simulation is variable-step; there is no fixed-rate
accumulator to keep in step with the frame rate.

**Debug options.** A table of developer options (names in `default.xex`, parsed by
`sub_824F8150`, defaults set in `sub_824F7898`) shows the design: `unlockframerate` (+0x1048)
and `framesperrender` (+0x964; the main loop skips the vblank wait when `unlockframerate` is
set or `framesperrender` is not 1), `frontend30fps`, `mainthread30fps`,
`lockupdatetimeto60fps`, `forcephysicsminupdatehz`, `forcecarphysicsupdatehz`, `syncwait`
(present interval 1 instead of immediate), `showframerate`. Retail builds have no command
line to set them.

## What changes above 60 fps, and the fix

**Frame time.** Above 60 fps the millisecond tick makes each frame's dt whole milliseconds.
The frames start on emulated vblanks that the SDK's VSync thread fires at its next 1 ms
check, so at 144 fps the game measured 5 to 9 ms for frames that are 6.94 ms apart (sd
0.9 ms, 13% of the frame), and now and then 0 ms (a 0.1 ms frame). The sum stays real time,
but each frame's motion is off: the car's displacement from one frame to the next varied
with an sd of 16.5% of its local mean at 144 fps (a race, `FORZA_FRAME_TIME=game`), against
2.6-2.8% with the fix.

`src/hooks/frame_time.cpp` (above 30 fps) answers the main loop's call of `sub_8247C168`
(return address `0x823EDB08`, right after `f31 = ms * 0.001`) with true and `f31` set from
the guest tick clock, so the loop stores and passes on that dt (and clears its leftover).
Each frame gets a timestamp: the nominal time of the vblank that released it if the frame
started within 2 ms of that vblank's callback, else the time it started (a late frame). The
nominal vblank times are kept from the callbacks (`sub_8247C678` is overridden too): the
VSync thread fires vblank j at the first 1 ms check after start + j * interval, so a
callback is never early and the schedule is the earliest one consistent with every
callback. dt is the difference of two timestamps, so frames that keep up get exactly the
frame period, late frames their real length, and the sum is real time. The game's rules
stay: more than 4 s still counts as one 60 Hz frame, and dt is at least 0.1 ms. At 144 fps
99-100% of the frames get exactly 6.944 ms (`FORZA_FRAMETIME_LOG=1` logs the statistics).

**Pacing.** The divider of two stays above 30 and the guest vblank runs at twice the frame
rate (60 -> 120 Hz, 120 -> 240 Hz, 144 -> 288 Hz). A fast vblank matters when the GPU
emulation is the bound: the emulated GPU's swap waits end on a vblank (SDK patch 0030), so
the render thread's frames come in whole vblanks. The SDK capped the guest refresh rate at
240 Hz (`GetConfiguredVideoModeRefreshRate`, and the setting's range); SDK patch 0037
(`docs/sdk_patches.md`) raises it to 480 Hz. Without that patch the game falls back on a
divider of one for rates whose double does not fit (the hook clears `mainthread30fps`
before each vblank's check; `frame_time.cpp` reads the setting's range to know): 144 fps
then runs a 144 Hz vblank, and every render frame that misses 6.9 ms takes 13.9: free roam
rendered 71.9 fps instead of 111.5, and a race 65.2 instead of 70.1 (clean runs below).

**What else reads the frame.** The main loop hands this dt to its per-frame updates (14
calls, among them the world update `sub_823E40D8`, which steps the physics). Replays and Rivals
ghosts are recorded on time and error thresholds, not per frame
(`GameTunableSettings.ini`: `ReplayRecordKeyframeFrequency 20`, position, orientation and
velocity buffers, playback springs). AI traffic's path prediction updates every N frames
(`AI/Traffic/PathPrediction/UpdateIntervalFrames`), which only makes it more frequent at
higher rates. The pre-race camera sequence and the 3-2-1 countdown take the same time at 60
and 144 (start pressed to GO: 17.1 s and 16.9 s, read from the race clock in screenshots).

## Online with mixed frame rates

No gate is needed: a 144 fps player and a 60 fps player race together normally. Test (two
instances on one machine, private Forza Live server on 21600/21601, the Horizon World with
a world event, `--world-events 4 --world-event-laps 1`, both cars driven by
`tools/autodrive.py`, CPU drivers on both consoles; scratch harness derived from the
`docs/online_vision.md` tests): A (host) at 144, B at 60, then both at 60 as the baseline.
Both raced the event to the end and went back to the world (the harness's checks), each
seeing the other's car. `tools/carlog.py` sampled both games at once (same host clock) and
`tools/net_sync_report.py` compared each player's own car with its copy on the other
console (the first 144 run used a 144 Hz vblank, the second SDK patch 0037's 288 Hz):

| Pair | A's car as B sees it: mean / p95 distance | B's car as A sees it | Datagrams a second (both ways, per console) |
| --- | --- | --- | --- |
| A 60, B 60 | 0.06 / 0.12 m | 0.05 / 0.13 m | about 194 |
| A 144 (144 Hz), B 60 | 0.31 / 0.76 m (0.16 / 0.54 m shifted by 20 ms) | 0.06 / 0.14 m | about 266 (A sends about 150 a second, B about 100) |
| A 144 (288 Hz), B 60 | 0.42 / 0.83 m (0.04 / 0.12 m shifted by 20 ms) | 0.05 / 0.12 m | about 300 (A sends about 200 a second, B about 100) |

At about 25 m/s that is a few centimetres to a few tens of centimetres: the 144 fps car's copy
on the 60 fps console runs about 20 ms ahead (shifted by 20 ms it is as close as at 60
against 60), well below the network delay of a real connection. The traffic grows with the
frame rate (about 65 datagrams a second each way at 30 fps in an earlier free-roam test,
about 100 at 60, 150-200 at 144, more when the render thread keeps up): a 144 fps player
sends up to twice the traffic of a 60 fps one (about 50 KB/s to each peer at about 250
bytes a datagram; measured through the relay with three players: 15-18 KB/s per peer at 144 fps, `docs/online_vision.md`, "Three players"). Through the server's relay (160 KB/s per player, `--rate-limit`,
`docs/hosting.md`) that budget runs out sooner with several peers; direct peer-to-peer
paths are not limited. Seen in both
runs and unrelated to the frame rate: the host's race clock started about 12 s before the
peer's (A 00:15.150, B 00:03.100 at the same moment, 60 against 60).

**Rivals ghosts.** A ghost recorded at 30 fps (DriverA's 1:47.228 lap, ghost 4 of the test
server's data) raced in X RIVALS at 144 and at 60 fps (the user's Xenia save, private
server, `tools/autodrive.py` on the saved line): the ghost car (kind 2 in the car list)
reached each point of the lap at the same time after its start in both runs: the
difference was constant within 16 ms from 100 m to 3.3 km (a 0.72 s constant from the
start detection). A Rivals lap driven at 144 fps (1:55.546, against a board whose best
was 200 s so that the game submits it) was uploaded as a 17,992-byte ghost (header
`0000028D 000043B3 00000285 00000ABC`), the size of the 30 fps ghosts of similar laps
(17,332 bytes for 1:55.13, header `000002A0 0000410C 00000298 00000ABC`): the game records
ghosts on its thresholds, not per frame. That ghost, raced at 60 fps as the rival,
followed the lap the player drove at 144 with a constant delay (2.758 s from the start
detection, sd 15 ms over 58 points matched by position along the lap; 13 ms apart between
the first and the last ten). (In these runs the game submitted a Rivals lap only when it
beat the board's best from `GetBestScores`, at 60 and 144 alike.)

## The frame_rate setting

`frame_rate` (`src/main.cpp`; 30 by default; 60 to 240 allowed; it needs a restart) sets the
guest vblank (`video_mode_refresh_rate`, which `VdQueryVideoMode` reports and the SDK's
VSync thread follows) to twice the frame rate, or to the frame rate when twice is past the
SDK's limit (480 Hz with patch 0037, 240 without), unless `video_mode_refresh_rate` is set
explicitly (then the frame rate is that rate divided by the same divider). The frame
stats' `ontarget` uses the same target. Test switches: `FORZA_FRAME_TIME=game` (the millisecond frame time), `FORZA_RENDER_SYNC=0`
(no render sync, below),
`FORZA_VBLANK_DIVIDER=1|2`, `FORZA_FRAMETIME_LOG=1`, `FORZA_FRAMETIME_CSV=<path>` (per frame:
time, dt, the game's ms, on target, the player's car position).

## Measurements

Clean runs: one reserved window, one game at a time (`docs/perf.md`, 2026-10-12 rows). Race:
the GoPro Millennia Masters festival race (sign-up at the spawn point of the user's Xenia
save; Clear Springs Circuit, 7 AI cars), full throttle for 26 s from the countdown. Free
roam: the same save, full throttle for 50 s. "Guest" frames are the render thread's swaps;
the main loop ran at the target rate in every run.

| frame_rate (guest vblank) | Race: guest fps, p50 / p95 / p99 ms, stutters | Free roam: guest fps, p50 / p95 / p99 ms, stutters | Main loop dt: mean, sd (game's ms sd) |
| --- | --- | --- | --- |
| 60 before the hook (120 Hz) | 59.6, 16.8 / 18.1 / 21.6, 0 | 59.9, 16.7 / 18.1 / 19.7, 0 | (1/59.94 snaps) |
| 60 (120 Hz) | 59.6, 16.8 / 18.0 / 21.9, 0 | 59.9, 16.7 / 17.8 / 19.3, 0 | 16.667, 0.08 ms (0.81) |
| 120 (240 Hz) | 75.7, 13.0 / 17.6 / 18.6, 0 | 115.2, 8.4 / 11.5 / 13.1, 15 | 8.333, 0.08 ms (0.74) |
| 144 (288 Hz, SDK patch 0037) | 70.1, 14.2 / 18.0 / 19.0, 0 | 111.5, 9.2 / 11.2 / 12.5, 10 | 6.944, 0.18 ms (0.83) |
| 144 without patch 0037 (144 Hz, divider 1) | 65.2, 14.3 / 20.8 / 21.8, 1 | 71.9, 13.8 / 15.3 / 16.4, 1 | 6.944, 0.19 ms (0.85) |

- **Races are bound by the GPU emulation** above 60: the render thread makes 76 fps at a
  120 fps target and 70 at 144, its frames whole vblanks (above); free roam makes 115 at
  120 and 112 at 144. At 60 nothing changed with the hook (same fps and tail). With patch
  0037 the audio the game submits kept its rate at 144 (940 frames of 256 samples every
  5 s, `FORZA_AUDIOLOG`, as at 60), and the 1 ms polling of the SDK's VSync thread shows no
  worse tail at 288 Hz than at 240 Hz (p99 12.5 ms at 144 against 13.1 ms at 120).
- **Simulation speed.** The race clock against real time between two screenshots 18.3 s
  apart: 18.367 / 18.315 s (60 before), 18.367 / 18.315 (60), 18.284 / 18.315 (120),
  18.458 / 18.360 (144); the differences are the screenshot latency (up to 0.1 s). The
  car's distance from the launch (sampled from guest memory, `tools/carlog.py`) at 1 / 2 /
  3 s: 9.1 / 28.5 / 55.2 m (60 before), 9.0 / 28.3 / 55.9 (60), 9.0 / 28.2 / 56.1 (120),
  9.0 / 28.4 / 56.8 (144); 0-100 km/h in 2.38-2.48 s at every rate (2.67 s in the 60-before
  run, a slower launch). Past 5 s the AI cars and the first corner make the runs differ.
- **The same lap at every rate.** `tools/autodrive.py` driving the saved racing line
  (`AD_PATH_LOAD`) from the grid back to the start point, contended runs: 114.58 s at 60,
  114.56 s at 120, 115.13 s at 144 (the driver's own spread is about a second); 0-100 km/h
  2.40 / 2.43 / 2.39 s.
- **Even motion.** The player's car moved by the same distance every frame within 2.8% at
  144 (sd of each frame's displacement over the mean of its neighbours; 1.1% at 60, 1.2% at
  120), following dt within 0.5%. With the game's millisecond frame time at 144
  (`FORZA_FRAME_TIME=game`, contended) the same measure was 16.5%.
- Menus run at the target (144.0 fps, p99 8.0 ms at 144). No rendering fault in the
  screenshots at any rate. The race-clock, acceleration and lap checks at 144 ran before
  patch 0037 (144 Hz vblank); the Rivals runs and the second online
  run used it.

Earlier results (2026-10-10, before the GPU patches; 30 and 60 fps):

| Guest vblank | Main menu | Free roam | Race | Race clock / real time | Speed at race time ~0.7 / ~2.8 / ~5 s |
| --- | --- | --- | --- | --- | --- |
| 60 Hz (default) | 30.0 fps | 29.9 fps, p50 33.4 ms | 30.0 fps, p50 33.4 ms | 23.332 s / 23.339 s | 33 / 101 / 148 km/h |
| 120 Hz (`frame_rate = 60`) | 60.0 fps | 58.9 fps, p50 16.8, p95 19.5 | 41.6 fps, p50 24.8, p95 30.2 | 22.384 s / 22.351 s | 29 / 98 / 147 km/h |

The intro videos play at their speed at a 120 Hz vblank (they present every vblank and show
the same frames at the same times as at 60 Hz). The SDK's 10 ms sleep in
XMPGetPlaybackController (`FORZA_XMP_NOSLEEP`, docs/perf.md) does not limit the frame rate.

**Tools.** `tools/perf_scenario.sh race DIR warm --user_data_root=<copy of the Xenia save>
--frame_rate=N` (with `FORZA_XUID`) runs the race scenario: free roam, the sign-up at the
spawn (inputs X, A, A, X, then A at the race menu), the throttle held from the countdown,
screenshots for the race clock and the car positions. `tools/carlog.py PID SECS OUT`
samples every car's position from a running game at 250 Hz; `tools/frametime_report.py DIR`
reads `FORZA_FRAMETIME_CSV` (per-frame displacement against dt) and the car log (distance
from the launch, 0-100 km/h, the time back at the launch point);
`tools/net_sync_report.py A B` compares two consoles' car logs. The lap runs used
`tools/autodrive.py` with `AD_PATH_LOAD` (a saved Clear Springs racing line, written by
`AD_PATH_SAVE`). Rivals from the spawn: X (the ticket), X (RIVALS), A (the rival), A (the car), X (race
anyway), A (START RIVALS).

## Leftovers

- **Races above 60 are bound by the GPU emulation** (the render thread waits in
  `BlockOnFence`): 76 fps at 120, 70 at 144 with the SDK as it was. SDK patches 0036, 0038 and
  0039 (docs/perf.md > "GPU emulation at high refresh rates") raised the race at 144 to 97 fps
  (p99 15 ms), at 120 to 90 fps and free roam at 144 to 141; the command processor is still
  the bound.
- **Patch 0037 for RecompiledHaloReach**: the patch is written for both (Reach's own
  frame-rate scheme has the same 240 Hz cap); not ported yet.
- `tools/build_rexglue_sdk.sh` stopped at patch 0018 on a clone that already had the whole
  series (0035 changed 0018's context, so neither the forward nor the reverse check passed).
  Fixed: the series is applied to a temporary index and only files that differ are rewritten.
- Not measured: rates other than 60, 120 and 144 (165 and 240 run 330 and 480 Hz vblanks),
  more than two players online at mixed rates, the relay path (the test peers talked
  directly), Windows. Run at 240 (#66, no numbers): a new profile's festival intro video
  and opening drive, an Autoshow purchase and the return to free roam, Single Player
  after a restart (238 fps in the menus, 225-235 in the Autoshow).
- Seen at every rate, not from this work: in a world event the peer's race clock started
  about 12 s after the host's (the cars raced together); at 60 fps in the race the frames
  handed to the presenter have a p99 of 32 ms (14-15 stutters in 26 s, before and after
  the hook) while the guest frames are steady.
- The developer options `framesperrender` and `unlockframerate` were not tried (they would
  run the main loop without the vblank wait).

## Render sync: HUD missing and judder when the render thread falls behind (#78, #62)

Report (#78, RX 9070 XT, Windows, `frame_rate = 240`, render scale 2, FXAA extreme; #62 the same
symptom): in a race among AI cars the frame rate drops, motion stutters and the HUD flickers. The
reporter's video shows single frames with the whole HUD missing (progress, place, standings,
minimap, speedometer; the 3D name tags stay), and in the pack about 10-17 repeated frames a second
of its 60 fps capture.

Cause: above 30 fps the main loop runs at the target rate whatever the render thread makes, and the
render thread draws the newest main frame it finds (see "Rendering is decoupled"). In the race at
240 the render thread made 63 frames a second here (GPU emulation bound) while the main loop ran
237: three or four main frames per drawn frame. Now and then the drawn frame has no HUD, and the
simulated time between two drawn frames is a whole number of 4.2 ms main frames (12.5 or 16.7 or
20.8 ms for frames shown about 16 ms apart), which is judder on top of the low frame rate. At 60,
where the render thread keeps up, neither happens.

Fix (`src/hooks/frame_time.cpp`, "render sync"): the VdSwap hook counts the render thread's swaps
and keeps a moving average of their interval (about 16 swaps). While that interval is more than
1.15 target frames and swaps keep coming (one in the last 100 ms), each main frame waits after its
timestamp until the render thread has swapped since the previous main frame (a condition variable,
at most 50 ms), so the game runs at the rate it draws. The timestamp is taken before the wait, so
dt still sums to real time; a late frame gets its real length as before. When the render thread
keeps up, nothing waits (at 60: 0 waits, dt 16.667 ms on 100% of frames, as before). At 30 (the
default) the hook does nothing. `FORZA_RENDER_SYNC=0` turns it off; the FRAMETIME line counts the
waits.

Measured: race scenario (Millennia Masters, 7 AI cars, 26 s at full throttle), TU4 build, warm
cache, the reporter's settings (`--frame_rate=240 --resolution_scale=2 --anisotropic_override=5
--swap_post_effect=fxaa_extreme`), BENCH lock, one game at a time. HUD missing = burst screenshots
(`FORZA_SCREENSHOT_BURST=20:1`, 13 bursts of 20 consecutive frames, 247 frames a run) with no white
pixels in both the lap counter and the standings:

| Run | Main loop | Guest fps | p50 / p95 / p99 ms | Frames with no HUD |
| --- | --- | --- | --- | --- |
| 240, scale 2, before (2 runs) | 237 fps | 62.9 / 62.7 | 15.8-16.0 / 21.6-22.5 / 27.2-27.7 | 5 and 1 of 247 |
| 240, scale 2, render sync (3 runs) | 63 fps | 63.1 / 63.2 / 62.9 | 15.9-16.0 / 17.0-17.1 / 17.8-18.1 | 0, 0, 0 of 247 |
| 240, scale 1, before | 237 fps | 105.5 | 10.0 / 12.2 / 13.1 | 1 of 247 |
| 240, scale 1, render sync | 108 fps | 103.9 | 10.2 / 12.2 / 12.8 | 0 of 247 |
| 60, scale 2, before | 60 fps | 59.8 | 16.7 / 17.7 / 19.1 | 0 of 247 |
| 60, scale 2, render sync (0 waits) | 60 fps | 59.8 | 16.7 / 17.6 / 18.6 | 0 of 247 |

The drawn frame rate does not change (the render thread is the bound); the HUD stays, the tail of
the frame times shortens (p95 22 to 17 ms) and each drawn frame advances the simulation by its own
length. Boot, title, menus, loading and the race intro ran at the same rates with and without it.

Left (not changed here):

- The race frame rate itself: the GPU emulation is the bound (docs/perf.md), 63 fps at scale 2 and
  105 at scale 1 on the RX 9060 XT. Pipelines were not the stutter here (25-31 created in the
  race with a warm cache, and the reporter's later sessions loaded 689 stored pipelines; only
  their first session started cold).
- Presentation at render scale 2 with FIFO (the default present mode): at 240 the presenter showed
  53 of the 63 frames a second here, at irregular 1-5 host vblanks (144 Hz monitor), and the title
  screen was held to 144 fps (240 at scale 1). With `vulkan_allow_present_mode_mailbox = true`
  every frame was shown (62.8 of 63.1 fps, p95 17.1 ms). At 60 with scale 2 FIFO showed every
  frame. The reporter's AMD Windows driver offers no MAILBOX (IMMEDIATE, FIFO, FIFO_RELAXED and
  FIFO_LATEST_READY). Patch 0070 uses FIFO_LATEST_READY (`VK_EXT`/`VK_KHR_present_mode_fifo_latest_ready`)
  instead of plain FIFO when the device feature and the surface offer it: vsync without tearing,
  but the vblank takes the newest finished frame instead of the oldest queued one. Switch:
  `vulkan_allow_present_mode_fifo_latest_ready` (default true, launcher: Advanced, "Use FIFO
  latest ready"); false keeps plain FIFO. The chosen mode is logged once ("VulkanPresenter:
  presentation mode ..." and the game's "present mode" line). Not measured on hardware yet: this
  RADV does not offer it (plain FIFO as before); an AMD Windows player is asked to test.

## Garage and showroom camera timing (2026-10-17)

The frontend has two frame-based camera paths independent of the race-intro
timing below. `CUI4AnimatedCamera` passes a fixed 1/30 s (1/60 with its developer
option) to `CTSCCamera` or `CCamAnimPlayer` on each update. The automatic orbit
in `CUI4CarTargetCamera` adds 0.1 degree each update. Both speed up as the UI
frame rate increases.

`hooks/garage_camera.cpp` replaces only the animated camera caller's fixed step
with elapsed time and the orbit increment with 3 degrees per elapsed second.
Other callers retain their original dt, and manual rotation and camera
transitions retain their existing paths. Per-camera animation timestamps avoid
counting time spent dormant; returning after a gap above 250 ms starts with one
original step rather than skipping ahead through the shot.

A copied, progressed save was used in Dak's Garage / Custom Upgrade on Windows
TU4 at native 2560x1440 with the 120 FPS limit. The original camera clock advanced
8.0000004 seconds in 2.0030654 real seconds (3.994x). The corrected clock advanced
1.9998623 seconds in 2.0016332 real seconds (0.999x). The fixed 1/30 input and
the elapsed-time input were also observed at the guest update hooks. These are
camera-clock measurements, not estimates from the selected FPS cap.

`FORZA_GARAGE_CAMERA=game` retains the original timing for comparison;
`FORZA_GARAGE_CAMERA_TRACE=1` logs the caller, camera and dt every 300 updates.
The standalone `tests/garage_camera_math_test.cpp` checks ten-second orbit
distances at 30/60/120/144/240 FPS, delayed frames, wrapping, zero and invalid dt.
The Windows TU4 build passes. Disc addresses are mapped; the disc build has not
been run locally.

## Fixed: race-start animations looked too fast (#7, 2026-10-12, fixed 2026-10-14)

Report: in every race start the crowd, the intro shots, the camera sweep over the grid and
the countdown look too fast. The player saw it at the default `frame_rate` (30) on a 144 Hz
monitor, and again while watching test runs of the current build. It was the stands crowd (below).

What was measured (Millennia Masters race start, host wall clock, no debugger attached
while sampling):

- **Shot timeline.** The cuts land at the same wall time at frame_rate 30, 60 and 144: the
  cut to the player's car 11.0 / 10.7 / 10.7 s after START RACE, the chase camera 14.0 /
  13.7 / 13.7 s, GO about 17.3 s. Screenshots every 0.1-0.3 s show the same camera pose at
  the same wall time at 60 and 144.
- **Clocks that follow real time.** The pre-race track camera (`CTSCCamera` family; update
  `sub_82862170`, called from the world update) gets the main loop's dt (1/144 s at 144)
  and its clock (+0x2D8, double, advanced in `sub_82855900`) runs 1.003 s per second.
  Granny model clocks (`GrannySetModelClock` = `sub_829C3CB8`, thunk `sub_823F7660`; set
  from `sub_823F7858` and `sub_82463910`) run 0.985 s per second at 30 and 1.000 at 144.
  They are driven on the render thread by `CProceduralAnimatedScene` (vtable slot 15,
  `sub_8245A2F8`) with the simulated time accumulated since the last render (per-view dt at
  +0x1DE8, set by `CTrackPresentation` slot 54, `sub_823F1828`).
- **Guest swaps** run at 30.0 a second at 30 and never above 144 at 144, so nothing is
  consumed twice per simulated frame; the guest vblank is the SDK's wall-clock timer
  (`GraphicsSystem` VSync thread), not tied to host presents.

Fixed steps found, none of them seen driving the race start:

- `CAnimatedModelPresentation@Presentation_Unified::Update` (vtable slot 14,
  `sub_82DD2B78`) adds 1/60 per call through `sub_82D83268`; not called in the race. In
  the opening drive animated models get the real dt through `sub_82D8E458`.
- `CCrowdPresentation@Presentation_Unified` (sprite crowd: 25 ms flipbook frames in
  `sub_82DE2130`, skinned crowd bake at 1/30 in `sub_82DDD6A8`): never called in the
  race or the opening drive.
- A render-thread fade (`sub_8257E5B8`, render object +0x1940..+0x1964) counts down 1/30
  per rendered frame: right at 30, faster above.

So the visible crowd is probably not the Granny models that were clocked: next, find the
crowd draw in a RenderDoc capture of the race start (its shader and the constant that
animates it: impostor or flipbook crowds, a per-frame counter, a vblank count), measure a
crowd member's motion period in frame-dump bursts at 30, 60 and 144, and compare it with
the clip lengths in `media/Spectators.zip` (`anims/*.anim.bin`). Tools used: gdb on the
running game (breakpoints on `sub_XXXXXXXX`, f1 is at PPCContext+344), sampling guest
memory through `/proc/PID/mem`, and a scan of the guest heap for values that rise
steadily, compared between 60 and 144.

### Findings (2026-10-14)

**Car images (#3) are a resolve readback problem, at every frame rate.** The car
thumbnails (Car Select, garage tiles, the car panel picture) are rendered once, read back
by the CPU, compressed and saved in the profile: `ForzaProfile/Thumbnails/Thumbnail_N.xdc`
(header `cxds`, version 2, sizes, then raw deflate of a D3D texture: 0x34-byte header,
fetch constant 768x288 `k_8_8_8_8`, tiled). The SDK's `readback_resolve` defaults to
`none`, so the CPU reads whatever was in guest memory: every thumbnail this build made
(`Thumbnail_46`-`52` in the user's TU4 profile, about 860-884 KB each, nearly
incompressible) is noise or stale data, and Car Select shows noise instead of the car (seen
at 30 and at 144). The Xenia save has the same: thumbnails made before its config had
`readback_resolve = "fast"` are garbage (`Thumbnail_3`, `4`, `17`), later ones are correct
car renders (about 20-120 KB). With `--readback_resolve=fast` a thumbnail regenerated by
this build (after an upgrade in the garage) is a correct McLaren F1 render (85 KB). A
thumbnail is rebuilt when the car changes (upgrade, paint); a deleted one shows black
until then (deleting them and entering and leaving the garage regenerates none). Broken
ones already in a save stay broken until the car is changed (`docs/playing.md`).

Fix: `readback_resolve` defaults to `some` (first `fast`; `some` since `fast` cost 16-21% at 144; `ApplyForzaGpuCvarDefaults` in
`src/main.cpp`, applied once the GPU plugin, which defines the setting, is loaded; a value
from `forza.toml` or the command line wins). Checked on the TU4 build without the flag: an
upgrade rebuilt a broken thumbnail as a correct render. Cost of each mode: docs/perf.md > "Resolve readback".

**Crowd at the race start (#7) moves faster above 30.** Screenshot bursts
(`FORZA_SCREENSHOT_BURST=N:K`, every frame) of the Millennia Masters intro, 4 s after START
RACE, same shot: at 30 a spectator does a slow arm wave over about 0.9 s; at 144 the same
spectators switch poses every 60-120 ms. Ruled out with measurements (base build, call
counters on about 5800 functions, rates per scene at 30 and 144):

- Granny model clocks: every model (18 in free roam, up to 133 in the intro) runs
  0.997-1.002 s per second at 144 (`GrannySetModelClock` per model). Forcing every model
  clock to 0 does not stop the stands crowd, so the stands people are not driven by them.
- Controls whose local clock the game sets itself (`GrannySetControlRawLocalClock` from
  `sub_82463910` and `sub_82D83170`): held poses (rate 0, speed 0), not the crowd.
- `CCrowdPresentation@Presentation_Unified` update paths (`sub_82DE2130` flipbook,
  `sub_82DDD6A8` 1/30 bake), `CCrowdPresentation@Default_Presentation`,
  `CCrowdPresentationDeferred` and `CProceduralCharacters` methods: never called in the
  intro. The per-render crowd functions that do run (`sub_82DDE600`, `sub_82DE2958`,
  `sub_82DE3370`) do culling/LOD, no time step found.
- Fixed steps that run per frame in the intro (rate x4.8 or x3.6 at 144) but are not the
  crowd: `sub_8243DF70` passes 1/30 per rendered frame to `sub_82466CF8` (culling radius
  scale), `sub_824DBC58` passes 1/60 per main frame to `sub_8265D7C8` (ignores it) and a
  virtual call, `sub_8257E5B8` (a sun-glare/occlusion fade, 1/30 per rendered frame),
  world update and `sub_825581E8`/`sub_8255DE80` only clamp dt to 1/30.
- Texture streaming (`CBixTextureChainResource`, `CR1TextureResourceType`,
  `CTrackRenderModel`, procedural geometry loads) runs 10-100x more calls a second at 144:
  per-frame budgets, faster streaming, not animation.

A RenderDoc capture of the intro at 144 (5,782 draws over 3 guest frames, 4 s after
START RACE) was taken; the draw list was not analysed before the session ended.

**Cause found (2026-10-14, static analysis; not yet confirmed in a run).** The stands
spectators are the skinned procedural crowd (`PROC_CHARACTER_SKIN*_VS`, vertex shader table
index 66-69, created by `sub_8247A060`). Their bones come from animations baked at 1/30 s
per frame (`sub_82DDD6A8` samples each Granny clip with the constant 1/30 at
`0x820256E4`); the vertex shader's `AnimInfo` (c156) is that frame's offset. The chain:

- `sub_824788B0` (per rendered view) tail-calls `sub_82DF7BB0` with the view's simulated
  time since its last render (+0x1DE8) and the crowd object (+0x1DE4).
- `sub_82DF7BB0` keeps a microsecond accumulator (crowd object +0x3EAE0, 25 ms frames,
  25000 at `0x832B9BA8`) and stores the frames to advance at +0x3EAE4, then overwrites
  that step with `dt > 0 ? 1 : 0`.
- `sub_82E08A00` adds the step to each spectator's frame (u16 at +2, or +66 for the
  second list; a new random clip when the clip ends) and appends the instance through
  `sub_82DF79C8`/`sub_82DF7AC0`; `sub_82E20E80` turns them into 128-byte records
  (InstanceMatrix, `AnimInfo.x = clip start + bones * frame`, FadeValues) that
  `sub_8243C050` draws (constants c152-c157).

So the crowd advances one baked frame per rendered frame: right at 30, about 3.5x at 144
(the intro renders about 100 fps). Fix: `src/hooks/crowd_anim.cpp` replaces
`sub_82DF7BB0` above 30 fps: the step is the number of 1/30 s periods the simulated time
crossed, the remainder kept in the same accumulator (in 1/3 us); at 30 the game's
function runs, `FORZA_CROWD_ANIM=game` keeps it at every rate. TU4: `sub_82EB9DF0`, the
same code and offsets (`sub_82ECAB38` is TU4's `sub_82E08A00`). Both builds compile.

**Verified (2026-10-14, TU4 build, scratch copy of the Xenia save, Millennia Masters race
start, a log line in the hook counting the baked frames it hands out per 2 s of wall time;
the log was not kept in the code).** Baked frames per second the crowd advances, intro
4 s after START RACE:

| frame_rate | renders/s of the crowd | with the fix | `FORZA_CROWD_ANIM=game` (before) |
| --- | --- | --- | --- |
| 30 | 30 | 29.7-30.0 | (the game's own code) |
| 60 | 60 | 29.6-30.5 | not run |
| 120 | about 100 | 29.8-30.0 | not run |
| 144 | 70-115 (about 95) | 29.7-30.4 | 69-112 (2.3-3.7x) |

So a baked clip plays in its real time at every rate (an arm wave of 27 frames: 0.9 s);
before, at 144 it took 0.25-0.4 s, the 60-120 ms pose changes seen. In the screenshot
bursts (`FORZA_SCREENSHOT_BURST=100:1`, TU4 and base build) the same spectators wave
slowly at 60, 120 and 144 with the fix, a swing from arms up to arms out taking 0.5-0.75
s; with `game` at 144 the same kind of swing took about 0.15 s. The period of a single
spectator's wave was not measured directly: each spectator picks a random clip, bursts
of 1-2 s at 144 hold at most one cycle, and the camera drifts, so frames from two runs
cannot be compared pixel by pixel. The 30 steps a second are the measurement.

Nothing else moved: race start, countdown and a full lap (1/4 laps after 21 s) ran
normally at 144 with the fix (`tools/perf_scenario.sh race`, TU4): race clock 2.819 to
21.167 s (18.348 s) between two screenshots 18.338 s apart in wall time, and no fault.
The intro's shots, camera sweep and countdown were already real time (measured above), so
the crowd was the only part that looked fast.
