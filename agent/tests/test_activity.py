"""进度文字：思考、联网、以及真正调用的计算。"""

from __future__ import annotations

import asyncio
import unittest

from agent.activity import (
    LOADS_RUNNING,
    SAP_RUNNING,
    SNOW_RUNNING,
    WEB_LOOKUP,
    WIND_RUNNING,
    activity_for_tool,
    bind_activity,
    load_activity,
    report_activity,
    reset_activity,
    tool_names_from_chunk,
)
from agent.server import _drive


class ActivityTests(unittest.TestCase):
    def test_tool_names_pick_the_sentence(self) -> None:
        self.assertEqual(activity_for_tool("web_search"), WEB_LOOKUP)
        self.assertEqual(activity_for_tool("tavily_search"), WEB_LOOKUP)
        self.assertEqual(activity_for_tool("windEN1991"), WIND_RUNNING)
        self.assertEqual(activity_for_tool("snowASCE16"), SNOW_RUNNING)
        self.assertEqual(activity_for_tool("moduleDead"), LOADS_RUNNING)
        self.assertEqual(activity_for_tool("run_sap2000"), SAP_RUNNING)
        self.assertEqual(activity_for_tool("lookup_case"), "")
        self.assertEqual(load_activity(["windEN1991", "moduleDead"]), WIND_RUNNING)
        self.assertEqual(load_activity(["windEN1991", "snowEN1991"]), LOADS_RUNNING)

    def test_report_is_silent_until_someone_is_listening(self) -> None:
        report_activity(WEB_LOOKUP)
        notes: list[str] = []
        token = bind_activity(notes.append)
        try:
            report_activity(WEB_LOOKUP)
            report_activity("")
        finally:
            reset_activity(token)
        self.assertEqual(notes, [WEB_LOOKUP])

    def test_chunk_tool_name_is_read(self) -> None:
        chunk = type("Chunk", (), {"tool_call_chunks": [{"name": "web_search", "args": ""}], "tool_calls": []})()
        self.assertEqual(tool_names_from_chunk(chunk), ["web_search"])

    def test_drive_forwards_the_status_before_the_result(self) -> None:
        def work() -> str:
            report_activity(WEB_LOOKUP)
            return "done"

        async def run():
            sink: dict = {}
            seen: list[str] = []
            async for text in _drive(work, (), sink):
                seen.append(text)
            return seen, sink["result"]

        seen, result = asyncio.run(run())
        self.assertEqual(seen, [WEB_LOOKUP])
        self.assertEqual(result, "done")
