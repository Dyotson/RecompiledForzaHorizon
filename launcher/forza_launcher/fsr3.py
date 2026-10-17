"""AMD FidelityFX FSR 3 temporal upscaling (docs/rendering.md#upscaling).

The renderer's scene/UI split, as for NVIDIA DLSS, with FSR 3.1's upscaler (no frame
generation) as the reconstruction: any Vulkan GPU. The scene renders at the mode's input
size, FSR 3 reconstructs it at the output resolution, and the HUD is drawn natively over it.
On an NVIDIA GPU with DLSS on, DLSS wins.
"""
from . import dlss, paths

MODES = {"quality": "Quality", "balanced": "Balanced", "performance": "Performance",
         "native": "Native AA"}
# output: (width, height, the UI's integer render scale)
SIZES = {"1080p": (1920, 1080, 2), "1440p": (2560, 1440, 2), "4k": (3840, 2160, 3)}


def enabled(cfg) -> bool:
    return (cfg.settings.get("present_effect") == "fsr3" or
            cfg.settings.get("forza_antialiasing") == "fsr3_native") and not dlss.enabled(cfg)


def configure(cfg, args, notes):
    if not enabled(cfg):
        return
    native_aa = cfg.settings.get("forza_antialiasing") == "fsr3_native" and cfg.settings.get("present_effect") != "fsr3"
    mode = "native" if native_aa else cfg.settings.get("fsr3_mode", "performance")
    resolution = cfg.settings.get("resolution", "1440p") if native_aa else cfg.settings.get("fsr3_output_resolution", "1440p")
    if mode not in MODES:
        raise RuntimeError(f"Unknown AMD FSR 3 mode: {mode}")
    if resolution not in SIZES:
        raise RuntimeError(f"Unsupported AMD FSR 3 output resolution: {resolution}")
    width, height, scale = SIZES[resolution]
    # FSR 1 stays the presenter's filter: it is what the game falls back to when FSR 3
    # cannot start (and the output is already at window size otherwise).
    args[:] = [a for a in args if not a.startswith("--present_effect=")]
    if paths.IS_WINDOWS:
        args.append("--gpu_backend=vulkan")
    args += [f"--resolution={resolution}", f"--resolution_scale={scale}",
             f"--fh1_output_width={width}", f"--fh1_output_height={height}",
             f"--fh1_upscaler=fsr3_{mode}", "--present_effect=fsr"]
    floor = " Input at least 720p." if height < 1440 and mode in ("balanced", "performance") else ""
    notes.append(f"AMD FSR 3 {MODES[mode]}: {resolution} output and native {resolution} UI.{floor}")
