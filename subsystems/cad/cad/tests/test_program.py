"""读快捷方式时不弹出窗口。"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cad.program import _shortcut_target, metric_template


class ProgramTests(unittest.TestCase):
    def test_shortcut_is_read_without_a_console_window(self) -> None:
        with patch("cad.program.subprocess.run") as run:
            run.return_value.stdout = b"D:\\Program Files\\Autodesk\\AutoCAD 2020\\acad.exe"
            with patch.object(Path, "is_file", return_value=True):
                target = _shortcut_target(Path(r"C:\Users\Public\Desktop\AutoCAD 2020.lnk"))
        self.assertEqual(target, Path(r"D:\Program Files\Autodesk\AutoCAD 2020\acad.exe"))
        self.assertEqual(run.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)

    def test_metric_template_comes_from_the_language_folder(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            program = root / "acad.exe"
            program.write_bytes(b"")
            template = root / "UserDataCache" / "zh-cn" / "Template" / "acadiso.dwt"
            template.parent.mkdir(parents=True)
            template.write_bytes(b"dwt")
            self.assertEqual(metric_template(program), template)
