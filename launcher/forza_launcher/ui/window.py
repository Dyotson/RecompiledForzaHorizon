"""The main window: a sidebar and the Play, Setup, Settings and About pages."""
import sys
import threading

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__, builder, cleanenv, game, paths, dlss
from ..config import Config, import_toml, render_toml
from . import theme
from .pages import AboutPage, PlayPage, SetupPage
from .settings_page import SettingsPage


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        if not cfg.gpu.get("vendor") and not cfg.gpu.get("checked"):
            cfg.detect_gpu()   # once: preselects the GPU's choice in Settings > Display (#52)
            try:
                cfg.save()
            except OSError:
                pass
        self.session = None
        self.session_plan = None
        self._dlss_session_status = None
        self._busy = False
        self._dlss_task = None
        self._dlss_prepared = None
        self._dlss_result = (False, "")
        self._close_after_dlss = False
        self.setWindowTitle(APP_NAME)
        icon = paths.asset("logo.png")
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1040, 760)
        self.setMinimumSize(900, 620)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(210)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 22, 0, 16)
        sl.setSpacing(2)
        brand = QHBoxLayout()
        brand.setContentsMargins(18, 0, 12, 14)
        logo = QLabel()
        pm = QPixmap(str(paths.asset("logo.png")))
        if not pm.isNull():
            logo.setPixmap(pm.scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        a = QLabel("Forza Horizon 1")
        a.setObjectName("brand")
        b = QLabel("ReImagined")
        b.setObjectName("brandSub")
        col.addWidget(a)
        col.addWidget(b)
        brand.addLayout(col)
        sl.addLayout(brand)

        self.stack = QStackedWidget()
        self.play = PlayPage(cfg, self)
        self.setup = SetupPage(cfg, self)
        self.settings = SettingsPage(cfg, self)
        self.about = AboutPage(cfg, self)
        self.navs = QButtonGroup(self)
        for i, (name, page) in enumerate((("Play", self.play), ("Setup", self.setup),
                                          ("Settings", self.settings), ("About", self.about))):
            btn = QPushButton(name)
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            self.navs.addButton(btn, i)
            sl.addWidget(btn)
            self.stack.addWidget(page)
        self.navs.idClicked.connect(self.show_page)
        sl.addStretch(1)
        self.version = QLabel(f"Launcher {__version__}")
        self.version.setObjectName("version")
        self.version.setContentsMargins(20, 0, 10, 0)
        self.version.setWordWrap(True)
        self.update_notice = QPushButton("Update available")
        self.update_notice.setObjectName("link")
        self.update_notice.setStyleSheet("margin-left: 20px; margin-right: 10px;")
        self.update_notice.hide()
        self.update_notice.clicked.connect(lambda: self.show_page(3))
        self.about.updates.available.connect(lambda tag: self.update_notice.setVisible(bool(tag)))
        sl.addWidget(self.update_notice)
        sl.addWidget(self.version)
        h.addWidget(side)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(28, 24, 20, 8)
        bl.addWidget(self.stack, 1)
        self.footer = QLabel("")
        self.footer.setObjectName("muted")
        bl.addWidget(self.footer)
        h.addWidget(body, 1)

        self.play.goto_setup.connect(lambda: self.show_page(1))
        self.play.play_requested.connect(self.start_game)
        self.setup.changed.connect(self.refresh_all)
        self.settings.changed.connect(self.play.refresh)
        self.poll = QTimer(self)
        self.poll.setInterval(500)
        self.poll.timeout.connect(self._poll)
        self._first_run()
        self.show_page(0)
        self.refresh_all()
        if sys.platform == "win32":
            QTimer.singleShot(600, self.setup.offer_move)
        update_result = self.show_update_result()
        if not paths.in_checkout() and cfg.d["check_updates"] and not update_result:
            QTimer.singleShot(1500, self.about.updates.check)

    def show_update_result(self):
        from .. import linux_update
        result = linux_update.consume_result()
        if result:
            self.about.updates.message.setText(result.partition(": ")[2] or result)
            self.show_page(3)
        return bool(result)

    # ---- navigation -------------------------------------------------------------------
    def show_page(self, i):
        self.stack.setCurrentIndex(i)
        self.navs.button(i).setChecked(True)
        if i == 0:
            self.play.refresh()
        elif i == 1:
            self.setup.refresh()
        elif i == 3:
            self.about.refresh()
        self.footer.setText("")

    def refresh_all(self):
        self.play.refresh()
        self.about.refresh()
        install, _ = game.find_game(self.cfg)
        self.version.setText(f"Launcher {__version__}\nGame: {game.game_version(install)}")
        self.write_toml()

    def status(self, text, error=False):
        self.footer.setText(text)
        self.footer.setStyleSheet(f"color: {theme.ERR if error else theme.MUTED};")

    def set_busy(self, busy):
        self._busy = busy

    def closeEvent(self, e):
        if self.about.updates.busy():
            if self.about.updates.installing:
                self.status("Installing the update. The launcher will restart when it's ready…")
                e.ignore()
                return
            self.about.updates.closing = True
            self.about.updates.cancel_task()
            self.status("Stopping the update request before closing…")
            e.ignore()
            return
        if self._dlss_task is not None and self._dlss_task.isRunning():
            self._close_after_dlss = True
            self._dlss_task.cancel()
            self.status("Cancelling the DLSS download…")
            e.ignore()
            return
        if self.setup.busy():
            if QMessageBox.question(self, "Quit", "A task is still running. Stop it and quit? "
                                    "A build resumes where it stopped.") != QMessageBox.Yes:
                e.ignore()
                return
            self.setup.task.cancel()
            self.setup.task.wait(15000)
        # Installation flushed settings before handing off. Avoid writing the old config
        # over migrations made by a newly started Flatpak launcher.
        if not self.about.updates.restarting:
            self.settings.flush()
        self.stop_game()
        super().closeEvent(e)

    # ---- first run ---------------------------------------------------------------------
    def _first_run(self):
        if self.cfg.loaded:
            return
        install, _ = game.find_game(self.cfg)
        toml = install.dir / "forza.toml" if install else None
        if toml and toml.is_file():
            try:
                import_toml(self.cfg, toml.read_text(encoding="utf-8"))
            except OSError:
                pass
        try:
            self.cfg.save()
        except OSError:
            pass

    # ---- forza.toml ---------------------------------------------------------------------
    def write_toml(self):
        install, _ = game.find_game(self.cfg)
        if install is None:
            return
        try:
            from ..config import write_toml
            write_toml(self.cfg, install.dir / "forza.toml")
        except OSError as e:
            self.status(f"Could not write forza.toml in {install.dir}: {e}", True)

    def preview_text(self):
        install, looked = game.find_game(self.cfg)
        if install is None:
            return render_toml(self.cfg) + "\n# (the game is not built yet)"
        try:
            plan = game.build_plan(self.cfg, install, write=False)
        except Exception as e:
            return render_toml(self.cfg) + f"\n# {e}"
        lines = [f"# {plan.toml_path}", plan.toml_text.rstrip(), "", "# environment"]
        lines += [f"{k}={v}" for k, v in sorted(plan.env.items()) if k != "LD_LIBRARY_PATH"]
        lines += [f"unset {k}" for k in plan.unset]
        lines += ["", "# command", plan.command_line()]
        if plan.server_argv:
            lines += ["", "# local server", " ".join(plan.server_argv)]
        return "\n".join(lines)

    def reset_settings(self):
        if QMessageBox.question(self, "Reset settings", "Reset every setting on the Settings page to its default?") \
                != QMessageBox.Yes:
            return
        from .. import config, gpu, schema
        self.cfg.d["settings"] = {**schema.defaults(), **config.FIRST_RUN}
        gpu.apply_preset(self.cfg.settings, self.cfg.gpu_vendor())
        self.cfg.d["online"] = {"mode": "public", "custom_server": ""}
        self.cfg.d["profile"] = {"mode": "own", "xenia_content": "", "xenia_xuid": ""}
        for k in ("extra_args", "extra_env", "extras_toml"):
            self.cfg.advanced[k] = ""
        self.settings.rebuild()
        self.settings.flush()

    # ---- playing -----------------------------------------------------------------------
    def running(self):
        return self.session is not None and self.session.poll() is None

    def start_game(self):
        if self.running() or self._dlss_task is not None:
            return
        install, looked = game.find_game(self.cfg)
        if install is None:
            self.play.show_message(game.missing_message(looked), True)
            return
        ok, msg = __import__("forza_launcher.installer", fromlist=["x"]).check_game_folder(self.cfg.game_files())
        if not ok:
            self.play.show_message(msg, True)
            return
        self.settings.flush()
        preparation = (self.cfg.data_home(), install.dir, self.cfg.settings.get("fh1_upscaler"))
        if (dlss.enabled(self.cfg) or dlss.menu_runtime_enabled(self.cfg)) and self._dlss_prepared != preparation:
            self._prepare_dlss(install.dir)
            return
        self._dlss_prepared = None
        try:
            plan = game.build_plan(self.cfg, install, write=True, log=lambda t: self.status(t))
            session = game.Session(plan)
            session.start()
        except (RuntimeError, OSError) as e:
            paths.log_error("start the game", e)
            self.play.show_message(f"Could not start the game: {e}\nLog: {paths.launcher_log()}", True, keep=True)
            return
        self.session = session
        self.session_plan = plan
        self._dlss_session_status = None
        self.play.clear_message()
        if plan.notes:   # what the player set up but the game will not find (TU4, DLC): keep it in view
            self.play.show_message("The game is running. " + " ".join(plan.notes), True, keep=True)
        else:
            self.play.show_message("The game is running.")
        self.poll.start()
        self.play.refresh()

    def _prepare_dlss(self, renderer_folder=None):
        from .workers import Task
        from types import SimpleNamespace
        from ..installer import InstallError
        from ..fetch import Cancelled

        # Settings remain editable while the worker runs. Pin this download to
        # the data folder selected when Play was pressed.
        home = self.cfg.data_home()
        vendor = self.cfg.gpu_vendor()
        # prepare() checks the graphics card too (#107): pin it with the folder.
        download_cfg = SimpleNamespace(data_home=lambda: home, gpu_vendor=lambda: vendor)

        preparation = (home, renderer_folder, self.cfg.settings.get("fh1_upscaler"))

        def run(task):
            try:
                if renderer_folder is not None:
                    dlss.check_renderer(renderer_folder)
                dlss.prepare(download_cfg,
                             lambda done, total: task.progress.emit(done / total if total else 0,
                                                                   "Downloading NVIDIA DLSS"),
                             task.cancelled)
                if task.cancelled():
                    raise Cancelled()
            except (OSError, RuntimeError) as error:
                raise InstallError(str(error)) from error
            return "NVIDIA DLSS is ready."

        task = Task(run, "set up NVIDIA DLSS")
        self._dlss_task = task
        self._dlss_preparing = preparation
        self._dlss_result = (False, "DLSS setup did not finish.")
        self.play.play.setEnabled(False)
        self.play.show_message("Checking NVIDIA DLSS. First use downloads about 56 MB.")
        task.progress.connect(lambda fraction, _detail: self.status(
            f"Downloading NVIDIA DLSS… {fraction:.0%}"))
        task.done.connect(self._dlss_download_done)
        task.finished.connect(self._dlss_download_finished)
        task.start()
        self.play.refresh()

    def _dlss_download_done(self, ok, message):
        self._dlss_result = (ok, message)

    def _dlss_download_finished(self):
        task, self._dlss_task = self._dlss_task, None
        task.deleteLater()
        self.play.play.setEnabled(True)
        self.play.refresh()
        if self._close_after_dlss:
            self.close()
            return
        ok, message = self._dlss_result
        self.status(message, not ok)
        if ok:
            self._dlss_prepared = self._dlss_preparing
            self.start_game()
        else:
            if not dlss.enabled(self.cfg) and dlss.menu_runtime_enabled(self.cfg):
                # DLSS is optional in a native session. A failed download must
                # not prevent playing offline with native rendering.
                self._dlss_prepared = self._dlss_preparing
                self.start_game()
                self.play.show_message(f"Native rendering is available. Could not set up NVIDIA DLSS: {message}",
                                       True, keep=True)
            else:
                self._dlss_prepared = None
                self.play.show_message(f"Could not set up NVIDIA DLSS: {message}", True, keep=True)

    def stop_game(self):
        if self._dlss_task is not None:
            self._dlss_task.cancel()
            self.status("Cancelling the DLSS download…")
            return
        if self.session is not None:
            self.session.stop()

    def _poll(self):
        if self.session is None:
            self.poll.stop()
            return
        code = self.session.poll()
        if code is None:
            status = dlss.session_status(self.session_plan)
            if status and status != self._dlss_session_status:
                self._dlss_session_status = status
                error, message = status
                self.play.show_message(message, error, keep=error)
            return
        if code == game.RELAUNCH_EXIT_CODE:
            try:
                if self.session.relaunch():
                    return
            except OSError as e:
                paths.log_error("start the game again", e)
        self.poll.stop()
        stopped = getattr(self.session, "stop_requested", False) is True
        self.session.cleanup()
        self.session = None
        plan = self.session_plan
        self.play.clear_message()
        if not game.exit_is_crash(plan, code, stopped):
            self.play.show_message("The game closed.")
        else:
            self.play.show_message(game.crash_reason(plan, code), True, keep=True)
        self.play.refresh()


def run(argv):
    cleanenv.restore_process_environment()   # programs Qt starts (xdg-open) must not inherit _internal
    from PySide6.QtCore import Qt as _Qt
    QApplication.setHighDpiScaleFactorRoundingPolicy(_Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([sys.argv[0]] + argv)
    app.setApplicationName("forza-reimagined-launcher")
    app.setDesktopFileName(paths.FLATPAK_ID or "forza-reimagined")
    if paths.IN_FLATPAK:
        # The portal's file chooser hands out /run/user/.../doc paths for the one file picked, so a
        # Games on Demand package would lose its <name>.data folder. The Flatpak is given read access
        # to the home folder and removable media instead, and the Qt dialog shows the real paths.
        app.setAttribute(_Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    app.setStyleSheet(theme.QSS)

    def report(exc_type, exc, tb):
        """Any exception that reaches the top (a slot, a thread): log it and say so, never vanish."""
        exc.__traceback__ = tb
        log = paths.log_error(f"unhandled {exc_type.__name__}", exc)
        if threading.current_thread() is not threading.main_thread():
            return   # a dialog must come from the GUI thread; the task wrappers report their own failures
        try:
            QMessageBox.critical(None, "Unexpected error", f"{exc_type.__name__}: {exc}\n\nDetails: {log}")
        except Exception:
            pass
    sys.excepthook = report
    threading.excepthook = lambda a: report(a.exc_type, a.exc_value, a.exc_traceback)
    win = MainWindow(Config())
    win.show()
    return app.exec()
