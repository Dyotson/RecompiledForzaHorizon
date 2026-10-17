"""The optional NVIDIA runtime, downloaded from NVIDIA's pinned public SDK.

No system-wide installation or DLL search-path changes. The renderer receives
the private runtime folder for NGX's explicit feature search path.
"""
import os
import json
import threading
import re
import uuid
from pathlib import Path

from . import fetch, gpu, paths, pins

SDK_REVISION = "374959484e79a640feaba44c93ac8cfb0a03f5b5"
_BASE = f"https://raw.githubusercontent.com/NVIDIA/DLSS/{SDK_REVISION}"
RUNTIME_SHA256 = "3975567b8943c53acce397f2b72380092f84f162d00b0d2c7d08a1025c563983"
LICENSE_SHA256 = "d4216e39ebef5f9b50a6712ebb37beeb5379862a67733a9999c651f21592aaf0"

# fetch.download uses the same checked/resumable path as the toolchain installer.
pins.DOWNLOADS.update({
    "dlss-runtime-windows": (
        f"{_BASE}/lib/Windows_x86_64/rel/nvngx_dlss.dll", RUNTIME_SHA256, "file"),
    "dlss-license": (f"{_BASE}/LICENSE.txt", LICENSE_SHA256, "file"),
})


_hash_cache = {}
_hash_lock = threading.Lock()


def _sha256(path):
    path = Path(path).resolve()
    stat = path.stat()
    identity = (stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns, stat.st_ino)
    with _hash_lock:
        cached = _hash_cache.get(path)
        if cached and cached[0] == identity:
            return cached[1]
        digest = fetch.sha256_of(path)
        # Do not cache a digest for a file changed while it was being read.
        after = path.stat()
        if identity == (after.st_mtime_ns, after.st_size, after.st_ctime_ns, after.st_ino):
            if len(_hash_cache) >= 128:
                _hash_cache.clear()
            _hash_cache[path] = (identity, digest)
        return digest


def runtime_dir(cfg) -> Path:
    return cfg.data_home() / "graphics" / "nvidia-dlss" / SDK_REVISION


def enabled(cfg) -> bool:
    return (cfg.gpu_vendor() == gpu.NVIDIA and
            cfg.settings.get("fh1_upscaler", "off") != "off")


def menu_runtime_enabled(cfg) -> bool:
    """Prepare NGX before a native session so its menu can enable DLSS later."""
    return (paths.IS_WINDOWS and cfg.gpu_vendor() == gpu.NVIDIA and
            cfg.settings.get("gpu_backend", "vulkan") == "vulkan")


def check_renderer(folder):
    """An older SDK overlay must not silently ignore the native settings."""
    try:
        folder = Path(folder)
        capabilities = json.loads((folder / "fh1-native-dlss.json").read_text(encoding="utf-8"))
        valid = (isinstance(capabilities, dict) and capabilities.get("api") == 2 and
                 capabilities.get("renderer_sha256") == _sha256(folder / "rexgpu-xenos.dll"))
    except (OSError, ValueError):
        valid = False
    if not valid:
        raise RuntimeError("This game build does not include the native DLSS renderer. "
                           "Rebuild with this branch's updated SDK, or turn NVIDIA DLSS off.")


def configure(cfg, env, args, notes, write=True):
    if not enabled(cfg):
        return
    mode = cfg.settings.get("fh1_upscaler")
    if mode not in ("quality", "balanced", "dlss", "dlaa"):
        raise RuntimeError(f"Unknown NVIDIA reconstruction mode: {mode}")
    if not paths.IS_WINDOWS:
        raise RuntimeError("Native DLSS currently supports Windows only.")
    resolution, width, height, scale = output_settings(cfg)
    if write:
        prepare(cfg)
    env["FORZA_DLSS_RUNTIME"] = str(runtime_dir(cfg))
    status = cfg.data_home() / "logs" / f"nvidia-dlss-{uuid.uuid4().hex}.status"
    if write:
        status.parent.mkdir(parents=True, exist_ok=True)
    env["FORZA_DLSS_STATUS_FILE"] = str(status)
    args += ["--gpu_backend=vulkan", f"--resolution={resolution}", f"--resolution_scale={scale}",
             f"--fh1_output_width={width}", f"--fh1_output_height={height}"]
    label = {"quality": "DLSS Quality", "balanced": "DLSS Balanced", "dlss": "DLSS Performance",
             "dlaa": "DLAA"}[mode]
    notes.append(f"{label}: {resolution} output and native {resolution} UI. " +
                 ("Output-sized NGX input." if mode == "dlaa" else
                  "NVIDIA selects the DLSS input; the scene raster rounds up to an integer scale."))


def output_settings(cfg):
    resolution = cfg.settings.get("fh1_output_resolution", "1440p")
    sizes = {"1080p": (1920, 1080, 2), "1440p": (2560, 1440, 2), "4k": (3840, 2160, 3)}
    if resolution not in sizes:
        raise RuntimeError(f"Unsupported NVIDIA output resolution: {resolution}")
    return (resolution, *sizes[resolution])



def session_status(plan):
    """The renderer reports readiness only after its first successful NGX frame."""
    path = plan.env.get("FORZA_DLSS_STATUS_FILE")
    if not path:
        return None
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if text.startswith(("ready: ", "error: ")):
        return text.startswith("error: "), text.split(": ", 1)[1]
    return None


def ready(cfg) -> bool:
    folder = runtime_dir(cfg)
    try:
        return (_sha256(folder / "nvngx_dlss.dll") == RUNTIME_SHA256 and
                _sha256(folder / "LICENSE.txt") == LICENSE_SHA256)
    except OSError:
        return False


def prepare(cfg, progress=lambda done, total: None, cancelled=lambda: False) -> Path:
    """Fetch on first use, repair changed files, and reuse verified files offline."""
    if not paths.IS_WINDOWS:
        raise RuntimeError("This DLSS integration currently supports Windows only.")
    if cfg.gpu_vendor() != gpu.NVIDIA:
        raise RuntimeError("DLSS runtime setup requires an NVIDIA graphics card.")
    dest = runtime_dir(cfg)
    if ready(cfg):
        _remove_download_copies(cfg)
        return dest
    cache = cfg.data_home() / "downloads" / "nvidia-dlss" / SDK_REVISION
    assets = [("dlss-runtime-windows", "nvngx_dlss.dll"), ("dlss-license", "LICENSE.txt")]
    # Verify every asset before replacing any installed file.
    sources = []
    for key, name in assets:
        target = dest / name
        expected = RUNTIME_SHA256 if name == "nvngx_dlss.dll" else LICENSE_SHA256
        try:
            valid = _sha256(target) == expected
        except OSError:
            valid = False
        sources.append((target if valid else fetch.download(key, cache, progress, cancelled), name))
    dest.mkdir(parents=True, exist_ok=True)
    for source, name in sources:
        if cancelled():
            raise fetch.Cancelled()
        target = dest / name
        if source != target:
            os.replace(source, target)
        # fetch.download already verified this exact file before the atomic move.
        stat = target.stat()
        digest = RUNTIME_SHA256 if name == "nvngx_dlss.dll" else LICENSE_SHA256
        with _hash_lock:
            _hash_cache[target.resolve()] = ((stat.st_mtime_ns, stat.st_size,
                                             stat.st_ctime_ns, stat.st_ino), digest)
    _remove_download_copies(cfg)
    return dest


def _remove_download_copies(cfg):
    cache = cfg.data_home() / "downloads" / "nvidia-dlss" / SDK_REVISION
    for name in ("nvngx_dlss.dll", "LICENSE.txt"):
        (cache / name).unlink(missing_ok=True)


def cleanup_status(plan):
    # Only remove our own generated status file, never an arbitrary extra-env path.
    value = getattr(plan, "dlss_status_file", None)
    if value:
        path = Path(value)
        if re.fullmatch(r"nvidia-dlss-[0-9a-f]{32}\.status", path.name):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
