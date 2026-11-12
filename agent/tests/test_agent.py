"""对话存储和模型配置的本地检查。"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.chat import chunk_text, explain, resolve_model, rewrite_extraction_reply, to_messages
from agent.load_tools import run_load_tool, stream_with_load_tools
from agent.extract import ExtractionError, extract_project_materials
from agent.intent import (
    CAD,
    CHAT,
    DESIGN,
    EXTRACT,
    INQUIRE,
    LOADS,
    SAP,
    SNOW,
    UPDATE,
    WIND,
    classify_intent,
    parse_intent,
    resolve_project_inquiry,
)
from agent.load_check import (
    answer_load_request,
    answer_parameter_update,
    resolve_load_follow_up,
    resolve_parameter_edit,
)
from agent.settings import ConfigError, Settings, reload_env, require_settings
from agent.store import (
    ConversationNotFound,
    ProjectExists,
    MaterialError,
    ProjectNameError,
    ProjectNotFound,
    Store,
    title_from_text,
)


class TitleTests(unittest.TestCase):
    def test_short_title_keeps_one_line(self) -> None:
        self.assertEqual(title_from_text("  核对   风速  "), "核对 风速")

    def test_long_title_is_cut(self) -> None:
        text = "一二三四五六七八九十一二三四五六七八九十一二三四五"
        self.assertEqual(len(title_from_text(text)), 23)
        self.assertTrue(title_from_text(text).endswith("…"))


class StoreTests(unittest.TestCase):
    def test_turn_title_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "assistant.db")
            project = store.create_project("甲项目")
            first = store.start_turn(project["id"], None, "第一句话用来做标题")
            store.start_turn(project["id"], first["id"], "第二句不应该改标题")
            store.append_assistant(first["id"], "收到。")
            saved = store.get(first["id"])
            self.assertEqual(saved["title"], "第一句话用来做标题")
            self.assertEqual(saved["project_id"], project["id"])
            self.assertEqual([item["role"] for item in saved["messages"]], ["user", "user", "assistant"])
            self.assertEqual(store.list_summaries(project["id"])[0]["id"], first["id"])
            self.assertTrue(store.delete(first["id"]))
            self.assertIsNone(store.get(first["id"]))
            self.assertFalse(store.delete(first["id"]))

    def test_conversations_do_not_cross_projects(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "assistant.db")
            first = store.create_project("甲项目")
            second = store.create_project("乙项目")
            left = store.start_turn(first["id"], None, "只属于甲")
            store.start_turn(second["id"], None, "只属于乙")
            left_titles = [item["title"] for item in store.list_summaries(first["id"])]
            right_titles = [item["title"] for item in store.list_summaries(second["id"])]
            self.assertEqual(left_titles, ["只属于甲"])
            self.assertEqual(right_titles, ["只属于乙"])
            with self.assertRaises(ConversationNotFound):
                store.start_turn(second["id"], left["id"], "把甲的对话写进乙")
            materials = Path(folder) / "projects" / "甲项目" / "资料"
            self.assertTrue(materials.is_dir())
            self.assertTrue(store.delete_project(first["id"]))
            self.assertTrue(materials.is_dir())
            self.assertEqual(store.list_summaries(first["id"]), [])
            self.assertIsNone(store.get(left["id"]))
            self.assertEqual(store.list_summaries(second["id"])[0]["title"], "只属于乙")

    def test_project_name_rules(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "assistant.db")
            store.create_project("  甲项目  ")
            with self.assertRaises(ProjectExists):
                store.create_project("甲项目")
            with self.assertRaises(ProjectNameError):
                store.create_project("  ")
            with self.assertRaises(ProjectNameError):
                store.create_project("甲/乙")
            with self.assertRaises(ProjectNotFound):
                store.start_turn("a" * 12, None, "没有这个项目")
            with self.assertRaises(ProjectNameError):
                store.create_project("CON")

    def test_create_project_makes_separate_folders(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = Store(root / "assistant.db", projects_root=root / "projects")
            project = store.create_project("甲项目")
            self.assertEqual(project["path"], "projects/甲项目")
            self.assertTrue((root / "projects" / "甲项目" / "资料").is_dir())
            self.assertTrue((root / "projects" / "甲项目" / "成果").is_dir())

    def test_imports_json_and_keeps_it_after_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            created = "2026-11-11T00:00:00+00:00"
            (root / "conversations.json").write_text(
                json.dumps(
                    {
                        "projects": [
                            {
                                "id": "abc123abc123",
                                "name": "补目录",
                                "created_at": created,
                                "updated_at": created,
                            }
                        ],
                        "conversations": [
                            {
                                "id": "def456def456",
                                "project_id": "abc123abc123",
                                "title": "旧对话",
                                "created_at": created,
                                "updated_at": created,
                                "messages": [
                                    {"role": "user", "content": "还在", "created_at": created}
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            store = Store(root / "assistant.db", projects_root=root / "projects")
            listed = store.list_projects()
            self.assertEqual(listed[0]["name"], "补目录")
            self.assertEqual(listed[0]["path"], "projects/补目录")
            self.assertTrue((root / "projects" / "补目录" / "成果").is_dir())
            self.assertEqual(store.get("def456def456")["messages"][0]["content"], "还在")
            self.assertFalse((root / "conversations.json").exists())
            again = Store(root / "assistant.db", projects_root=root / "projects")
            self.assertEqual(again.list_projects()[0]["id"], "abc123abc123")
            self.assertEqual(again.get("def456def456")["title"], "旧对话")

    def test_workspace_lists_files_inside_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = Store(root / "assistant.db", projects_root=root / "projects")
            project = store.create_project("甲项目")
            results = root / "projects" / "甲项目" / "成果"
            (results / "说明.pdf").write_bytes(b"pdf")
            (results / "子目录").mkdir()
            (results / "子目录" / "计算书.docx").write_bytes(b"doc")
            (results / "~$说明.pdf").write_bytes(b"lock")
            listed = store.list_workspace(project["id"])
            files = listed["folders"][1]["files"]
            self.assertEqual(listed["folders"][0]["files"], [])
            self.assertEqual([item["name"] for item in files], ["子目录", "说明.pdf"])
            self.assertEqual(files[0]["children"][0]["name"], "计算书.docx")
            self.assertNotIn("/", files[0]["children"][0]["name"])
            (results / "SAP2000").mkdir()
            (results / "SAP2000" / "model.sdb").write_bytes(b"sdb")
            (results / "SAP2000" / "model.LOG").write_bytes(b"log")
            files = store.list_workspace(project["id"])["folders"][1]["files"]
            self.assertEqual([item["name"] for item in files], ["SAP2000", "子目录", "说明.pdf"])
            sap = next(item for item in files if item["name"] == "SAP2000")
            self.assertTrue(sap["directory"])
            self.assertEqual([item["name"] for item in sap["children"]], ["model.LOG", "model.sdb"])
            self.assertTrue(store.resolve_workspace_file(project["id"], sap["path"], allow_directory=True).is_dir())
            target = store.resolve_workspace_file(project["id"], "projects/甲项目/成果/说明.pdf")
            self.assertEqual(target.name, "说明.pdf")
            with self.assertRaises(FileNotFoundError):
                store.resolve_workspace_file(project["id"], "projects/甲项目/成果/../../别的/机密.txt")

    def test_delete_workspace_file_stays_inside_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = Store(root / "assistant.db", projects_root=root / "projects")
            project = store.create_project("甲项目")
            store.save_material(project["id"], "说明.pdf", b"pdf")
            results = root / "projects" / "甲项目" / "成果"
            (results / "计算书.docx").write_bytes(b"doc")
            outside = root / "projects" / "别的.txt"
            outside.write_text("留着", encoding="utf-8")
            materials = root / "projects" / "甲项目" / "资料" / "说明.pdf"
            store.delete_workspace_file(project["id"], "projects/甲项目/资料/说明.pdf")
            self.assertFalse(materials.exists())
            store.delete_workspace_file(project["id"], "projects/甲项目/成果/计算书.docx")
            self.assertFalse((results / "计算书.docx").exists())
            self.assertTrue(outside.exists())
            with self.assertRaises(FileNotFoundError):
                store.delete_workspace_file(project["id"], "projects/甲项目/成果/../../别的.txt")
            with self.assertRaises(FileNotFoundError):
                store.delete_workspace_file(project["id"], "projects/甲项目/成果")

    def test_save_material_writes_only_inside_materials(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = Store(root / "assistant.db", projects_root=root / "projects")
            project = store.create_project("甲项目")
            store.save_material(project["id"], r"..\成果\偷偷.txt", "只在资料".encode())
            materials = root / "projects" / "甲项目" / "资料"
            results = root / "projects" / "甲项目" / "成果"
            self.assertEqual((materials / "偷偷.txt").read_text(encoding="utf-8"), "只在资料")
            self.assertEqual(list(results.iterdir()), [])
            store.save_material(project["id"], "偷偷.txt", "新的".encode())
            self.assertEqual((materials / "偷偷.txt").read_text(encoding="utf-8"), "新的")
            names = [item["name"] for item in store.list_workspace(project["id"])["folders"][0]["files"]]
            self.assertEqual(names, ["偷偷.txt"])
            with self.assertRaises(MaterialError):
                store.save_material(project["id"], "CON.txt", b"no")
            with mock.patch("agent.store.MAX_MATERIAL_BYTES", 4):
                with self.assertRaises(MaterialError):
                    store.save_material(project["id"], "太大.txt", b"12345")

    def test_unknown_id(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "assistant.db")
            project = store.create_project("甲项目")
            with self.assertRaises(ConversationNotFound):
                store.start_turn(project["id"], "not-an-id", "你好")


class ExtractionIntentTests(unittest.TestCase):
    def test_parse_intent_reads_only_the_label(self) -> None:
        self.assertEqual(parse_intent('{"intent":"extract_design_parameters"}'), EXTRACT)
        self.assertEqual(
            parse_intent('```json\n{"intent":"extract_design_parameters"}\n```'),
            EXTRACT,
        )
        self.assertEqual(parse_intent('{"intent":"chat"}'), CHAT)
        self.assertEqual(parse_intent('{"intent":"calculate_wind"}'), WIND)
        self.assertEqual(parse_intent('{"intent":"calculate_snow"}'), SNOW)
        self.assertEqual(parse_intent('{"intent":"calculate_loads"}'), LOADS)
        self.assertEqual(parse_intent('{"intent":"update_parameters"}'), UPDATE)
        self.assertEqual(parse_intent('{"intent":"design_line_model"}'), DESIGN)
        self.assertEqual(parse_intent('{"intent":"run_sap2000"}'), SAP)
        self.assertEqual(parse_intent('{"intent":"draw_cad"}'), CAD)
        self.assertEqual(parse_intent('{"intent":"inquire_project"}'), INQUIRE)
        self.assertEqual(parse_intent("今天天气怎么样"), CHAT)
        self.assertEqual(parse_intent('{"intent":"other"}'), CHAT)

    def test_classify_intent_uses_the_model_label(self) -> None:
        settings = Settings(api_key="sk-test", base_url="https://api.deepseek.com", model="deepseek-flash")
        reply = type("M", (), {"content": '{"intent":"extract_design_parameters"}'})()
        model = mock.Mock()
        model.invoke.return_value = reply
        with mock.patch("agent.intent.build_model", return_value=model) as build:
            found = classify_intent(settings, "仔细阅读提交文件，找出设计指标")
        self.assertEqual(found, EXTRACT)
        sent = model.invoke.call_args.args[0]
        self.assertEqual(sent[-1].content, "仔细阅读提交文件，找出设计指标")
        self.assertEqual(build.call_args.kwargs["temperature"], 0)
        self.assertEqual(build.call_args.kwargs["max_tokens"], 80)

    def test_missing_sheet_does_not_write_a_case(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = Store(root / "assistant.db", projects_root=root / "projects")
            project = store.create_project("甲项目")
            with self.assertRaises(ExtractionError):
                extract_project_materials(store, project["id"])
            self.assertFalse((root / "projects" / "甲项目" / "成果" / "design_case.json").exists())

    def test_writes_design_case_into_results(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "projects"
            / "aaaaaaa"
            / "资料"
            / "Barabant Design Data Collection Sheet.pdf"
        )
        if not source.is_file():
            self.skipTest("没有可用的资料表")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = Store(root / "assistant.db", projects_root=root / "projects")
            project = store.create_project("甲项目")
            target = root / "projects" / "甲项目" / "资料" / source.name
            target.write_bytes(source.read_bytes())
            message, wrote = extract_project_materials(store, project["id"])
            output = root / "projects" / "甲项目" / "成果" / "design_case.json"
            self.assertTrue(wrote)
            self.assertTrue(output.is_file())
            case = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(case["schema_version"], "1.0.0")
            self.assertEqual(case["status"], "draft")
            self.assertEqual(case["project_id"], "甲项目")
            self.assertEqual(case["site"]["wind_speed"], 25.3)
            self.assertIn("projects/甲项目/成果/design_case.json", message)


class SettingsTests(unittest.TestCase):
    def test_missing_key(self) -> None:
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "  "}, clear=False):
            with self.assertRaises(ConfigError):
                require_settings()

    def test_reload_strips_quotes(self) -> None:
        keys = ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL")
        old = {key: os.environ.get(key) for key in keys}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text(
                'DEEPSEEK_API_KEY="sk-test"\nDEEPSEEK_MODEL=deepseek-v4-pro\n',
                encoding="utf-8",
            )
            try:
                reload_env(path)
                self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "sk-test")
                self.assertEqual(os.environ["DEEPSEEK_MODEL"], "deepseek-v4-pro")
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


class ChatTests(unittest.TestCase):
    def test_resolve_model_rejects_unknown(self) -> None:
        settings = Settings(api_key="sk-test", base_url="https://api.deepseek.com", model="deepseek-flash")
        self.assertEqual(resolve_model("deepseek-v4-pro", settings), "deepseek-v4-pro")
        self.assertEqual(resolve_model("other-model", settings), "deepseek-flash")

    def test_chunk_text(self) -> None:
        self.assertEqual(chunk_text(type("C", (), {"content": "你好"})()), "你好")
        chunk = type("C", (), {"content": [{"type": "text", "text": "甲"}, "乙"]})()
        self.assertEqual(chunk_text(chunk), "甲乙")

    def test_rewrite_extraction_reply_uses_the_case(self) -> None:
        settings = Settings(api_key="sk-test", base_url="https://api.deepseek.com", model="deepseek-flash")
        reply = type("M", (), {"content": "已经从资料表提取出草稿，风速是 25.3 m/s。"})()
        model = mock.Mock()
        model.invoke.return_value = reply
        with mock.patch("agent.chat.build_model", return_value=model) as build:
            text = rewrite_extraction_reply(
                settings,
                "仔细阅读提交文件，找出设计指标",
                "projects/甲项目/成果/design_case.json",
                '{"site":{"wind_speed":25.3}}',
            )
        self.assertIn("25.3", text)
        sent = model.invoke.call_args.args[0]
        self.assertIn("projects/甲项目/成果/design_case.json", sent[-1].content)
        self.assertIn('"wind_speed":25.3', sent[-1].content)
        self.assertEqual(build.call_args.kwargs["temperature"], 0.3)

    def test_to_messages_names_the_project_code_and_case(self) -> None:
        messages = to_messages(
            [{"role": "user", "content": "算一下雪荷载"}],
            "甲项目",
            design_case='{"site":{"design_code":"USA(ASCE7-16)","snow_load":1.5}}',
            load_tools=True,
        )
        text = messages[0].content
        self.assertIn("windASCE16", text)
        self.assertIn("USA(ASCE7-16)", text)
        self.assertIn("1.5", text)
        self.assertIn("甲项目", text)

    def test_project_question_includes_the_design_case(self) -> None:
        self.assertEqual(resolve_project_inquiry(CHAT, "这个项目的组件排布是怎样的"), INQUIRE)
        self.assertEqual(resolve_project_inquiry(CHAT, "桩的埋深是多少"), INQUIRE)
        self.assertEqual(resolve_project_inquiry(CHAT, "今天天气怎么样"), CHAT)
        self.assertEqual(resolve_project_inquiry(INQUIRE, "计算风荷载"), WIND)
        self.assertEqual(resolve_project_inquiry(DESIGN, "这个项目的组件排布"), DESIGN)
        plain = to_messages([{"role": "user", "content": "你好"}], "aaa")
        self.assertNotIn("arrangement_columns", plain[0].content)
        messages = to_messages(
            [{"role": "user", "content": "这个项目的组件排布和桩的埋深"}],
            "aaa",
            design_case='{"geometry":{"arrangement_columns":"11/22","pile_embedment_depth_mm":1500}}',
            project_facts=True,
        )
        text = messages[0].content
        self.assertIn("projects/aaa/成果/design_case.json", text)
        self.assertIn("11/22", text)
        self.assertIn("1500", text)
        self.assertNotIn("windASCE16", text)
        missing = to_messages(
            [{"role": "user", "content": "桩的埋深"}],
            "aaa",
            project_facts=True,
        )
        self.assertIn("还没有 projects/aaa/成果/design_case.json", missing[0].content)

    def test_load_tool_stays_on_the_project_code(self) -> None:
        blocked = run_load_tool(
            "windEN1991",
            {
                "wind_speed": 25,
                "wind_speed_unit": "m/s",
                "wind_speed_averaging": "10 min mean",
                "terrain_category": "II",
                "module_length_mm": 2000,
                "module_width_mm": 1000,
                "ground_clearance_mm": 2000,
            },
            "USA(ASCE7-16)",
        )
        self.assertIn("error", blocked)
        snow = run_load_tool(
            "snowASCE16",
            {"snow_load": 1.5, "snow_load_unit": "KN/m2", "risk_category": "I", "module_width_mm": 1303},
            "USA(ASCE7-16)",
        )
        self.assertEqual(snow["cases"][0]["value"], 0.9072)
        dead = run_load_tool(
            "moduleDead",
            {"module_weight_kg": 37.7, "module_length_mm": 2384, "module_width_mm": 1303},
            "Europe(Eurocode 1991-4)",
        )
        self.assertEqual(dead["cases"][0]["value"], 0.1190)

    def test_stream_calls_the_tool_before_answering(self) -> None:
        script = _ScriptedModel()

        async def run() -> str:
            with mock.patch("agent.chat.build_model", return_value=script):
                parts = [
                    piece
                    async for piece in stream_with_load_tools(
                        Settings(api_key="sk-test", base_url="https://api.deepseek.com", model="deepseek-flash"),
                        [{"role": "user"}],
                        _OpenRequest(),
                        design_code="USA(ASCE7-16)",
                        disable_thinking=True,
                    )
                ]
            return "".join(parts)

        text = asyncio.run(run())
        self.assertIn("0.9072", text)
        tool_messages = [
            message
            for message in script.seen[1]
            if message.__class__.__name__ == "ToolMessage"
        ]
        self.assertTrue(tool_messages)
        self.assertIn("0.9072", tool_messages[0].content)
        self.assertEqual(
            script.tool_names,
            ["windASCE16", "snowASCE16", "windEN1991", "snowEN1991", "moduleDead"],
        )

    def test_explain_hides_key(self) -> None:
        settings = Settings(api_key="sk-secret", base_url="https://api.deepseek.com", model="deepseek-flash")
        text = explain(RuntimeError("bad key sk-secret"), settings)
        self.assertNotIn("sk-secret", text)


class LoadCheckTests(unittest.TestCase):
    def test_euro_wind_asks_before_calling_when_the_case_is_incomplete(self) -> None:
        answer, wrote = answer_load_request(
            WIND,
            json.dumps(_EURO_CASE),
            "aaaaa",
            [{"role": "user", "content": "计算风荷载"}],
        )
        self.assertFalse(wrote)
        self.assertIn("还不能计算风荷载", answer)
        self.assertIn("projects/aaaaa/成果/design_case.json", answer)
        self.assertIn("风速时距", answer)
        self.assertIn("地形类别", answer)
        self.assertIn("不会调用", answer)
        self.assertNotIn("峰值速度风压", answer)

    def test_euro_wind_runs_after_the_missing_values_are_given(self) -> None:
        answer, wrote = answer_load_request(
            WIND,
            json.dumps(_EURO_CASE),
            "aaaaa",
            [{"role": "user", "content": "计算风荷载，时距 10 min mean，地形类别 II"}],
        )
        self.assertFalse(wrote)
        self.assertIn("峰值速度风压", answer)
        self.assertIn("板面风压（0°，最大正风压）", answer)
        self.assertIn("板面风压（0°，最大负风压）", answer)
        self.assertIn("板面风压（60°，最大正风压）", answer)
        self.assertIn("板面风压（60°，最大负风压）", answer)
        self.assertNotIn("屋面风压", answer)
        self.assertNotIn("F 区", answer)
        self.assertIn("kN/m2", answer)
        self.assertNotIn("还不能计算", answer)

    def test_euro_snow_asks_for_exposure(self) -> None:
        answer, _wrote = answer_load_request(
            SNOW,
            json.dumps(_EURO_CASE),
            "aaaaa",
            [{"role": "user", "content": "计算雪荷载"}],
        )
        self.assertIn("还不能计算雪荷载", answer)
        self.assertIn("windswept", answer)
        self.assertNotIn("EN 1991-1-3 雪荷载", answer)

    def test_follow_up_uses_the_values_and_calculates(self) -> None:
        messages = [
            {"role": "assistant", "content": "还不能计算风荷载。\n- 风速时距是空的。"},
            {"role": "user", "content": "10 min mean，地形类别 II"},
        ]
        self.assertEqual(resolve_load_follow_up(CHAT, messages), WIND)
        self.assertEqual(resolve_load_follow_up(UPDATE, messages), WIND)
        answer, _wrote = answer_load_request(WIND, json.dumps(_EURO_CASE), "aaaaa", messages)
        self.assertIn("峰值速度风压", answer)

    def test_asce_snow_uses_the_case_values(self) -> None:
        case = {
            "status": "confirmed",
            "site": {
                "design_code": "USA(ASCE7-16)",
                "snow_load": 1.5,
                "snow_load_unit": "KN/m2",
                "risk_category": "I",
            },
            "geometry": {"module_width_mm": 1303},
        }
        answer, wrote = answer_load_request(
            SNOW,
            json.dumps(case),
            "甲项目",
            [{"role": "user", "content": "算雪荷载"}],
        )
        self.assertFalse(wrote)
        self.assertIn("0.9072", answer)
        self.assertNotIn("还不能计算", answer)

    def test_loads_ask_for_module_weight_before_the_dead_load(self) -> None:
        case = {
            "status": "confirmed",
            "site": {"design_code": "USA(ASCE7-16)"},
            "geometry": {"module_length_mm": 2384, "module_width_mm": 1303},
        }
        answer, wrote = answer_load_request(
            LOADS,
            json.dumps(case),
            "甲项目",
            [{"role": "user", "content": "计算荷载"}],
        )
        self.assertFalse(wrote)
        self.assertIn("还不能计算", answer)
        self.assertIn("组件重量是空的", answer)
        self.assertNotIn("组件自重：", answer)

    def test_colon_after_wei_is_written_before_the_check(self) -> None:
        from agent.load_check import collect_updates

        updates = collect_updates("风速时距改为:10 min mean\n地形类别为:I\n雪荷载暴露条件为:windswept")
        self.assertEqual(updates["site.wind_speed_averaging"], "10 min mean")
        self.assertEqual(updates["site.terrain_category"], "I")
        self.assertEqual(updates["site.snow_exposure"], "windswept")

    def test_missing_case_does_not_calculate(self) -> None:
        answer, wrote = answer_load_request(LOADS, None, "aaaaa", [{"role": "user", "content": "算荷载"}])
        self.assertFalse(wrote)
        self.assertIn("还没有", answer)
        self.assertIn("不会计算", answer)


class DesignCaseEditTests(unittest.TestCase):
    def test_edit_words_become_an_update_even_if_chat_was_guessed(self) -> None:
        self.assertEqual(resolve_parameter_edit(CHAT, "把风速时距改成 10 min mean"), UPDATE)
        self.assertEqual(resolve_parameter_edit(UPDATE, "我们继续看主梁布置"), CHAT)
        self.assertEqual(resolve_parameter_edit(WIND, "把风速时距改成 10 min mean"), WIND)
        self.assertEqual(
            resolve_parameter_edit(CHAT, "计算风荷载，时距 10 min mean，地形类别 II"),
            WIND,
        )

    def test_conversation_writes_only_the_stated_parameters(self) -> None:
        from agent.settings import ROOT

        sample = json.loads((ROOT / "fixtures" / "design_case.sample.json").read_text(encoding="utf-8"))
        sample["site"]["design_code"] = "Europe(Eurocode 1991-4)"
        sample["code_pack"] = "Europe(Eurocode 1991-4)"
        sample["site"]["wind_speed"] = 25.3
        sample["site"]["wind_speed_unit"] = "m/s"
        sample["site"]["snow_load"] = 1.5
        sample["site"]["snow_load_unit"] = "KN/m2"
        sample["site"]["risk_category"] = "I"
        sample["geometry"]["module_length_mm"] = 2384
        sample["geometry"]["module_width_mm"] = 1303
        sample["geometry"]["module_weight_kg"] = 37.7
        sample["geometry"]["ground_clearance_mm"] = 800
        sample["geometry"]["arrangement_rows"] = 2
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            original = path.read_text(encoding="utf-8")
            asking, wrote = answer_load_request(
                LOADS,
                original,
                "aaaaa",
                [{"role": "user", "content": "计算风荷载和雪荷载"}],
                path,
            )
            self.assertFalse(wrote)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertTrue(asking.startswith("还不能计算风荷载和雪荷载"))

            reply, wrote = answer_parameter_update(
                original,
                "aaaaa",
                [{"role": "user", "content": "风速时距改为 10 min mean，地形类别 II，暴露条件改为 windswept"}],
                path,
            )
            self.assertTrue(wrote)
            self.assertIn("已写入 projects/aaaaa/成果/design_case.json", reply)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["site"]["wind_speed_averaging"], "10 min mean")
            self.assertEqual(saved["site"]["terrain_category"], "II")
            self.assertEqual(saved["site"]["snow_exposure"], "windswept")
            self.assertEqual(saved["site"]["wind_speed"], 25.3)
            self.assertIsNone(saved["site"]["client_name"])
            recorded = {
                item["name"]: item
                for item in saved["parameters"]
                if item["name"] in ("site.wind_speed_averaging", "site.terrain_category", "site.snow_exposure")
            }
            self.assertEqual(set(recorded), {"site.wind_speed_averaging", "site.terrain_category", "site.snow_exposure"})
            self.assertTrue(all(item["status"] == "confirmed" for item in recorded.values()))
            self.assertTrue(all(item["source"] == "用户在对话中填写" for item in recorded.values()))

            again, wrote = answer_load_request(
                LOADS,
                path.read_text(encoding="utf-8"),
                "aaaaa",
                [{"role": "user", "content": "计算风荷载和雪荷载"}],
                path,
            )
            self.assertFalse(wrote)
            self.assertNotIn("还不能计算", again)
            self.assertIn("峰值速度风压", again)
            self.assertIn("0.96", again)
            self.assertIn("组件自重", again)
            self.assertIn("0.119 kN/m2", again)

    def test_rejected_value_is_not_written(self) -> None:
        from agent.settings import ROOT

        sample = json.loads((ROOT / "fixtures" / "design_case.sample.json").read_text(encoding="utf-8"))
        sample["site"]["design_code"] = "USA(ASCE7-16)"
        sample["code_pack"] = "USA(ASCE7-16)"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            before = path.read_text(encoding="utf-8")
            reply, wrote = answer_parameter_update(
                before,
                "aaaaa",
                [{"role": "user", "content": "风速时距改为 fastest-mile"}],
                path,
            )
            self.assertFalse(wrote)
            self.assertIn("没有写入", reply)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_same_value_does_not_rewrite(self) -> None:
        from agent.settings import ROOT

        sample = json.loads((ROOT / "fixtures" / "design_case.sample.json").read_text(encoding="utf-8"))
        sample["site"]["design_code"] = "Europe(Eurocode 1991-4)"
        sample["code_pack"] = "Europe(Eurocode 1991-4)"
        sample["site"]["wind_speed_averaging"] = "10 min mean"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            before = path.read_text(encoding="utf-8")
            reply, wrote = answer_parameter_update(
                before,
                "aaaaa",
                [{"role": "user", "content": "风速时距改为 10 min mean"}],
                path,
            )
            self.assertFalse(wrote)
            self.assertIn("已经一样", reply)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_follow_up_writes_temperature_orientation_and_pile(self) -> None:
        from agent.settings import ROOT

        sample = json.loads((ROOT / "fixtures" / "design_case.sample.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            reply, wrote = answer_parameter_update(
                path.read_text(encoding="utf-8"),
                "ccc",
                [
                    {
                        "role": "assistant",
                        "content": "还不能开始支架设计和绘图。极端最低温度、极端最高温度是空的。组件朝向是空的。",
                    },
                    {
                        "role": "user",
                        "content": "桩入土深度 1500 mm，确认。极端最高温度为65度，最低温度为0度，组件朝向为竖排",
                    },
                ],
                path,
            )
            self.assertTrue(wrote)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["geometry"]["pile_embedment_depth_mm"], 1500)
            self.assertEqual(saved["site"]["temperature_high_c"], 65)
            self.assertEqual(saved["site"]["temperature_low_c"], 0)
            self.assertEqual(saved["geometry"]["module_orientation"], "Portrait")
            self.assertIn("已写入 projects/ccc/成果/design_case.json", reply)


_EURO_CASE = {
    "status": "draft",
    "code_pack": "Europe(Eurocode 1991-4)",
    "site": {
        "design_code": "Europe(Eurocode 1991-4)",
        "wind_speed": 25.3,
        "wind_speed_unit": "m/s",
        "wind_speed_averaging": None,
        "snow_load": 1.5,
        "snow_load_unit": "KN/m2",
        "risk_category": "I",
        "altitude_m": 217,
    },
    "geometry": {
        "module_length_mm": 2384,
        "module_width_mm": 1303,
        "ground_clearance_mm": 800,
        "arrangement_rows": 2,
    },
}


class WindowOriginTests(unittest.TestCase):
    def test_centers_inside_the_work_area(self) -> None:
        from agent.runtime import centered_origin

        self.assertEqual(centered_origin(0, 0, 1920, 1040, 1360, 860), (280, 90))

    def test_stays_inside_when_the_window_is_taller_than_the_screen(self) -> None:
        from agent.runtime import centered_origin

        self.assertEqual(centered_origin(0, 40, 1536, 800, 1360, 860), (88, 40))


class _OpenRequest:
    async def is_disconnected(self) -> bool:
        return False


class _ScriptedModel:
    def __init__(self) -> None:
        self.calls = 0
        self.seen: list = []
        self.tool_names: list[str] = []

    def bind_tools(self, tools):
        self.tool_names = [tool.name for tool in tools]
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        self.seen.append(messages)
        if self.calls == 1:
            return type(
                "Reply",
                (),
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "name": "snowASCE16",
                            "args": {
                                "snow_load": 1.5,
                                "snow_load_unit": "KN/m2",
                                "risk_category": "I",
                                "module_width_mm": 1303,
                            },
                            "id": "call-1",
                        }
                    ],
                },
            )()
        return type("Reply", (), {"content": "0° 雪荷载是 0.9072 kN/m²。", "tool_calls": []})()


if __name__ == "__main__":
    unittest.main()
