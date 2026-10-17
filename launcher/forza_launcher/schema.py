"""Every forza.toml key the launcher manages.

Each entry is a ReXGlue SDK cvar or one this project defines in forza-recomp/src (frame_rate,
live_server, the Horizon World switches, ...). A cvar can be set in forza.toml next to the game
binary or as --name=value on the command line; the launcher writes forza.toml. A key that
holds its default is not written, so the file stays small. `default` is what "unset" means
for the game (a few use 0/"" as "automatic").
"""
from dataclasses import dataclass, field

from .paths import IS_WINDOWS

GROUPS = ["Display", "Controls", "Audio", "Online", "Profile", "Advanced"]


@dataclass
class Setting:
    key: str
    label: str
    group: str
    kind: str  # bool, int, float, str, choice, combo, fps, keys
    default: object
    help: str = ""
    section: str = ""  # sub-heading inside the group
    choices: list = field(default_factory=list)  # [(value, label)], for choice / combo
    lo: float | None = None
    hi: float | None = None
    step: float = 1
    platform: str = ""  # "linux" or "windows": shown only there
    restart: bool = False
    legacy: dict = field(default_factory=dict)  # value an older version offered -> the one it became

    def applies(self) -> bool:
        return not self.platform or (self.platform == "windows") == IS_WINDOWS


def _c(*values):
    return [(v, v) for v in values]


S = []


def add(*a, **k):
    S.append(Setting(*a, **k))


# --- Display ---------------------------------------------------------------------------
add("frame_rate", "Frame rate", "Display", "fps", 30,
    "30 is the console's rate; 60 to 240 (60, 120, 144, ...) run the game faster. Physics and "
    "race timing keep their speed (docs/framerate.md).", "Frame rate")
add("forza_performance_overlay", "Performance overlay", "Display", "choice", "off",
    "Measured game FPS, optionally with a frame-time graph. Does not count UI redraws.",
    "Frame rate", choices=[("off", "Off"), ("fps", "FPS"), ("graph", "FPS + frame-time graph")])
add("vsync", "Vertical sync", "Display", "bool", True,
    "Wait for the display's refresh. Turn off only for testing.", "Frame rate")
add("video_mode_refresh_rate", "Guest refresh rate (Hz)", "Display", "float", 0.0,
    "0 picks it from the frame rate. Set it to override.", "Frame rate", lo=0, hi=480, step=1)
add("fullscreen", "Fullscreen", "Display", "bool", True,
    "Start in fullscreen (borderless at the desktop mode).", "Window")
add("fullscreen_exclusive", "Exclusive fullscreen", "Display", "bool", False,
    "Switch the display mode instead of staying borderless.", "Window")
add("window_width", "Window width", "Display", "int", 0,
    "Logical pixels for windowed mode. 0 uses the default.", "Window", lo=0, hi=8192, step=10)
add("window_height", "Window height", "Display", "int", 0,
    "Logical pixels for windowed mode. 0 uses the default.", "Window", lo=0, hi=8192, step=10)
add("monitor", "Monitor", "Display", "int", 0,
    "0 default, 1 primary, 2 second monitor, ...", "Window", lo=0, hi=16)
add("video_driver", "Video driver", "Display", "choice", "",
    "SDL video driver. Automatic is right unless the window misbehaves.", "Window",
    choices=[("", "Automatic"), ("wayland", "Wayland"), ("x11", "X11")], platform="linux",
    restart=True)
add("forza_ultrawide", "Ultrawide gameplay", "Display", "bool", False,
    "Follow the window's aspect ratio with a wider horizontal view. Menus and map stay 16:9. "
    "Renders at the physical window resolution with proportional HUD. Render scale is automatic. "
    "Requires Vulkan, the patched SDK and a physical window height divisible by 720 (720/1440/2160). "
    "1080-line windows use ordinary 16:9 rendering. Restart after resizing to change render resolution.",
    "Ultrawide and HUD", restart=True)
add("forza_hud_edges", "Expand HUD to ultrawide edges", "Display", "bool", False,
    "Anchor side HUD elements toward the full window edges while keeping gauges and text proportional. "
    "Keeps the original screen insets. Experimental: long centered text and race overlays need more testing. "
    "Applies during gameplay; restart after changing.",
    "Ultrawide and HUD", restart=True)
add("forza_hud_layout", "Customize HUD layout", "Display", "bool", False,
    "Adjust the HUD safe area and position at 16:9 or ultrawide, without changing the camera. "
    "Applies on the next game launch.", "Ultrawide and HUD", restart=True)
add("forza_hud_safe_width", "HUD safe width %", "Display", "float", 100.0,
    "Fit the centered 16:9 HUD within this width. The smaller safe-area percentage sets the "
    "uniform scale, keeping gauges and text proportional.", "Ultrawide and HUD", lo=50, hi=100, step=1)
add("forza_hud_safe_height", "HUD safe height %", "Display", "float", 100.0,
    "Fit the HUD within this height. Applies during gameplay.", "Ultrawide and HUD", lo=50, hi=100, step=1)
add("forza_hud_offset_x", "HUD horizontal position %", "Display", "float", 0.0,
    "Move the HUD as a group: negative left, positive right. Clamped to keep it on screen.",
    "Ultrawide and HUD", lo=-20, hi=20, step=1)
add("forza_hud_offset_y", "HUD vertical position %", "Display", "float", 0.0,
    "Move the HUD as a group: negative up, positive down. Clamped to keep it on screen.",
    "Ultrawide and HUD", lo=-20, hi=20, step=1)
add("resolution", "Resolution preset", "Display", "combo", "",
    "Guest video mode and window size in one: 720p, 1080p, 1440p, 4k or WxH. Empty keeps the "
    "defaults (1280x720 guest). The game still draws at 1280x720; Render scale sets the "
    "drawing resolution.", "Picture",
    choices=[("", "Default"), ("720p", "720p"), ("1080p", "1080p"), ("1440p", "1440p"),
             ("4k", "4K")])
add("resolution_scale", "Render scale", "Display", "int", 1,
    "Draws at 1x to 8x the guest resolution. 1 with FSR 1 is the fast default; 2 is real extra detail "
    "for about 40% fewer fps; above 2 is experimental (flicker on NVIDIA, issue #47).", "Picture",
    lo=1, hi=8, restart=True)
add("anisotropic_override", "Anisotropic filtering", "Display", "choice", 3,
    "Texture sharpness at oblique angles.", "Picture",
    choices=[(-1, "Game default"), (0, "Off"), (1, "1x"), (2, "2x"), (3, "4x"), (4, "8x"),
             (5, "16x")])
add("present_effect", "Upscaling filter", "Display", "choice", "bilinear",
    "How the 720p picture is scaled to the window. AMD FSR 1 is the sharp, cheap choice (about the "
    "cost of bilinear); CAS only sharpens, up to 2x. AMD FSR 3 (temporal) reconstructs the scene "
    "from several jittered frames at the output resolution below, with the HUD drawn natively; "
    "any GPU (Vulkan).", "Picture",
    choices=[("bilinear", "Bilinear"), ("cas", "AMD CAS (sharpen)"), ("fsr", "AMD FSR 1"),
             ("fsr3", "AMD FSR 3 (temporal)")],
    restart=True, legacy={"fsr2": "fsr"})
add("fsr3_mode", "FSR 3 quality", "Display", "choice", "performance",
    "The scene's input size for AMD FSR 3: Quality 1/1.5 of the output per axis, Balanced 1/1.7, "
    "Performance 1/2 (720p for 1440p); never below the game's native 1280x720, "
    "so at a 1080p output Balanced and Performance also use 720p. Only with the AMD FSR 3 filter.",
    "AMD FSR 3", choices=[("quality", "Quality"), ("balanced", "Balanced"),
                          ("performance", "Performance")], restart=True)
add("fsr3_output_resolution", "FSR 3 output resolution", "Display", "choice", "1440p",
    "The reconstructed picture and native UI resolution for AMD FSR 3.", "AMD FSR 3",
    choices=[("1080p", "1920 x 1080"), ("1440p", "2560 x 1440"), ("4k", "3840 x 2160 (4K)")],
    restart=True)
if IS_WINDOWS:
    add("fh1_upscaler", "NVIDIA DLSS", "Display", "choice", "off",
        "Reconstruct the scene with NVIDIA's recommended input size for the selected mode, "
        "with integrated temporal anti-aliasing. Menus, HUD and car labels stay at output resolution. "
        "The scene uses an integer emulator scale, then resamples between scales; these modes may cost extra. "
        "Requires an RTX GPU; the NVIDIA runtime downloads automatically on first use.",
        "NVIDIA DLSS", choices=[("off", "Off"), ("quality", "Quality"), ("balanced", "Balanced"),
                                ("dlss", "Performance")],
        platform="windows", restart=True)
    add("fh1_output_resolution", "Output resolution", "Display", "choice", "1440p",
        "The reconstructed picture and native UI resolution. Restart the game after changing it.",
        "NVIDIA DLSS", choices=[("1080p", "1920 x 1080"), ("1440p", "2560 x 1440"),
                                ("4k", "3840 x 2160 (4K)")], platform="windows", restart=True)

add("forza_antialiasing", "Anti-aliasing", "Display", "choice", "game",
    "Game default preserves guest MSAA. SMAA 1x is spatial and needs no NVIDIA runtime. "
    "DLAA and FSR Native AA are temporal at output resolution. A separate method is available "
    "only with upscaling off; filtering occurs before the native HUD.", "Picture",
    choices=[("game", "Game default (MSAA)"), ("smaa", "SMAA 1x"),
             *([("dlaa", "NVIDIA DLAA")] if IS_WINDOWS else []),
             ("fsr3_native", "FSR Native AA (TAA)")], restart=True)
add("swap_post_effect", "Anti-aliasing post effect", "Display", "choice", "none",
    "FXAA on the final image.", "Picture",
    choices=[("none", "None"), ("fxaa", "FXAA"), ("fxaa_extreme", "FXAA extreme")], restart=True)
add("present_letterbox", "Letterbox other aspect ratios", "Display", "bool", True,
    "Keep 16:9 with black bars instead of stretching.", "Picture")
add("present_cas_additional_sharpness", "CAS extra sharpness", "Display", "float", 0.0,
    "0 to 1, for the CAS filter.", "Picture", lo=0, hi=1, step=0.05)
add("present_dither", "Output dithering", "Display", "bool", False,
    "Dither the final image to hide banding.", "Picture", restart=True)
add("native_2x_msaa", "Native 2x MSAA implementation", "Display", "bool", True,
    "Implement guest-requested 2x targets using native GPU multisampling. This does not force MSAA or choose the game's sample count.", "Picture")
if IS_WINDOWS:
    add("gpu_backend", "Graphics API", "Display", "choice", "vulkan",
        "Vulkan includes this project's fixes and is recommended; Direct3D 12 is the SDK's own and "
        "flickers on some NVIDIA cards (greenish reflections, issue #46).", "Picture",
        choices=[("vulkan", "Vulkan"), ("d3d12", "Direct3D 12")], platform="windows",
        restart=True)

# --- Controls --------------------------------------------------------------------------
add("mnk_mode", "Keyboard and mouse", "Controls", "bool", False,
    "Keys stand in for a controller (the bindings below).", "Keyboard")
add("mnk_mouse", "Mouse moves the right stick", "Controls", "bool", False,
    "Look around (and aim the photo mode camera) with the mouse; the pointer is captured "
    "while the game has focus. Off: the right stick comes from its keys only.", "Keyboard")
add("mnk_sensitivity", "Mouse sensitivity", "Controls", "float", 1.0,
    "1.0 turns the right stick halfway at 1000 pixels a second.", "Keyboard",
    lo=0.01, hi=10, step=0.1)
add("mnk_stick_ramp", "Steering ramp (seconds)", "Controls", "float", 0.2,
    "How long a held key takes to push the left stick (steering) from its first "
    "deflection to full lock; letting go takes half as long. 0 is all or nothing.",
    "Keyboard", lo=0, hi=2, step=0.05)
add("mnk_passthrough", "Raw keyboard to the game", "Controls", "bool", False,
    "For titles that read a USB keyboard. Not needed for Forza.", "Keyboard")
add("vibration", "Controller vibration", "Controls", "bool", True, "", "Controller")
add("guide_button", "Guide button pass-through", "Controls", "bool", False, "", "Controller")
add("left_stick_deadzone_percentage", "Left stick deadzone", "Controls", "float", 0.0,
    "Fraction of the stick's range, 0 to 1.", "Controller", lo=0, hi=1, step=0.01)
add("right_stick_deadzone_percentage", "Right stick deadzone", "Controls", "float", 0.0,
    "Fraction of the stick's range, 0 to 1.", "Controller", lo=0, hi=1, step=0.01)
add("input_backend", "Input backend", "Controls", "choice", "sdl",
    "SDL works with any pad; XInput is Windows only.", "Controller",
    choices=[("sdl", "SDL"), ("xinput", "XInput")])
add("hid_mappings_file", "Controller mapping file", "Controls", "str", "gamecontrollerdb.txt",
    "SDL game controller mappings.", "Controller")

# Racing wheels (patch 0074): an SDL joystick that is a wheel is presented as the Xbox 360 Wireless
# Racing Wheel. SDL backend only.
add("wheel_mode", "Racing wheel", "Controls", "choice", "auto",
    "Auto: a controller SDL reports as a wheel (or named like one) is used as the 360 racing "
    "wheel. On: every controller without a gamepad mapping counts as a wheel.", "Racing wheel",
    choices=[("auto", "Auto"), ("on", "On"), ("off", "Off")], restart=True)
add("wheel_rotation", "Wheel rotation (degrees)", "Controls", "int", 900,
    "Lock to lock, as set in the wheel's own driver.", "Racing wheel", lo=90, hi=2520, step=10)
add("wheel_lock", "Steering lock (degrees)", "Controls", "int", 900,
    "Wheel travel, lock to lock, that gives the game's full steering. Below the rotation makes "
    "the steering quicker.", "Racing wheel", lo=90, hi=2520, step=10)
add("wheel_deadzone", "Steering deadzone", "Controls", "float", 0.0,
    "Fraction of the wheel's range, 0 to 0.5.", "Racing wheel", lo=0, hi=0.5, step=0.01)
add("wheel_invert_steering", "Invert steering", "Controls", "bool", False, "", "Racing wheel")
add("wheel_pedals", "Pedals", "Controls", "choice", "auto",
    "Combined: one axis, throttle one way and brake the other (G25 style).", "Racing wheel",
    choices=[("auto", "Separate (detected)"), ("separate", "Separate"), ("combined", "Combined")])
add("wheel_invert_throttle", "Invert throttle", "Controls", "bool", False,
    "Turn on when the throttle works backwards.", "Racing wheel")
add("wheel_invert_brake", "Invert brake", "Controls", "bool", False,
    "Turn on when the brake works backwards.", "Racing wheel")
add("wheel_throttle_curve", "Throttle curve", "Controls", "float", 1.0,
    "A gamma: 1 is linear, above 1 is softer at the start.", "Racing wheel",
    lo=0.2, hi=4, step=0.1)
add("wheel_brake_curve", "Brake curve", "Controls", "float", 1.0,
    "A gamma: 1 is linear, above 1 is softer at the start.", "Racing wheel",
    lo=0.2, hi=4, step=0.1)
add("wheel_axes", "Axis numbers", "Controls", "str", "",
    "Overrides, e.g. steer=0,throttle=2,brake=5,clutch=1. Empty detects them from where each "
    "axis rests when the wheel is plugged in (pedals released).", "Racing wheel")
add("wheel_buttons", "Button numbers", "Controls", "str", "",
    "Overrides, e.g. a=0,b=1,x=2,y=3,lb=5,rb=4,back=8,start=9,ls=11,rs=10,up=12,down=13,"
    "left=14,right=15. The d-pad hat is used as is.", "Racing wheel")
add("wheel_ffb", "Force feedback", "Controls", "bool", True,
    "Approximate: a centring spring and a vibration taken from the game's rumble motors. "
    "Untested on real wheels.", "Racing wheel", restart=True)
add("wheel_ffb_strength", "Force feedback strength (%)", "Controls", "int", 60,
    "0 to 100.", "Racing wheel", lo=0, hi=100, step=5)

KEYBINDS = [
    ("a", "A", "Semicolon,Space"), ("b", "B", "Quote,Backspace"), ("x", "X", "L"),
    ("y", "Y", "P"), ("left_trigger", "Left trigger", "Q,I"),
    ("right_trigger", "Right trigger", "E,O"), ("left_shoulder", "Left shoulder", "1"),
    ("right_shoulder", "Right shoulder", "3"), ("lstick_up", "Left stick up", "W"),
    ("lstick_down", "Left stick down", "S"), ("lstick_left", "Left stick left", "A"),
    ("lstick_right", "Left stick right", "D"), ("lstick_press", "Left stick press", "F"),
    ("rstick_up", "Right stick up", "Up"), ("rstick_down", "Right stick down", "Down"),
    ("rstick_left", "Right stick left", "Left"), ("rstick_right", "Right stick right", "Right"),
    ("rstick_press", "Right stick press", "K"), ("dpad_up", "D-pad up", "Shift+Up"),
    ("dpad_down", "D-pad down", "Shift+Down"), ("dpad_left", "D-pad left", "Shift+Left"),
    ("dpad_right", "D-pad right", "Shift+Right"), ("back", "Back", "Z,Tab"),
    ("start", "Start", "X,Return"), ("guide", "Guide", ""),
]
for _k, _label, _default in KEYBINDS:
    add("keybind_" + _k, _label, "Controls", "keys", _default,
        "Key names (A, Space, Return, Up, Semicolon, F5, Numpad1, LMB for the left mouse "
        "button, ...), comma separated for alternatives, Shift+Up for a combination.",
        "Keyboard bindings (used when keyboard and mouse is on)")

# --- Audio -----------------------------------------------------------------------------
add("audio_mute", "Mute", "Audio", "bool", False, "", "Output")
add("audio_maxqframes", "Audio buffer (frames)", "Audio", "int", 8,
    "4 to 64. Lower is less delay but may crackle.", "Output", lo=4, hi=64)

# --- Online ----------------------------------------------------------------------------
add("live_signin", "Sign in to Xbox LIVE", "Online", "bool", True,
    "Through the Forza Live server: friends and LIVE lobbies.", "Forza Live")
add("live_room", "Room", "Online", "str", "",
    "Only players in the same room on the server see each other. Empty is the default room.",
    "Forza Live")
add("live_accept_invites", "Show game invites", "Online", "bool", True,
    "Another player's invite asks you: hold Back + A (or Enter) to join. Off ignores them.",
    "Forza Live")
add("live_friends_key", "Friends screen key", "Online", "str", "F8",
    "Opens the friends screen (a controller: hold the left stick press).", "Forza Live")
add("live_chat_key", "Chat key", "Online", "str", "F9",
    "Opens the chat (a controller: the friends screen's Chat tab).", "Forza Live")
add("world_drop_in", "Horizon World drop-in", "Online", "bool", True,
    "The Horizon World playlist is a shared free roam that players jump into.",
    "Horizon World")
add("world_events", "Horizon World events", "Online", "bool", True,
    "The world's host takes the events the server starts.", "Horizon World")
add("world_challenges", "Head-to-head challenges", "Online", "bool", True,
    "Challenge another player's car in the world.", "Horizon World")
add("world_event_wait_seconds", "Event lobby wait (s)", "Online", "int", 30,
    "How long the wait lobby before an event lasts.", "Horizon World", lo=0, hi=600)
add("world_event_cpu_with_peers", "AI drivers in multi-player world events", "Online", "bool",
    True, "Only the Horizon World events the server starts; playlist and custom races have no AI "
    "drivers, as on the Xbox 360. Off: only a solo event gets them.", "Horizon World")
add("world_event_cpu_ready", "Do not wait for AI after events", "Online", "bool", True,
    "The results screen returns to the lobby without waiting for them.", "Horizon World")
add("world_event_ai_grid", "AI difficulty grid size (test)", "Online", "int", 0,
    "Test knob: 0 uses the event's grid.", "Horizon World", lo=0, hi=16)

# --- Profile ---------------------------------------------------------------------------
add("gamertag", "Gamertag", "Profile", "str", "",
    "Up to 15 characters. Empty uses the one kept in live_identity.txt (your login name).",
    "Identity")
add("user_language", "Language ID", "Profile", "int", 1,
    "Xbox language code: 1 English, 2 Japanese, 3 German, 4 French, 5 Spanish, 6 Italian, "
    "7 Korean, 8 Chinese (Traditional), 9 Portuguese, 10 Chinese (Simplified), 11 Polish, 12 Russian.",
    "Identity", lo=0, hi=20)
add("user_country", "Country ID", "Profile", "int", 103, "Xbox country code.", "Identity",
    lo=0, hi=300)
add("license_mask", "DLC license mask", "Profile", "int", 0,
    "Licence mask for activated content.", "Identity", lo=0, hi=2147483647)

# --- Advanced --------------------------------------------------------------------------
add("log_level", "Log level", "Advanced", "choice", "info", "", "Log",
    choices=_c("trace", "debug", "info", "warn", "error", "critical", "off"))
add("log_noisy", "Noisy logging", "Advanced", "bool", False,
    "High-frequency log messages.", "Log")
add("log_flush_interval", "Log flush interval (s)", "Advanced", "int", 0,
    "0 flushes at exit only.", "Log", lo=0, hi=60, restart=True)
add("vulkan_device", "Vulkan device", "Advanced", "int", -1,
    "-1 picks the best GPU. Use another index on multi-GPU systems.", "GPU", lo=-1, hi=16,
    restart=True)
add("vulkan_allow_present_mode_immediate", "Allow tearing present mode", "Advanced", "bool",
    False, "No vsync wait. Spins the GPU; leave off.", "GPU")
add("vulkan_allow_present_mode_mailbox", "Allow mailbox present mode", "Advanced", "bool",
    False, "Triple buffering.", "GPU")
add("vulkan_allow_present_mode_fifo_relaxed", "Allow relaxed FIFO", "Advanced", "bool", False,
    "", "GPU")
add("vulkan_allow_present_mode_fifo_latest_ready", "Use FIFO latest ready", "Advanced", "bool",
    True, "Vsync that shows the newest finished frame when the game draws slower than the "
    "refresh rate, if the driver offers it. Off: plain FIFO.", "GPU")
add("store_shaders", "Keep a shader cache", "Advanced", "bool", True,
    "Fewer stutters the second time you play.", "GPU")
add("async_shader_compilation", "Compile shaders in the background", "Advanced", "bool", True,
    "", "GPU")
add("present_safe_area_x", "Safe area width %", "Advanced", "int", 90, "", "GPU",
    lo=0, hi=100)
add("present_safe_area_y", "Safe area height %", "Advanced", "int", 90, "", "GPU",
    lo=0, hi=100)
add("video_mode_width", "Guest video width", "Advanced", "int", 1280,
    "Overridden by the resolution preset.", "GPU", lo=640, hi=4095, restart=True)
add("video_mode_height", "Guest video height", "Advanced", "int", 720,
    "Overridden by the resolution preset.", "GPU", lo=480, hi=4095, restart=True)

BY_KEY = {s.key: s for s in S}


def for_group(group):
    return [s for s in S if s.group == group and s.applies()]


def defaults():
    return {s.key: s.default for s in S}


def coerce(setting, value):
    """Make a value (from JSON, TOML or a widget) fit the setting's type, or the default."""
    try:
        if setting.kind == "bool":
            return bool(value)
        if setting.kind in ("int", "fps"):
            v = int(float(value))
            if setting.kind == "fps":
                return 30 if v < 60 else min(v, 240)
            lo = -(10 ** 9) if setting.lo is None else int(setting.lo)
            hi = 10 ** 9 if setting.hi is None else int(setting.hi)
            return max(lo, min(hi, v))
        if setting.kind == "float":
            v = float(value)
            lo = -1e9 if setting.lo is None else setting.lo
            hi = 1e9 if setting.hi is None else setting.hi
            return max(lo, min(hi, v))
        if setting.kind == "choice" and setting.choices:
            value = setting.legacy.get(value, value)
            values = [c[0] for c in setting.choices]
            if value in values:
                return value
            for c in values:
                if str(c) == str(value):
                    return c
            return setting.default
        return str(value)
    except (TypeError, ValueError):
        return setting.default
