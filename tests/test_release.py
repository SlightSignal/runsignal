"""Archive-layout regression; simulates Windows paths, not a Windows OS run."""
from contextlib import redirect_stdout
import io
from pathlib import Path, PureWindowsPath
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from runsignal import __version__


class ReleaseTests(unittest.TestCase):
    def test_windows_relative_paths_produce_a_portable_runnable_zipapp(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="runsignal-release-test-") as temporary:
            copied = Path(temporary) / "source"
            (copied / "tools").mkdir(parents=True)
            (copied / "runsignal").mkdir()
            builder = copied / "tools" / "build_release.py"
            shutil.copyfile(source / "tools" / "build_release.py", builder)
            package_files = [file for file in (source / "runsignal").iterdir()
                             if file.is_file() and file.suffix in {".py", ".html"}]
            for file in package_files:
                shutil.copyfile(file, copied / "runsignal" / file.name)

            original_relative_to = Path.relative_to
            emulated_paths = []

            def windows_relative_to(path, *other, **options):
                relative = original_relative_to(path, *other, **options)
                windows_path = PureWindowsPath(relative)
                emulated_paths.append(windows_path)
                return windows_path

            # Keep ordinary local I/O, but make the real copied builder receive
            # Windows-style relative path objects at the archive-naming boundary.
            with patch.object(Path, "relative_to", windows_relative_to):
                with redirect_stdout(io.StringIO()):
                    runpy.run_path(str(builder), run_name="__main__")

            self.assertTrue(any("\\" in str(path) for path in emulated_paths))
            app = copied / "dist" / "runsignal.pyz"
            with zipfile.ZipFile(app) as archive:
                names = archive.namelist()
                self.assertEqual(set(names), {"__main__.py"} |
                                 {f"runsignal/{file.name}" for file in package_files})
                self.assertTrue(all("\\" not in name for name in names))
                self.assertIn("runsignal/report.html", names)
                self.assertIsNone(archive.testzip())

            # Isolated interpreter, outside the checkout: the archive must supply
            # its own package instead of succeeding via an import-path fallback.
            process = subprocess.run(
                [sys.executable, "-I", str(app), "--version"],
                cwd=temporary, capture_output=True, text=True, timeout=20, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout.strip(), __version__)


if __name__ == "__main__":
    unittest.main()
