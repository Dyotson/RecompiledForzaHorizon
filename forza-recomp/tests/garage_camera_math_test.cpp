#include "../src/platform/garage_camera_math.h"
#include <cassert>
#include <cmath>
#include <initializer_list>
#include <limits>

int main() {
  using forza::garage_camera::CorrectOrbit;
  constexpr float step = 0.001745329238474369f;
  constexpr double turn = 6.283185307179586;
  for (int fps : {30, 60, 120, 144, 240}) {
    float angle = 0;
    for (int n = 0; n < fps * 10; ++n)
      angle = CorrectOrbit(float(std::fmod(angle + step, turn)), 1.0 / fps);
    assert(std::abs(angle - step * 30 * 10) < 0.0001);
  }
  // A stalled renderer must use elapsed time rather than the requested cap.
  assert(std::abs(CorrectOrbit(step, 0.1) - step * 3) < 1e-7);
  assert(std::abs(CorrectOrbit(step, 0)) < 1e-7);
  assert(CorrectOrbit(1, -1) == 1);
  assert(CorrectOrbit(1, std::numeric_limits<double>::quiet_NaN()) == 1);
  assert(CorrectOrbit(1, std::numeric_limits<double>::infinity()) == 1);
  auto wrapped = CorrectOrbit(0.0001f, 1.0 / 120);
  assert(wrapped > 6 && wrapped < turn);
}
