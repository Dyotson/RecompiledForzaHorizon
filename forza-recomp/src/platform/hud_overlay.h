// forza - a text box over the game for the Horizon World's head-to-head challenges
// (src/hooks/world_challenge.cpp): prompts, countdowns, the race's distance and results.
//
// Drawn with the SDK's ImGui drawer at the top centre of the window, without taking input,
// and registered with the drawer only while it shows (as the achievement toasts are,
// achievement_toast.h): the drawer repaints the window nonstop while any dialog is
// registered. It is drawn over the presented frame, so tools/live_shot.sh screenshots
// (the game's output image) don't show it; every text is also logged ("HUD: ...").
//
// The invite prompts (src/kernel/live_invites.cpp) and the friends screen
// (src/kernel/live_friends.cpp) also read the keyboard through it: while one wants keys
// (HudWantKeys), the window's text input is on and each drawn frame collects the typed
// text and the keys below for HudTakeKeys. A body line starting with
// kHudHighlight is drawn highlighted (the picker's cursor).

#pragma once

#include <string>

namespace rex::ui {
class ImGuiDrawer;
class Window;
class WindowedAppContext;
}  // namespace rex::ui

namespace forza {

// ForzaApp::OnCreateDialogs.
void InstallHud(rex::ui::ImGuiDrawer* drawer, rex::ui::WindowedAppContext& app_context,
                rex::ui::Window* window);

// Passive performance overlay: Off / FPS / FPS with frame-time history.
void PerformanceOverlayFrame();  // called only for guest VdSwap, any thread
void UpdatePerformanceOverlay(); // checks its hot cvar, any thread

constexpr char kHudHighlight = '\x01';

// Shows `title` (first line, highlighted) and `body` for `seconds`, replacing what shows.
// Any thread. `log` false skips the log line (texts that change every frame).
void HudShow(const std::string& title, const std::string& body, double seconds, bool log = true);
void HudClear();

// Keyboard input since the last HudTakeKeys, collected while the HUD shows and keys are
// wanted. `typed`: text input (UTF-8); `key_frames`: drawn frames with any key down (the
// keyboard also drives the pad in mnk_mode, so pad input during them came from it).
struct HudKeys {
  std::string typed;
  int backspace = 0;
  bool enter = false, escape = false, up = false, down = false, left = false, right = false;
  unsigned key_frames = 0;  // a counter: compare two readings
};
void HudWantKeys(bool on);  // any thread
HudKeys HudTakeKeys();

}  // namespace forza
