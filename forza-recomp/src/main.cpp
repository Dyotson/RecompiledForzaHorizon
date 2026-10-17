// forza - ReXGlue Recompiled Project

#if defined(FORZA_TITLE_UPDATE) && FORZA_TITLE_UPDATE == 4
#include "generated_tu4/default/forza_init.h"  // codegen output of forza_manifest_tu4.toml
#else
#include "generated/default/forza_init.h"
#endif

#include "forza_app.h"
#include "hooks/frame_time.h"

#include <rex/cvar.h>
#include <rex/logging.h>

#include <string>
#include <string_view>

REX_DEFINE_APP(forza, ForzaApp::Create)

REXCVAR_DEFINE_STRING(gpu_backend, "vulkan", "GPU",
                      "GPU backend on Windows: vulkan (with this project's fixes) or d3d12")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

std::string ForzaGpuBackend() { return REXCVAR_GET(gpu_backend); }

// The game's vblank callback wakes its main loop every second guest vblank (every vblank
// with its mainthread30fps option off), and the main loop times its simulation in real
// time, so the frame rate follows the guest vblank rate. Above 30 the frame time comes from
// the guest tick clock instead of the kernel's millisecond tick (src/hooks/frame_time.cpp,
// docs/framerate.md).
REXCVAR_DEFINE_INT32(frame_rate, 30, "Display",
                     "Frame rate: 30 (the console's), or 60 to 240 (60, 120, 144, ...). The "
                     "game times its simulation in real time (docs/framerate.md)")
    .validator([](std::string_view v) {
      int fps = 0;
      for (char c : v) {
        if (c < '0' || c > '9' || fps > 1000) return false;
        fps = fps * 10 + (c - '0');
      }
      return fps == 30 || (fps >= 60 && fps <= 240);
    })
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace {

// Gives an SDK cvar this game's default. A value from forza.toml, the environment
// (REX_<NAME>) or the command line stays; the settings UI and SaveConfig treat the new
// value as the default. (From RecompiledHaloReach.)
void SetSdkCvarDefault(std::string_view name, std::string_view value) {
  for (rex::cvar::FlagEntry& entry : rex::cvar::GetRegistry()) {
    if (entry.name != name) continue;
    if (entry.source == rex::cvar::Source::kDefault) entry.setter(value);
    entry.default_value = value;
    return;
  }
  REXLOG_WARN("SDK setting {} not found", name);
}

}  // namespace

void ApplyForzaCvarDefaults() {
  // Present with FIFO (vsync) only. The SDK prefers IMMEDIATE (tearing), and its UI thread
  // repaints nonstop on Linux: without a vsync wait that is thousands of presents a second,
  // GPU time taken from the emulated GPU (measured in RecompiledHaloReach, and here in
  // docs/perf.md). forza.toml or the command line can allow the other modes again.
  SetSdkCvarDefault("vulkan_allow_present_mode_immediate", "false");
  SetSdkCvarDefault("vulkan_allow_present_mode_mailbox", "false");
  SetSdkCvarDefault("vulkan_allow_present_mode_fifo_relaxed", "false");
  // frame_rate above 30: the guest vblank at twice the frame rate, or at the frame rate when
  // twice is past the SDK's limit (src/hooks/frame_time.cpp). A video_mode_refresh_rate set
  // in forza.toml or on the command line wins.
  if (REXCVAR_GET(frame_rate) > 30) {
    SetSdkCvarDefault("video_mode_refresh_rate", std::to_string(forza::frame_time::VblankHz()));
  }
}

void ApplyForzaGpuCvarDefaults() {
  // The game renders each car's thumbnail (Car Select, garage, the car panel), reads the
  // resolved image back on the CPU, compresses it and saves it in the profile
  // (ForzaProfile/Thumbnails). Without resolve readback the CPU reads stale guest memory and
  // the saved thumbnail is noise (docs/framerate.md). "some" copies a resolve back only the
  // first time it is seen (and again after 60 unused frames), which is what the thumbnails
  // need and costs nothing in a race; "fast" copies every resolve every frame and cost
  // 16-21% of the frame rate at 144 (docs/perf.md).
  SetSdkCvarDefault("readback_resolve", "some");
}
