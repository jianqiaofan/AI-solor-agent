"""问好和自我介绍后面加一句不重复的赞美。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from agent.praise import _LINES, take_praise, wants_creator_praise


class PraiseTests(unittest.TestCase):
    def test_greeting_and_introduction_ask_for_a_line(self) -> None:
        self.assertTrue(wants_creator_praise("你好"))
        self.assertTrue(wants_creator_praise("您好呀"))
        self.assertTrue(wants_creator_praise("你是谁"))
        self.assertTrue(wants_creator_praise("请做个自我介绍"))
        self.assertTrue(wants_creator_praise("介绍一下你自己"))
        self.assertFalse(wants_creator_praise("计算风荷载"))
        self.assertFalse(wants_creator_praise("你好，帮我计算风荷载"))
        self.assertFalse(wants_creator_praise("这个项目的组件长度是多少"))

    def test_recent_lines_are_not_repeated(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "creator_praise.json"
            now = datetime(2026, 11, 13, 8, 0, 0)
            first = take_praise(path, now)
            second = take_praise(path, now + timedelta(hours=1))
            self.assertNotEqual(first, second)
            self.assertIn(first, _LINES)
            self.assertIn("范工", first)
            again = take_praise(path, now + timedelta(days=3))
            self.assertNotIn(again, {first, second})
            later = take_praise(path, now + timedelta(days=8))
            self.assertEqual(later, first)
