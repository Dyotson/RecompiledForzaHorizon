// Garage/showroom automatic orbit. The original car-target camera adds 0.1
// degree per UI update in state 2. Keep its 30 Hz speed at every frame rate.
#include "../platform/guest_addr.h"
#include "../platform/guest_memory.h"
#include "../platform/garage_camera_math.h"

#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/logging.h>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <chrono>
#include <mutex>
#include <unordered_map>
#include <cstdlib>

namespace {
bool OriginalTiming() {
  static const bool original = [] {
    const char* value = std::getenv("FORZA_GARAGE_CAMERA");
    return value && std::strcmp(value, "game") == 0;
  }();
  return original;
}
float LoadFloat(uint8_t* base, uint32_t address) {
  const auto* p = forza::GuestPtr(base, address);
  const uint32_t bits = uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 |
                        uint32_t(p[2]) << 8 | p[3];
  float value;
  std::memcpy(&value, &bits, sizeof(value));
  return value;
}
void StoreFloat(uint8_t* base, uint32_t address, float value) {
  uint32_t bits;
  std::memcpy(&bits, &value, sizeof(bits));
  auto* p = forza::GuestPtr(base, address);
  p[0] = uint8_t(bits >> 24);
  p[1] = uint8_t(bits >> 16);
  p[2] = uint8_t(bits >> 8);
  p[3] = uint8_t(bits);
}

// CUI4AnimatedCamera passes 1/30 (or its developer option's 1/60) to
// CTSCCamera/CCamAnimPlayer on every UI update. Only replace that caller's
// fixed dt: world/race cameras already receive simulation time.
double AnimatedDelta(uint32_t camera, double initial) {
  using Clock = std::chrono::steady_clock;
  static std::mutex mutex;
  static std::unordered_map<uint32_t, Clock::time_point> clocks;
  const auto now = Clock::now();
  std::lock_guard lock(mutex);
  if (clocks.size() > 64) clocks.clear();
  auto [it, inserted] = clocks.try_emplace(camera, now);
  const double dt = std::chrono::duration<double>(now - it->second).count();
  it->second = now;
  // Do not fast-forward a shot when returning to a dormant camera.
  return inserted || dt > 0.25 ? initial : dt;
}
void Trace(PPCContext& ctx) {
  if (!std::getenv("FORZA_GARAGE_CAMERA_TRACE")) return;
  static std::mutex mutex;
  static std::unordered_map<uint32_t, unsigned> counts;
  std::lock_guard lock(mutex);
  auto& count = counts[uint32_t(ctx.lr)];
  if (count++ % 300 == 0)
    REXLOG_INFO("Garage camera: caller={:08X} camera={:08X} dt={:.6f}",
                uint32_t(ctx.lr), ctx.r3.u32, ctx.f1.f64);
}
}  // namespace

extern "C" REX_FUNC(sub_8246EBB8);  // UI timer: elapsed seconds since reset
extern "C" REX_FUNC(__imp__sub_82647B78);
extern "C" REX_FUNC(sub_82647B78) {
  // Only the automatic-orbit call from CUI4CarTargetCamera::Update. Other
  // callers use this transform routine for manual input and camera transitions.
  if (!OriginalTiming() && uint32_t(ctx.lr) == FORZA_ADDR(0x82653588)) {
    const uint32_t camera = ctx.r3.u32;
    PPCContext timer = ctx;
    const auto* p = forza::GuestPtr(base, camera + 0x70);
    timer.r3.u64 = uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 |
                   uint32_t(p[2]) << 8 | p[3];
    sub_8246EBB8(timer, base);
    const double dt = timer.f1.f64;
    // Replace the fixed step before building the view, using the camera's own
    // timer (reset by the base camera update), not the selected FPS cap.
    StoreFloat(base, camera + 0x80, forza::garage_camera::CorrectOrbit(
        LoadFloat(base, camera + 0x80), dt));
  }
  __imp__sub_82647B78(ctx, base);
}

extern "C" REX_FUNC(__imp__sub_82862170);
extern "C" REX_FUNC(sub_82862170) {
  if (!OriginalTiming() && uint32_t(ctx.lr) == FORZA_ADDR(0x826499D4))
    ctx.f1.f64 = AnimatedDelta(ctx.r3.u32, ctx.f1.f64);
  Trace(ctx);
  __imp__sub_82862170(ctx, base);
}
extern "C" REX_FUNC(__imp__sub_82862CD0);
extern "C" REX_FUNC(sub_82862CD0) {
  if (!OriginalTiming() && uint32_t(ctx.lr) == FORZA_ADDR(0x826499D4))
    ctx.f1.f64 = AnimatedDelta(ctx.r3.u32, ctx.f1.f64);
  Trace(ctx);
  __imp__sub_82862CD0(ctx, base);
}
