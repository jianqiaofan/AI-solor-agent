"""读快捷方式时不弹出窗口，启动 SAP2000 后不等待它退出。"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from sap2000.program import _shortcut_target, start_sap2000


class ProgramTests(unittest.TestCase):
    def test_shortcut_is_read_without_a_console_window(self) -> None:
        with patch("sap2000.program.subprocess.run") as run:
            run.return_value.stdout = r"E:\Program Files\Computers and Structures\SAP2000 26\SAP2000.exe"
            with patch.object(Path, "is_file", return_value=True):
                target = _shortcut_target(Path(r"C:\Users\Public\Desktop\SAP2000 26.lnk"))
        self.assertEqual(target, Path(r"E:\Program Files\Computers and Structures\SAP2000 26\SAP2000.exe"))
        self.assertEqual(run.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)

    def test_sap_is_started_and_not_waited_on(self) -> None:
        with patch("sap2000.program.subprocess.Popen") as popen:
            start_sap2000(Path(r"E:\Program Files\Computers and Structures\SAP2000 26\SAP2000.exe"))
        args = popen.call_args.args[0]
        flags = popen.call_args.kwargs["creationflags"]
        self.assertEqual(args, [r"E:\Program Files\Computers and Structures\SAP2000 26\SAP2000.exe"])
        self.assertEqual(flags & subprocess.DETACHED_PROCESS, subprocess.DETACHED_PROCESS)
        self.assertFalse(popen.return_value.wait.called)
