#pragma once
#include <filesystem>
#include <cstdint>
struct PPCContext;

namespace forza::graphics_menu {
void Initialize(const std::filesystem::path& data_root);
void Tick(PPCContext& ctx, uint8_t* base);
}
