// Original pause-menu entry and difficulty-style graphics settings.
// tu_address_map: TU4 addresses
// The scene/model layouts below are validated for Title Update 4 only.
#include "../platform/graphics_menu.h"
#include "../platform/guest_addr.h"
#include "../platform/guest_memory.h"
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/kernel_state.h>
#include <string>
#include <vector>
#include "frame_time.h"
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace forza::graphics_menu {
namespace {
std::filesystem::path pending_path;
}
void Initialize(const std::filesystem::path &root) {
  const char *path = std::getenv("FORZA_GRAPHICS_SETTINGS");
  pending_path = path && *path ? std::filesystem::path(path)
                               : root / "graphics-settings.json";
}
} // namespace forza::graphics_menu

#if FORZA_TU4
#define MenuBind sub_827D1618
#define OriginalBind __imp__sub_827D1618
#define MenuSelect sub_827EBEE0
#define OriginalSelect __imp__sub_827EBEE0
extern "C" REX_FUNC(OriginalBind);
extern "C" REX_FUNC(OriginalSelect);

namespace forza::graphics_menu {
namespace {
constexpr uint32_t kGraphics = 0x7000;
uint32_t Read(uint8_t *base, uint32_t address) {
  const auto *p = GuestPtr(base, address);
  return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 |
         p[3];
}
void Write(uint8_t *base, uint32_t address, uint32_t value) {
  auto *p = GuestPtr(base, address);
  p[0] = uint8_t(value >> 24);
  p[1] = uint8_t(value >> 16);
  p[2] = uint8_t(value >> 8);
  p[3] = uint8_t(value);
}

// The original guest constructors retain their own references to the text.
// Scratch storage is private to this synchronous call and never retained by a
// UI object.
class Native {
public:
  Native(PPCContext &ctx, uint8_t *base) : ctx_(ctx), base_(base) {
    scratch_ = REX_KERNEL_MEMORY()->SystemHeapAlloc(1024);
  }
  ~Native() {
    if (scratch_)
      REX_KERNEL_MEMORY()->SystemHeapFree(scratch_);
  }
  explicit operator bool() const { return scratch_ != 0; }
  uint32_t Call(uint32_t address, std::initializer_list<uint32_t> args) {
    unsigned i = 3;
    // GPRs are contiguous in PPCContext, but use named registers for ABI
    // stability.
    for (uint32_t value : args) {
      switch (i++) {
      case 3:
        ctx_.r3.u64 = value;
        break;
      case 4:
        ctx_.r4.u64 = value;
        break;
      case 5:
        ctx_.r5.u64 = value;
        break;
      case 6:
        ctx_.r6.u64 = value;
        break;
      case 7:
        ctx_.r7.u64 = value;
        break;
      case 8:
        ctx_.r8.u64 = value;
        break;
      case 9:
        ctx_.r9.u64 = value;
        break;
      }
    }
    rex::runtime::ResolveIndirectFunction(address)(ctx_, base_);
    return ctx_.r3.u32;
  }
  uint32_t Text(const std::string &text) {
    if (text.size() > 240)
      return 0;
    auto *out = GuestPtr(base_, scratch_ + 32);
    for (size_t i = 0; i < text.size(); ++i) {
      out[i * 2] = 0;
      out[i * 2 + 1] = uint8_t(text[i]);
    }
    out[text.size() * 2] = out[text.size() * 2 + 1] = 0;
    uint32_t object = Call(0x824265C8, {16});
    if (!object)
      return 0;
    Write(base_, object, 0x82001674);
    Write(base_, object + 4, 0);
    Write(base_, object + 8, 0);
    Write(base_, object + 12, 0);
    Call(0x82D6DE20, {object, scratch_ + 32, uint32_t(text.size())});
    Call(0x82555B90, {scratch_, object});
    return scratch_;
  }
  void Add(uint32_t menu, uint32_t id, const std::string &label) {
    if (uint32_t text = Text(label))
      Call(0x828F5818, {menu + 0x174, text, id, 1, 0});
  }
  uint32_t scratch() const { return scratch_; }
  uint32_t Hash(const std::string &value) {
    std::copy(value.begin(), value.end(), GuestPtr(base_, scratch_ + 512));
    GuestPtr(base_, scratch_ + 512)[value.size()] = 0;
    return Call(0x82F354E0, {scratch_ + 512});
  }
  void Field(uint32_t screen, const std::string &name, uint32_t binding,
             const std::string &text) {
    auto id = Hash(name);
    auto bound = Call(0x82F21830, {screen, id, binding});
    REXLOG_INFO("Graphics menu: field {} bound={}", name, bound);
    if (bound)
      Binding(binding, text);
  }
  void PathText(uint32_t screen, const std::string &path, uint32_t binding,
                const std::string &label) {
    auto engine = Read(base_, screen + 8);
    auto access = Call(Read(base_, Read(base_, engine) + 0x1C), {engine});
    std::copy(path.begin(), path.end(), GuestPtr(base_, scratch_ + 512));
    GuestPtr(base_, scratch_ + 512)[path.size()] = 0;
    auto node = Call(0x82F348B8,
                     {access, Read(base_, screen + 0x58), scratch_ + 512, 0});
    if (node) {
      Call(0x82F35610, {binding, engine, node});
      Binding(binding, label);
    }
  }
  void Binding(uint32_t target, const std::string &label) {
    if (uint32_t text = Text(label)) {
      Call(0x82F3A728, {target, text});
      Call(0x824CEAB0, {text});
    }
  }
  uint32_t Event(uint32_t screen, uint32_t event) {
    Write(base_, scratch_, 0x5D);
    Write(base_, scratch_ + 4, 0x60);
    uint32_t found = Call(Read(base_, Read(base_, screen) + 0xA8),
                          {screen, event, scratch_, 2});
    return found ? Read(base_, found) : 0;
  }
  PPCContext &context() { return ctx_; }

private:
  PPCContext ctx_;
  uint8_t *base_;
  uint32_t scratch_ = 0;
};

struct Choice {
  std::string value, label;
};
struct Setting {
  std::string key, cvar, label, value;
  std::vector<Choice> choices;
};
uint32_t active_menu = 0;
std::vector<Setting> settings;
std::vector<Setting> saved_settings;
std::vector<Setting> applying_settings;
std::string applying_request;
uint64_t request_id = 0;
std::vector<std::pair<std::string, std::string>> preview_baseline;

bool IsLive(const Setting &setting) {
  return setting.key == "vsync" || setting.key == "anisotropic_override" ||
         setting.key == "forza_hud_edges";
}

void RememberPreview() {
  preview_baseline.clear();
  for (const auto &setting : settings)
    if (IsLive(setting))
      preview_baseline.emplace_back(setting.cvar,
                                    rex::cvar::GetFlagByName(setting.cvar));
}

void RestorePreview() {
  for (const auto &[name, value] : preview_baseline) {
    if (rex::cvar::GetFlagByName(name) == value)
      continue;
    if (rex::cvar::SetFlagByName(name, value))
      REXLOG_INFO("Graphics menu: reverted live {}={}", name, value);
  }
  preview_baseline.clear();
}

bool ApplyPreview() {
  bool success = true;
  for (const auto &setting : settings) {
    if (!IsLive(setting) ||
        rex::cvar::GetFlagByName(setting.cvar) == setting.value)
      continue;
    const bool applied = rex::cvar::SetFlagByName(setting.cvar, setting.value);
    REXLOG_INFO("Graphics menu: live {}={} applied={}", setting.cvar,
                setting.value, applied);
    success &= applied;
  }
  return success;
}

void Snapshot() {
  settings = {
      {"output",
       "resolution",
       "Output resolution",
       "",
       {{"1080p", "1920 x 1080"},
        {"1440p", "2560 x 1440"},
        {"4k", "3840 x 2160"}}},
      {"upscaler", "fh1_upscaler", "Anti-aliasing", "", {{"off", "Native"}}},
      {"resolution_scale",
       "resolution_scale",
       "Native render scale",
       "",
       {{"1", "1x (720p)"},
        {"2", "2x (1440p)"},
        {"3", "3x (2160p, experimental)"}}},
      {"frame_rate",
       "frame_rate",
       "Frame rate limit",
       "",
       {{"30", "30 FPS"},
        {"60", "60 FPS"},
        {"90", "90 FPS"},
        {"120", "120 FPS"},
        {"144", "144 FPS"},
        {"165", "165 FPS"},
        {"180", "180 FPS"},
        {"240", "240 FPS"}}},
      {"vsync",
       "vsync",
       "Vertical sync",
       "",
       {{"true", "On"}, {"false", "Off"}}},
      {"anisotropic_override",
       "anisotropic_override",
       "Texture filtering",
       "",
       {{"-1", "Game default"},
        {"0", "Off"},
        {"1", "1x"},
        {"2", "2x"},
        {"3", "4x"},
        {"4", "8x"},
        {"5", "16x"}}},
      {"forza_hud_edges",
       "forza_hud_edges",
       "Ultrawide HUD",
       "",
       {{"false", "Centered"}, {"true", "Screen edges"}}},
  };
  auto &modes = settings[1].choices;
#ifdef _WIN32
  if (rex::cvar::GetFlagByName("gpu_backend") == "vulkan" &&
      (rex::cvar::GetFlagByName("gpu_vendor") == "nvidia" ||
       std::getenv("FORZA_DLSS_RUNTIME"))) {
    modes.insert(modes.end(), {{"quality", "DLSS Quality"},
                               {"balanced", "DLSS Balanced"},
                               {"dlss", "DLSS Performance"},
                               {"dlaa", "DLAA"}});
  }
#endif
  if (rex::cvar::GetFlagByName("gpu_backend") == "vulkan") {
    modes.insert(modes.end(), {{"fsr3_quality", "FSR 3 Quality"},
                               {"fsr3_balanced", "FSR 3 Balanced"},
                               {"fsr3_performance", "FSR 3 Performance"},
                               {"fsr3_native", "FSR 3 Native AA"}});
  }
  for (auto &setting : settings) {
    setting.value = rex::cvar::GetFlagByName(setting.cvar);
    if (setting.value.empty())
      setting.value = setting.choices.front().value;
  }
  if (rex::cvar::GetFlagByName("fh1_scene_720p_native_hud") == "true")
    settings[2].value = rex::cvar::GetFlagByName("fh1_native_scene_scale");
  if (rex::cvar::GetFlagByName("present_effect") == "fsr3")
    settings[1].value = "fsr3_" + rex::cvar::GetFlagByName("fsr3_mode");
  if (!saved_settings.empty()) {
    for (size_t i = 0; i < settings.size(); ++i)
      if (!IsLive(settings[i]))
        settings[i].value = saved_settings[i].value;
  }
  RememberPreview();
}

bool Save() {
  std::error_code ec;
  std::filesystem::create_directories(pending_path.parent_path(), ec);
  if (ec)
    return false;
  auto temp = pending_path;
  temp += ".tmp";
  std::ofstream out(temp, std::ios::binary | std::ios::trunc);
  out << "{\n  \"version\": 1,\n  \"settings\": {\n";
  for (size_t i = 0; i < settings.size(); ++i) {
    const auto &s = settings[i];
    out << "    \"" << s.key << "\": \"" << s.value << "\""
        << (i + 1 < settings.size() ? "," : "") << "\n";
  }
  out << "  }\n}\n";
  out.close();
  if (!out)
    return false;
  // Windows rename does not replace an existing destination. Keep the previous
  // request intact until the complete replacement has been written.
#ifdef _WIN32
  return MoveFileExW(temp.c_str(), pending_path.c_str(),
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
#else
  std::filesystem::rename(temp, pending_path, ec);
  return !ec;
#endif
}
} // namespace
} // namespace forza::graphics_menu

extern "C" REX_FUNC(MenuBind) {
  using namespace forza::graphics_menu;
  active_menu = ctx.r3.u32;
  Native ui(ctx, base);
  if (ui) {
    ui.Add(active_menu, kGraphics, "GRAPHICS SETTINGS");
    REXLOG_INFO("Graphics menu: native pause entry added");
  }
  OriginalBind(ctx, base);
}
namespace forza::graphics_menu {
namespace {
bool opening_graphics = false;
uint32_t graphics_screen = 0;
std::vector<uint32_t> native_rows;
uint32_t empty_pause_source = 0;
void PauseRows(Native &ui, uint8_t *base, bool show) {
  auto component = Read(base, active_menu + 0x170);
  if (!show && !empty_pause_source) {
    empty_pause_source = ui.Call(0x824265C8, {0x38});
    if (!empty_pause_source)
      return;
    ui.Call(0x828EED20, {empty_pause_source});
  }
  ui.Call(0x828B82C8,
          {component, show ? active_menu + 0x174 : empty_pause_source});
  ui.Call(Read(base, Read(base, component + 0x6C) + 0x28), {component + 0x6C});
  if (show && empty_pause_source) {
    ui.Call(Read(base, Read(base, empty_pause_source)),
            {empty_pause_source, 1});
    empty_pause_source = 0;
    ui.Call(0x827D6348, {active_menu});
  }
}
const char *Help(size_t i) {
  constexpr const char *help[] = {
      "Output resolution. The HUD stays native. Save applies the change in this session.",
      "DLSS increases performance; DLAA uses native input. Save applies the change in this session.",
      "Scene resolution with Native selected. Reconstruction chooses its own input size. Save applies the change.",
      "Maximum frame rate. Save applies the limit without restarting.",
      "Synchronize presentation with the display. Previews immediately. Back undoes unsaved edits.",
      "Improve texture detail on roads and distant surfaces. Previews immediately. Back undoes unsaved edits.",
      "Move ultrawide HUD anchors to the center or edges. Previews immediately when HUD layout is enabled."};
  return i < std::size(help) ? help[i] : "Save applies graphics changes without restarting.";
}
void Footer(Native &ui, uint8_t *base) {
  auto footer = ui.Call(0x82746638, {graphics_screen});
  if (!footer)
    return;
  ui.Call(0x8289A908, {footer});
  for (auto [index, label] : {std::pair{0u, "SAVE"}, std::pair{1u, "BACK"}}) {
    auto text = ui.Text(label);
    ui.Call(0x8289E2B0, {footer, index, text});
    ui.Call(0x824CEAB0, {text});
  }
  ui.Call(Read(base, Read(base, footer + 0x6C) + 0x28), {footer + 0x6C});
}
} // namespace
} // namespace forza::graphics_menu
extern "C" REX_FUNC(__imp__sub_827303E8);
extern "C" REX_FUNC(__imp__sub_82739190);
extern "C" REX_FUNC(__imp__sub_827142C0);
extern "C" REX_FUNC(__imp__sub_82736B08);

extern "C" REX_FUNC(sub_827303E8) {
  using namespace forza::graphics_menu;
  if (!opening_graphics) {
    __imp__sub_827303E8(ctx, base);
    return;
  }
  opening_graphics = false;
  graphics_screen = ctx.r3.u32;
  Native ui(ctx, base);
  if (!ui)
    return;
  uint32_t source = ui.Call(0x824265C8, {0x28});
  ui.Call(0x8267A4B0, {source});
  Write(base, graphics_screen + 0x1A0, source);
  Write(base, Read(base, graphics_screen + 0xA4) + 0x1C, source);
  native_rows.clear();
  for (size_t i = 0; i < settings.size(); ++i) {
    auto &setting = settings[i];
    uint32_t row = ui.Call(0x824265C8, {0x1C});
    for (unsigned offset = 0; offset < 0x1C; offset += 4)
      Write(base, row + offset, 0);
    Write(base, row, 0x82049434);
    auto label = ui.Text(setting.label);
    ui.Call(0x82471820, {row + 0x10, label});
    ui.Call(0x824CEAB0, {label});
    Write(base, row + 0xC, uint32_t(i));
    uint32_t choices = ui.Call(0x824265C8, {0x28});
    ui.Call(0x828DD2A8, {choices, uint32_t(setting.choices.size())});
    Write(base, row + 4, choices);
    for (size_t j = 0; j < setting.choices.size(); ++j) {
      auto text = ui.Text(setting.choices[j].label);
      ui.context().f1.f64 = 0;
      ui.Call(0x828DDCA8, {choices, uint32_t(j), text, 0, 0, 0, 1});
      ui.Call(0x824CEAB0, {text});
      if (setting.choices[j].value == setting.value)
        Write(base, row + 8, uint32_t(j));
    }
    Write(base, ui.scratch(), row);
    ui.Call(0x826D9C80, {source + 0x18, ui.scratch()});
    native_rows.push_back(row);
  }
  ui.Call(0x827FBDD0, {graphics_screen});
  ui.Call(0x82F1EC20, {graphics_screen, ui.Hash("DIFFICULTY")});
  ui.Field(graphics_screen, "TEXT_SCREEN_NAME", graphics_screen + 0x1F4,
           "GRAPHICS SETTINGS");
  ui.Field(graphics_screen, "TEXT_EARNINGS", graphics_screen + 0x1E8,
           "NO RESTART NEEDED");
  ui.Field(graphics_screen, "TEXT_TITLE", graphics_screen + 0x170,
           "GRAPHICS SETTINGS");
  ui.Field(graphics_screen, "TEXT_DESCRIPTION", graphics_screen + 0x17C,
           Help(0));
  ui.PathText(graphics_screen,
              "parent.Layer.Group_BLADE.Group_EARNINGS.Text_EARNINGS_LABEL",
              graphics_screen + 0x1DC, "GRAPHICS");
  PauseRows(ui, base, false);
  Footer(ui, base);
  REXLOG_INFO("Graphics menu: native fixed settings page built ({} rows)",
              native_rows.size());
}
extern "C" REX_FUNC(sub_82739190) {
  using namespace forza::graphics_menu;
  if (ctx.r3.u32 != graphics_screen) {
    __imp__sub_82739190(ctx, base);
    return;
  }
  if (ctx.r4.u32 != 1)
    return;
  Native ui(ctx, base);
  if (!ui)
    return;
  uint32_t component = Read(base, graphics_screen + 0x16C);
  if (ctx.r5.u32 == component + 8) {
    ui.Binding(graphics_screen + 0x17C, Help(ctx.r6.u32));
  } else {
    for (size_t i = 0; i < native_rows.size(); ++i) {
      auto choice = Read(base, native_rows[i] + 8);
      if (choice < settings[i].choices.size())
        settings[i].value = settings[i].choices[choice].value;
    }
    ApplyPreview();
  }
}
extern "C" REX_FUNC(sub_827142C0) {
  using namespace forza::graphics_menu;
  if (ctx.r3.u32 != graphics_screen) {
    __imp__sub_827142C0(ctx, base);
    return;
  }
  Native ui(ctx, base);
  if (!ui)
    return;
  if (empty_pause_source)
    PauseRows(ui, base, true);
  RestorePreview();
  for (uint32_t row : native_rows) {
    auto choices = Read(base, row + 4);
    ui.Call(Read(base, Read(base, choices)), {choices, 1});
    ui.Call(Read(base, Read(base, row)), {row, 1});
  }
  auto source = Read(base, graphics_screen + 0x1A0);
  ui.Call(Read(base, Read(base, source)), {source, 1});
  Write(base, graphics_screen + 0x1A0, 0);
  native_rows.clear();
  graphics_screen = 0;
}
extern "C" REX_FUNC(sub_82736B08) {
  using namespace forza::graphics_menu;
  if (ctx.r3.u32 != graphics_screen) {
    __imp__sub_82736B08(ctx, base);
    return;
  }
  Native ui(ctx, base);
  if (!ui)
    return;
  auto event = ui.Event(graphics_screen, ctx.r4.u32);
  if (!applying_request.empty()) return;
  if (event == 0x5D) {
    for (size_t i = 0; i < native_rows.size(); ++i) {
      auto choice = Read(base, native_rows[i] + 8);
      if (choice < settings[i].choices.size())
        settings[i].value = settings[i].choices[choice].value;
    }
    if (!applying_request.empty()) return;
    if (rex::cvar::GetFlagByName("gpu_backend") != "vulkan" ||
        !rex::cvar::GetFlagInfo("fh1_graphics_request")) {
      ui.Binding(graphics_screen + 0x17C, "Live graphics requires the updated Vulkan renderer.");
      return;
    }
    const auto output = settings[0].value;
    const auto width = output == "4k" ? "3840" : output == "1080p" ? "1920" : "2560";
    const auto height = output == "4k" ? "2160" : output == "1080p" ? "1080" : "1440";
    applying_settings = settings;
    applying_request = std::to_string(++request_id) + " " + width + " " + height +
        " " + settings[2].value + " " + settings[1].value;
    if (!rex::cvar::SetFlagByName("fh1_graphics_request", applying_request)) {
      applying_request.clear();
      ui.Binding(graphics_screen + 0x17C, "Could not apply graphics settings.");
      return;
    }
    ui.Binding(graphics_screen + 0x17C, "Applying graphics settings...");
  } else if (event == 0x60) {
    RestorePreview();
    PauseRows(ui, base, true);
    ui.Call(0x827F20F0, {graphics_screen});
  } else {
    auto component = Read(base, graphics_screen + 0x16C);
    ui.Call(Read(base, Read(base, component) + 0x34), {component, ctx.r4.u32});
    // Read the spinner's final model after its callback dispatch has completed.
    for (size_t i = 0; i < native_rows.size(); ++i) {
      auto choice = Read(base, native_rows[i] + 8);
      if (choice < settings[i].choices.size())
        settings[i].value = settings[i].choices[choice].value;
    }
    if (!ApplyPreview())
      ui.Binding(graphics_screen + 0x17C,
                 "Could not apply this live change. Back restores the previous "
                 "settings.");
  }
}
extern "C" REX_FUNC(MenuSelect) {
  using namespace forza::graphics_menu;
  if (ctx.r3.u32 == active_menu && ctx.r4.u32 == 2 && ctx.r6.u32 == kGraphics) {
    Snapshot();
    opening_graphics = true;
    Native ui(ctx, base);
    if (!ui)
      return;
    auto params = ui.Call(0x824265C8, {0x88});
    ui.Call(0x825A5640, {params, 0});
    auto title = ui.Text("GRAPHICS SETTINGS");
    ui.Call(0x82471820, {params + 0xC, title});
    ui.Call(0x824CEAB0, {title});
    Write(base, ui.scratch(), params);
    ui.Call(0x82675B00, {active_menu, 5, ui.scratch(), 0});
    REXLOG_INFO("Graphics menu: opening native graphics settings scene");
    return;
  }
  OriginalSelect(ctx, base);
}

namespace forza::graphics_menu {
void Tick(PPCContext& ctx, uint8_t* base) {
  if (applying_request.empty()) return;
  const auto result = rex::cvar::GetFlagByName("fh1_graphics_result");
  const auto prefix = applying_request + "|";
  if (result.rfind(prefix, 0) != 0) return;
  const auto status = result.substr(prefix.size());
  applying_request.clear();
  std::string message;
  if (status == "ok") {
    settings = applying_settings;
    const bool rate_changed = rex::cvar::GetFlagByName("frame_rate") != settings[3].value;
    rex::cvar::SetFlagByName("frame_rate", settings[3].value);
    rex::cvar::SetFlagByName("video_mode_refresh_rate", std::to_string(frame_time::VblankHz()));
    if (rate_changed) frame_time::ResetRenderTiming();
    rex::cvar::SetFlagByName("resolution", settings[0].value);
    const bool saved = Save();
    saved_settings = settings;
    RememberPreview();
    message = saved ? "Applied and saved. No restart needed."
                    : "Applied, but could not save. Select Save to retry.";
  } else {
    message = status;
  }
  applying_settings.clear();
  REXLOG_INFO("Graphics menu: {}", message);
  if (graphics_screen) {
    Native ui(ctx, base);
    if (ui) ui.Binding(graphics_screen + 0x17C, message);
  }
}
} // namespace forza::graphics_menu
#else
namespace forza::graphics_menu {
void Tick(PPCContext&, uint8_t*) {}
}
#endif // FORZA_TU4
