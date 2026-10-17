// forza - frame pacing and frame time above 30 fps (src/hooks/frame_time.cpp,
// docs/framerate.md).

#pragma once

namespace forza::frame_time {

// Guest vblanks per game frame for the frame_rate setting: 2 at 30 (the console's), and
// above 30 two when twice the frame rate fits under the SDK's limit for the guest refresh
// rate (480 Hz with SDK patch 0037, else 240), else one.
int VblanksPerFrame();

// The guest vblank rate frame_rate asks for (frame_rate * VblanksPerFrame()).
int VblankHz();

// The frame time the game aims for, in ms: VblanksPerFrame() guest vblanks at the
// configured guest refresh rate.
double TargetMs();

// The render thread handed a frame to VdSwap (src/debug/frame_dump.cpp).
void OnGuestSwap();
void ResetRenderTiming();

}  // namespace forza::frame_time
