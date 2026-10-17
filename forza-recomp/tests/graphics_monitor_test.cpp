// Standalone: c++ -std=c++17 graphics_monitor_test.cpp -o graphics_monitor_test
#include "../src/platform/performance_history.h"
#include "../src/platform/graphics_presets.h"
#include <cassert>
#include <limits>
#include <iostream>
int main() {
  forza::PerformanceHistory h;
  assert(h.Fps(0) == 0);
  for (int i = 0; i <= 120; ++i) h.Record(double(i) / 60);
  assert(std::abs(h.Fps(2) - 60) < 0.01);
  assert(h.Fps(4) == 0); // no game frames, even if the UI repaints
  h.Record(2.5);
  assert(std::abs(h.Ordered()[h.count() - 1] - 500) < 0.01);
  assert(h.Fps(2.5) < 40); // preserve the hitch in the rolling FPS
  const auto count = h.count();
  h.Record(std::numeric_limits<double>::quiet_NaN());
  assert(h.count() == count);
  for (int i = 1; i <= 300; ++i) h.Record(2.5 + double(i) / 30);
  assert(h.count() == h.kCapacity);
  assert(std::abs(h.Fps(12.5) - 30) < 0.01);
  for (auto ms : h.Ordered()) assert(std::abs(ms - 1000.0 / 30) < 0.01);
  using forza::graphics_menu::ChoosePreset;
  assert(ChoosePreset("auto", "1080p", true, true).mode == "off");
  assert(ChoosePreset("auto", "1440p", true, true).mode == "quality");
  assert(ChoosePreset("auto", "4k", false, true).mode == "fsr3_quality");
  assert(ChoosePreset("low", "1440p", true, true).mode == "dlss");
  assert(ChoosePreset("medium", "1440p", true, true).mode == "balanced");
  const auto native = ChoosePreset("high", "1440p", false, false);
  assert(native.mode == "off" && native.scene_scale == 2 && native.filtering == 5);
  const auto low = ChoosePreset("low", "4k", false, false);
  assert(low.scene_scale == 1 && low.filtering == 2);
  std::cout << "Graphics monitor and presets passed\n";
}
