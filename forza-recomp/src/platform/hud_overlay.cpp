// forza - the challenge text box over the game; see hud_overlay.h.

#include "hud_overlay.h"
#include "performance_history.h"
#include <rex/cvar.h>
#include <string_view>

#include <imgui.h>
#include <rex/logging.h>
#include <rex/ui/imgui_dialog.h>
#include <rex/ui/imgui_drawer.h>
#include <rex/ui/window.h>
#include <rex/ui/windowed_app_context.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>

REXCVAR_DEFINE_STRING(forza_performance_overlay, "off", "Display",
    "Performance overlay: off, fps, or graph (game-frame timing)")
    .validator([](std::string_view value) {
      return value == "off" || value == "fps" || value == "graph";
    })
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace forza {
namespace {

using Clock = std::chrono::steady_clock;

class HudDialog final : public rex::ui::ImGuiDialog {
 public:
  HudDialog(rex::ui::ImGuiDrawer* drawer, rex::ui::WindowedAppContext& app_context,
            rex::ui::Window* window)
      : ImGuiDialog(drawer), drawer_(drawer), app_context_(app_context), window_(window) {
    drawer_->RemoveDialog(this);  // the constructor registered it; registered while shown
  }

  void Show(const std::string& title, const std::string& body, double seconds) {
    {
      std::lock_guard lock(mutex_);
      title_ = title;
      body_ = body;
      until_ = Clock::now() + std::chrono::milliseconds(int64_t(seconds * 1000));
    }
    if (!registered_.exchange(true)) {
      app_context_.CallInUIThread([this] { drawer_->AddDialog(this); });
    }
  }

  void Clear() {
    std::lock_guard lock(mutex_);
    until_ = Clock::time_point{};
  }

  void WantKeys(bool on) {
    {
      std::lock_guard lock(mutex_);
      if (want_keys_ == on) return;
      want_keys_ = on;
      keys_ = {};
    }
    // SDL text input: UI thread only. Without it no text arrives, keys still do.
    if (window_) app_context_.CallInUIThread([w = window_, on] { w->SetTextInputActive(on); });
  }

  HudKeys TakeKeys() {
    std::lock_guard lock(mutex_);
    HudKeys keys = keys_;
    keys_.typed.clear();
    keys_.backspace = 0;
    keys_.enter = keys_.escape = keys_.up = keys_.down = keys_.left = keys_.right = false;
    return keys;
  }

 protected:
  void OnDraw(ImGuiIO& io) override {
    std::string title, body;
    {
      std::lock_guard lock(mutex_);
      if (Clock::now() >= until_) {
        // The drawer detaches from the presenter once its last dialog is gone.
        registered_ = false;
        drawer_->RemoveDialog(this);
        return;
      }
      title = title_;
      body = body_;
      if (want_keys_) CollectKeys(io);
    }
    const float scale = std::clamp(io.DisplaySize.y / 720.0f, 1.0f, 2.5f);
    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.06f),
                            ImGuiCond_Always, ImVec2(0.5f, 0.0f));
    ImGui::SetNextWindowBgAlpha(0.72f);
    const ImGuiWindowFlags flags =
        ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoMove |
        ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoInputs |
        ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoFocusOnAppearing;
    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding, 6.0f * scale);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(16.0f * scale, 10.0f * scale));
    if (ImGui::Begin("##forza_hud", nullptr, flags)) {
      ImGui::SetWindowFontScale(1.5f * scale);
      ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1.0f, 0.62f, 0.1f, 1.0f));
      ImGui::TextUnformatted(title.c_str());
      ImGui::PopStyleColor();
      ImGui::SetWindowFontScale(1.25f * scale);
      size_t start = 0;
      while (start < body.size()) {
        size_t end = body.find('\n', start);
        if (end == std::string::npos) end = body.size();
        if (body[start] == kHudHighlight) {
          ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1.0f, 0.85f, 0.3f, 1.0f));
          ImGui::TextUnformatted(body.data() + start + 1, body.data() + end);
          ImGui::PopStyleColor();
        } else {
          ImGui::TextUnformatted(body.data() + start, body.data() + end);
        }
        start = end + 1;
      }
    }
    ImGui::End();
    ImGui::PopStyleVar(2);
  }

 private:
  // This frame's keyboard input (mutex_ held). The drawer feeds ImGui the window's key and
  // text events while any dialog is registered.
  void CollectKeys(ImGuiIO& io) {
    for (int i = 0; i < io.InputQueueCharacters.Size; ++i) {
      const unsigned c = io.InputQueueCharacters[i];
      if (c < 0x20 || c == 0x7F) continue;
      if (c < 0x80) {
        keys_.typed += char(c);
      } else if (c < 0x800) {
        keys_.typed += char(0xC0 | c >> 6);
        keys_.typed += char(0x80 | (c & 0x3F));
      } else {
        keys_.typed += char(0xE0 | c >> 12);
        keys_.typed += char(0x80 | (c >> 6 & 0x3F));
        keys_.typed += char(0x80 | (c & 0x3F));
      }
    }
    if (ImGui::IsKeyPressed(ImGuiKey_Backspace, true)) ++keys_.backspace;
    keys_.enter |= ImGui::IsKeyPressed(ImGuiKey_Enter, false) ||
                   ImGui::IsKeyPressed(ImGuiKey_KeypadEnter, false);
    keys_.escape |= ImGui::IsKeyPressed(ImGuiKey_Escape, false);
    keys_.up |= ImGui::IsKeyPressed(ImGuiKey_UpArrow, true);
    keys_.down |= ImGui::IsKeyPressed(ImGuiKey_DownArrow, true);
    keys_.left |= ImGui::IsKeyPressed(ImGuiKey_LeftArrow, true);
    keys_.right |= ImGui::IsKeyPressed(ImGuiKey_RightArrow, true);
    for (int k = ImGuiKey_NamedKey_BEGIN; k < ImGuiKey_GamepadStart; ++k) {  // keyboard keys
      if (ImGui::IsKeyDown(ImGuiKey(k))) {
        ++keys_.key_frames;
        break;
      }
    }
  }

  rex::ui::ImGuiDrawer* drawer_;
  rex::ui::WindowedAppContext& app_context_;
  rex::ui::Window* window_;
  std::mutex mutex_;
  bool want_keys_ = false;
  HudKeys keys_;
  std::string title_, body_;
  Clock::time_point until_{};
  std::atomic<bool> registered_{false};
};

class PerformanceDialog final : public rex::ui::ImGuiDialog {
 public:
  PerformanceDialog(rex::ui::ImGuiDrawer* drawer, rex::ui::WindowedAppContext& context)
      : ImGuiDialog(drawer), drawer_(drawer), context_(context) {
    drawer_->RemoveDialog(this);
  }
  bool WantsContinuousRepaint() const override { return false; }
  void Update() {
    const auto value = REXCVAR_GET(forza_performance_overlay);
    const int mode = value == "graph" ? 2 : value == "fps" ? 1 : 0;
    const int previous = mode_.exchange(mode);
    if (previous == mode) return;
    if (!previous) {
      std::lock_guard lock(mutex_);
      history_ = PerformanceHistory{};
    }
    context_.CallInUIThread([this] {
      if (mode_.load()) drawer_->AddDialog(this);
      else drawer_->RemoveDialog(this);
    });
  }
  void Frame() {
    if (!mode_.load()) return;
    std::lock_guard lock(mutex_);
    history_.Record(Now());
  }
 protected:
  void OnDraw(ImGuiIO& io) override {
    const int mode = mode_.load();
    if (!mode) return;
    std::array<float, PerformanceHistory::kCapacity> ms;
    size_t count;
    double fps;
    {
      std::lock_guard lock(mutex_);
      ms = history_.Ordered();
      count = history_.count();
      fps = history_.Fps(Now());
    }
    const float scale = std::clamp(io.DisplaySize.y / 1080.0f, 1.0f, 2.0f);
    ImGui::SetNextWindowPos(ImVec2(16 * scale, 16 * scale), ImGuiCond_Always);
    ImGui::SetNextWindowBgAlpha(0.78f);
    constexpr auto flags = ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoInputs |
        ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings |
        ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoFocusOnAppearing;
    if (ImGui::Begin("##forza_performance", nullptr, flags)) {
      ImGui::SetWindowFontScale(1.5f * scale);
      ImGui::Text("%.0f FPS", fps);
      if (mode == 2) {
        const float latest = count ? ms[count - 1] : 0;
        const float peak = count ? *std::max_element(ms.begin(), ms.begin() + count) : 0;
        ImGui::Text("%.1f ms   peak %.1f ms", latest, peak);
        // Auto-range retains long hitches instead of clipping them at 33 ms.
        ImGui::PlotLines("##frame_times", ms.data(), int(count), 0, "Game frame time (ms)",
                         0, std::max(33.3f, peak * 1.1f), ImVec2(270 * scale, 70 * scale));
      }
    }
    ImGui::End();
  }
 private:
  static double Now() {
    return std::chrono::duration<double>(Clock::now().time_since_epoch()).count();
  }
  rex::ui::ImGuiDrawer* drawer_;
  rex::ui::WindowedAppContext& context_;
  std::atomic<int> mode_{0};
  std::mutex mutex_;
  PerformanceHistory history_;
};
PerformanceDialog* performance = nullptr;

// Lives for the whole run (the drawer keeps a raw pointer while it is registered).
HudDialog* hud = nullptr;

}  // namespace

void InstallHud(rex::ui::ImGuiDrawer* drawer, rex::ui::WindowedAppContext& app_context,
                rex::ui::Window* window) {
  if (!drawer || hud) return;
  hud = new HudDialog(drawer, app_context, window);
  performance = new PerformanceDialog(drawer, app_context);
  performance->Update();
}

void HudShow(const std::string& title, const std::string& body, double seconds, bool log) {
  if (log) REXLOG_INFO("HUD: {} | {}", title, body);
  if (hud) hud->Show(title, body, seconds);
}

void PerformanceOverlayFrame() { if (performance) performance->Frame(); }
void UpdatePerformanceOverlay() { if (performance) performance->Update(); }

void HudClear() {
  if (hud) hud->Clear();
}

void HudWantKeys(bool on) {
  if (hud) hud->WantKeys(on);
}

HudKeys HudTakeKeys() { return hud ? hud->TakeKeys() : HudKeys{}; }

}  // namespace forza
