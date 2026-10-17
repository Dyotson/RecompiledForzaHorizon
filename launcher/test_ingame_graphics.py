import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from forza_launcher import ingame, schema
from forza_launcher.config import Config


class InGameGraphicsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = Config(self.root / "launcher.json")
        self.cfg.advanced["data_root"] = str(self.root)
        self.pending = self.root / ingame.FILENAME

    def request(self, **values):
        self.pending.write_text(json.dumps({"version": 1, "settings": values}))

    def test_native_output_and_filtering_are_imported_and_persisted(self):
        self.cfg.settings["present_effect"] = "fsr3"
        self.request(output="1440p", upscaler="off", resolution_scale="2",
                     frame_rate="120", vsync="true", anisotropic_override="5",
                     forza_hud_edges="false")
        self.assertTrue(ingame.import_pending(self.cfg, lambda _: None))
        self.assertFalse(self.pending.exists())
        saved = Config(self.cfg.path)
        self.assertEqual(saved.settings["resolution"], "1440p")
        self.assertEqual(saved.settings["resolution_scale"], 2)
        self.assertEqual(saved.settings["frame_rate"], 120)
        self.assertEqual(saved.settings["present_effect"], "bilinear")
        self.assertEqual(saved.settings["anisotropic_override"], 5)
        self.assertFalse(saved.settings["forza_hud_edges"])

    @unittest.skipUnless("fh1_upscaler" in schema.BY_KEY, "Windows NVIDIA setting")
    def test_dlss_choice_preserves_native_output_setting(self):
        self.request(output="1440p", upscaler="quality")
        self.assertTrue(ingame.import_pending(self.cfg, lambda _: None))
        self.assertEqual(self.cfg.settings["fh1_upscaler"], "quality")
        self.assertEqual(self.cfg.settings["fh1_output_resolution"], "1440p")

    def test_fsr3_turns_off_nvidia_and_sets_the_matching_mode(self):
        self.request(output="4k", upscaler="fsr3_balanced")
        self.assertTrue(ingame.import_pending(self.cfg, lambda _: None))
        self.assertEqual(self.cfg.settings["present_effect"], "fsr3")
        self.assertEqual(self.cfg.settings["fsr3_mode"], "balanced")
        self.assertEqual(self.cfg.settings["fsr3_output_resolution"], "4k")
        if "fh1_upscaler" in schema.BY_KEY:
            self.assertEqual(self.cfg.settings["fh1_upscaler"], "off")

    def test_invalid_request_does_not_partially_apply(self):
        previous = dict(self.cfg.settings)
        for values in [{"frame_rate": "120", "output": "12k"},
                       {"frame_rate": "360"}, {"resolution_scale": "0"},
                       {"vsync": "maybe"}, {"upscaler": "dlss5"},
                       {"extra_args": "--unknown=true"}]:
            with self.subTest(values=values):
                self.request(**values)
                self.assertFalse(ingame.import_pending(self.cfg, lambda _: None))
                self.assertEqual(self.cfg.settings, previous)
                self.assertTrue(self.pending.exists())

    def test_failed_config_save_keeps_the_request_for_retry(self):
        previous = dict(self.cfg.settings)
        self.request(frame_rate="120")
        with patch.object(self.cfg, "save", side_effect=OSError("read only")):
            self.assertFalse(ingame.import_pending(self.cfg, lambda _: None))
        self.assertEqual(self.cfg.settings, previous)
        self.assertTrue(self.pending.exists())
        self.assertTrue(ingame.import_pending(self.cfg, lambda _: None))

    def test_non_string_values_and_boolean_version_are_rejected(self):
        previous = dict(self.cfg.settings)
        for document in [{"version": True, "settings": {"frame_rate": "120"}},
                         {"version": 1, "settings": {"output": []}},
                         {"version": 1, "settings": {"vsync": True}}]:
            with self.subTest(document=document):
                self.pending.write_text(json.dumps(document))
                self.assertFalse(ingame.import_pending(self.cfg, lambda _: None))
                self.assertEqual(self.cfg.settings, previous)

    def test_starting_launcher_imports_settings_before_showing_them(self):
        self.cfg.save()
        self.request(frame_rate="144")
        reloaded = Config(self.cfg.path)
        self.assertEqual(reloaded.settings["frame_rate"], 144)
        self.assertFalse(self.pending.exists())

    def test_unrelated_settings_and_profile_are_preserved(self):
        self.cfg.online["mode"] = "offline"
        self.cfg.settings["async_shader_compilation"] = False
        self.request(frame_rate="90")
        ingame.import_pending(self.cfg, lambda _: None)
        self.assertEqual(self.cfg.online["mode"], "offline")
        self.assertFalse(self.cfg.settings["async_shader_compilation"])


if __name__ == "__main__":
    unittest.main()
