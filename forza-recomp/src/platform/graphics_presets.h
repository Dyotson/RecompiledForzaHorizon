#pragma once
#include <string>
#include <string_view>
namespace forza::graphics_menu {
struct Preset {
  std::string mode;
  int scene_scale;
  int filtering;
};
// These presets alter reconstruction and filtering, never output/HUD resolution,
// frame cap, or the game's car/shadow LOD. Auto is capability-based, not a benchmark.
inline Preset ChoosePreset(std::string_view name, std::string_view output,
                           bool dlss, bool fsr) {
  const bool automatic = name == "auto";
  const bool native = automatic && output == "1080p";
  const std::string quality = name == "low" ? "performance" :
                              name == "medium" ? "balanced" : "quality";
  std::string mode = "off";
  if (!native && dlss) mode = quality == "performance" ? "dlss" : quality;
  else if (!native && fsr) mode = "fsr3_" + quality;
  const int scale = name == "low" ? 1 : output == "4k" ? 3 : 2;
  return {mode, scale, name == "low" ? 2 : name == "medium" ? 4 : 5};
}
}  // namespace forza::graphics_menu
