"""Import graphics choices saved by the game's native pause menu."""
import json

from . import schema

FILENAME = "graphics-settings.json"
KEYS = {"output", "upscaler", "resolution_scale", "frame_rate", "vsync",
        "anisotropic_override", "forza_hud_edges", "forza_performance_overlay", "anti_aliasing"}
NVIDIA = {"quality", "balanced", "dlss", "dlaa"}
FSR3 = {"fsr3_quality", "fsr3_balanced", "fsr3_performance", "fsr3_native"}


def configure_runtime(cfg, env, args, write=True):
    """Keep native scene scale independent of the output/HUD, as the live menu does."""
    from . import dlss, fsr3, paths
    if write and paths.IS_WINDOWS and "FORZA_DLSS_RUNTIME" not in env and dlss.ready(cfg):
        env.setdefault("FORZA_DLSS_RUNTIME", str(dlss.runtime_dir(cfg)))
    values = cfg.settings
    aa = values.get("forza_antialiasing", "game")
    scaling = values.get("fh1_upscaler", "off") != "off" or values.get("present_effect") == "fsr3"
    if scaling or aa != "game":
        args.append("--swap_post_effect=none")
    if scaling and aa != "game":
        raise RuntimeError("Upscaling includes anti-aliasing. Turn it off before choosing a separate AA method.")
    if aa != "game" and (values.get("gpu_backend", "vulkan") != "vulkan" or values.get("forza_ultrawide")):
        raise RuntimeError("Separate scene anti-aliasing currently requires Vulkan and standard 16:9 output.")
    if aa == "dlaa" and not dlss.enabled(cfg):
        raise RuntimeError("DLAA requires an NVIDIA RTX GPU and its runtime.")
    if (values.get("gpu_backend", "vulkan") != "vulkan" or
            values.get("forza_ultrawide") or dlss.enabled(cfg) or
            fsr3.enabled(cfg)):
        return
    sizes = {"1080p": (1920, 1080, 2), "1440p": (2560, 1440, 2), "4k": (3840, 2160, 3)}
    size = sizes.get(values.get("resolution"))
    scene_scale = int(values.get("resolution_scale", 1))
    if size is None or scene_scale not in (1, 2, 3):
        return
    width, height, output_scale = size
    if aa == "smaa":
        args += ["--fh1_upscaler=smaa"]
        scene_scale = output_scale
    args += ["--fh1_scene_720p_native_hud=true", f"--fh1_native_scene_scale={scene_scale}",
             f"--resolution_scale={output_scale}", f"--fh1_output_width={width}",
             f"--fh1_output_height={height}"]


def translate(document, current):
    """Validate the complete request before changing any launcher setting."""
    if (not isinstance(document, dict) or
            type(document.get("version")) is not int or document["version"] != 1):
        raise ValueError("unsupported graphics settings version")
    values = document.get("settings")
    if not isinstance(values, dict) or not values or values.keys() - KEYS:
        raise ValueError("unknown graphics settings")
    changes = {}
    for key, value in values.items():
        if not isinstance(value, str):
            raise ValueError(f"invalid {key}")
        if key == "output":
            if value not in {"1080p", "1440p", "4k"}:
                raise ValueError("unsupported output resolution")
            changes.update(resolution=value, fsr3_output_resolution=value)
            if "fh1_output_resolution" in schema.BY_KEY:
                changes["fh1_output_resolution"] = value
        elif key == "upscaler":
            if value not in {"off"} | NVIDIA | FSR3:
                raise ValueError("unsupported upscaler")
            if value in NVIDIA and "fh1_upscaler" not in schema.BY_KEY:
                raise ValueError("NVIDIA reconstruction is unavailable on this platform")
            if "fh1_upscaler" in schema.BY_KEY:
                changes["fh1_upscaler"] = value if value in NVIDIA else "off"
            if value in FSR3:
                changes.update(present_effect="fsr3", fsr3_mode=value[5:])
            elif current.get("present_effect") == "fsr3":
                changes["present_effect"] = "bilinear"
        elif key == "anti_aliasing":
            if value not in {"game", "integrated", "smaa", "dlaa", "fsr3_native"}:
                raise ValueError("unsupported anti-aliasing")
            if value == "dlaa" and "fh1_upscaler" not in schema.BY_KEY:
                raise ValueError("NVIDIA anti-aliasing is unavailable on this platform")
            changes["forza_antialiasing"] = "game" if value == "integrated" else value
        elif key == "forza_performance_overlay":
            if value not in {"off", "fps", "graph"}:
                raise ValueError("unsupported performance overlay")
            changes[key] = value
        elif key in {"vsync", "forza_hud_edges"}:
            if value not in ("true", "false"):
                raise ValueError(f"invalid {key}")
            changes[key] = value == "true"
        else:
            if not isinstance(value, str) or not value.lstrip("-").isdigit():
                raise ValueError(f"invalid {key}")
            number = int(value)
            valid = ((key == "frame_rate" and (number == 30 or 60 <= number <= 240)) or
                     (key == "resolution_scale" and 1 <= number <= 8) or
                     (key == "anisotropic_override" and -1 <= number <= 5))
            if not valid:
                raise ValueError(f"unsupported {key}")
            changes[key] = number
    if "anti_aliasing" in values:
        mode = values.get("upscaler")
        if mode is None:
            mode = current.get("fh1_upscaler", "off")
            if mode == "off" and current.get("present_effect") == "fsr3":
                mode = "fsr3_" + current.get("fsr3_mode", "quality")
        aa = values["anti_aliasing"]
        if (mode != "off" and aa != "integrated") or (mode == "off" and aa == "integrated"):
            raise ValueError("incompatible upscaling and anti-aliasing")
    elif "upscaler" in values:
        changes["forza_antialiasing"] = "game"
    # Accept old version-1 requests from builds with the combined selector.
    if "anti_aliasing" not in values and values.get("upscaler") == "dlaa":
        changes.update(fh1_upscaler="off", forza_antialiasing="dlaa")
    elif "anti_aliasing" not in values and values.get("upscaler") == "fsr3_native":
        changes.update(present_effect="bilinear", forza_antialiasing="fsr3_native")
    return changes


def import_pending(cfg, log=print):
    pending = cfg.data_home() / FILENAME
    try:
        if pending.stat().st_size > 16384:
            raise ValueError("graphics settings file is too large")
        changes = translate(json.loads(pending.read_text(encoding="utf-8")), cfg.settings)
    except FileNotFoundError:
        return False
    except (OSError, ValueError, TypeError) as error:
        log(f"Could not load in-game graphics settings: {error}")
        return False
    previous = dict(cfg.settings)
    cfg.settings.update(changes)
    try:
        cfg.save()
    except OSError as error:
        cfg.settings.clear()
        cfg.settings.update(previous)
        log(f"Could not save in-game graphics settings: {error}")
        return False
    try:
        pending.unlink()
    except OSError as error:
        log(f"Graphics settings saved, but the pending file could not be removed: {error}")
    log("Applied the graphics settings saved in the game's pause menu.")
    return True
