import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path

from forza_launcher.config import Config
from forza_launcher import schema
try:
    from PySide6.QtWidgets import QApplication
    from forza_launcher.ui.settings_page import SettingsPage
except ImportError:
    QApplication = None


class WindowStub:
    def status(self, *args):
        pass

    def write_toml(self):
        pass

    def reset_settings(self):
        pass

    def preview_text(self):
        return ""


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
@unittest.skipUnless("fh1_upscaler" in schema.BY_KEY, "DLSS controls are Windows-only")
class VendorControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = Config(Path(self.temp.name) / "launcher.json")
        self.cfg.advanced["data_root"] = self.temp.name
        self.cfg.settings["fh1_upscaler"] = "quality"
        self.cfg.gpu["vendor"] = "nvidia"
        self.page = SettingsPage(self.cfg, WindowStub())
        self.addCleanup(self.page.deleteLater)
        self.addCleanup(self.page._save_timer.stop)

    def test_gpu_change_hides_dlss_and_releases_native_controls(self):
        for vendor in ("nvidia", "amd", "intel", "deck", "", "nvidia"):
            with self.subTest(vendor=vendor):
                self.cfg.gpu["vendor"] = vendor
                self.page._apply_dependencies()
                supported = vendor == "nvidia"
                for key in ("fh1_upscaler", "fh1_output_resolution"):
                    self.assertEqual(self.page.rows[key].isHidden(), not supported)
                for key in ("gpu_backend", "resolution", "resolution_scale", "present_effect"):
                    self.assertEqual(self.page.rows[key].control.isEnabled(), not supported)

    def test_separate_aa_disabled_while_upscaling_and_dlaa_vendor_gated(self):
        aa = self.page.rows["forza_antialiasing"].control
        self.assertFalse(aa.isEnabled())
        self.page.set_value("fh1_upscaler", "off")
        self.assertTrue(aa.isEnabled())
        self.cfg.gpu["vendor"] = "amd"
        self.page._apply_dependencies()
        self.assertFalse(aa.model().item(aa.findData("dlaa")).isEnabled())
        self.page.set_value("forza_antialiasing", "smaa")
        self.page.set_value("present_effect", "fsr3")
        self.assertEqual(self.cfg.settings["forza_antialiasing"], "game")
        self.assertFalse(aa.isEnabled())

    def test_stale_mode_does_not_change_native_settings_on_amd(self):
        self.cfg.gpu["vendor"] = "amd"
        self.cfg.settings.update(gpu_backend="d3d12", resolution="720p", resolution_scale=1)
        self.page.set_value("fh1_output_resolution", "4k")
        self.assertEqual(self.cfg.settings["gpu_backend"], "d3d12")
        self.assertEqual(self.cfg.settings["resolution"], "720p")
        self.assertEqual(self.cfg.settings["resolution_scale"], 1)

    def test_ultrawide_toggle_preserves_dlss_control_locks(self):
        for vendor in ("nvidia", "amd"):
            self.cfg.gpu["vendor"] = vendor
            for mode in ("off", "quality", "dlaa"):
                self.cfg.settings["fh1_upscaler"] = mode
                for ultrawide in (True, False, True, False):
                    with self.subTest(vendor=vendor, mode=mode, ultrawide=ultrawide):
                        self.page.set_value("forza_ultrawide", ultrawide)
                        active = vendor == "nvidia" and mode != "off"
                        for key in ("gpu_backend", "resolution_scale"):
                            self.assertEqual(self.page.rows[key].control.isEnabled(),
                                             not active and not ultrawide)
                        for key in ("resolution", "present_effect"):
                            self.assertEqual(self.page.rows[key].control.isEnabled(), not active)


if __name__ == "__main__":
    unittest.main()
