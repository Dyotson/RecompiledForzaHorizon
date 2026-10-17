#pragma once
#include <array>
#include <algorithm>
#include <cmath>
#include <cstddef>

namespace forza {
// Game-frame intervals, never UI redraws. Caller supplies a monotonic clock in seconds.
class PerformanceHistory {
 public:
  static constexpr size_t kCapacity = 240;
  void Record(double now) {
    if (!std::isfinite(now)) return;
    if (has_last_ && now > last_) {
      samples_[next_] = float((now - last_) * 1000.0);
      next_ = (next_ + 1) % kCapacity;
      count_ = std::min(count_ + 1, kCapacity);
    }
    last_ = now;
    has_last_ = true;
  }
  size_t count() const { return count_; }
  std::array<float, kCapacity> Ordered() const {
    std::array<float, kCapacity> out{};
    for (size_t i = 0; i < count_; ++i)
      out[i] = samples_[(next_ + kCapacity - count_ + i) % kCapacity];
    return out;
  }
  double Fps(double now) const {
    if (!count_ || now - last_ > 1.0) return 0;
    double ms = 0;
    size_t n = 0;
    // A rolling second, not the arithmetic mean of instantaneous FPS.
    while (n < count_ && ms < 1000.0) {
      ms += samples_[(next_ + kCapacity - 1 - n) % kCapacity];
      ++n;
    }
    return ms > 0 ? 1000.0 * n / ms : 0;
  }
 private:
  std::array<float, kCapacity> samples_{};
  size_t next_ = 0, count_ = 0;
  double last_ = 0;
  bool has_last_ = false;
};
}  // namespace forza
