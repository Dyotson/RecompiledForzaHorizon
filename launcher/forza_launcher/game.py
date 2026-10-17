"""Finding the game binary and starting it the way tools/play.sh and play.bat do."""
import glob
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import TITLE_ID, cleanenv, gpu, paths, dlss, fsr3
from .config import Config, render_toml, write_toml

EXE = "forza.exe" if paths.IS_WINDOWS else "forza"
LOCAL_PROFILE = "B13EBABEBABEBABE"  # the runtime's own profile folder
LOCAL_SERVER = "127.0.0.1:21200"
LOCAL_HTTP_PORT = 21201


# --- locating the game ----------------------------------------------------------------

@dataclass
class GameInstall:
    dir: Path
    exe: Path
    lib_dirs: list = field(default_factory=list)  # added to LD_LIBRARY_PATH (Linux)
    source: str = ""


def _sdk_lib_dirs():
    """The SDK libraries of a source build, like play.sh (REXSDK, patched overlay, nightly)."""
    home = Path.home()
    for c in (os.environ.get("REXSDK"),
              home / "rexglue-sdk-patched-forza/0.10.0.24/linux-amd64",
              home / "rexglue-sdk-patched/0.10.0.24/linux-amd64",
              home / "rexglue-sdk-nightly/0.10.0.24/linux-amd64"):
        if c and (Path(c) / "lib").is_dir():
            return [Path(c) / "lib"]
    return []


def candidate_dirs(cfg: Config):
    override = cfg.advanced.get("game_dir", "").strip() or os.environ.get("FORZA_GAME_DIR", "")
    if override:
        yield Path(override), "set in Advanced settings", False
    from . import builder
    yield builder.runtime_dir(cfg.data_home()), "built by the launcher", False
    if paths.in_checkout() and not paths.IS_WINDOWS:  # development: this checkout's own build
        build = os.environ.get("FORZA_BUILD", "linux")
        yield paths.REPO_ROOT / "forza-recomp/out/build" / build, "the build in this checkout", True


def find_game(cfg: Config):
    """Returns (GameInstall | None, [places looked in])."""
    looked = []
    for d, why, needs_sdk in candidate_dirs(cfg):
        looked.append(f"{d} ({why})")
        exe = d / EXE
        if exe.is_file():
            return GameInstall(d, exe, _sdk_lib_dirs() if needs_sdk else [], why), looked
    return None, looked


def missing_message(looked):
    return ("The game has not been built on this computer yet. Open Setup and press Build.\n"
            "Looked in:\n  " + "\n  ".join(looked))


def game_version(game: GameInstall | None) -> str:
    """The build the package was made from: version.txt, else 'Built from commit X' in README.txt."""
    if game is None:
        return "not installed"
    for name in ("version.txt", "README.txt"):
        try:
            text = (game.dir / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if name == "version.txt" and text.strip():
            return text.strip().splitlines()[0]
        m = re.search(r"Built from commit (\w+)", text)
        if m:
            return "build " + m.group(1)
    if paths.in_checkout():
        try:
            out = subprocess.run(["git", "-C", str(paths.REPO_ROOT), "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True, timeout=5,
                                 env=cleanenv.clean_environment())
            if out.returncode == 0 and out.stdout.strip():
                return "source build " + out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return "unknown build"


def installed_dlc(cfg: Config) -> int:
    d = cfg.data_home() / "0000000000000000" / TITLE_ID / "00000002"
    try:
        return sum(1 for p in d.iterdir() if p.is_dir())
    except OSError:
        return 0


# --- the Forza Live server --------------------------------------------------------------

def server_script(game: GameInstall | None) -> Path | None:
    for d in ((game.dir,) if game else ()) + (paths.app_dir(), paths.REPO_ROOT):
        p = d / "server" / "forza_live_server.py"
        if p.is_file():
            return p
    return None


def server_listening(port=LOCAL_HTTP_PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def server_command(script: Path, data_dir: Path):
    args = ["--host", "127.0.0.1", "--port", LOCAL_SERVER.split(":")[1],
            "--http-port", str(LOCAL_HTTP_PORT), "--data-dir", str(data_dir)]
    if paths.FROZEN:  # run the server inside this executable (no Python needed)
        return [sys.executable, "--live-server", str(script)] + args
    return [sys.executable, str(script)] + args


# --- the Xenia save -----------------------------------------------------------------------

def default_xenia_content() -> Path:
    return Path(os.environ.get("FORZA_XENIA_CONTENT") or Path.home() / "xenia_canary_windows" / "content")


def xenia_candidates(content: Path):
    """XUIDs of Xenia profiles with a Forza Horizon save."""
    out = []
    for d in sorted(glob.glob(str(content / "*" / TITLE_ID / "00000001"))):
        xuid = Path(d).parent.parent.name
        if xuid != "0000000000000000":
            out.append(xuid)
    return out


def _link_dir(link: Path, target: Path):
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except OSError:
        pass
    if paths.IS_WINDOWS:  # a junction needs no privilege
        try:
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                           capture_output=True, creationflags=0x08000000)
        except (OSError, subprocess.SubprocessError):
            pass


def prepare_xenia(cfg: Config, refresh=False, log=print):
    """Copies the Xenia save (once; again with refresh) and returns (root, xuid)."""
    content = Path(cfg.profile.get("xenia_content") or default_xenia_content())
    xuid = cfg.profile.get("xenia_xuid", "").strip().upper()
    if not xuid:
        cands = xenia_candidates(content)
        if len(cands) != 1:
            raise RuntimeError(f"Found {len(cands)} Xenia profiles with a Forza Horizon save in "
                               f"{content}; choose one under Settings > Profile.")
        xuid = cands[0]
    if not re.fullmatch(r"[0-9A-F]{16}", xuid):
        raise RuntimeError("The Xenia XUID must be 16 hex digits.")
    src = content / xuid / TITLE_ID
    if not src.is_dir():
        raise RuntimeError(f"No Forza Horizon save at {src}")
    home = cfg.data_home()
    root = home / f"xenia-{xuid}"
    dest = root / LOCAL_PROFILE / TITLE_ID
    if refresh or not dest.is_dir():
        shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        log(f"Copied the Xenia save of {xuid} to {dest}")
    # Installed DLC lives with the normal profile; share it.
    share_dlc(home, root, log)
    return root, xuid


def _is_link(p: Path) -> bool:
    return os.path.islink(p) or bool(getattr(os.path, "isjunction", lambda _p: False)(p))


def _same_dir(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _remove_link(p: Path):
    try:
        os.unlink(p)
    except OSError:
        os.rmdir(p)      # a Windows junction or directory symlink


def _mirror(src: Path, dst: Path) -> int:
    """Makes `dst` hold every file of `src` (hard links where the disk allows, else copies); files
    already there with the same size are kept. Returns the number of files added."""
    n = 0
    for dirpath, _dirs, files in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        for f in files:
            s, d = Path(dirpath) / f, dst / rel / f
            if d.is_file() and d.stat().st_size == s.stat().st_size:
                continue
            d.parent.mkdir(parents=True, exist_ok=True)
            if d.exists():
                d.unlink()
            try:
                os.link(s, d)
            except OSError:
                shutil.copy2(s, d)
            n += 1
    return n


def share_dlc(home: Path, root: Path, log=print) -> str:
    """Makes the DLC installed in `home` (home/0000000000000000) visible to a game started on the user
    data root `root` (a Xenia save's copy): a link (Linux), a symbolic link or junction (Windows) at
    root/0000000000000000. Repairs a link that points elsewhere (a folder that moved) or a real folder
    left in its place (its packages are first copied to `home`, then it is renamed, never deleted).
    When no link can be made, mirrors the packages with hard links. Returns "linked" or "mirrored"."""
    from . import datafolder
    target = home / "0000000000000000"
    target.mkdir(parents=True, exist_ok=True)
    link = root / "0000000000000000"
    if _same_dir(link, target):
        return "linked"
    how = Path("..") / "0000000000000000" if not paths.IS_WINDOWS else target
    if os.path.lexists(link) and _is_link(link):
        log(f"{link} pointed to another folder; linking it to {target}")
        _remove_link(link)
    backup = None
    if os.path.lexists(link):
        # A real folder: keep its packages, then move it aside.
        datafolder.carry_dlc(root, home, log)
        backup = link.with_name("0000000000000000.old")
        i = 1
        while os.path.lexists(backup):
            backup, i = link.with_name(f"0000000000000000.old{i}"), i + 1
        os.rename(link, backup)
    _link_dir(link, how)
    if _same_dir(link, target):
        if backup is not None:
            log(f"moved the folder {link} aside to {backup} and linked {link} to {target}")
        return "linked"
    if os.path.lexists(link) and _is_link(link):
        _remove_link(link)
    if backup is not None and not os.path.lexists(link):
        os.rename(backup, link)
    n = _mirror(target, link)
    log(f"could not link {link} to {target}: mirrored the DLC there instead ({n} files)")
    return "mirrored"


# --- the launch plan -------------------------------------------------------------------------

@dataclass
class LaunchPlan:
    game: GameInstall
    cwd: Path
    argv: list
    env: dict            # variables to set
    unset: list          # variables to remove
    toml_path: Path
    toml_text: str
    server_argv: list | None = None   # a local Forza Live server to start (when not running)
    notes: list = field(default_factory=list)
    log_dir: Path | None = None
    dlss_status_file: Path | None = None

    def command_line(self) -> str:
        return " ".join(shlex.quote(a) for a in self.argv)


def split_args(text: str):
    text = text.strip()
    if not text:
        return []
    if paths.IS_WINDOWS:
        return [a.strip('"') for a in shlex.split(text, posix=False)]
    return shlex.split(text)


def parse_env(text: str):
    env = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def content_warnings(cfg: Config, game: GameInstall, home: Path, root: Path, extra_update=False,
                     check_dlc=True) -> list:
    """What the player set up but the game will not find: Title Update 4 chosen but this build has
    no update (the base game starts: no Horizon Rally, no 1000 Club), or DLC installed or chosen but
    none in the user data folder the game is started on (Horizon Rally then says "Xbox LIVE
    Marketplace error"; issues #65, #70), or DLC there without the Rally Expansion Pack (the same
    error, #79)."""
    from . import datafolder
    out = []
    if cfg["tu_package"].strip() and not extra_update and not (game.dir / "update").is_dir():
        out.append(f"Title Update 4 is chosen in Setup, but this build has none ({game.dir / 'update'} is "
                   "missing): the game starts without Horizon Rally and the 1000 Club. Open Setup and press "
                   "Rebuild.")
    if not check_dlc:
        return out
    seen = datafolder.dlc_packages(root)
    installed = datafolder.dlc_packages(home)
    if not seen and (installed or cfg["dlc_dir"].strip()):
        where = f"{root / datafolder.DLC_DIR / '00000002'}"
        out.append(f"No DLC in the game's folder ({where})" +
                   (f", though {len(installed)} package(s) are installed in {home}" if installed else "") +
                   ": the game starts without its DLC cars, and Horizon Rally says \"Xbox LIVE Marketplace "
                   "error\". Open Setup and install the DLC again (step 2).")
    elif seen:
        bare = datafolder.dlc_without_header(root)
        if bare:
            out.append(f"{len(bare)} DLC package(s) have no header in {root / datafolder.DLC_DIR / 'Headers'} "
                       f"({', '.join(bare[:3])}{' ...' if len(bare) > 3 else ''}): install the DLC again in Setup.")
        has_update = extra_update or (game.dir / "update").is_dir()
        if has_update and "1600" not in datafolder.dlc_offers(root):
            out.append(f"The Rally Expansion Pack is not among the {len(seen)} DLC package(s) in "
                       f"{root / datafolder.DLC_DIR / '00000002'}: Horizon Rally says \"Xbox LIVE Marketplace "
                       "error\" (issue #79). Open Setup and install the DLC again (step 2) with the Rally "
                       "Expansion Pack.")
    return out


def gpu_vendor_arg(cfg: Config, extra_args=()) -> str:
    """--gpu_vendor=nvidia|amd|intel for the graphics card chosen in Settings (#89): a laptop with an
    Intel iGPU and a GeForce otherwise started on the Intel one (Vulkan 1.2, old driver, device lost).
    Nothing when the choice is "Other" or the Steam Deck (one GPU) or the player set it themselves
    (extra flags, other settings, or a device index, which wins in the game anyway); the game then
    prefers a discrete GPU over an integrated one."""
    vendor = cfg.gpu_vendor()
    if vendor not in gpu.SDK_VENDORS:
        return ""
    mine = ("gpu_vendor", "vulkan_device", "d3d12_adapter")
    if int(cfg.settings.get("vulkan_device", -1)) >= 0:
        return ""
    for a in extra_args:
        if a.lstrip("-").split("=", 1)[0] in mine:
            return ""
    for line in cfg.advanced.get("extras_toml", "").splitlines():
        if line.split("=", 1)[0].strip() in mine:
            return ""
    return f"--gpu_vendor={gpu.SDK_VENDORS[vendor]}"


def build_plan(cfg: Config, game: GameInstall, write=True, refresh_xenia=False, log=print) -> LaunchPlan:
    from . import ingame
    if write:
        ingame.import_pending(cfg, log)
    home = cfg.data_home()
    data = cfg.game_files()
    toml_path = game.dir / "forza.toml"
    toml_text = write_toml(cfg, toml_path) if write else render_toml(cfg)

    args = [f"--game_data_root={data}"]
    notes = []
    env, unset = {}, []
    env["FORZA_GRAPHICS_SETTINGS"] = str(home / ingame.FILENAME)

    # The profile: your own, or a copy of your Xenia Canary save (play.sh --xenia).
    log_file = home / "forza.log"
    if write and paths.IS_WINDOWS:
        # DLC an older launcher (or the game, started without --user_data_root) installed in
        # Documents\forza while the launcher's folder has none (issues #65, #70).
        from . import datafolder
        if not datafolder.dlc_packages(home):
            try:
                datafolder.carry_dlc(datafolder.game_default_data_home(), home, log)
            except OSError as e:
                log(f"could not copy the DLC from {datafolder.game_default_data_home()}: {e}")
    root = home
    if cfg.profile["mode"] == "xenia":
        if write:
            root, xuid = prepare_xenia(cfg, refresh_xenia, log)
        else:  # a preview: no copy
            xuid = cfg.profile.get("xenia_xuid", "").strip().upper()
            if not xuid:
                found = xenia_candidates(Path(cfg.profile.get("xenia_content") or default_xenia_content()))
                xuid = found[0] if len(found) == 1 else "<XUID>"
            root = home / f"xenia-{xuid}"
        args += [f"--user_data_root={root}", f"--cache_root={home / 'cache'}",
                 f"--profile_xuid={xuid}"]
    elif cfg.advanced.get("data_root", "").strip() or paths.IS_WINDOWS:
        # Windows: the game's own default is Documents\forza, not the launcher's folder
        # (%LOCALAPPDATA%\ForzaReImagined): name it, or saves, DLC and the shader cache go there.
        root = home
        if write and paths.IS_WINDOWS:
            from . import datafolder
            old = datafolder.game_default_data_home()
            try:
                datafolder.carry_game_written_data(old, home, LOCAL_PROFILE, log)
            except OSError as e:
                # The saves could not be copied: play on them where they are, try again next time.
                log(f"could not copy the saves from {old} to {home} ({e}); starting the game on {old}")
                notes.append(f"Your saves are still in {old}: they could not be copied to {home} ({e}).")
                root = old
        args.append(f"--user_data_root={root}")

    # Xbox LIVE: public/custom through the server named in forza.toml (and FORZA_SERVER, which
    # outranks it); local starts a Forza Live server on this PC; offline uses none.
    server_argv = None
    mode = cfg.online["mode"]
    if mode in ("public", "custom") and cfg.server_spec():
        env["FORZA_SERVER"] = cfg.server_spec()
    elif mode == "local":
        script = server_script(game)
        if script is None:
            notes.append("The Forza Live server files were not found: starting offline.")
            unset.append("FORZA_SERVER")
        else:
            env["FORZA_SERVER"] = LOCAL_SERVER
            if not server_listening():
                server_argv = server_command(script, home / "live_server")
    else:
        if mode == "custom":
            notes.append("No custom server address set: starting offline.")
        unset.append("FORZA_SERVER")

    extra_update = any(a.startswith("--update_data_root") for a in split_args(cfg.advanced.get("extra_args", "")))
    if (game.dir / "update").is_dir() and not extra_update:
        args.append(f"--update_data_root={game.dir / 'update'}")  # the title update's files
    notes += content_warnings(cfg, game, home, root, extra_update, check_dlc=write or root.exists())
    if cfg.advanced.get("pad_per_user"):
        env["FORZA_PAD_PER_USER"] = "1"

    if write and dlss.enabled(cfg):
        dlss.check_renderer(game.dir)
    dlss.configure(cfg, env, args, notes, write)
    dlss_status_file = Path(env["FORZA_DLSS_STATUS_FILE"]) if "FORZA_DLSS_STATUS_FILE" in env else None
    fsr3.configure(cfg, args, notes)
    ingame.configure_runtime(cfg, env, args, write=write)

    extra = split_args(cfg.advanced.get("extra_args", ""))
    vendor_arg = gpu_vendor_arg(cfg, extra)
    if vendor_arg:
        args.append(vendor_arg)
    if not any(a == "--log_file" or a.startswith("--log_file=") for a in extra):
        args.append(f"--log_file={log_file}")
    args += extra
    env.update(parse_env(cfg.advanced.get("extra_env", "")))

    if not paths.IS_WINDOWS:
        # play.sh: LD_LIBRARY_PATH="$SDK/lib:$BUILD" for a source build, "$DIR" for a package.
        libs = [str(p) for p in game.lib_dirs] + [str(game.dir)]
        # the player's own path, not the frozen launcher's _internal (#87)
        user_libs = cleanenv.clean_environment().get("LD_LIBRARY_PATH")
        if user_libs:
            libs.append(user_libs)
        env["LD_LIBRARY_PATH"] = ":".join(libs)
    return LaunchPlan(game, game.dir, [str(game.exe)] + args, env, unset, toml_path,
                      toml_text, server_argv, notes, home, dlss_status_file)


def log_path_of(plan: "LaunchPlan"):
    for a in (plan.argv if plan is not None else ()):
        if str(a).startswith("--log_file="):
            return Path(str(a).split("=", 1)[1])
    return None


# Log lines at error level that the game writes in normal play (missing sound banks, audio frames the
# decoder does not like, XAM/XLIVEBASE calls the runtime has no answer for): never the reason a game
# stopped, so "Last errors" skips them (#98).
HARMLESS_ERRORS = (
    "ffmpeg:",
    "Unimplemented XLIVEBASE message",
    "Unimplemented XAM message",
    "ResolvePath(",
    "device not found",
    "[NtCreateFile] FAILED",
    "STUB",
)

# Log lines the game writes when it closes by itself, after the player closed the window or chose to quit.
CLEAN_CLOSE_MARKERS = ("Title terminated; hard-exiting process", "Execution complete")


def _log_tail(plan: "LaunchPlan", lines=200):
    log = log_path_of(plan)
    try:
        if log is not None and log.is_file():
            with open(log, "r", encoding="utf-8", errors="replace") as f:
                return f.readlines()[-lines:]
    except OSError:
        pass
    return []


def last_errors(tail, count=3):
    """The last `count` error lines of a log tail that are not among the harmless ones."""
    out = [ln.strip() for ln in tail
           if ("[error]" in ln or "[critical]" in ln or "[fatal]" in ln)
           and not any(h in ln for h in HARMLESS_ERRORS)]
    return out[-count:]


def closed_cleanly(plan: "LaunchPlan") -> bool:
    """Did the game end its log the way a normal close does (the last lines say it shut down)?"""
    tail = [ln for ln in _log_tail(plan, 12) if ln.strip()]
    return any(m in ln for ln in tail[-4:] for m in CLEAN_CLOSE_MARKERS)


def exit_is_crash(plan: "LaunchPlan", code, stopped=False) -> bool:
    """Should the launcher show the "game stopped" box for this exit? Not for 0, not when the player
    stopped the game from the launcher (Windows then reports 1, Linux -15), not for the player
    ending it from outside (Ctrl+C, kill: -2, -15), and not when the log ends with the game's own
    shutdown lines. 75 is the relaunch request and is handled before."""
    if code in (0, None):
        return False
    if stopped:
        return False
    if not paths.IS_WINDOWS and code in (-2, -15):
        return False
    return not closed_cleanly(plan)


def crash_reason(plan: "LaunchPlan", code) -> str:
    """A readable text for a game that stopped early: its exit code, the last error lines of its
    log and, for the usual causes, what to do."""
    log = log_path_of(plan)
    errors = last_errors(_log_tail(plan))
    text = f"The game stopped (exit code {code})."
    joined = " ".join(errors)
    if "Vulkan" in joined:
        text += (" It needs a graphics card with Vulkan support and an up-to-date graphics driver; none was "
                 "found (a virtual machine or a remote desktop session usually has none).")
    elif "memory" in joined.lower() or "alloc" in joined.lower():
        text += " It may have run out of memory: close other programs and try again."
    if errors:
        text += "\nLast errors in the log:\n" + "\n".join(errors)
    text += f"\nLog: {log}" if log is not None else "\nOpen the log folder: forza.log has the details."
    return text


# The game exits with this code when it restarts itself (accepting an invite in free roam,
# src/kernel/xam_loader.cpp) and FORZA_LAUNCHER_RELAUNCH is set: start it again.
RELAUNCH_EXIT_CODE = 75
# A game that keeps exiting with that code (a bug, not an invite each time) is not started
# again more than this many times within this many seconds: the exit then counts as a stop.
RELAUNCH_LIMIT = 4
RELAUNCH_WINDOW = 60.0


def request_window_close(pid: int) -> int:
    """Windows: ask the game's windows to close, as the close button does (WM_CLOSE), so it shuts down
    and writes its log. Returns how many windows were asked. (Python's terminate() is TerminateProcess:
    exit code 1, nothing flushed.)"""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    asked = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
            asked.append(hwnd)
        return True

    user32.EnumWindows(each, 0)
    return len(asked)


# How long the game gets to close after the window was asked to, before it is ended.
STOP_GRACE_SECONDS = 10.0


class Session:
    """A running game, and the local Forza Live server started for it."""

    def __init__(self, plan: LaunchPlan, log=print):
        self.plan = plan
        self.server = None
        self.proc = None
        self.log = log
        self.relaunches = []   # monotonic times of the restarts (RELAUNCH_LIMIT within RELAUNCH_WINDOW)
        self.stop_requested = False   # the player stopped it from the launcher: its exit code is no crash
        self.stop_deadline = None

    def start(self):
        plan = self.plan
        if plan.log_dir:
            plan.log_dir.mkdir(parents=True, exist_ok=True)
        flags = 0x08000000 if paths.IS_WINDOWS else 0  # CREATE_NO_WINDOW for the server
        if plan.server_argv:
            data_dir = Path(plan.server_argv[plan.server_argv.index("--data-dir") + 1])
            data_dir.mkdir(parents=True, exist_ok=True)
            self.server_log = open(data_dir / "server.log", "ab")
            self.server = subprocess.Popen(plan.server_argv, stdout=self.server_log,
                                           stderr=subprocess.STDOUT, creationflags=flags,
                                           stdin=subprocess.DEVNULL, env=cleanenv.clean_environment())
            self.log("Started a local Forza Live server")
        self._start_game({})

    def _start_game(self, extra):
        plan = self.plan
        env = cleanenv.clean_environment()
        for k in plan.unset:
            env.pop(k, None)
        env.update(plan.env)
        env["FORZA_LAUNCHER_RELAUNCH"] = "1"
        env.update(extra)
        self.proc = subprocess.Popen(plan.argv, cwd=plan.cwd, env=env, stdin=subprocess.DEVNULL)

    def relaunch(self):
        """The game asked to be started again (RELAUNCH_EXIT_CODE); the server keeps running.
        Returns False, starting nothing, when it asked too often."""
        now = time.monotonic()
        self.relaunches = [t for t in self.relaunches if now - t < RELAUNCH_WINDOW]
        if len(self.relaunches) >= RELAUNCH_LIMIT:
            self.log("The game keeps restarting itself; not starting it again")
            return False
        self.relaunches.append(now)
        self.log("The game restarts itself")
        self._start_game({"FORZA_RELAUNCHED": "1"})
        return True

    def poll(self):
        if self.proc is None:
            return None
        code = self.proc.poll()
        if code is None and self.stop_deadline is not None and time.monotonic() > self.stop_deadline:
            self.stop_deadline = None
            self.log("The game did not close by itself; ending it")
            self.proc.terminate()
        return code

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.stop_requested = True
            if paths.IS_WINDOWS:
                try:
                    if request_window_close(self.proc.pid):
                        self.stop_deadline = time.monotonic() + STOP_GRACE_SECONDS
                        return
                except (OSError, AttributeError, ValueError) as e:
                    paths.log_error("ask the game to close", e)
            self.proc.terminate()

    def cleanup(self):
        """After the game ends: stop our server and free guest memory left in /dev/shm."""
        if self.server and self.server.poll() is None:
            self.server.terminate()
        dlss.cleanup_status(self.plan)
        if not paths.IS_WINDOWS:
            clean_shm()


def clean_shm():
    """Guest memory (/dev/shm/xenia_memory_*, 5 GB) is not unlinked when the game is killed."""
    for shm in glob.glob("/dev/shm/xenia_memory_*"):
        try:
            if os.stat(shm).st_uid != os.getuid():
                continue
            name = os.path.basename(shm)
            in_use = False
            for maps in glob.glob("/proc/[0-9]*/maps"):
                try:
                    with open(maps, "r", errors="replace") as f:
                        if name in f.read():
                            in_use = True
                            break
                except OSError:
                    continue
            if not in_use:
                os.unlink(shm)
        except OSError:
            continue
