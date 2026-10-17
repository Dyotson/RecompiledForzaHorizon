// forza - the ReXGlue app: runtime setup for Forza Horizon.
//
// Customize by overriding virtual hooks from rex::ReXApp.

#pragma once

#include "debug/frame_stats.h"
#include "kernel/live.h"
#include "platform/achievement_toast.h"
#include "platform/hud_overlay.h"
#include "platform/graphics_menu.h"
#include "platform/vulkan_hooks.h"
#include "platform/ultrawide.h"
#include <rex/ui/window.h>
#include <rex/cvar.h>
#include <array>

#include <string>

#include <rex/filesystem/devices/host_path_device.h>
#include <rex/filesystem/vfs.h>
#include <rex/logging.h>
#include <rex/rex_app.h>
#include <rex/runtime.h>
#include <rex/system/gpu_plugin.h>
#include <rex/ui/overlay/achievement_notification.h>

#include <filesystem>
#include <string>

namespace forza {
void InstallFaultGuard();  // src/debug/fault_guard.cpp
void LogGuestThreads(const char* why);  // src/debug/fault_guard.cpp
void PatchMotionBlurStencilThreshold();  // src/platform/motion_blur_fix.cpp
void LogDlcPackages(const std::filesystem::path& user_data_root);  // src/debug/dlc_log.cpp
}  // namespace forza

// SDK settings with this game's defaults (src/main.cpp); the GPU plugin's own settings exist
// only once the plugin is loaded.
void ApplyForzaCvarDefaults();
void ApplyForzaGpuCvarDefaults();

// GPU backend on Windows (the gpu_backend setting, src/main.cpp).
std::string ForzaGpuBackend();

class ForzaApp : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<ForzaApp>(new ForzaApp(ctx, "forza",
        PPCImageConfig));
  }

  // Runs after forza.toml and the command line are applied, before the window opens.
  void OnPostInitLogging() override { ApplyForzaCvarDefaults(); }

  void OnPreSetup(rex::RuntimeConfig& config) override {
    if (!config.graphics && config.gpu_plugin.empty()) {
      config.gpu_plugin = "xenos";
    }
    // Loaded here rather than by the SDK so OnCreateDialogs can reach the GPU provider.
    if (!config.graphics && !config.gpu_plugin.empty()) {
#ifdef _WIN32
      config.graphics = rex::system::LoadGpuPlugin(config.gpu_plugin, ForzaGpuBackend());
#else
      config.graphics = rex::system::LoadGpuPlugin(config.gpu_plugin);
#endif
    }
    graphics_ = config.graphics.get();
    ApplyForzaGpuCvarDefaults();
  }

  // The GPU provider exists now and the window has no swapchain yet: hook the Vulkan
  // calls (swapchain present-mode log, RECOMP_PERF timing; src/platform/vulkan_hooks.h).
  // Also the text box of the Horizon World's head-to-head challenges and of the invite
  // prompts (platform/hud_overlay.h).
  void OnCreateDialogs(rex::ui::ImGuiDrawer* drawer) override {
    forza::InstallVulkanHooks(graphics_);
    forza::InstallHud(drawer, app_context(), window());
    forza::InstallFriendsKey();
  }

  void OnPostSetup() override { forza::InstallVulkanHooks(runtime()->graphics_system()); }
  std::optional<rex::PathConfig> OnFinalizePaths(const rex::PathConfig& defaults,
      std::function<void(rex::PathConfig)> /*resume*/) override {
    if (window()) forza::ultrawide::Prepare(window()->GetActualPhysicalWidth(), window()->GetActualPhysicalHeight());
    return defaults;
  }
  void OnWindowPixelSizeChanged(uint32_t width, uint32_t height) override {
    forza::ultrawide::Resize(width, height);
  }

  // The SDK's achievement toasts, registered with the ImGui drawer only while one shows, so
  // the window is not repainted nonstop (src/platform/achievement_toast.h; from
  // RecompiledHaloReach).
  std::unique_ptr<rex::ui::AchievementNotificationDialog> CreateAchievementNotificationDialog()
      override {
    return forza::MakeOnDemandToast(rex::ReXApp::CreateAchievementNotificationDialog(),
                                    imgui_drawer(), app_context());
  }

  // The SDK hard-exits right after a close request is accepted (SIGINT included), so the
  // frame statistics summary is written here, and where each guest thread is (a game that
  // loads forever is closed this way, #76).
  bool OnWindowCloseRequested() override {
    forza::perf::Shutdown();
    forza::LogGuestThreads("at close");
    return true;
  }

  // The game keeps ghost and replay streams on the console's utility partition
  // (cache:\ghost_stream_N, cache:\replay_stream, as in Xenia's cache folder). Its
  // XAPI XMountUtilityDrive gets no symbolic link from the runtime (the SDK backs the
  // raw Cache0/Cache1 partitions with a null device), so cache:\ fails with "device
  // not found". Mount a host folder there as Xenia does with mount_cache.
  void OnPreLaunchModule() override {
    forza::graphics_menu::Initialize(user_data_root());
    if (window()) forza::ultrawide::Initialize(window()->GetActualPhysicalWidth(),
        window()->GetActualPhysicalHeight(),
        [this, last = std::array<double, 6>{-1,-1,-1,-1,-1,-1}]
        (bool letterbox, double sx, double sy, double ox, double oy, double edges) mutable {
          const std::array<double, 6> next{double(letterbox), sx, sy, ox, oy, edges};
          if (last == next) return;
          last = next;
          app_context().CallInUIThreadDeferred([this, letterbox, sx, sy, ox, oy, edges] {
            rex::cvar::SetFlagByName("forza_present_16_9", "true");
            rex::cvar::SetFlagByName("present_letterbox", letterbox ? "true" : "false");
            rex::cvar::SetFlagByName("forza_ultrawide_hud_x", std::to_string(sx));
            rex::cvar::SetFlagByName("forza_ultrawide_hud_y", std::to_string(sy));
            rex::cvar::SetFlagByName("forza_ultrawide_hud_offset_x", std::to_string(ox));
            rex::cvar::SetFlagByName("forza_ultrawide_hud_offset_y", std::to_string(oy));
            rex::cvar::SetFlagByName("forza_ultrawide_hud_edge_shift", std::to_string(edges));
            if (window()) window()->RequestPaint();
          });
        });
    // After the runtime's own handlers (MMIO, GPU watches), so it only sees faults
    // nothing else takes.
    forza::InstallFaultGuard();
    // The executable's image is loaded: fix the speed blur's stencil threshold.
    forza::PatchMotionBlurStencilThreshold();
    // Which DLC the game will find (#79: Horizon Rally without the Rally Expansion Pack).
    forza::LogDlcPackages(user_data_root());
    auto* vfs = runtime()->file_system();
    const std::filesystem::path host = cache_root() / "cache";
    std::error_code ec;
    std::filesystem::create_directories(host, ec);
    auto device = std::make_unique<rex::filesystem::HostPathDevice>("\\CACHE", host, false);
    if (!device->Initialize() || !vfs->RegisterDevice(std::move(device)) ||
        !vfs->RegisterSymbolicLink("cache:", "\\CACHE")) {
      REXLOG_ERROR("Failed to mount cache: at {}", host.string());
    }
  }

#if defined(FORZA_TITLE_UPDATE) && FORZA_TITLE_UPDATE == 4
  // Title Update 4 build: the patched executable, its facade DLLs and the update's media.zip
  // are in one folder (tools/apply_title_update.py), mounted as update: (the SDK's
  // update_data_root setting; default: tu4 next to the game folder).
  void OnConfigurePaths(rex::PathConfig& paths) override {
    if (paths.update_data_root.empty()) {
      auto game = std::filesystem::absolute(paths.game_data_root).lexically_normal();
      if (!game.has_filename()) game = game.parent_path();
      paths.update_data_root = game.parent_path() / "tu4";
    }
    if (!std::filesystem::exists(paths.update_data_root / "default.xex")) {
      REXLOG_ERROR("This build is for Title Update 4 and needs the patched default.xex in {} "
                   "(tools/apply_title_update.py; set update_data_root)",
                   paths.update_data_root.string());
    }
  }
  // game:\default.xex and the facades resolve to the update's: symbolic links from their
  // game: device paths, which ResolvePath follows after game: itself.
  void OnLoadXexImage(std::string& /*xex_image*/) override {
    auto* vfs = runtime()->file_system();
    for (const char* name : {"default.xex", "XMediaFacade_default.xex", "SpeechFacade_default.xex"}) {
      vfs->RegisterSymbolicLink(std::string("\\Device\\Harddisk0\\Partition1\\") + name,
                                std::string("\\Device\\Harddisk0\\PartitionUpdate\\") + name);
    }
    REXLOG_INFO("Title Update 4 build: executable and facades from update:");
  }
#endif

 private:
  rex::system::IGraphicsSystem* graphics_ = nullptr;
};
