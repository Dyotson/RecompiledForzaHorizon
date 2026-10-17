"""Tool discovery skips MSYS2/Cygwin programs on Windows (#100): python3 -m unittest launcher/test_tools_msys.py"""
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from forza_launcher import build_env as be   # noqa: E402


def fake(root, rel, name):
    d = Path(root, *rel.split("/"))
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text("#!/bin/sh\n")
    f.chmod(0o755)
    return str(d), str(f)


class MsysSkipped(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_reason_by_path(self):
        for p in (r"c:\devkitPro\msys2\usr\bin\cmake.EXE", r"C:\msys64\mingw64\bin\ninja.exe",
                  r"C:\tools\Cygwin64\bin\git.exe", "C:/cygwin/bin/clang.exe"):
            self.assertIsNotNone(be.msys_reason(p, windows=True), p)
        for p in (r"C:\Program Files\CMake\bin\cmake.exe", r"C:\Program Files\Git\cmd\git.exe",
                  r"C:\Users\x\AppData\Local\ForzaReImagined\toolchain\cmake-4.4.4\bin\cmake.exe"):
            self.assertIsNone(be.msys_reason(p, windows=True), p)

    def test_not_on_linux(self):
        self.assertIsNone(be.msys_reason("/home/x/msys64/bin/cmake", windows=False))

    def test_reason_by_version_text_and_runtime_dll(self):
        self.assertIn("MSYS", be.msys_reason(r"C:\x\bin\cmake.exe", True, "cmake (MSYS2) 3.30"))
        self.assertIsNone(be.msys_reason(r"C:\x\bin\cmake.exe", True, "cmake version 3.30"))
        d, exe = fake(self.tmp.name, "tools/bin", "cmake.exe")
        Path(d, "msys-2.0.dll").write_text("")
        self.assertIn("msys-2.0.dll", be.msys_reason(exe, True))

    def test_find_tool_skips_msys_and_logs(self):
        d1, bad = fake(self.tmp.name, "devkitPro/msys2/usr/bin", "cmake")
        d2, good = fake(self.tmp.name, "Program Files/CMake/bin", "cmake")
        notes = []
        path = os.pathsep.join([d1, d2])
        self.assertEqual(be.find_tool("cmake", notes, path=path, windows=True), good)
        self.assertEqual(len(notes), 1)
        self.assertIn(bad, notes[0])
        self.assertIn("msys2", notes[0])

    def test_find_tool_only_msys_gives_none(self):
        d1, _ = fake(self.tmp.name, "msys64/usr/bin", "ninja")
        notes = []
        self.assertIsNone(be.find_tool("ninja", notes, path=d1, windows=True))
        self.assertTrue(notes)

    def test_find_tool_version_text(self):
        d1, bad = fake(self.tmp.name, "odd/bin", "git")
        d2, good = fake(self.tmp.name, "Git/cmd", "git")
        probe = lambda exe: "git version 2 (msys)" if exe == bad else "git version 2"
        notes = []
        self.assertEqual(be.find_tool("git", notes, path=os.pathsep.join([d1, d2]), windows=True,
                                      version_probe=probe), good)
        self.assertIn("--version", notes[0])

    def test_linux_unchanged(self):
        d1, exe = fake(self.tmp.name, "msys2/usr/bin", "cmake")
        self.assertEqual(be.find_tool("cmake", path=d1, windows=False), exe)

    @unittest.mock.patch.object(os, "pathsep", ";")
    def test_native_path(self):
        path = os.pathsep.join([r"C:\Windows", r"c:\devkitPro\msys2\usr\bin", r"C:\Program Files\CMake\bin"])
        kept, dropped = be.native_path(path, windows=True)
        self.assertEqual(kept, os.pathsep.join([r"C:\Windows", r"C:\Program Files\CMake\bin"]))
        self.assertEqual(dropped, [r"c:\devkitPro\msys2\usr\bin"])
        self.assertEqual(be.native_path(path, windows=False), (path, []))

    def test_vs_bundled(self):
        v = be.VSInstall(self.tmp.name, (17, 14))
        d, exe = fake(self.tmp.name, "Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin", "cmake.exe")
        orig = sys.platform
        try:
            sys.platform = "win32"
            self.assertEqual(be.vs_bundled_tool("cmake", [v]), exe)
            self.assertIsNone(be.vs_bundled_tool("ninja", [v]))
        finally:
            sys.platform = orig



class NinjaVersion(unittest.TestCase):
    """#123: a ninja older than 1.10 (some Visual Studio bundles) is not used."""

    def pick(self, sys_ver, vs_ver):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        def version_of(cmd, rx):
            exe = cmd[0]
            if "vsninja" in exe:
                return vs_ver
            if "sysninja" in exe:
                return sys_ver
            return None
        def find(name, notes, version_probe=None):
            return "/x/sysninja" if name == "ninja" and sys_ver else None
        with unittest.mock.patch.object(be, "find_tool", side_effect=find), \
                unittest.mock.patch.object(be, "_version_of", side_effect=version_of), \
                unittest.mock.patch.object(be, "vs_bundled_tool", side_effect=lambda n: "/vs/vsninja" if n == "ninja" else None):
            return be._detect_tools(Path(tmp.name))

    def test_old_vs_ninja_is_skipped(self):
        t = self.pick(None, (1, 8))
        self.assertEqual(t.ninja, "")
        self.assertTrue(any(m.startswith("ninja") for m in t.missing))

    def test_new_vs_ninja_is_used(self):
        t = self.pick(None, (1, 12))
        self.assertEqual(t.ninja, "/vs/vsninja")

    def test_old_system_ninja_is_skipped(self):
        t = self.pick((1, 9), None)
        self.assertNotEqual(t.ninja, "/x/sysninja")

if __name__ == "__main__":
    unittest.main()
