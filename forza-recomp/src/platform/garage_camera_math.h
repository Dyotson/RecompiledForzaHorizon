#pragma once
#include <cmath>

namespace forza::garage_camera {
// The guest has already added one fixed step and wrapped the angle.
inline float CorrectOrbit(float angle, double dt) {
  if (!std::isfinite(dt) || dt < 0.0) return angle;
  constexpr double step = 0.001745329238474369;
  constexpr double turn = 6.283185307179586;
  double corrected = std::fmod(angle - step + step * 30.0 * dt, turn);
  if (corrected < 0.0) corrected += turn;
  return float(corrected);
}
}  // namespace forza::garage_camera
